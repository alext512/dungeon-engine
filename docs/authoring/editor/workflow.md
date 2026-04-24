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
- supporting docks for layers, tilesets, properties, and area tools
- on-demand structured dialogs for focused entity-instance editing

## Basic Area Editing Loop

1. Open a project manifest.
2. Open an area from the browser.
3. Choose the active tile layer.
4. Choose a `Target` and `Tool` combination.
5. Place or select entities.
6. Adjust focused parameters, advanced instance fields, or the guarded JSON tab.
7. Save the area back to JSON.

## Tile Editing

Current tile workflows include:

- `Tiles + Pencil` paints on the active layer
- `Tiles + Eraser` clears tiles with left-click
- Alt-click eyedrop
- `Tiles + Select` for rectangular tile selection on the active layer
- copy, cut, paste, and clear selected tile blocks
- drag-select tileset regions and paint them as stamps

## Cell Flags

Cell flags are edited in a dedicated mode rather than as a side effect of tile painting.

Use the `Cell Flags` tab in Area Tools to choose the current brush before
painting. The built-in presets set or clear `blocked`; the custom brush can
paint any other cell-flag key with a JSON-compatible value. `Flags + Pencil`
paints the selected brush; `Flags + Eraser` clears it with left-click.

This is important because:

- blocked flags and tile art are separate systems
- the engine only gives built-in meaning to selected flags such as `blocked`
- areas may still carry custom cell metadata

## Entity Editing

Current entity workflows include:

- world-space entity placement from templates with `Entities + Pencil`
- screen-space template placement from the screen pane with `Entities + Pencil`
- hover-assisted picking for stacked entities in `Entities + Select`
- screen-space entity selection from the screen pane with `Entities + Select`
- dragging selected world entities by tile cell
- dragging selected screen-space entities by pixel
- nudging world entities by tiles
- nudging screen-space entities by pixels
- focused parameter editing through the entity edit dialog
- advanced structured editing of less-frequent instance fields
- guarded raw JSON editing for the rest

If the active template is screen-space, keep `Entities + Pencil` active and
click inside the screen pane to place the new entity at screen-pixel coordinates.

In `Entities + Select`, double-click an entity on the canvas to open the
entity-instance editor dialog. The dialog stays pinned to that entity while you
continue selecting or inspecting other entities. The Area Tools `Entities` list
can also be used to select hard-to-click instances and open the same editor.

When a template parameter expects an `entity_id`, the structured editor now
offers a dedicated picker. It starts from the current area when possible, lets
you switch to other areas or project globals, and filters the list by id,
template, space, or position before writing back only the chosen entity id.
Boolean parameters use checkboxes, and typed `entity_command_id` parameters can
pick from the command names available on the selected target entity.
When an `entity_id` parameter is tied to an `area_id` parameter, such as a
transition's `destination_entity_id` using `target_area`, the picker locks to
that chosen area.

The raw JSON tab shows the authored entity instance payload, not a merged view
with template defaults. Use the focused `Parameters` tab when you want the
default placeholders and typed controls.

If several entities overlap under the pointer, pausing briefly in `Entities + Select`
opens a small picker for choosing the specific target. When deleting overlapping
entities with `Entities + Eraser`, the same picker is used to choose which entity
to remove.

## Area Startup Editing

The editor keeps `Layers` focused on map structure and puts area startup behavior in a separate `Area Start` tab. That surface is especially helpful for common `enter_commands` actions such as:

- `route_inputs_to_entity`
- `run_entity_command`
- `open_dialogue_session`
- `set_camera_follow_entity`
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
- dragging a file entry onto a folder to move it with the same reference-update
  preview used by `Rename/Move...`
- reference-update previews before applying changes
- delete with explicit warnings when references are not automatically repaired

That makes the editor useful even outside direct canvas editing.

## Saving Philosophy

The editor aims to preserve unknown fields instead of aggressively rewriting documents into only the subset it understands. That preservation story is a big part of why it is safe to use alongside a fast-moving runtime.
