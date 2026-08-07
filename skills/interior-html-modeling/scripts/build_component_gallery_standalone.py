#!/usr/bin/env python3
import argparse
import base64
import json
from pathlib import Path
from urllib.parse import quote


def data_url(path, mime):
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


parser = argparse.ArgumentParser()
parser.add_argument("--project", required=True)
parser.add_argument("--out", required=True)
parser.add_argument("--component-ids", default="")
parser.add_argument("--limit", type=int, default=24)
args = parser.parse_args()
root = Path(args.project).resolve()
library = root / "component-library"
gallery = library / "gallery"
html = (gallery / "index.html").read_text(encoding="utf-8")
css = (gallery / "styles.css").read_text(encoding="utf-8")
explorer = (gallery / "explorer.js").read_text(encoding="utf-8")
library_contract = (library / "shared/library-contract.js").read_text(encoding="utf-8")
public_catalog = json.loads((library / "catalog/public-assets.json").read_text(encoding="utf-8"))
all_assets = public_catalog["assets"]
requested = [item.strip() for item in args.component_ids.split(",") if item.strip()]
if requested:
    by_id = {asset["id"]: asset for asset in all_assets}
    missing = [item for item in requested if item not in by_id]
    if missing:
        raise SystemExit("unknown component IDs: " + ", ".join(missing))
    selected = [by_id[item] for item in requested]
else:
    selected = []
    seen_categories = set()
    for asset in all_assets:
        if asset["category"] not in seen_categories:
            selected.append(asset)
            seen_categories.add(asset["category"])
    for asset in all_assets:
        if len(selected) >= args.limit:
            break
        if asset not in selected:
            selected.append(asset)

def catalog_module(partition, assets, export_name):
    payload = json.dumps(assets, ensure_ascii=False, separators=(",", ":"))
    return (
        'import { definePartitionCatalog } from "@interior/library-contract";\n'
        f"const entries={payload};\n"
        f'export const {export_name}=definePartitionCatalog("{partition}",entries);\n'
    )

movable_assets = [asset.copy() for asset in selected if asset["placementClass"] == "movable-green"]
fixed_assets = [asset.copy() for asset in selected if asset["placementClass"] == "fixed-purple"]
for asset in movable_assets + fixed_assets:
    glb_path = library / asset["assetPath"].removeprefix("./")
    if not glb_path.is_file():
        raise SystemExit(
            f"{asset['id']}: materialized GLB is missing; run materialize_component_assets.mjs first"
        )
    asset["assetPath"] = data_url(glb_path, "model/gltf-binary")

movable_catalog = catalog_module("movable-green", movable_assets, "MOVABLE_GREEN_COMPONENTS")
fixed_catalog = catalog_module("fixed-purple", fixed_assets, "FIXED_PURPLE_COMPONENTS")
catalog = (library / "index.js").read_text(encoding="utf-8")
runtime = (library / "component-library.js").read_text(encoding="utf-8")
three = (root / "vendor/three.module.js").read_text(encoding="utf-8")
controls = (root / "vendor/controls/OrbitControls.js").read_text(encoding="utf-8")
gltf_loader = (root / "vendor/loaders/GLTFLoader.js").read_text(encoding="utf-8").replace(
    "'../utils/BufferGeometryUtils.js'", "'three/addons/utils/BufferGeometryUtils.js'"
)
buffer_geometry_utils = (root / "vendor/utils/BufferGeometryUtils.js").read_text(encoding="utf-8")
imports = json.dumps({"imports": {
    "three": "data:text/javascript;charset=utf-8," + quote(three, safe=""),
    "three/addons/controls/OrbitControls.js": "data:text/javascript;charset=utf-8," + quote(controls, safe=""),
    "three/addons/loaders/GLTFLoader.js": "data:text/javascript;charset=utf-8," + quote(gltf_loader, safe=""),
    "three/addons/utils/BufferGeometryUtils.js": "data:text/javascript;charset=utf-8," + quote(buffer_geometry_utils, safe=""),
    "@interior/library-contract": "data:text/javascript;charset=utf-8," + quote(library_contract, safe=""),
    "@interior/movable-green-catalog": "data:text/javascript;charset=utf-8," + quote(movable_catalog, safe=""),
    "@interior/fixed-purple-catalog": "data:text/javascript;charset=utf-8," + quote(fixed_catalog, safe=""),
    "@interior/component-catalog": "data:text/javascript;charset=utf-8," + quote(catalog, safe=""),
    "@interior/component-library": "data:text/javascript;charset=utf-8," + quote(runtime, safe=""),
}}, separators=(",", ":"))
html = html.replace('<link rel="stylesheet" href="./styles.css">', f"<style>{css}</style>")
start = html.index('<script type="importmap">')
end = html.index("</script>", start) + len("</script>")
html = html[:start] + f'<script type="importmap">{imports}</script>' + html[end:]
html = html.replace('href="../../index.html"', 'href="interior-empty-structure-template.html"')
html = html.replace('<script type="module" src="./explorer.js"></script>', f'<script type="module">{explorer}</script>')
out = Path(args.out).resolve()
out.write_text(html, encoding="utf-8")
print(json.dumps({"out": str(out), "bytes": out.stat().st_size}))
