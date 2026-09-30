#!/usr/bin/env python3
"""Download explicitly reviewed Poly Haven CC0 PBR maps at a fixed resolution."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import requests


API = "https://api.polyhaven.com/files"
MAPS = {"diffuse": "Diffuse", "roughness": "Rough", "normal": "nor_gl"}


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def choose_file(value: dict, resolution: str, role: str) -> dict:
    formats = value.get(resolution, {})
    order = ("jpg", "png", "exr") if role != "normal" else ("png", "jpg", "exr")
    for extension in order:
        if extension in formats and formats[extension].get("url"):
            return {"extension": extension, **formats[extension]}
    raise RuntimeError(f"Poly Haven map lacks {resolution} file for {role}")


def download(session: requests.Session, url: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with session.get(url, stream=True, timeout=(10, 180)) as response:
        response.raise_for_status()
        with output.open("wb") as target:
            for chunk in response.iter_content(1 << 20):
                if chunk:
                    target.write(chunk)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()
    request_path = Path(args.request).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if request.get("schema") != "interior.blender-material-acquisition-request.v1":
        raise SystemExit("material request schema is invalid")
    out_root = Path(args.out_root).resolve()
    resolution = str(request.get("resolution", "1k"))
    session = requests.Session()
    session.headers["User-Agent"] = "interior-blender-modeling/5.0 (+managed CC0 material acquisition)"
    records = []
    for item in request.get("materials", []):
        asset_id = item["polyHavenAssetId"]
        response = session.get(f"{API}/{asset_id}", timeout=(10, 60))
        response.raise_for_status()
        files = response.json()
        maps = {}
        for role, source_key in MAPS.items():
            selected = choose_file(files[source_key], resolution, role)
            output = out_root / item["materialId"] / f"{role}.{selected['extension']}"
            if not output.is_file() or output.stat().st_size == 0:
                download(session, selected["url"], output)
            maps[role] = {"path": str(output), "bytes": output.stat().st_size, "sha256": sha256(output)}
        records.append({
            **item, "provider": "Poly Haven", "license": "CC0-1.0",
            "sourcePage": f"https://polyhaven.com/a/{asset_id}",
            "resolution": resolution, "maps": maps,
        })
        print(f"downloaded {item['materialId']}", flush=True)
    manifest = {
        "schema": "interior.blender-material-acquisition-manifest.v1",
        "requestSha256": sha256(request_path), "materials": records,
    }
    output = Path(args.manifest).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
