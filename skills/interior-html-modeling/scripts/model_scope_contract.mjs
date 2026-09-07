import crypto from "node:crypto";

export const MODEL_SCOPE_REQUEST_SCHEMA = "interior.model-scope-request.v1";
export const MODEL_SCOPE_SCHEMA = "interior.model-scope.v1";

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

function digest(value) {
  return crypto.createHash("sha256").update(canonical(value)).digest("hex");
}

function uniqueStrings(value, label) {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || !item)) {
    throw new Error(`${label} must be a string array`);
  }
  if (new Set(value).size !== value.length) throw new Error(`${label} must not contain duplicates`);
  return [...value].sort();
}

function roomGraph(structure) {
  const graph = new Map((structure.rooms || []).map((room) => [room.id, new Set()]));
  for (const connection of structure.connections || []) {
    const left = connection.fromRoomId;
    const right = connection.toRoomId;
    if (graph.has(left) && graph.has(right)) {
      graph.get(left).add(right);
      graph.get(right).add(left);
    }
  }
  return graph;
}

function assertContextConnected(structure, requested, context) {
  if (!context.length) return;
  const allowed = new Set([...requested, ...context]);
  const graph = roomGraph(structure);
  const reached = new Set(requested);
  const queue = [...requested];
  while (queue.length) {
    const current = queue.shift();
    for (const neighbor of graph.get(current) || []) {
      if (!allowed.has(neighbor) || reached.has(neighbor)) continue;
      reached.add(neighbor);
      queue.push(neighbor);
    }
  }
  const disconnected = context.filter((roomId) => !reached.has(roomId));
  if (disconnected.length) {
    throw new Error(`allowedContextRoomIds are not source-connected to requested rooms: ${disconnected.join(", ")}`);
  }
}

export function compileModelScope(request, structure, binding) {
  const roomIds = uniqueStrings((structure.rooms || []).map((room) => room.id), "structure room IDs");
  if (!roomIds.length) throw new Error("structure must contain rooms before model scope compilation");
  const known = new Set(roomIds);
  const input = request || {
    schema: MODEL_SCOPE_REQUEST_SCHEMA,
    mode: "whole-floor",
  };
  if (input.schema !== MODEL_SCOPE_REQUEST_SCHEMA) {
    throw new Error(`model scope request must use ${MODEL_SCOPE_REQUEST_SCHEMA}`);
  }
  if (!['whole-floor', 'room-subset'].includes(input.mode)) {
    throw new Error("model scope mode must be whole-floor or room-subset");
  }

  // A room list is not permission to rebuild an isolated room. Unless the user
  // explicitly requested an independent-space deliverable, compile the accepted
  // floorplan as one model and let the camera plan choose which rooms to shoot.
  const independentSpaceRequested =
    input.mode === "room-subset" && input.explicitIndependentSpaceRequest === true;
  const effectiveMode = independentSpaceRequested ? "room-subset" : "whole-floor";

  let requestedRoomIds;
  let allowedContextRoomIds;
  let reason;
  if (effectiveMode === "whole-floor") {
    requestedRoomIds = roomIds;
    allowedContextRoomIds = [];
    reason = "compile-the-complete-accepted-floorplan";
  } else {
    requestedRoomIds = uniqueStrings(input.requestedRoomIds, "requestedRoomIds");
    allowedContextRoomIds = uniqueStrings(input.allowedContextRoomIds || [], "allowedContextRoomIds");
    if (!requestedRoomIds.length) throw new Error("room-subset scope needs at least one requested room");
    const unknown = [...requestedRoomIds, ...allowedContextRoomIds].filter((roomId) => !known.has(roomId));
    if (unknown.length) throw new Error(`model scope references unknown rooms: ${[...new Set(unknown)].join(", ")}`);
    const overlap = requestedRoomIds.filter((roomId) => allowedContextRoomIds.includes(roomId));
    if (overlap.length) throw new Error(`requested and context rooms overlap: ${overlap.join(", ")}`);
    reason = String(input.reason || "").trim();
    if (!reason) reason = "user-explicitly-requested-independent-space-model";
    assertContextConnected(structure, requestedRoomIds, allowedContextRoomIds);
  }

  const allowed = new Set([...requestedRoomIds, ...allowedContextRoomIds]);
  const scope = {
    schema: MODEL_SCOPE_SCHEMA,
    mode: effectiveMode,
    requestedRoomIds,
    allowedContextRoomIds,
    excludedRoomIds: roomIds.filter((roomId) => !allowed.has(roomId)),
    reason,
    compilerPolicy: "same-floorplan-handoff-v3-template-and-component-pipeline",
    sameTemplateAsWholeFloor: true,
    customProjectGeometryAllowed: false,
    bindings: {
      floorplanId: binding.floorplanId,
      handoffDigestSha256: binding.handoffDigestSha256,
      structureDataSha256: binding.structureDataSha256,
    },
  };
  if (effectiveMode === "room-subset") {
    scope.explicitIndependentSpaceRequest = true;
  }
  scope.scopeDigestSha256 = digest(scope);
  return scope;
}

export function validateCompiledModelScope(scope, structure, binding) {
  if (scope?.schema !== MODEL_SCOPE_SCHEMA) throw new Error(`model scope must use ${MODEL_SCOPE_SCHEMA}`);
  const payload = structuredClone(scope);
  const declaredDigest = payload.scopeDigestSha256;
  delete payload.scopeDigestSha256;
  if (digest(payload) !== declaredDigest) throw new Error("model scope digest mismatch");
  const request = scope.mode === "whole-floor"
    ? { schema: MODEL_SCOPE_REQUEST_SCHEMA, mode: "whole-floor" }
    : {
      schema: MODEL_SCOPE_REQUEST_SCHEMA,
      mode: scope.mode,
      requestedRoomIds: scope.requestedRoomIds,
      allowedContextRoomIds: scope.allowedContextRoomIds,
      reason: scope.reason,
      explicitIndependentSpaceRequest: scope.explicitIndependentSpaceRequest,
    };
  const recomputed = compileModelScope(request, structure, binding);
  if (canonical(recomputed) !== canonical(scope)) throw new Error("model scope differs from deterministic compilation");
  return recomputed;
}
