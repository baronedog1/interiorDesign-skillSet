const CLEARANCE_M = 0.05;

function positiveHeights(walls) {
  return walls
    .filter((wall) => wall?.enabled !== false && Number(wall?.height) > 0)
    .map((wall) => Number(wall.height));
}

function roomCeilingHeight(structure, roomId) {
  const room = (structure?.rooms || []).find((candidate) => candidate.id === roomId);
  const explicitHeight = Number(room?.ceilingHeight ?? room?.height);
  if (explicitHeight > 0) return { height: explicitHeight, source: `room:${roomId}:explicit` };

  const heights = positiveHeights((structure?.walls || []).filter(
    (wall) => (wall.adjacentRoomIds || []).includes(roomId),
  ));
  if (heights.length) {
    return { height: Math.max(...heights), source: `room:${roomId}:wall-envelope` };
  }

  const allHeights = positiveHeights(structure?.walls || []);
  return allHeights.length
    ? { height: Math.max(...allHeights), source: "structure:wall-envelope" }
    : { height: null, source: "unresolved" };
}

export function resolvePlacementHeightGuard(structure, placement, definition) {
  const mountType = definition?.mountType;
  if (!["floor", "wall", "countertop"].includes(mountType)) return null;

  if (mountType === "wall") {
    const hostWallIds = new Set(placement?.hostWallIds || []);
    const hostWalls = (structure?.walls || []).filter((wall) => hostWallIds.has(wall.id));
    const hostHeights = positiveHeights(hostWalls);
    if (hostHeights.length) {
      const height = Math.min(...hostHeights);
      return {
        envelopeHeight: height,
        limit: height - CLEARANCE_M,
        source: `host-wall:${[...hostWallIds].sort().join(",")}`,
      };
    }
  }

  const roomEnvelope = roomCeilingHeight(structure, placement?.roomId);
  return Number.isFinite(roomEnvelope.height)
    ? {
        envelopeHeight: roomEnvelope.height,
        limit: roomEnvelope.height - CLEARANCE_M,
        source: roomEnvelope.source,
      }
    : null;
}

export function auditPlacementHeight(structure, placement, definition) {
  const guard = resolvePlacementHeightGuard(structure, placement, definition);
  if (!guard) return null;

  const uniformScale = Number(placement?.uniformScale ?? 1);
  const visualHeight = Number(
    placement?.visualDimensions?.height
      ?? Number(definition?.defaultDimensions?.height) * uniformScale,
  );
  const elevation = Number(placement?.elevation ?? definition?.defaultElevation ?? 0);
  const top = visualHeight + elevation;
  return {
    placementId: placement?.id || null,
    mountType: definition?.mountType || null,
    roomId: placement?.roomId || null,
    top,
    limit: guard.limit,
    envelopeHeight: guard.envelopeHeight,
    source: guard.source,
    ok: Number.isFinite(visualHeight)
      && Number.isFinite(elevation)
      && top <= guard.limit + 1e-6,
  };
}
