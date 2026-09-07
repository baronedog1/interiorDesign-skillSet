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
parser.add_argument("--max-total-asset-bytes", type=int, default=14 * 1024 * 1024)
parser.add_argument("--max-output-bytes", type=int, default=29 * 1024 * 1024)
args = parser.parse_args()
root = Path(args.project).resolve()
html = (root / "index.html").read_text(encoding="utf-8")
model = json.loads((root / "coauthoring-model.json").read_text(encoding="utf-8"))
model.setdefault("meta", {})["documentRole"] = "generated-coauthoring-html"
model["meta"]["coauthoringEditorVersion"] = "1.4.0"
component_layout = json.loads((root / "component-layout.json").read_text(encoding="utf-8"))

three = (root / "vendor/three.module.js").read_text(encoding="utf-8")
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
component_library = (root / "component-library/component-library.js").read_text(encoding="utf-8").replace(
    '"./catalog/runtime-geometry-admission.v1.js"', '"@interior/runtime-geometry-admission"'
)
runtime_geometry_admission = (
    root / "component-library/catalog/runtime-geometry-admission.v1.js"
).read_text(encoding="utf-8")
placement_geometry = (root / "component-library/shared/placement-geometry.js").read_text(encoding="utf-8")
gltf_exporter_global = (root / "vendor/exporters/GLTFExporter.global.js").read_text(encoding="utf-8")
public_catalog = json.loads(
    (root / "component-library/catalog/public-assets.json").read_text(encoding="utf-8")
)
catalog_by_id = {asset["id"]: asset for asset in public_catalog["assets"]}

used_component_ids = sorted({
    placement["componentId"]
    for placement in component_layout.get("placements", [])
    if placement.get("componentId")
})
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
        raise SystemExit(f"{component_id}: runtime GLB exceeds the standalone per-asset budget")
    embedded_asset_bytes += asset_bytes
    if embedded_asset_bytes > args.max_total_asset_bytes:
        raise SystemExit("standalone runtime assets exceed the total delivery budget")
    embedded_assets.append({"componentId": component_id, "path": relative_asset_path, "bytes": asset_bytes})
    embedded = data_url(glb_path, "model/gltf-binary")
    if asset["placementClass"] == "movable-green":
        movable_catalog = movable_catalog.replace(asset["assetPath"], embedded)
    else:
        fixed_catalog = fixed_catalog.replace(asset["assetPath"], embedded)

imports = json.dumps({"imports": {
    "three": "data:text/javascript;charset=utf-8," + quote(three, safe=""),
    "three/addons/loaders/GLTFLoader.js": "data:text/javascript;charset=utf-8," + quote(gltf_loader, safe=""),
    "three/addons/utils/BufferGeometryUtils.js": "data:text/javascript;charset=utf-8," + quote(buffer_geometry_utils, safe=""),
    "@interior/library-contract": "data:text/javascript;charset=utf-8," + quote(library_contract, safe=""),
    "@interior/movable-green-catalog": "data:text/javascript;charset=utf-8," + quote(movable_catalog, safe=""),
    "@interior/fixed-purple-catalog": "data:text/javascript;charset=utf-8," + quote(fixed_catalog, safe=""),
    "@interior/component-catalog": "data:text/javascript;charset=utf-8," + quote(catalog, safe=""),
    "@interior/runtime-geometry-admission": "data:text/javascript;charset=utf-8," + quote(runtime_geometry_admission, safe=""),
    "@interior/component-library": "data:text/javascript;charset=utf-8," + quote(component_library, safe=""),
    "@interior/placement-geometry": "data:text/javascript;charset=utf-8," + quote(placement_geometry, safe=""),
}}, separators=(",", ":"))

start = html.index('<script type="importmap">')
end = html.index('</script>', start) + len('</script>')
html = html[:start] + f'<script type="importmap">{imports}</script>' + html[end:]
model_payload = json.dumps(model, ensure_ascii=False, separators=(",", ":")).replace("</script", "<\\/script")
template_data_start = html.index('<script id="template-data" type="application/json">')
template_data_content_start = html.index(">", template_data_start) + 1
template_data_end = html.index("</script>", template_data_content_start)
html = html[:template_data_content_start] + model_payload + html[template_data_end:]
html = html.replace(
    '<script src="./coauthoring-model.js"></script>',
    f'<script>window.__INTERIOR_COAUTHORING_MODEL__={model_payload};</script>',
)
html = html.replace(
    '<script src="./vendor/exporters/GLTFExporter.global.js"></script>',
    f'<script>{gltf_exporter_global}</script>',
)
if 'src="./coauthoring-model.js"' in html:
    raise SystemExit("external coauthoring model reference remains in standalone output")
if 'src="./vendor/exporters/GLTFExporter.global.js"' in html:
    raise SystemExit("external GLTF exporter reference remains in standalone output")
if "window.GLTFExporter = GLTFExporter" not in html:
    raise SystemExit("inlined GLTF exporter is missing from standalone output")
if "__INTERIOR_COAUTHORING_EDITOR__" not in html:
    raise SystemExit("canonical editor API is missing from standalone output")
output_bytes = len(html.encode("utf-8"))
if output_bytes > args.max_output_bytes:
    raise SystemExit(
        f"standalone output would be {output_bytes} bytes, above the {args.max_output_bytes}-byte delivery budget"
    )
Path(args.out).resolve().write_text(html, encoding="utf-8")
print(json.dumps({
    "out": str(Path(args.out).resolve()),
    "bytes": output_bytes,
    "embeddedAssetBytes": embedded_asset_bytes,
    "embeddedAssets": embedded_assets,
    "furnitureCount": len(model.get("furniture", [])),
    "template": "室内户型人机共创模板",
}, ensure_ascii=False))
