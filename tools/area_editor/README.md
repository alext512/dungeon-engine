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

The editor is currently useful but partially outdated relative to the runtime. Recent
engine work added new authoring surfaces such as inventory items, shared UI presets,
`global_entities`, pause/inventory controllers, and more engine-owned entity fields.
Those workflows are not yet represented equally well in the tool, so an editor catch-up
pass is planned before treating it as the primary way to author full projects.

The current editor can:

- open a project manifest
- browse areas, entity templates, dialogues, commands, and assets
- load an area into an editable canvas
- render tile layers, world entities, and area-owned screen-space entities
- show an offset screen pane sized from the project's configured display dimensions
- toggle layers, entities, and the grid
- zoom, pan, and show hovered world-cell or screen-pixel coordinates
- edit `cell_flags` on area tabs through a dedicated edit mode
- paint tiles on the active layer
- place and delete world-space entities with the template brush
- select stacked world entities by cell and select screen-space entities from the screen pane
- nudge selected world entities by tiles and selected screen-space entities by pixels
- edit selected entity instances through a structured Fields tab or guarded raw JSON tab
- edit layer/entity render properties from a shared dock
- edit dialogue/template/command JSON through guarded viewer tabs
- save edited area files back to JSON with unknown-field preservation
- run focused automated tests around manifest loading, canvas interaction, and document round-tripping

What is still not implemented:

- first-class browsing/editing for `item_paths` item definitions
- direct browsing/editing for `shared_variables.json` and UI preset data
- visual placement of new screen-space entities from the canvas
- drag-to-move entity manipulation
- project-level `global_entities` editing
- broader structured editing for newer engine-owned entity fields
- advanced reference pickers for entity-linked parameters
- runtime handoff / launch integration

## Expected Responsibilities

The future tool is expected to help with:

- tile painting
- layer-oriented map editing
- cell flag editing
- entity placement
- editing common per-instance values
- selecting other entity ids when parameters reference them
- preserving room JSON without forcing the user to hand-edit common cases

## Screen-Space Notes

The area canvas now includes a separate screen pane to the right of the world grid.

- It is a reference frame for area-owned screen-space entities only.
- Its size comes from the project's configured shared variables display size, with runtime-matching defaults when that data is absent.
- Existing screen-space entities can be selected, nudged, and deleted there.
- Screen-space paint/placement is intentionally deferred for now.
- `global_entities` from `project.json` are not shown in the area canvas yet.

## Current Non-Goals

The current editor still does not:

- simulate gameplay in-process
- import runtime code from `dungeon_engine`
- act as a second engine or persistence previewer
- revive the archived built-in editor

It also should not be described as fully caught up with the runtime yet. Right now it is
best understood as a strong area editor with some newer project-authoring workflows still
pending.

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
python -m area_editor --project ../../projects/test_project/project.json
```

## Related Runtime Docs

- [../../AUTHORING_GUIDE.md](../../AUTHORING_GUIDE.md)
- [../../ENGINE_JSON_INTERFACE.md](../../ENGINE_JSON_INTERFACE.md)
- [../../architecture.md](../../architecture.md)

## Historical Reference

The old built-in editor lives under:

- [../../archived_editor/README.md](../../archived_editor/README.md)

That folder is reference material, not the new architecture.
