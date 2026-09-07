import fs from 'node:fs';
import path from 'node:path';

const [structurePath, layoutPath, scenePath, outputJson, outputScript, outputReport] = process.argv.slice(2);
if (![structurePath, layoutPath, scenePath, outputJson, outputScript, outputReport].every(Boolean)) {
  console.error('usage: node compile_coauthoring_model.mjs <structure.json> <component-layout.json> <scene-rig.json> <output.json> <output.js> <report.json>');
  process.exit(2);
}

const structure = JSON.parse(fs.readFileSync(structurePath, 'utf8'));
const componentLayout = JSON.parse(fs.readFileSync(layoutPath, 'utf8'));
const sceneRig = JSON.parse(fs.readFileSync(scenePath, 'utf8'));

const round = (value, precision = 6) => Number(Number(value).toFixed(precision));
const distance = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const wallLength = (wall) => Math.hypot(wall.b.x - wall.a.x, wall.b.z - wall.a.z);
const pointAverage = (points) => ({
  x: round(points.reduce((sum, p) => sum + p[0], 0) / points.length),
  z: round(points.reduce((sum, p) => sum + p[1], 0) / points.length),
});

const walls = structure.walls.map((wall) => ({
  id: wall.id,
  name: wall.name || wall.id,
  a: { x: round(wall.start[0]), z: round(wall.start[1]) },
  b: { x: round(wall.end[0]), z: round(wall.end[1]) },
  thickness: round(wall.thickness || 0.16, 4),
  height: round(wall.height || structure.coordinateSystem?.defaultWallHeightMeters || 2.8, 3),
  loadBearing: (wall.thickness || 0) >= 0.24 || wall.type === 'load-bearing',
  adjacentRoomIds: wall.adjacentRoomIds || [],
}));

const openings = (structure.windows || []).map((window) => ({
  id: window.id,
  type: 'window',
  wallId: window.wallId,
  center: round(window.offset),
  width: round(window.width),
  bottom: round(window.sill || 0),
  height: round(window.openingHeight || 1.2),
  name: window.name || window.id,
  floorLocked: false,
}));

const boundaryWallIds = [];
for (const feature of structure.boundaryFeatures || []) {
  if (feature.kind !== 'full-height-glazing') continue;
  const wallId = `wall-${feature.id}`;
  const width = distance(feature.start, feature.end);
  walls.push({
    id: wallId,
    name: feature.name || feature.id,
    a: { x: round(feature.start[0]), z: round(feature.start[1]) },
    b: { x: round(feature.end[0]), z: round(feature.end[1]) },
    thickness: 0.06,
    height: round(feature.height || 2.8),
    loadBearing: false,
    adjacentRoomIds: [feature.roomId, 'exterior'],
  });
  openings.push({
    id: `opening-${feature.id}`,
    type: 'window',
    wallId,
    center: round(width / 2),
    width: round(Math.max(0.3, width - 0.02)),
    bottom: 0,
    height: round(feature.height || 2.8),
    name: feature.name || feature.id,
    floorLocked: false,
  });
  boundaryWallIds.push(wallId);
}

function matchConnectionToWall(connection) {
  const start = connection.start;
  const end = connection.end;
  const cx = (start[0] + end[0]) / 2;
  const cz = (start[1] + end[1]) / 2;
  const cdx = end[0] - start[0];
  const cdz = end[1] - start[1];
  const cLength = Math.hypot(cdx, cdz);
  if (cLength < 0.01) return null;
  const cux = cdx / cLength;
  const cuz = cdz / cLength;
  let best = null;
  for (const wall of walls) {
    if (boundaryWallIds.includes(wall.id)) continue;
    const dx = wall.b.x - wall.a.x;
    const dz = wall.b.z - wall.a.z;
    const length = Math.hypot(dx, dz);
    if (length < 0.01) continue;
    const ux = dx / length;
    const uz = dz / length;
    const parallel = Math.abs(ux * cux + uz * cuz);
    if (parallel < 0.965) continue;
    const relX = cx - wall.a.x;
    const relZ = cz - wall.a.z;
    const along = relX * ux + relZ * uz;
    const perpendicular = Math.abs(relX * (-uz) + relZ * ux);
    const outside = along < 0 ? -along : along > length ? along - length : 0;
    if (perpendicular > Math.max(0.35, wall.thickness / 2 + 0.2) || outside > 0.35) continue;
    const score = perpendicular * 10 + outside * 10 + (1 - parallel) * 4;
    if (!best || score < best.score) best = { wall, along, score, perpendicular, width: cLength };
  }
  return best;
}

