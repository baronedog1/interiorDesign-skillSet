import {
  FIXED_PURPLE_COMPONENTS,
} from "@interior/fixed-purple-catalog";
import {
  MOVABLE_GREEN_COMPONENTS,
} from "@interior/movable-green-catalog";
import {
  FIXED_PURPLE,
  LIBRARY_PARTITIONS,
  MOVABLE_GREEN,
} from "@interior/library-contract";

export const COMPONENT_LIBRARY_VERSION = "6.1.1";

export const COMPONENT_LIBRARY_BY_SEMANTIC = Object.freeze({
  [MOVABLE_GREEN]: MOVABLE_GREEN_COMPONENTS,
  [FIXED_PURPLE]: FIXED_PURPLE_COMPONENTS,
});

export const COMPONENT_CATALOG = Object.freeze([
  ...MOVABLE_GREEN_COMPONENTS,
  ...FIXED_PURPLE_COMPONENTS,
]);

export const COMPONENT_CATEGORIES = Object.freeze(
  Object.fromEntries(
    COMPONENT_CATALOG.map((item) => [item.category, item.categoryName]),
  ),
);

const COMPONENT_BY_ID = new Map(
  COMPONENT_CATALOG.map((item) => [item.id, item]),
);

export function getPartitionCatalog(semantic) {
  return COMPONENT_LIBRARY_BY_SEMANTIC[semantic] || null;
}

export function getComponentDefinition(componentId, semantic = null) {
  if (semantic) {
    const partition = getPartitionCatalog(semantic);
    return partition?.find((item) => item.id === componentId) || null;
  }
  return COMPONENT_BY_ID.get(componentId) || null;
}

export function assertComponentRoute(componentId, semantic) {
  const definition = getComponentDefinition(componentId, semantic);
  if (definition) return definition;

  const other = getComponentDefinition(componentId);
  if (other) {
    throw new Error(
      `${componentId}: ${semantic} cannot read ${other.libraryPartition}/${other.libraryDirectory}`,
    );
  }
  throw new Error(`${componentId}: component does not exist`);
}

export function catalogByCategory(semantic = null) {
  const catalog = semantic
    ? getPartitionCatalog(semantic) || []
    : COMPONENT_CATALOG;
  return catalog.reduce((groups, item) => {
    if (!groups[item.category]) groups[item.category] = [];
    groups[item.category].push(item);
    return groups;
  }, {});
}

export function componentGeometrySignature(item) {
  return JSON.stringify([
    item.builder,
    item.variant,
    item.shapeClass,
    item.defaultDimensions,
    item.parameters,
  ]);
}

export {
  FIXED_PURPLE,
  FIXED_PURPLE_COMPONENTS,
  LIBRARY_PARTITIONS,
  MOVABLE_GREEN,
  MOVABLE_GREEN_COMPONENTS,
};
