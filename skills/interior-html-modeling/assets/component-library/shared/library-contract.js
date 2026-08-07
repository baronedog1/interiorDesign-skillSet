export const MOVABLE_GREEN = "movable-green";
export const FIXED_PURPLE = "fixed-purple";

export const LIBRARY_PARTITIONS = Object.freeze({
  [MOVABLE_GREEN]: Object.freeze({
    id: MOVABLE_GREEN,
    name: "绿色活动家具库",
    directory: "movable-green",
  }),
  [FIXED_PURPLE]: Object.freeze({
    id: FIXED_PURPLE,
    name: "紫色固定组件库",
    directory: "fixed-purple",
  }),
});

export function definePartitionCatalog(partition, entries) {
  const metadata = LIBRARY_PARTITIONS[partition];
  if (!metadata) throw new Error(`unknown component library partition: ${partition}`);
  if (!Array.isArray(entries)) throw new Error(`${partition}: catalog must be an array`);

  const normalized = entries.map((entry) => {
    if (entry.placementClass !== partition) {
      throw new Error(
        `${entry.id || "unknown"}: ${partition} catalog cannot contain ${entry.placementClass}`,
      );
    }
    return Object.freeze({
      ...entry,
      libraryPartition: partition,
      libraryDirectory: metadata.directory,
    });
  });

  return Object.freeze(normalized);
}
