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
parser.add_argument("--max-asset-bytes", type=int, default=8 * 1024 * 1024)
parser.add_argument("--max-total-asset-bytes", type=int, default=18 * 1024 * 1024)
parser.add_argument("--max-output-bytes", type=int, default=29 * 1024 * 1024)
args = parser.parse_args()
root = Path(args.project).resolve()
html = (root / "index.html").read_text(encoding="utf-8")
css = (root / "styles.css").read_text(encoding="utf-8")
app = (root / "app.js").read_text(encoding="utf-8")
three = (root / "vendor/three.module.js").read_text(encoding="utf-8")
controls = (root / "vendor/controls/OrbitControls.js").read_text(encoding="utf-8")
gltf_loader = (root / "vendor/loaders/GLTFLoader.js").read_text(encoding="utf-8").replace(
    "'../utils/BufferGeometryUtils.js'", "'three/addons/utils/BufferGeometryUtils.js'"
)
buffer_geometry_utils = (root / "vendor/utils/BufferGeometryUtils.js").read_text(encoding="utf-8")
library_contract = (root / "component-library/shared/library-contract.js").read_text(encoding="utf-8")
movable_catalog = (root / "component-library/movable-green/catalog.js").read_text(encoding="utf-8").replace(
    '"../shared/library-contract.js"', '"@interior/library-contract"'
)
fixed_catalog = (root / "component-library/fixed-purple/catalog.js").read_text(encoding="utf-8").replace(
    '"../shared/library-contract.js"', '"@interior/library-contract"'
)
catalog = (root / "component-library/index.js").read_text(encoding="utf-8")
component_library = (root / "component-library/component-library.js").read_text(encoding="utf-8")
placement_geometry = (root / "component-library/shared/placement-geometry.js").read_text(encoding="utf-8")
data = json.loads((root / "structure-data.json").read_text(encoding="utf-8"))
component_layout = json.loads((root / "component-layout.json").read_text(encoding="utf-8"))
model_scope = json.loads((root / "model-scope.json").read_text(encoding="utf-8"))
public_catalog = json.loads((root / "component-library/catalog/public-assets.json").read_text(encoding="utf-8"))
catalog_by_id = {asset["id"]: asset for asset in public_catalog["assets"]}
used_component_ids = sorted({placement["componentId"] for placement in component_layout.get("placements", [])})
embedded_asset_bytes = 0
embedded_assets = []
for component_id in used_component_ids:
    asset = catalog_by_id.get(component_id)
    if not asset:
        raise SystemExit(f"{component_id}: missing from canonical public asset catalog")
    web_variant = asset.get("runtimeVariants", {}).get("webStandalone", {})
    selected_asset_path = web_variant.get("assetPath") or asset["assetPath"]
    relative_asset_path = selected_asset_path.removeprefix("./")
    glb_path = root / "component-library" / relative_asset_path
    if not glb_path.is_file():
        raise SystemExit(
            f"{component_id}: materialized GLB is missing; run materialize_component_assets.mjs first"
        )
    asset_bytes = glb_path.stat().st_size
    if asset_bytes > args.max_asset_bytes:
        raise SystemExit(
            f"{component_id}: runtime GLB is {asset_bytes} bytes, above the "
            f"{args.max_asset_bytes}-byte standalone budget; publish a reviewed "
            "webStandalone LOD/texture-compressed variant instead of embedding the source GLB"
        )
    embedded_asset_bytes += asset_bytes
    if embedded_asset_bytes > args.max_total_asset_bytes:
        raise SystemExit(
            f"standalone runtime assets total {embedded_asset_bytes} bytes, above the "
            f"{args.max_total_asset_bytes}-byte budget; choose smaller tagged assets or "
            "prepare webStandalone variants"
        )
    embedded_assets.append({"componentId": component_id, "path": relative_asset_path, "bytes": asset_bytes})
    embedded = data_url(glb_path, "model/gltf-binary")
    if asset["placementClass"] == "movable-green":
        movable_catalog = movable_catalog.replace(asset["assetPath"], embedded)
    else:
        fixed_catalog = fixed_catalog.replace(asset["assetPath"], embedded)
