# Environment Contract

## Runtime

- Python `>=3.11`
- Standard library only
- No API key, browser session, database, paid service, or network access

## External authority

This Skill reads but does not own:

- `interior.floorplan-handoff.v3`
- source floorplan image
- `interior.floorplan-structure.v3`
- `interior.trace-components.v2`
- `interior.native-model-manifest.v1`
- current HTML, Blender, or CAD layout state
- the native model file

It owns only `interior.circulation-*` outputs.

## Write boundary

Scripts write only paths passed through `--out` or `--svg-out`. They do not edit the native model, floorplan handoff, structure, trace data, asset library, or another Skill.

## Security

- No credentials are read.
- No shell command is constructed from document values.
- All referenced evidence is hash-checked before final acceptance.
- Symbolic policy aliases and environment overrides are not supported; the checked-in policy is the sole numerical source.
