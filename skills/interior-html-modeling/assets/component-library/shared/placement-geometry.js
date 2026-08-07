export function rotatedRectangle(center, width, depth, rotation = 0) {
  const cos = Math.cos(rotation);
  const sin = Math.sin(rotation);
  return [
    [-width / 2, -depth / 2],
    [width / 2, -depth / 2],
    [width / 2, depth / 2],
    [-width / 2, depth / 2],
  ].map(([x, z]) => [
    center[0] + x * cos - z * sin,
    center[1] + x * sin + z * cos,
  ]);
}

export function connectionOpeningPolygon(connection, openingDepth = 0.08) {
  const start = connection?.start;
  const end = connection?.end;
  if (!Array.isArray(start)
    || !Array.isArray(end)
    || start.length !== 2
    || end.length !== 2
    || ![...start, ...end].every(Number.isFinite)) {
    return [];
  }
  const dx = end[0] - start[0];
  const dz = end[1] - start[1];
  const length = Math.hypot(dx, dz);
  if (!(length > 0.01)) return [];
  return rotatedRectangle(
    [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2],
    length,
    openingDepth,
    Math.atan2(dz, dx),
  );
}

function pointOnSegment(point, first, second, tolerance = 0.000001) {
  const cross = (point[1] - first[1]) * (second[0] - first[0])
    - (point[0] - first[0]) * (second[1] - first[1]);
  if (Math.abs(cross) > tolerance) return false;
  const dot = (point[0] - first[0]) * (second[0] - first[0])
    + (point[1] - first[1]) * (second[1] - first[1]);
  if (dot < -tolerance) return false;
  const squaredLength = (second[0] - first[0]) ** 2 + (second[1] - first[1]) ** 2;
  return dot <= squaredLength + tolerance;
}

function pointInPolygon(point, polygon, includeBoundary = false) {
  for (let index = 0; index < polygon.length; index += 1) {
    if (pointOnSegment(point, polygon[index], polygon[(index + 1) % polygon.length])) {
      return includeBoundary;
    }
  }
  let inside = false;
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index, index += 1) {
    const [currentX, currentZ] = polygon[index];
    const [previousX, previousZ] = polygon[previous];
    const intersects = ((currentZ > point[1]) !== (previousZ > point[1]))
      && point[0] < (previousX - currentX) * (point[1] - currentZ)
        / (previousZ - currentZ || Number.EPSILON) + currentX;
    if (intersects) inside = !inside;
  }
  return inside;
}

function orientation(first, second, third, tolerance) {
  const value = (second[1] - first[1]) * (third[0] - second[0])
    - (second[0] - first[0]) * (third[1] - second[1]);
  if (Math.abs(value) <= tolerance) return 0;
  return value > 0 ? 1 : 2;
}

function segmentsProperlyIntersect(firstA, firstB, secondA, secondB, tolerance) {
  const firstOrientation = orientation(firstA, firstB, secondA, tolerance);
  const secondOrientation = orientation(firstA, firstB, secondB, tolerance);
  const thirdOrientation = orientation(secondA, secondB, firstA, tolerance);
  const fourthOrientation = orientation(secondA, secondB, firstB, tolerance);
  return firstOrientation !== 0
    && secondOrientation !== 0
    && thirdOrientation !== 0
    && fourthOrientation !== 0
    && firstOrientation !== secondOrientation
    && thirdOrientation !== fourthOrientation;
}

function isConvexPolygon(polygon, tolerance = 0.000001) {
  let direction = 0;
  for (let index = 0; index < polygon.length; index += 1) {
    const first = polygon[index];
    const second = polygon[(index + 1) % polygon.length];
    const third = polygon[(index + 2) % polygon.length];
    const cross = (second[0] - first[0]) * (third[1] - second[1])
      - (second[1] - first[1]) * (third[0] - second[0]);
    if (Math.abs(cross) <= tolerance) continue;
    const nextDirection = Math.sign(cross);
    if (direction && nextDirection !== direction) return false;
    direction = nextDirection;
  }
  return direction !== 0;
}

function projectPolygon(polygon, axis) {
  let min = Infinity;
  let max = -Infinity;
  polygon.forEach(([x, z]) => {
    const projection = x * axis[0] + z * axis[1];
    min = Math.min(min, projection);
    max = Math.max(max, projection);
  });
  return { min, max };
}

function convexPolygonsOverlapBeyondTolerance(first, second, tolerance) {
  const axes = [];
  [first, second].forEach((polygon) => {
    polygon.forEach((point, index) => {
      const next = polygon[(index + 1) % polygon.length];
      const edgeX = next[0] - point[0];
      const edgeZ = next[1] - point[1];
      const length = Math.hypot(edgeX, edgeZ);
      if (length > Number.EPSILON) axes.push([-edgeZ / length, edgeX / length]);
    });
  });
  for (const axis of axes) {
    const firstProjection = projectPolygon(first, axis);
    const secondProjection = projectPolygon(second, axis);
    const penetration = Math.min(firstProjection.max, secondProjection.max)
      - Math.max(firstProjection.min, secondProjection.min);
    if (penetration <= tolerance) return false;
  }
  return true;
}

