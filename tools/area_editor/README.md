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
Phase 3 has started with a first editable slice for area saving plus
cell-flag painting.

The current editor can:

- open a project manifest
- browse areas, entity templates, dialogues, commands, and assets
- load an area into a read-only canvas
- render tile layers plus entity markers and template sprite previews
- toggle layers, entities, and the grid
- zoom, pan, and show hovered cell coordinates
- edit `cell_flags` on area tabs through a dedicated edit mode
- save edited area files back to JSON with unknown-field preservation
- run focused tests around manifest loading, asset resolution, and document round-tripping

What is not implemented yet:

- tile painting
- entity placement, movement, deletion, or reordering
- inspector editing for instance fields and parameters
- validation or runtime handoff actions

## Expected Responsibilities

The future tool is expected to help with:

- tile painting
- layer-oriented map editing
- cell flag editing
- entity placement
- editing common per-instance values
- selecting other entity ids when parameters reference them
- preserving room JSON without forcing the user to hand-edit common cases

## Current Non-Goals

The current editor still does not:

- simulate gameplay in-process
- import runtime code from `dungeon_engine`
- act as a second engine or persistence previewer
- revive the archived built-in editor

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
