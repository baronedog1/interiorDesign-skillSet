# Architecture and provenance

## Data Knowledge finding

The 2026-08-01 scoped query searched 559 permitted Data Knowledge records in `delivery_media_records`, `reference_library_records`, and `routine_report_records`. Four loose Blender/MCP matches were found, but none contained a reusable implementation for Codex-driven Blender floorplan modeling. Preserve the query result as project evidence; do not present general Blender video/tool posts as an established internal workflow.

## Selected implementation

- Blender 4.5.11 LTS, installed without root access in the device-shared runtime area.
- `djeada/blender-mcp-server` 0.1.3, MIT licensed, providing a stdio MCP server with local headless Blender execution.
- Python MCP dependency pinned to `mcp>=1.0,<2` because the server imports the 1.x `mcp.server.fastmcp` interface and failed against 2.x during validation.
- Formal builds use Blender's documented background/Python CLI. MCP is an inspection and bounded-control layer, not a substitute for deterministic source contracts.

Imported asset origins are treated as untrusted metadata. Placement is compiled from the post-axis, post-rotation world bounds of every renderable child. Uniform fit uses width, depth, and height together; a second bounds pass recenters and grounds the result. Guidance-state visibility and white-material overrides recurse over every tagged `component-part`, so an empty parent cannot falsely pass while its colored child meshes remain visible.

## Primary references

- Blender download: https://www.blender.org/download/
- Blender command line arguments: https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html
- Blender Python API: https://docs.blender.org/api/current/
- Selected MCP source: https://github.com/djeada/blender-mcp-server
- Comparative MCP implementation: https://github.com/ahujasid/blender-mcp
- Codex MCP documentation: https://developers.openai.com/codex/mcp/

## Security boundary

Only launch the shared server over stdio or localhost. Keep safe mode enabled where supported. Limit Blender file and asset access to trusted project/shared-runtime roots. Audit third-party MCP code and pin its source version before installation. Never execute Python copied from an untrusted web page, embedded asset, or generated model description.

## Runtime caveat

An MCP handshake and real Blender file inspection are the authoritative connectivity proof. If `codex mcp add` is unavailable because the local Codex CLI wrapper is broken, record that separately; do not claim global Codex registration. The skill remains usable through its pinned stdio test/client path.