camera_plan = json.loads((root / "camera-plan.json").read_text(encoding="utf-8"))
scene_rig = json.loads((root / "scene-rig.json").read_text(encoding="utf-8"))
backend_options = json.loads((root / "backend-options.json").read_text(encoding="utf-8"))
imports = json.dumps({"imports": {
    "three": "data:text/javascript;charset=utf-8," + quote(three, safe=""),
    "three/addons/controls/OrbitControls.js": "data:text/javascript;charset=utf-8," + quote(controls, safe=""),
    "three/addons/loaders/GLTFLoader.js": "data:text/javascript;charset=utf-8," + quote(gltf_loader, safe=""),
    "three/addons/utils/BufferGeometryUtils.js": "data:text/javascript;charset=utf-8," + quote(buffer_geometry_utils, safe=""),
    "@interior/library-contract": "data:text/javascript;charset=utf-8," + quote(library_contract, safe=""),
    "@interior/movable-green-catalog": "data:text/javascript;charset=utf-8," + quote(movable_catalog, safe=""),
    "@interior/fixed-purple-catalog": "data:text/javascript;charset=utf-8," + quote(fixed_catalog, safe=""),
    "@interior/component-catalog": "data:text/javascript;charset=utf-8," + quote(catalog, safe=""),
    "@interior/component-library": "data:text/javascript;charset=utf-8," + quote(component_library, safe=""),
    "@interior/placement-geometry": "data:text/javascript;charset=utf-8," + quote(placement_geometry, safe=""),
}}, separators=(",", ":"))
html = html.replace('<link rel="stylesheet" href="./styles.css">', f"<style>{css}</style>")
start = html.index('<script type="importmap">')
end = html.index('</script>', start) + len('</script>')
html = html[:start] + f'<script type="importmap">{imports}</script>' + html[end:]
html = html.replace('src="./structure-source.png"', f'src="{data_url(root / "structure-source.png", "image/png")}"')
payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
component_payload = json.dumps(component_layout, ensure_ascii=False, separators=(",", ":"))
model_scope_payload = json.dumps(model_scope, ensure_ascii=False, separators=(",", ":"))
camera_payload = json.dumps(camera_plan, ensure_ascii=False, separators=(",", ":"))
scene_rig_payload = json.dumps(scene_rig, ensure_ascii=False, separators=(",", ":"))
backend_options_payload = json.dumps(backend_options, ensure_ascii=False, separators=(",", ":"))
html = html.replace('href="./component-library/gallery/index.html"', 'href="#component-library"')
app = app.replace("./component-library/gallery/index.html?partition=", "#component-library-partition=")
html = html.replace('<script type="module" src="./app.js"></script>', f'<script>window.__STRUCTURE_DATA__={payload};window.__COMPONENT_LAYOUT__={component_payload};window.__MODEL_SCOPE__={model_scope_payload};window.__CAMERA_PLAN__={camera_payload};window.__SCENE_RIG__={scene_rig_payload};window.__BACKEND_OPTIONS__={backend_options_payload};</script><script type="module">{app}</script>')
output_bytes = len(html.encode("utf-8"))
if output_bytes > args.max_output_bytes:
    raise SystemExit(
        f"standalone output would be {output_bytes} bytes, above the "
        f"{args.max_output_bytes}-byte delivery budget; no oversized HTML was written"
    )
Path(args.out).resolve().write_text(html, encoding="utf-8")
print(json.dumps({
    "out": str(Path(args.out).resolve()),
    "bytes": output_bytes,
    "embeddedAssetBytes": embedded_asset_bytes,
    "embeddedAssets": embedded_assets,
    "budgets": {
        "maxAssetBytes": args.max_asset_bytes,
        "maxTotalAssetBytes": args.max_total_asset_bytes,
        "maxOutputBytes": args.max_output_bytes,
    },
}))