export function polygonsOverlap(a, b, tolerance = 0.006) {
  if (!Array.isArray(a) || !Array.isArray(b) || a.length < 3 || b.length < 3) return false;
  const normalizedTolerance = Math.max(0, Number(tolerance) || 0);
  if (isConvexPolygon(a) && isConvexPolygon(b)) {
    return convexPolygonsOverlapBeyondTolerance(a, b, normalizedTolerance);
  }
  for (let firstIndex = 0; firstIndex < a.length; firstIndex += 1) {
    const firstA = a[firstIndex];
    const firstB = a[(firstIndex + 1) % a.length];
    for (let secondIndex = 0; secondIndex < b.length; secondIndex += 1) {
      const secondA = b[secondIndex];
      const secondB = b[(secondIndex + 1) % b.length];
      if (segmentsProperlyIntersect(
        firstA,
        firstB,
        secondA,
        secondB,
        normalizedTolerance,
      )) return true;
    }
  }
  return a.some((point) => pointInPolygon(point, b))
    || b.some((point) => pointInPolygon(point, a));
}

export function transformedTraceOutline(placement) {
  const outline = placement?.sourceShapeEvidence?.outline;
  const width = Number(placement?.targetDimensions?.width);
  const depth = Number(placement?.targetDimensions?.depth);
  const center = placement?.position;
  if (!Array.isArray(outline)
    || outline.length < 4
    || !Array.isArray(center)
    || center.length !== 2
    || ![width, depth, ...center].every(Number.isFinite)) {
    return [];
  }
  const rotation = Number(placement.rotationY || 0);
  const cos = Math.cos(rotation);
  const sin = Math.sin(rotation);
  return outline.map(([normalizedX, normalizedZ]) => {
    const localX = Number(normalizedX) * width;
    const localZ = Number(normalizedZ) * depth;
    return [
      center[0] + localX * cos - localZ * sin,
      center[1] + localX * sin + localZ * cos,
    ];
  });
}

export function componentFootprint(placement, definition) {
  if (!placement || !definition) return [];
  const traceOutline = transformedTraceOutline(placement);
  if (traceOutline.length) return traceOutline;
  const scale = Number(placement.uniformScale ?? 1);
  const dimensions = definition.defaultDimensions;
  if (!dimensions || !Number.isFinite(scale) || scale <= 0) return [];
  const width = Number(placement.targetDimensions?.width ?? dimensions.width * scale);
  const depth = Number(placement.targetDimensions?.depth ?? dimensions.depth * scale);
  if (![width, depth].every((value) => Number.isFinite(value) && value > 0)) return [];
  return rotatedRectangle(
    placement.position,
    width,
    depth,
    Number(placement.rotationY || 0),
  );
}

function nearlyEqual(left, right, tolerance = 0.0001) {
  return Number.isFinite(Number(left))
    && Number.isFinite(Number(right))
    && Math.abs(Number(left) - Number(right)) <= tolerance;
}

export function placementMatchesSourceTransform(placement, tolerance = 0.0001) {
  const currentPosition = placement?.position;
  const sourcePosition = placement?.sourcePosition;
  const currentDimensions = placement?.targetDimensions;
  const sourceDimensions = placement?.sourceDimensions;
  return placement?.traceLock?.position === true
    && placement?.traceLock?.dimensions === true
    && placement?.traceLock?.rotation === true
    && placement?.traceLock?.outline === true
    && Array.isArray(currentPosition)
    && Array.isArray(sourcePosition)
    && currentPosition.length === 2
    && sourcePosition.length === 2
    && currentPosition.every(
      (value, index) => nearlyEqual(value, sourcePosition[index], tolerance),
    )
    && nearlyEqual(currentDimensions?.width, sourceDimensions?.width, tolerance)
    && nearlyEqual(currentDimensions?.depth, sourceDimensions?.depth, tolerance)
    && nearlyEqual(
      placement?.rotationY || 0,
      placement?.sourceRotationY || 0,
      tolerance,
    );
}

export function componentCollisionPairs(placements, resolveDefinition, tolerance = 0.006) {
  const footprints = placements.map((placement) => {
    const definition = resolveDefinition(placement.componentId, placement.semantic);
    return {
      placement,
      definition,
      footprint: componentFootprint(placement, definition),
    };
  });
  const collisions = [];
  for (let firstIndex = 0; firstIndex < footprints.length; firstIndex += 1) {
    const first = footprints[firstIndex];
    if (!first.footprint.length) continue;
    for (let secondIndex = firstIndex + 1; secondIndex < footprints.length; secondIndex += 1) {
      const second = footprints[secondIndex];
      if (!second.footprint.length) continue;
      const sharedFixedJoin = first.placement.semantic === "fixed-purple"
        && second.placement.semantic === "fixed-purple"
        && first.placement.joinGroup
        && first.placement.joinGroup === second.placement.joinGroup;
      if (sharedFixedJoin) continue;
      if (placementMatchesSourceTransform(first.placement)
        && placementMatchesSourceTransform(second.placement)) continue;
      if (first.definition?.variant === "rug"
        || second.definition?.variant === "rug") continue;
      const pairTolerance = Math.max(
        tolerance,
        Number(first.placement.collisionTolerance || 0),
        Number(second.placement.collisionTolerance || 0),
      );
      if (!polygonsOverlap(first.footprint, second.footprint, pairTolerance)) continue;
      collisions.push({
        firstId: first.placement.id,
        firstName: first.placement.name,
        firstSemantic: first.placement.semantic,
        secondId: second.placement.id,
        secondName: second.placement.name,
        secondSemantic: second.placement.semantic,
      });
    }
  }
  return collisions;
}
