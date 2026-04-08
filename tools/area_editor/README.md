# Area Editor

This folder contains the external area editor for the puzzle dungeon project.

It is intentionally separate from the runtime in `dungeon_engine/`.

## Why This Exists

The project still benefits from tooling for common authoring tasks, but the previous built-in editor became too coupled to runtime code and runtime assumptions.

The new direction is:

- keep the runtime focused on playing the game
- keep authoring tools outside the runtime package
- use the same JSON files as the shared contract

## Current State

Phase 1 is implemented.
Phase 2 is implemented.
Phase 3 is in active use.

The editor is currently a strong project/area authoring tool, but it is still not the
entire runtime authoring surface. The earlier catch-up pass for items, project-level
config, `global_entities`, reference-aware content reorganization, and safer layer
management is now in place. The main remaining gaps are visual screen-space placement,
drag-to-move manipulation, runtime handoff, and broader structured editing for some
newer engine-owned fields.

The current editor can:

- open a project manifest
- open shared variables and global entities
- browse areas, entity templates, items, dialogues, commands, and assets
- load an area into an editable canvas
- render tile layers, world entities, and area-owned screen-space entities
- show an offset screen pane sized from the project's configured display dimensions
- toggle tile-layer visibility, grid visibility, and entity visibility
- zoom, pan, and show hovered world-cell or screen-pixel coordinates
- edit `cell_flags` on area tabs through a dedicated edit mode
- paint tiles on the active layer
- use a dedicated `Tile Select` tool to select a rectangular region on the active
  layer, then clear/delete, copy, cut, or paste it
- drag-select multiple tiles in the tileset browser and paint them as a stamp brush
- add, rename, delete, and reorder real tile layers
- duplicate areas either as a `Full Copy` or as a stripped `Layout Copy`
- place and delete world-space entities with the template brush
- select stacked world entities by cell and select screen-space entities from the screen pane
- nudge selected world entities by tiles and selected screen-space entities by pixels
- use a tabbed right-side area workspace so `Layers` stays focused and area
  startup behavior lives in a dedicated `Area Start` tab
- edit area `enter_commands` through helper insertions plus direct JSON, including
  common actions like `route_inputs_to_entity`, `run_entity_command`,
  `open_dialogue_session`, `set_camera_follow`, and `play_music`
- edit selected entity instances through a structured Fields tab or guarded raw JSON tab
- edit entity templates, items, project manifest fields, shared variables, and
  global entities through structured tabs plus guarded raw JSON fallbacks
- edit layer/entity render properties from a shared dock
- edit dialogue/template/command JSON through guarded viewer tabs
- rename/move areas, templates, items, dialogues, commands, and assets with
  previewed reference updates
- delete those same content files with a usage preview and explicit warning that
  references are left unchanged
- show folders in the file-backed browsers, create folders, rename/move folders,
  and delete completely empty folders
- save edited area files back to JSON with unknown-field preservation
- write known dense JSON matrices such as tile grids in a more readable compact form
- run focused automated tests around manifest loading, canvas interaction, and document round-tripping

What is still not implemented:

- visual placement of new screen-space entities from the canvas
- drag-to-move entity manipulation
- broader structured editing for newer engine-owned entity fields and exposed workflow variables
- runtime handoff / launch integration

## Expected Responsibilities

The editor is meant to help with:

- tile painting
- layer-oriented map editing
- cell flag editing
- entity placement
- editing common per-instance values
- selecting other entity ids when parameters reference them
- editing area-enter behavior without opening the whole area file as raw JSON
- preserving room JSON without forcing the user to hand-edit common cases

## Screen-Space Notes

The area canvas now includes a separate screen pane to the right of the world grid.

- It is a reference frame for area-owned screen-space entities only.
- Its size comes from the project's configured shared variables display size, with runtime-matching defaults when that data is absent.
- Existing screen-space entities can be selected, nudged, and deleted there.
- Screen-space paint/placement is intentionally deferred for now.
- `global_entities` from `project.json` are not shown in the area canvas yet.

## Tile Selection Notes

- `Tile Select` is a separate tool from entity `Select`.
- It works on the active tile layer only.
- Drag on the canvas to select a rectangle.
- `Delete` clears the selected tiles.
- `Escape` clears the current tile selection.
- `Ctrl+C`, `Ctrl+X`, and `Ctrl+V` copy, cut, and paste the selected block.
- Paste anchors to the currently hovered tile when possible, otherwise to the
  selection's top-left.

## Tileset Stamp Notes

- The tileset browser now supports dragging a rectangular selection across one
  tileset sheet.
- That selection becomes the active paint stamp.
- Stamps paint with their top-left tile anchored to the clicked map cell.
- Switching tilesets still resets the brush to eraser until a new tile or stamp
  is selected from that sheet.

## Current Non-Goals

The current editor still does not:

- simulate gameplay in-process
- import runtime code from `dungeon_engine`
- act as a second engine or persistence previewer
- revive the archived built-in editor

It also should not be described as fully caught up with the runtime yet. Right now it is
best understood as a strong area editor with some newer project-authoring workflows still
pending, especially around the curated template-driven game-building path.

## Folder Intent

This folder now hosts:

- tool-specific code
- tool-specific tests
- tool-specific notes and decisions

## Running The Editor

From `tools/area_editor/`:

```text
pip install -r requirements.txt
python -m area_editor
python -m area_editor --project path/to/project.json
```

## Related Runtime Docs

- [../../AUTHORING_GUIDE.md](../../AUTHORING_GUIDE.md)
- [../../ENGINE_JSON_INTERFACE.md](../../ENGINE_JSON_INTERFACE.md)
- [../../architecture.md](../../architecture.md)

## Historical Reference

The old built-in editor lives under:

- [../../archived_editor/README.md](../../archived_editor/README.md)

That folder is reference material, not the new architecture.