const mappedConnections = [];
const skippedConnections = [];
for (const connection of structure.connections || []) {
  if (connection.kind === 'open-passage') {
    skippedConnections.push({ id: connection.id, kind: connection.kind, reason: 'semantic-divider-without-physical-host-wall' });
    continue;
  }
  const matched = matchConnectionToWall(connection);
  if (!matched) {
    skippedConnections.push({ id: connection.id, kind: connection.kind, reason: 'no-collinear-host-wall' });
    continue;
  }
  const type = connection.kind === 'sliding-door' ? 'sliding' : connection.kind === 'open-passage' ? 'passage' : 'door';
  const hostLength = wallLength(matched.wall);
  const width = Math.min(round(matched.width), Math.max(0.3, hostLength - 0.1));
  const center = Math.max(width / 2 + 0.05, Math.min(hostLength - width / 2 - 0.05, matched.along));
  const opening = {
    id: connection.id,
    type,
    wallId: matched.wall.id,
    center: round(center),
    width,
    bottom: round(connection.bottom || 0),
    height: round(connection.height || (type === 'passage' ? 2.8 : 2.1)),
    name: connection.name || connection.id,
    floorLocked: type !== 'window',
    hinge: 'left',
    swing: 'in',
  };
  openings.push(opening);
  mappedConnections.push({
    id: connection.id,
    kind: connection.kind,
    wallId: matched.wall.id,
    perpendicularDistance: round(matched.perpendicular, 4),
  });
}

const rooms = (structure.rooms || []).map((room) => {
  const center = pointAverage(room.polygon);
  return {
    id: room.id,
    name: room.name || room.id,
    x: center.x,
    z: center.z,
    wallIds: walls.filter((wall) => (wall.adjacentRoomIds || []).includes(room.id)).map((wall) => wall.id),
  };
});

const furnitureType = (functionalClass) => {
  if (/bed/.test(functionalClass)) return /sofa-bed/.test(functionalClass) ? 'sofa' : 'bed';
  if (/sofa/.test(functionalClass)) return 'sofa';
  if (/table|desk/.test(functionalClass)) return 'table';
  return 'cabinet';
};

const furnitureHeight = (functionalClass) => {
  const rules = [
    [/area-rug|floor-rug|(^|-)rug$|carpet/, 0.03], [/table-light|desk-lamp/, 0.38],
    [/cooktop/, 0.12], [/refrigerator/, 1.85], [/wardrobe/, 2.2], [/washing-machine/, 0.9],
    [/base-cabinet|sink-base-cabinet|bathroom-vanity|washbasin/, 0.86], [/toilet/, 0.72],
    [/double-bed/, 0.55], [/sofa-bed|sofa/, 0.78], [/dining-chair|office-chair|accent-chair/, 0.88],
    [/dining-table|desk/, 0.75], [/coffee-table|side-table/, 0.48], [/shoe-cabinet/, 1.05], [/tv-console/, 0.55],
  ];
  return rules.find(([pattern]) => pattern.test(functionalClass))?.[1] || 0.9;
};

const unmatchedPlacements = (componentLayout.placements || []).filter(
  (placement) => placement.assetStatus !== 'matched' || !placement.componentId,
);
if (unmatchedPlacements.length) {
  throw new Error(`component layout contains non-managed furniture: ${unmatchedPlacements.map((item) => item.id).join(', ')}`);
}

const furniture = (componentLayout.placements || []).map((placement) => {
  const dimensions = placement.targetDimensions || placement.visualDimensions || { width: 0.8, depth: 0.6 };
  const height = Number(dimensions.height || furnitureHeight(placement.functionalClass || ''));
  return {
    id: placement.id,
    type: furnitureType(placement.functionalClass || ''),
    functionalClass: placement.functionalClass || 'unknown',
    roomId: placement.roomId || null,
    name: placement.name || placement.id,
    x: round(placement.position[0]),
    y: 0,
    z: round(placement.position[1]),
    width: round(dimensions.width || 0.8),
    depth: round(dimensions.depth || 0.6),
    height: round(height),
    rotationY: round(placement.rotationY || 0),
    componentId: placement.componentId,
    assetStatus: 'matched',
    semantic: placement.semantic,
    category: placement.category,
    libraryPartition: placement.libraryPartition,
    sourceTraceId: placement.sourceTraceId,
    originalDimensions: {
      width: round(dimensions.width || 0.8),
      depth: round(dimensions.depth || 0.6),
      height: round(height),
    },
    richComponent: {
      uniformScale: placement.uniformScale ?? 1,
      targetDimensions: placement.targetDimensions,
      visualDimensions: placement.visualDimensions,
      shapeAdjustments: placement.shapeAdjustments,
      sourceShapeEvidence: placement.sourceShapeEvidence,
      finishPreset: placement.finishPreset || 'source-authored',
      elevation: placement.elevation ?? 0,
    },
  };
});

