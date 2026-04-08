# Editor Overview

The external area editor lives under `tools/area_editor/` and is the main authoring tool for common project workflows.

## Why The Editor Exists

The editor exists because the project benefits from a dedicated authoring tool, but the old built-in editor became too coupled to runtime code and assumptions.

The current direction is:

- keep runtime code focused on play mode
- keep authoring tools separate
- target the same JSON contract as the runtime

## What The Editor Can Do Today

The current editor is already strong for project and area authoring. It can:

- open a project manifest
- browse areas, templates, items, dialogues, commands, and assets
- load areas into an editable canvas
- render tile layers, world entities, and area-owned screen-space entities
- paint tiles and edit `cell_flags`
- select tile rectangles, copy, cut, paste, and delete them
- select multi-tile tileset regions and paint them as stamps
- add, rename, delete, reorder, and duplicate tile layers
- place, select, delete, and nudge entities
- edit render properties
- edit area startup behavior through a dedicated `Area Start` surface
- edit project manifest data, shared variables, items, global entities, templates, and entity instances through structured tabs
- fall back to guarded raw JSON where the structured UI is not enough
- rename or move file-backed content with reference-update previews

## What The Editor Does Not Try To Be

It is intentionally not:

- a second runtime
- an in-process gameplay simulator
- a persistence playback tool
- a replacement for every possible raw JSON workflow

## Current Practical Role

Right now the best mental model is:

- it is an excellent area editor
- it already covers several project-level content surfaces
- it still has catch-up work to do for some newer runtime-facing fields and workflows

## Recommended Usage

Use the editor first for:

- room layout
- cell blocking
- entity placement
- template-driven tuning
- item and shared-variable editing
- safe file reorganization

Use raw JSON when:

- you are working with deeper command payloads
- you need a surface the structured editor does not cover yet
- you are debugging an exact authored payload

## Deep References

- [tools/area_editor/README.md](https://github.com/alext512/dungeon-engine/blob/main/tools/area_editor/README.md)
- [tools/area_editor/ARCHITECTURE.md](https://github.com/alext512/dungeon-engine/blob/main/tools/area_editor/ARCHITECTURE.md)
- [tools/area_editor/SCOPE.md](https://github.com/alext512/dungeon-engine/blob/main/tools/area_editor/SCOPE.md)
