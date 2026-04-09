# Editor Workflow

This is the shortest practical path through the current editor.

## Launch

From `tools/area_editor/`:

```bash
pip install -r requirements.txt
python -m area_editor
python -m area_editor --project ../../projects/new_project/project.json
```

## How The UI Is Organized

The editor is built around a few core regions:

- a project browser for file-backed content
- a central tabbed document area
- an area canvas for world editing
- supporting docks for layers, tilesets, properties, and structured editors

## Basic Area Editing Loop

1. Open a project manifest.
2. Open an area from the browser.
3. Choose the active tile layer.
4. Paint tiles or edit cell flags.
5. Place or select entities.
6. Adjust structured fields or use the guarded JSON tab.
7. Save the area back to JSON.

## Tile Editing

Current tile workflows include:

- paint on the active layer
- right-click erase
- Alt-click eyedrop
- rectangular tile selection on the active layer
- copy, cut, paste, and clear selected tile blocks
- drag-select tileset regions and paint them as stamps

## Cell Flags

Cell flags are edited in a dedicated mode rather than as a side effect of tile painting.

This is important because:

- walkability and tile art are separate systems
- the engine only gives built-in meaning to selected flags such as `blocked`
- areas may still carry custom cell metadata

## Entity Editing

Current entity workflows include:

- world-space entity placement from templates
- screen-space template placement from the screen pane
- selection of stacked entities by cell
- screen-space entity selection from the screen pane
- nudging world entities by tiles
- nudging screen-space entities by pixels
- structured editing of common instance fields
- guarded raw JSON editing for the rest

If the active template is screen-space, keep `Paint` mode active and click inside the screen pane to place the new entity at screen-pixel coordinates.

## Area Startup Editing

The editor keeps `Layers` focused on map structure and puts area startup behavior in a separate `Area Start` tab. That surface is especially helpful for common `enter_commands` actions such as:

- `route_inputs_to_entity`
- `run_entity_command`
- `open_dialogue_session`
- `set_camera_follow`
- `play_music`

## Project-Level Editing

The editor is no longer only about areas. It can also edit:

- project manifest fields
- shared variables
- global entities
- items
- templates

Dialogue and command files currently rely more on guarded JSON views and editors than on a full guided builder.

## Reference-Aware File Operations

The file-backed browsers support:

- folder creation
- rename or move for supported content types
- reference-update previews before applying changes
- delete with explicit warnings when references are not automatically repaired

That makes the editor useful even outside direct canvas editing.

## Saving Philosophy

The editor aims to preserve unknown fields instead of aggressively rewriting documents into only the subset it understands. That preservation story is a big part of why it is safe to use alongside a fast-moving runtime.
