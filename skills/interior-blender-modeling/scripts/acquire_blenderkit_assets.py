#!/usr/bin/env python3
"""Acquire explicitly reviewed free BlenderKit assets into the managed asset root."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import time
import urllib.parse
import uuid

import requests


API = "https://www.blenderkit.com/api/v1"
CLIENT_ENDPOINT = "http://127.0.0.1:62485/v1.9/wrappers/blocking_request"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_client(binary: Path) -> subprocess.Popen | None:
    with socket.socket() as sock:
        sock.settimeout(0.2)
        if sock.connect_ex(("127.0.0.1", 62485)) == 0:
            return None
    process = subprocess.Popen(
        [str(binary), "-pid", str(os.getpid()), "-port", "62485", "-server", "https://www.blendkit.com", "-software", "blender", "-version", "3.21.0.260628", "-proxy_which", "NONE"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(80):
        with socket.socket() as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", 62485)) == 0:
                return process
        time.sleep(0.1)
    process.terminate()
    raise RuntimeError("BlenderKit client did not become ready")


def wrapper_get(url: str) -> requests.Response:
    version = "3.21.0.260628"
    payload = {
        "url": url, "method": "GET", "api_key": "", "app_id": 1,
        "platform_version": platform.platform(), "addon_version": version,
        "headers": {"accept": "application/json", "Platform-Version": platform.platform(), "addon-version": version},
    }
    response = requests.get(CLIENT_ENDPOINT, json=payload, timeout=(2, 120), proxies={"http": "", "https": ""})
    response.raise_for_status()
    return response


def asset_record(base_id: str) -> dict:
    query = urllib.parse.urlencode({"query": f"asset_base_id:{base_id}", "addon_version": "3.21.0", "blender_version": "4.5.11"})
    response = wrapper_get(f"{API}/search/?{query}").json()
    matches = [value for value in response.get("results", []) if value.get("assetBaseId") == base_id]
    if len(matches) != 1:
        raise RuntimeError(f"BlenderKit asset lookup is not unique: {base_id}")
    asset = matches[0]
    if asset.get("isFree") is not True or asset.get("canDownload") is not True:
        raise RuntimeError(f"asset is not anonymous-downloadable free content: {base_id}")
    return asset


def select_file(asset: dict) -> dict:
    by_type = {value.get("fileType"): value for value in asset.get("files", [])}
    chosen = by_type.get("resolution_1K") or by_type.get("blend")
    if not chosen or not chosen.get("downloadUrl"):
        raise RuntimeError(f"asset has no usable Blender file: {asset.get('assetBaseId')}")
    return chosen


def signed_url(endpoint: str, scene_uuid: str) -> str:
    separator = "&" if "?" in endpoint else "?"
    payload = wrapper_get(f"{endpoint}{separator}scene_uuid={scene_uuid}").json()
    if not payload.get("filePath"):
        raise RuntimeError("BlenderKit did not return a signed file path")
    return payload["filePath"]


def download(url: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.trust_env = False
    with session.get(url, stream=True, timeout=(10, 300)) as response:
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
    parser.add_argument("--client-bin", required=True)
    args = parser.parse_args()
    request_path = Path(args.request).resolve()
    request = json.loads(request_path.read_text(encoding="utf-8"))
    if request.get("schema") != "interior.blender-asset-acquisition-request.v1":
        raise SystemExit("asset request schema must be interior.blender-asset-acquisition-request.v1")
    out_root = Path(args.out_root).resolve()
    client = ensure_client(Path(args.client_bin).resolve())
    scene_uuid = str(uuid.uuid4())
    records = []
    try:
        for item in request.get("assets", []):
            asset = asset_record(item["assetBaseId"])
            selected_file = select_file(asset)
            output = out_root / item["assetId"] / f"{item['assetId']}.blend"
            if not output.is_file() or output.stat().st_size == 0:
                download(signed_url(selected_file["downloadUrl"], scene_uuid), output)
            record = {
                **item, "name": asset.get("displayName") or asset.get("name"),
                "license": asset.get("license"), "isFree": asset.get("isFree"),
                "sourcePage": f"https://www.blenderkit.com/asset-gallery-detail/{item['assetBaseId']}/",
                "fileType": selected_file.get("fileType"), "path": str(output),
                "bytes": output.stat().st_size, "sha256": sha256(output),
            }
            records.append(record)
            print(f"downloaded {item['assetId']} {record['bytes']}", flush=True)
    finally:
        if client is not None:
            client.terminate()
    manifest = {
        "schema": "interior.blender-asset-acquisition-manifest.v1",
        "provider": "BlenderKit", "requestSha256": sha256(request_path),
        "sceneUuid": scene_uuid, "assets": records,
    }
    manifest_path = Path(args.manifest).resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
