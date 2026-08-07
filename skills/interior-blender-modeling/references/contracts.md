# Input and delivery contracts

## Floorplan inputs

- Current `confirmed-version/manifest.json`
- Complete `interior.floorplan-handoff.v3`
- Matching `floorplan-import-receipt.json`
- Manifest-approved component layout with one placement per accepted source object
- Manifest-approved camera plan when accepted cameras exist

Reject naked structure JSON, historical HTML, screenshots as geometry truth, and files discovered only by broad directory search.

## Scene output

The `.blend` must contain provenance properties and named collections for structure, openings, floors, furniture, annotations, cameras, and lights. Each accepted source furniture candidate appears once as an editable object root with parameterized child parts.

## Delivery output

- Native `.blend`
- `.glb` exchange model
- Overall and accepted-camera preview images
- Build validation JSON with source hashes and object counts
- MCP connection test JSON with protocol version, tool inventory, Blender version, and reopened scene facts
- Runtime/install evidence with binary checksum and third-party source revision
- Skill package and concise delivery note

For Feishu delivery, link explicit files. Keep individual files below the direct-send limit; otherwise use the configured drive/OSS fallback and return a real remote link.
