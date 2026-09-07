#!/usr/bin/env node
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { FIXED_PURPLE_COMPONENTS } from "../assets/component-library/fixed-purple/catalog.js";
import { MOVABLE_GREEN_COMPONENTS } from "../assets/component-library/movable-green/catalog.js";

const assets = [...MOVABLE_GREEN_COMPONENTS, ...FIXED_PURPLE_COMPONENTS];
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outputPath = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(root, "assets/component-library/catalog/functional-class-tags.v1.json");

function classesFor(asset) {
  const name = `${asset.sourceName || ""} ${asset.name || ""}`.toLowerCase();
  const subcategory = String(asset.platform?.softSubcategory || asset.platform?.hardSubcategory || "");
  const result = new Set(asset.functionalClass ? [asset.functionalClass] : []);
  const add = (...values) => values.filter(Boolean).forEach((value) => result.add(value));

  switch (asset.category) {
    case "rug-textile": add("rug"); break;
    case "bed": add(subcategory === "bed_single" ? "single-bed" : "double-bed"); break;
    case "sofa": add("sofa"); break;
    case "stool": add("stool"); break;
    case "plant": add("plant"); break;
    case "mirror": add("mirror"); break;
    case "decor-art": add("wall-art"); break;
    case "decor-object": add("decor-object"); break;
    case "chair":
      if (/dining chair|gallinera chair|painted wooden chair|wooden chair/.test(name)) add("dining-chair");
      else if (/office|desk chair|gaming|schoolchair|school chair/.test(name)) add("office-chair");
      else if (/rocking/.test(name)) add("rocking-chair");
      else if (/barber/.test(name)) add("barber-chair");
      else if (/monobloc/.test(name)) add("utility-chair");
      else add("accent-chair");
      break;
    case "table":
      if (/coffee table|coffeetable/.test(name)) add("coffee-table");
      else if (/console/.test(name)) add("console-table");
      else if (/nightstand/.test(name)) add("nightstand");
      else if (/desk/.test(name)) add("desk");
      else if (/side table|small wooden table/.test(name)) add("side-table");
      else if (/tea table/.test(name)) add("tea-table");
      else add("dining-table");
      break;
    case "storage":
      if (/wardrobe/.test(name)) add("wardrobe");
      else if (/bookcase|bookshelf|shelves|shelf|rack/.test(name)) add("shelving");
      else if (/dresser|chest of drawers|drawer cabinet|commode|wooden drawer/.test(name)) add("dresser");
      else if (/base cabinet/.test(name)) add("base-cabinet");
      else if (/wall cabinet|upper cabinet/.test(name)) add("wall-cabinet");
      else if (/tall.*cabinet|high cabinet/.test(name)) add("tall-cabinet");
      else if (/shoe cabinet/.test(name)) add("shoe-cabinet", "storage-cabinet");
      else if (/laundry|washer cabinet|utility cabinet/.test(name)) add("utility-cabinet", "storage-cabinet");
      else if (/cupboard/.test(name)) add("closed-cupboard", "storage-cabinet");
      else if (/cabinet/.test(name)) add("storage-cabinet");
      else add("sideboard");
      if ((result.has("sideboard") || /credenza|buffet|low cabinet/.test(name))
          && Number(asset.defaultDimensions?.height) <= 0.95) add("tv-console");
      break;
    case "lighting":
      if (/wall sconce|wall lamp/.test(name)) add("wall-light");
      else if (/floor lamp|standing floor/.test(name)) add("floor-light");
      else if (/pendant|chandelier|hanging|ceiling lamp/.test(name)) add("pendant-light");
      else add("decorative-light");
      break;
    case "appliance":
      if (/toilet/.test(name)) add("toilet");
      else if (/washbasin/.test(name)) add("washbasin");
      else if (/vanity/.test(name)) add("vanity");
      else if (/cooktop|stove/.test(name)) add("cooktop");
      else if (/television/.test(name)) add("television");
      else if (/air conditioner|aircon/.test(name)) add("air-conditioner");
      else if (/ceiling fan/.test(name)) add("ceiling-fan");
      else add("appliance");
      break;
    default:
      throw new Error(`${asset.id}: unsupported category ${asset.category}`);
  }
  return [...result].sort();
}

const document = {
  schema: "interior.component-functional-class-tags.v1",
  generator: "build_functional_class_tags.mjs/v1",
  count: assets.length,
  assets: assets
    .map((asset) => ({
      assetId: asset.id,
      category: asset.category,
      supportedFunctionalClasses: classesFor(asset),
      evidence: "provider-title-category-and-reviewed-dimensions-v1",
    }))
    .sort((left, right) => left.assetId.localeCompare(right.assetId)),
  tagsDigestSha256: null,
};
document.tagsDigestSha256 = crypto.createHash("sha256")
  .update(JSON.stringify(document))
  .digest("hex");
fs.mkdirSync(path.dirname(outputPath), { recursive: true });
fs.writeFileSync(outputPath, `${JSON.stringify(document, null, 2)}\n`);
console.log(`${document.count} functional-class tag rows -> ${outputPath}`);