const allX = walls.flatMap((wall) => [wall.a.x, wall.b.x]);
const allZ = walls.flatMap((wall) => [wall.a.z, wall.b.z]);
const bounds = {
  minX: Math.min(...allX), maxX: Math.max(...allX),
  minZ: Math.min(...allZ), maxZ: Math.max(...allZ),
};
const center = { x: (bounds.minX + bounds.maxX) / 2, z: (bounds.minZ + bounds.maxZ) / 2 };
const cameras = (sceneRig.cameras || []).map((camera, index) => ({
  id: camera.id || `camera-${index + 1}`,
  name: camera.name || `机位 ${index + 1}`,
  x: round(camera.position?.[0] ?? bounds.maxX + 4),
  y: round(camera.position?.[1] ?? 5.2),
  z: round(camera.position?.[2] ?? bounds.maxZ + 4),
  target: {
    x: round(camera.target?.[0] ?? center.x),
    y: round(camera.target?.[1] ?? 1),
    z: round(camera.target?.[2] ?? center.z),
  },
  fov: round(camera.fov ?? 48),
}));
if (!cameras.length) cameras.push({
  id: 'camera-overview', name: '整屋概览机位',
  x: round(bounds.maxX + 4), y: 5.2, z: round(bounds.maxZ + 4),
  target: { x: round(center.x), y: 1, z: round(center.z) }, fov: 48,
});
const lights = (sceneRig.lights || []).map((light, index) => ({
  id: light.id || `light-${index + 1}`,
  name: light.name || `灯光 ${index + 1}`,
  type: light.type === 'spot' ? 'spot' : 'point',
  x: round(light.position?.[0] ?? center.x),
  y: round(light.position?.[1] ?? 3.2),
  z: round(light.position?.[2] ?? center.z),
  target: {
    x: round(light.target?.[0] ?? center.x),
    y: round(light.target?.[1] ?? 0),
    z: round(light.target?.[2] ?? center.z),
  },
  intensity: round(light.intensity ?? 2.8),
  color: light.color || '#fff1dc',
  distance: round(light.distance ?? 18),
  angle: round(light.angle ?? 0.7),
}));
if (!lights.length) lights.push({
  id: 'light-overview', name: '整屋主灯', type: 'point',
  x: round(center.x), y: 3.2, z: round(center.z),
  target: { x: round(center.x), y: 0, z: round(center.z) },
  intensity: 2.8, color: '#fff1dc', distance: 18, angle: 0.7,
});

const model = {
  meta: {
    id: structure.floorplanId || 'interior-coauthoring-model',
    name: structure.name || structure.floorplanName || '室内户型人机共创模型',
    version: '1.0.0',
    storageKey: `interior-coauthoring-${structure.floorplanId || 'model'}`,
    sourceFloorplanId: structure.floorplanId,
    componentLibraryVersion: componentLayout.libraryVersion,
    furnitureRenderer: 'managed-component-library',
  },
  settings: {
    wallHeight: structure.coordinateSystem?.defaultWallHeightMeters || 2.8,
    wallThickness: 0.16,
    grid: 0.1,
    materialMode: 'white',
  },
  floorBoundary: structure.floorBoundary || [],
  walls,
  openings,
  rooms,
  furniture,
  cameras,
  lights,
};

const report = {
  schema: 'interior.coauthoring-model-compilation.v1',
  sourceFloorplanId: structure.floorplanId,
  output: path.basename(outputJson),
  counts: {
    walls: walls.length,
    sourceWalls: structure.walls.length,
    glazingBoundaryWalls: boundaryWallIds.length,
    openings: openings.length,
    windows: (structure.windows || []).length + boundaryWallIds.length,
    mappedConnections: mappedConnections.length,
    skippedConnections: skippedConnections.length,
    rooms: rooms.length,
    furniture: furniture.length,
    cameras: cameras.length,
    lights: lights.length,
  },
  mappedConnections,
  skippedConnections,
  sourceSceneRigSummary: {
    cameras: sceneRig.cameras?.length || 0,
    lights: sceneRig.lights?.length || 0,
    note: 'The coauthoring model keeps editable camera and light controls.',
  },
  invariants: {
    stableWallIds: true,
    stableWindowIds: true,
    stableFurnitureIds: true,
    irregularFloorBoundaryPreserved: true,
    semanticOpenPassagesWithoutPhysicalWallsRemainRoomRelations: skippedConnections.every((item) => item.kind === 'open-passage'),
  },
};

fs.mkdirSync(path.dirname(outputJson), { recursive: true });
fs.writeFileSync(outputJson, `${JSON.stringify(model, null, 2)}\n`);
fs.writeFileSync(outputScript, `window.__INTERIOR_COAUTHORING_MODEL__=${JSON.stringify(model).replaceAll('</script', '<\\/script')};\n`);
fs.writeFileSync(outputReport, `${JSON.stringify(report, null, 2)}\n`);
console.log(JSON.stringify(report));
