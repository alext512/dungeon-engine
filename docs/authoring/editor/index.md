# Editor Overview

The external area editor lives under `tools/area_editor/` and is the main authoring tool for common project workflows.

On Windows, the quickest launcher is `tools\area_editor\Run_Editor.cmd`.
That launcher can create a local editor environment and install the editor dependencies automatically if needed.

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
- switch between `Target` and `Tool` combinations for tiles, entities, and flags
- select tile rectangles, copy, cut, paste, and delete them
- select multi-tile tileset regions and paint them as stamps
- add, rename, delete, reorder, and duplicate tile layers
- place, select, drag, delete, nudge, and double-click edit entities, including basic screen-space template placement from the screen pane
- edit render properties
- edit area startup behavior through a dedicated `Area Start` surface
- edit project manifest data, shared variables, items, global entities, templates, and entity instances through structured tabs or focused dialogs
- tune entity-instance parameters through a focused `Parameters` tab, including typed reference pickers and boolean controls when `parameter_specs` provides them
- fall back to guarded raw JSON where the structured UI is not enough
- rename or move file-backed content with reference-update previews
- use a growing structured command editor for common builtin command families;
  the current coverage list lives in the [full editor manual](editor-manual.md#structured-command-editor-coverage)

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
- it still has catch-up work to do for some newer runtime-facing fields and richer direct-manipulation workflows

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

- [Full Editor Manual](editor-manual.md)
- [Editor Architecture](../../development/editor-architecture.md)
- [Editor Scope](../../project/editor-scope.md)
- [Editor Vision](../../project/editor-vision.md)
