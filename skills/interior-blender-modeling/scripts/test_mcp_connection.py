#!/usr/bin/env python3
"""Exercise a Blender MCP stdio server through its headless Blender transport."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def run(args):
    env = dict(os.environ)
    env["BLENDER_BIN"] = str(Path(args.blender).resolve())
    params = StdioServerParameters(command=str(Path(args.server).resolve()), env=env)
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            initialized = await session.initialize()
            listed = await session.list_tools()
            tool_names = sorted(tool.name for tool in listed.tools)
            assert "blender_python_exec" in tool_names
            code = """
import json
scene = bpy.context.scene
roots = [obj for obj in bpy.data.objects if obj.get('sourceObjectCandidateId')]
__result__ = {
    'blenderVersion': bpy.app.version_string,
    'floorplanId': scene.get('floorplanId'),
    'handoffDigestSha256': scene.get('handoffDigestSha256'),
    'objectCount': len(bpy.data.objects),
    'collectionNames': sorted(collection.name for collection in bpy.data.collections),
    'sourceFurnitureRoots': len(roots),
    'cameraCount': sum(1 for obj in bpy.data.objects if obj.type == 'CAMERA'),
}
"""
            called = await session.call_tool(
                "blender_python_exec",
                arguments={
                    "code": code,
                    "transport": "headless",
                    "blend_file": str(Path(args.blend).resolve()),
                    "factory_startup": False,
                    "timeout_seconds": 60,
                },
            )
            text = "\n".join(item.text for item in called.content if getattr(item, "text", None))
            payload = json.loads(text)
            assert payload.get("error") is None, payload
            result = payload.get("result") or {}
            report = {
                "schema": "codex.blender-mcp-connection-test.v1",
                "status": "accepted",
                "server": str(Path(args.server).resolve()),
                "blender": str(Path(args.blender).resolve()),
                "blend": str(Path(args.blend).resolve()),
                "protocolVersion": initialized.protocolVersion,
                "toolCount": len(tool_names),
                "toolNames": tool_names,
                "headlessCallResult": result,
                "checks": {
                    "mcpInitialized": True,
                    "pythonExecToolAvailable": True,
                    "blendOpened": result.get("floorplanId") is not None,
                    "sourceFurniturePresent": result.get("sourceFurnitureRoots", 0) >= args.min_furniture,
                    "acceptedCamerasPresent": result.get("cameraCount", 0) >= args.min_cameras,
                },
            }
            assert all(report["checks"].values()), report
            Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"ok": True, "protocolVersion": report["protocolVersion"], "toolCount": report["toolCount"], "result": result}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True)
    parser.add_argument("--blender", required=True)
    parser.add_argument("--blend", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--min-furniture", type=int, default=1)
    parser.add_argument("--min-cameras", type=int, default=1)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
