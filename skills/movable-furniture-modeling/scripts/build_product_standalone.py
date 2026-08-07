#!/usr/bin/env python3
"""Build a self-contained component-aware Three.js visual-hull viewer."""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mask_utils import canonical_sha256, load_json  # noqa: E402


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def parse_reference(value: str) -> tuple[str, str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("reference must be viewId=path or viewId:label=path")
    key, path = value.split("=", 1)
    if ":" in key:
        view_id, label = key.split(":", 1)
    else:
        view_id, label = key, f"{key} 原图"
    return view_id, label, Path(path).resolve()


def classic_three(source: str) -> str:
    export_match = re.search(r"export\s*\{([\s\S]*?)\};\s*$", source)
    if not export_match:
        raise ValueError("Three.js classic transform failed")
    names = [item.strip() for item in export_match.group(1).split(",")]
    return source[: export_match.start()] + f"globalThis.THREE={{ {','.join(names)} }};"


def classic_orbit(source: str) -> str:
    source = re.sub(
        r"import\s*\{([\s\S]*?)\}\s*from\s*'three';",
        r"const {\1} = globalThis.THREE;",
        source,
        count=1,
    )
    source = re.sub(
        r"export\s*\{\s*OrbitControls\s*\};",
        r"globalThis.OrbitControls=OrbitControls;",
        source,
        count=1,
    )
    if "globalThis.OrbitControls" not in source:
        raise ValueError("OrbitControls classic transform failed")
    return source


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("state")
    parser.add_argument("output")
    parser.add_argument("--title", default="活动家具多视图雕刻模型")
    parser.add_argument("--reference", action="append", default=[], type=parse_reference)
    arguments = parser.parse_args()
    state = load_json(arguments.state)
    if state.get("stateSha256") != canonical_sha256(state, {"stateSha256"}):
        raise SystemExit("state SHA-256 mismatch")
    if state.get("status") not in {"candidate", "provisional"}:
        raise SystemExit("standalone requires the immutable candidate or provisional carving state")

    root = Path(__file__).resolve().parents[1]
    template = (root / "templates/standalone.html").read_text(encoding="utf-8")
    three = classic_three((root / "assets/vendor/three.module.js").read_text(encoding="utf-8"))
    orbit = classic_orbit((root / "assets/vendor/OrbitControls.js").read_text(encoding="utf-8"))
    references = {
        view_id: {"label": label, "data": data_uri(path)}
        for view_id, label, path in arguments.reference
    }
    state_json = json.dumps(state, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    references_json = json.dumps(references, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = (
        template.replace("__TITLE__", arguments.title)
        .replace("__STATE_JSON__", state_json)
        .replace("__REFERENCES_JSON__", references_json)
        .replace("__THREE_CLASSIC__", f"(()=>{{{three}}})();")
        .replace("__ORBIT_CLASSIC__", f"(()=>{{{orbit}}})();")
    )
    output = Path(arguments.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
