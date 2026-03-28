# Data Boundary

## Core Rule

The runtime and the future editor communicate through files, not imports.

The contract is authored JSON plus project assets on disk.

## Allowed Inputs

The future tool may read:

- `project.json`
- authored area JSON files
- entity template JSON files
- named command JSON files if needed for reference
- ordinary project JSON data if needed for context
- PNG assets and other discoverable project assets

## Allowed Outputs

The future tool may write:

- authored area JSON files
- possibly tool-owned sidecar metadata in a clearly separate location, if later approved

The future tool should not write:

- runtime save files unless explicitly asked
- engine code
- runtime-generated state
- hidden tool metadata inside gameplay fields without a documented decision

## Import Boundary

The future tool should not import:

- `dungeon_engine`
- runtime systems
- runtime commands
- runtime entity/world classes
- archived editor modules

If the tool needs runtime validation later, safer options are:

- independent validation logic for tool-owned concerns
- launching an external verification command
- reading canonical docs and following the JSON contract directly

## Preservation Rules

When loading and saving area JSON, the tool should aim to:

- preserve unknown keys
- preserve unknown nested structures
- avoid rewriting unrelated content unnecessarily
- avoid silently normalizing data unless that behavior is documented

This matters because the runtime may evolve faster than the tool.

## Entity Reference Support

The tool is expected to help with parameters that reference other entities.

That support should be based on authored room data and documented heuristics, not on imported runtime logic.

Possible approaches later:

- explicit field metadata
- sidecar field hints
- per-project configuration for known parameter names
- conservative heuristics with clear user-visible labels

## Tool State

Tool-only state should stay outside gameplay data.

Examples:

- recent projects
- panel layout
- temporary selections
- zoom level
- hidden layers in the UI
- cached scan results

If persistent tool state is ever added, it should live in a clearly tool-owned location.

## Safety Test For Proposed Changes

A design is probably crossing the boundary if it requires:

- importing runtime classes to interpret room data
- duplicating command execution behavior
- reconstructing gameplay state instead of authored state
- storing tool internals inside area/entity gameplay fields
