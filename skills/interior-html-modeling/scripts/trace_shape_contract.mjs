import crypto from "node:crypto";

const CURVED_CLASSES = new Set(["round", "curved", "organic"]);
const CONCAVE_CLASSES = new Set(["l-shaped", "u-shaped"]);
const RECTILINEAR_CLASSES = new Set(["rectilinear", "linear", "wall-mounted"]);

function finiteNumber(value, label) {
  const number = Number(value);
  if (!Number.isFinite(number)) throw new Error(`${label} must be numeric`);
  return number;
}

function canonicalOutline(rawOutline, traceId) {
  if (!Array.isArray(rawOutline) || rawOutline.length < 4) {
    throw new Error(`${traceId}: shapeEvidence.outline requires at least four points`);
  }
  const outline = rawOutline.map((point, index) => {
    if (!Array.isArray(point) || point.length !== 2) {
      throw new Error(`${traceId}: outline point ${index} must be [x,z]`);
    }
    const x = finiteNumber(point[0], `${traceId}: outline x`);
    const z = finiteNumber(point[1], `${traceId}: outline z`);
    if (Math.abs(x) > 0.5001 || Math.abs(z) > 0.5001) {
      throw new Error(`${traceId}: outline must use bbox-normalized coordinates`);
    }
    return [Number(x.toFixed(6)), Number(z.toFixed(6))];
  });
  const first = outline[0];
  const last = outline.at(-1);
  if (outline.length > 4 && first[0] === last[0] && first[1] === last[1]) outline.pop();
  if (new Set(outline.map((point) => point.join(","))).size < 4) {
    throw new Error(`${traceId}: outline requires four unique points`);
  }
  return outline;
}

function signedArea(outline) {
  return outline.reduce((sum, point, index) => {
    const next = outline[(index + 1) % outline.length];
    return sum + point[0] * next[1] - next[0] * point[1];
  }, 0) / 2;
}

function perimeter(outline) {
  return outline.reduce((sum, point, index) => {
    const next = outline[(index + 1) % outline.length];
    return sum + Math.hypot(next[0] - point[0], next[1] - point[1]);
  }, 0);
}

function concavityCount(outline) {
  const orientation = Math.sign(signedArea(outline)) || 1;
  let count = 0;
  outline.forEach((current, index) => {
    const previous = outline[(index - 1 + outline.length) % outline.length];
    const next = outline[(index + 1) % outline.length];
    const cross = (current[0] - previous[0]) * (next[1] - current[1])
      - (current[1] - previous[1]) * (next[0] - current[0]);
    if (Math.sign(cross) && Math.sign(cross) !== orientation) count += 1;
  });
  return count;
}

export function inspectTraceShape(shapeClass, shapeEvidence, traceId = "trace-object") {
  if (!shapeEvidence || typeof shapeEvidence !== "object") {
    throw new Error(`${traceId}: shapeEvidence is required`);
  }
  if (shapeEvidence.coordinateSpace !== "bbox-normalized") {
    throw new Error(`${traceId}: shapeEvidence.coordinateSpace must be bbox-normalized`);
  }
  if (!shapeEvidence.outlineSource || typeof shapeEvidence.outlineSource !== "string") {
    throw new Error(`${traceId}: shapeEvidence.outlineSource is required`);
  }
  const outline = canonicalOutline(shapeEvidence.outline, traceId);
  const area = Math.abs(signedArea(outline));
  const outlinePerimeter = perimeter(outline);
  const circularity = outlinePerimeter > 0
    ? 4 * Math.PI * area / (outlinePerimeter ** 2)
    : 0;
  const curveEdgeRatio = finiteNumber(
    shapeEvidence.curveEdgeRatio,
    `${traceId}: shapeEvidence.curveEdgeRatio`,
  );
  if (curveEdgeRatio < 0 || curveEdgeRatio > 1) {
    throw new Error(`${traceId}: curveEdgeRatio must be between 0 and 1`);
  }
  const handedness = shapeEvidence.handedness || "none";
  if (!["none", "left", "right"].includes(handedness)) {
    throw new Error(`${traceId}: handedness must be none, left or right`);
  }
  const concavities = concavityCount(outline);

  if (CURVED_CLASSES.has(shapeClass) && (outline.length < 12 || curveEdgeRatio < 0.35)) {
    throw new Error(`${traceId}: ${shapeClass} requires a sampled curved outline`);
  }
  if (shapeClass === "round" && (curveEdgeRatio < 0.8 || circularity < 0.72)) {
    throw new Error(`${traceId}: round outline is not circular enough`);
  }
  if (CONCAVE_CLASSES.has(shapeClass) && concavities < 1) {
    throw new Error(`${traceId}: ${shapeClass} requires a concave outline`);
  }
  if (shapeClass === "l-shaped" && !["left", "right"].includes(handedness)) {
    throw new Error(`${traceId}: l-shaped outline requires left/right handedness`);
  }
  if (RECTILINEAR_CLASSES.has(shapeClass) && curveEdgeRatio > 0.35) {
    throw new Error(`${traceId}: ${shapeClass} cannot declare a mostly curved outline`);
  }
  if (!(area > 0.08 && area <= 1.001)) {
    throw new Error(`${traceId}: normalized outline area is outside the valid range`);
  }

  const canonical = JSON.stringify({
    coordinateSpace: "bbox-normalized",
    outline,
    curveEdgeRatio: Number(curveEdgeRatio.toFixed(6)),
    handedness,
  });
  const outlineHash = crypto.createHash("sha256").update(canonical).digest("hex");
  const metrics = {
    pointCount: outline.length,
    areaRatio: Number(area.toFixed(6)),
    perimeterRatio: Number(outlinePerimeter.toFixed(6)),
    circularity: Number(circularity.toFixed(6)),
    curveEdgeRatio: Number(curveEdgeRatio.toFixed(6)),
    concavityCount: concavities,
    handedness,
  };
  const shapeAdjustments = {
    outline,
    curveRatio: metrics.curveEdgeRatio,
    handedness,
    concavityCount: concavities,
    sourceOutlineHash: outlineHash,
  };
  if (Number.isFinite(Number(shapeEvidence.arcRadians))) {
    shapeAdjustments.arcRadians = Number(shapeEvidence.arcRadians);
  }
  if (Number.isFinite(Number(shapeEvidence.returnDepthRatio))) {
    shapeAdjustments.returnDepthRatio = Number(shapeEvidence.returnDepthRatio);
  }
  return {
    outline,
    outlineHash,
    metrics,
    shapeAdjustments,
    outlineSource: shapeEvidence.outlineSource,
  };
}

export function sameShapeAdjustments(left, right) {
  return JSON.stringify(left || {}) === JSON.stringify(right || {});
}
