# Authoring Guide

## Purpose

This document explains how to build project content for the engine without reading the Python code first.

It focuses on:

- `project.json`
- `shared_variables.json`
- `items/*.json`
- area JSON
- entity template JSON
- project command JSON
- dialogue JSON
- both the newer engine-owned dialogue runtime and the older controller-owned
  dialogue/menu pattern

Use this guide for authoring patterns. Use `ENGINE_JSON_INTERFACE.md` when you need the exact current command/value-source surface.

## Mental Model

The engine is built from a few content layers:

1. `project.json`
2. `shared_variables.json`
3. `items/*.json`
4. `areas/*.json`
5. `entity_templates/*.json`
6. `commands/*.json`
7. ordinary project JSON data such as `dialogues/*.json`

The engine provides primitive commands. Your project combines them into behavior using JSON.

Important clarification:

- these category names are meaningful
- the exact folder names are just conventions
- the manifest paths decide what gets indexed automatically
- ordinary JSON data can still live anywhere inside the project and be loaded by relative path

How the categories connect:

```text
project.json
|-- points to areas/
|-- points to entity_templates/
|-- points to commands/
|-- points to items/
|-- points to assets/
|-- points to shared_variables.json
`-- instantiates global_entities

items
`-- define reusable item records with path-derived ids such as `items/copper_key`

areas
|-- place entity instances
|-- define transfer destinations and camera defaults
|-- call commands from enter hooks
`-- override input-target defaults

entity templates
|-- define visuals, entity commands, input maps, variables
|-- call project commands
`-- call dialogue builtins or controller entity commands to start dialogues

ordinary JSON data
`-- provide reusable dialogue/menu content or any other project-specific payloads

project commands
`-- provide reusable behavior chains
```

Two command-authoring rules apply everywhere:

- Any `commands: [...]` list is sequential by default.
- Use `run_commands` only when you want to execute a command-list value explicitly, such as one stored in a variable or passed as raw hook data.

## A Minimal Project

Typical layout:

```text
my_project/
    project.json
    shared_variables.json
    items/
    areas/
    entity_templates/
    commands/
    dialogues/                  # Optional ordinary JSON data
    assets/
```

That layout is recommended, but not mandatory.

## `project.json`

This file is the project manifest.

Example:

```json
{
  "entity_template_paths": ["entity_templates/"],
  "asset_paths": ["assets/"],
  "area_paths": ["areas/"],
  "command_paths": ["commands/"],
  "item_paths": ["items/"],
  "shared_variables_path": "shared_variables.json",
  "global_entities": [
    {
      "id": "dialogue_controller",
      "template": "entity_templates/dialogue_panel"
    },
    {
      "id": "pause_controller",
      "template": "entity_templates/pause_controller"
    },
    {
      "id": "debug_controller",
      "template": "entity_templates/debug_controller"
    }
  ],
  "startup_area": "areas/title_screen",
  "input_targets": {
    "menu": "pause_controller",
    "debug_toggle_pause": "debug_controller",
    "debug_step_tick": "debug_controller",
    "debug_zoom_in": "debug_controller",
    "debug_zoom_out": "debug_controller"
  },
  "debug_inspection_enabled": true
}
```

### Important fields

- `entity_template_paths`
  Folders containing entity templates.
- `asset_paths`
  Folders containing images, sounds, fonts, and tilesets.
- `area_paths`
  Folders containing area JSON files.
- `command_paths`
  Folders containing reusable project command JSON files.
- `item_paths`
  Folders containing reusable item definition JSON files.
- `shared_variables_path`
  Project-wide shared variable file.
- `global_entities`
  Entity instances that should exist in every runtime world.
- `startup_area`
  Default typed area id to open when only the project is selected, for example `areas/title_screen`.
- `input_targets`
  Default routed entity per logical input action. Areas can override specific actions, and any action omitted by both the project and the area stays unrouted until runtime commands change it.
- `save_dir`
  Directory for save files. Defaults to `saves`.

Authored entity ids are now project-wide identities. Do not reuse the same entity id across different areas or between area entities and `global_entities`.

## `items/*.json`

Inventory V1 item definitions are ordinary JSON files discovered through the
manifest `item_paths`.

Example:

```json
{
  "name": "Light Orb",
  "description": "Feeds the nearby beacon terminal once.",
  "icon": {
    "path": "assets/project/sprites/object_sheet.png",
    "frame_width": 16,
    "frame_height": 16,
    "frame": 2
  },
  "portrait": {
    "path": "assets/project/sprites/object_sheet.png",
    "frame_width": 16,
    "frame_height": 16,
    "frame": 2
  },
  "max_stack": 3,
  "consume_quantity_on_use": 1,
  "use_commands": [
    {
      "type": "set_entity_field",
      "entity_id": "$ref_ids.target_indicator",
      "field_name": "visible",
      "value": true
    }
  ]
}
```

Important fields:

- `name`
- `description`
- `icon`
- `portrait`
- `max_stack`
- `consume_quantity_on_use`
- `use_commands`

Current rules:

- item ids are path-derived, for example `items/light_orb`
- item files must not author their own `id`
- `max_stack` must be at least `1`
- `consume_quantity_on_use` must be `0` or greater
- items with no `use_commands` are still valid items
- `use_inventory_item` only consumes after the use commands finish cleanly

## `shared_variables.json`

Use this for shared project values.

Good use cases:

- render resolution
- movement timing like `ticks_per_tile`
- dialogue layout defaults
- inventory UI presets
- common tuning values reused by multiple commands

Example:

```json
{
  "display": {
    "internal_width": 256,
    "internal_height": 192
  },
  "movement": {
    "ticks_per_tile": 16
  },
  "dialogue_ui": {
    "default_preset": "standard"
  },
  "inventory_ui": {
    "default_preset": "standard"
  }
}
```

Read these values with tokens such as:

- `$project.display.internal_width`
- `$project.movement.ticks_per_tile`
- `$project.dialogue_ui.default_preset`
- `$project.inventory_ui.default_preset`

## Areas

An area file defines one room or screen.

Example structure:

```json
{
  "tile_size": 16,
  "camera": {
    "follow": {
      "mode": "entity",
      "entity_id": "player"
    }
  },
  "input_targets": {
    "interact": "player",
    "move_up": "player",
    "move_down": "player",
    "move_left": "player",
    "move_right": "player"
  },
  "variables": {},
  "tilesets": [],
  "tile_layers": [],
  "cell_flags": [],
  "enter_commands": [],
  "entities": []
}
```

### Important fields

- `tile_size`
  Tile size in pixels.
- `entry_points`
  Optional named destinations kept for compatibility with older transfer flows.
- `camera`
  Optional authored camera defaults for this area.
- `input_targets`
  Optional per-area overrides for which entity receives each logical input action.
- `variables`
  Mutable area-level variables.
- `tilesets`
  Tileset definitions used by the area.
- `tile_layers`
  Visual tile layers.
- `cell_flags`
  Walkability grid.
- `enter_commands`
  Optional command chain that runs immediately after the area loads.
- `entities`
  Placed area-local entity instances.

Important notes:

- area ids are derived from file path
- do not author an `id` or `area_id` field inside area JSON
- do not author a top-level area `name`; use the path-derived area id everywhere
- do not author `player_id`; the engine now uses explicit input routing, transition payloads, and camera defaults instead
- project-level global entities belong in `project.json`, not inside `entities`
- area `camera` defaults are just initial runtime state; commands can replace them later
- newer projects should prefer destination marker entities plus `destination_entity_id`
  instead of relying on authored `entry_points`

### Tilesets and layers

The runtime uses GIDs for visual tiles. `0` means empty.

Example tileset entry:

```json
{
  "firstgid": 1,
  "path": "assets/project/tiles/showcase_tiles.png",
  "tile_width": 16,
  "tile_height": 16
}
```

Each tile layer has a `grid` field: a 2D array of integer GIDs arranged as `[row][col]`, where `[0][0]` is the top-left corner. Example for a 4x3 area:

```json
{
  "name": "ground",
  "render_order": 0,
  "y_sort": false,
  "stack_order": 0,
  "grid": [
    [1, 1, 1, 1],
    [1, 2, 2, 1],
    [1, 1, 1, 1]
  ]
}
```

Tile-layer rendering is now controlled by four fields:

- `render_order`
  Coarse draw band. Lower values render first.
- `y_sort`
  When `true`, the layer is exploded into per-tile draw items so its cells can interleave with entities in the same render band.
- `sort_y_offset`
  Extra pixel offset added to the tile cell's y-sort pivot.
- `stack_order`
  Fine-grained tie-breaker inside the same render band / y-sort position.

Recommended defaults:

- ground and floor art: `render_order: 0`, `y_sort: false`
- actors and front walls that should interleave: `render_order: 10`, `y_sort: true`
- roofs / canopy overlays: `render_order: 20`, `y_sort: false`

`cell_flags` uses the same `[row][col]` layout.

The preferred current authored form is an object with `blocked`:

```json
"cell_flags": [
  [
    {"blocked": true},
    {"blocked": true},
    {"blocked": true},
    {"blocked": true}
  ],
  [
    {"blocked": true},
    {"blocked": false},
    {"blocked": false},
    {"blocked": true}
  ],
  [
    {"blocked": true},
    {"blocked": true},
    {"blocked": true},
    {"blocked": true}
  ]
]
```

Boolean cells are still accepted in authored area data as a concise older style:

```json
"cell_flags": [
  [false, false, false, false],
  [false, true,  true,  false],
  [false, false, false, false]
]
```

Area dimensions (`$area.width`, `$area.height`) are auto-computed from the first tile layer's grid. Do not author width or height fields.

### Placed entities

Placed entities usually reference a template:

```json
{
  "id": "lever_1",
  "grid_x": 4,
  "grid_y": 2,
  "template": "lever_toggle",
  "parameters": {
    "target_gate": "gate"
  }
}
```

For world-space placement, authored entities now use `grid_x` / `grid_y`. Screen-space entities continue to use `pixel_x` / `pixel_y`.

Authored `id` values are project-wide identities. If the same actor truly moves between areas, author it once and transfer it; do not keep duplicate placeholders with the same id in multiple areas.

## Entity Templates

Entity templates define reusable gameplay objects.

Example:

```json
{
  "kind": "sign",
  "solid": true,
  "interactable": true,
  "variables": {
    "dialogue_path": "dialogues/showcase/village_square_note.json"
  },
  "visuals": [
    {
      "id": "main",
      "path": "assets/project/sprites/sign.png",
      "frame_width": 16,
      "frame_height": 16,
      "frames": [0]
    }
  ],
  "entity_commands": {
    "interact": {
      "enabled": true,
      "commands": [
        {
          "type": "open_dialogue_session",
          "dialogue_path": "$dialogue_path",
          "dialogue_on_start": [],
          "dialogue_on_end": [],
          "segment_hooks": [],
          "allow_cancel": false,
          "entity_refs": {
            "instigator": "$ref_ids.instigator",
            "caller": "$self_id"
          }
        }
      ]
    }
  }
}
```

### Important entity fields

- `kind`
- `visuals`
- `space`
- `scope`
- `present`
- `visible`
- `render_order`
- `y_sort`
- `sort_y_offset`
- `stack_order`
- `tags`
- `variables`
- `inventory`
- `input_map`
- `entity_commands`
- `facing`
- `solid`
- `pushable`
- `weight`
- `push_strength`
- `collision_push_strength`
- `interactable`
- `interaction_priority`

### `inventory`

Inventories are entity-owned. That keeps the contract generic enough for the
player now and for chests, shops, or other containers later.

Example:

```json
{
  "kind": "player",
  "inventory": {
    "max_stacks": 4,
    "stacks": [
      {
        "item_id": "items/light_orb",
        "quantity": 1
      }
    ]
  }
}
```

Current rules:

- `inventory.max_stacks` limits how many stacks can exist
- each stack stores `item_id` plus `quantity`
- stack quantities must stay within the item's `max_stack`
- authored content rejects missing item definitions
- save/load preserves unresolved saved item ids with a warning instead of silently deleting them

### Inventory helpers

Inventory V1 currently gives you:

- `add_inventory_item`
- `remove_inventory_item`
- `use_inventory_item`
- `set_inventory_max_stacks`
- `open_inventory_session`
- `close_inventory_session`
- `$inventory_item_count`
- `$inventory_has_item`

Important rules:

- `add_inventory_item` and `remove_inventory_item` require
  `quantity_mode: "atomic" | "partial"`
- if you provide `result_var_name`, the operation result is written to
  `$self_id.variables[result_var_name]`
- if authored logic cares whether inventory state actually changed, check
  `changed_quantity > 0`
- inventory mutation commands now follow the target entity's persistence
  policy when `persistent` is omitted
- item `icon` is for list rows; item `portrait` is for the bottom detail panel
- the engine-owned inventory UI derives usability from whether `use_commands`
  exists and is non-empty

Typical pickup pattern:

```json
{
  "type": "add_inventory_item",
  "entity_id": "$ref_ids.instigator",
  "item_id": "$self.item_id",
  "quantity": "$self.quantity",
  "quantity_mode": "partial",
  "result_var_name": "last_inventory_result"
}
```

Entity rendering follows the same model as tile layers:

- `render_order`
  Coarse draw band. Lower values render first.
- `y_sort`
  When `true`, the entity is vertically interleaved with other y-sorted drawables in the same `render_order` band.
- `sort_y_offset`
  Pixel adjustment applied to the entity's y-sort pivot.
- `stack_order`
  Local tie-breaker after `render_order` and y-sort position.

Project-specific state like `toggled`, `dialogue_path`, and custom puzzle data
should live under `variables`.

The engine now also recognizes several top-level gameplay fields directly:

- `facing`
- `solid`
- `pushable`
- `weight`
- `push_strength`
- `collision_push_strength`
- `interactable`
- `interaction_priority`

That means:

- use top-level `solid` for standard blocking behavior
- use top-level `pushable` and `weight` for standard push behavior
- use top-level `facing` for standard facing-based movement / interaction
- use top-level `interactable` and optional `interaction_priority` for standard
  facing interaction lookup

You can still keep arbitrary project-defined state in `variables`. The important
boundary is that engine-owned runtime semantics should use the documented
top-level fields instead of hiding inside ordinary variables.

### `visuals`

Every entity now uses a `visuals` array instead of `sprite`.

Each visual can define:

- `id`
- `path`
- `frame_width`
- `frame_height`
- `frames`
- `animation_fps`
- `animate_when_moving`
- `flip_x`
- `visible`
- `tint`
- `offset_x`
- `offset_y`
- `draw_order`

If you still author `sprite`, loading fails on purpose.

### `space`

`space` controls the coordinate system:

- `world`
  Uses tile coordinates and participates in world lookup.
- `screen`
  Uses screen pixel coordinates.

Rules:

- world-space entities usually author `x` and `y`
- screen-space entities must not author `x` / `y`
- screen-space entities should use `pixel_x` / `pixel_y` or per-visual offsets

Screen-space entities do not participate in world-tile position queries and should not be used for tile/collision-based room interactions. Use them for HUD overlays, dialogue panels, menu controllers, and other UI that floats above the game world. A common pattern is `space: "screen"` combined with `scope: "global"` for persistent UI elements that survive area transitions (e.g. a health bar controller).

Screen-space entities are full entities with entity commands, variables, and command-driven behavior. This distinguishes them from the lightweight `show_screen_image` / `show_screen_text` commands, which create simple display-only screen elements without an entity command or variable system.

### `scope`

`scope` controls lifetime:

- `area`
  Normal area-local entity. Authored in area JSON, lives only while that area is loaded, and persists per-area.
- `global`
  Project-level runtime entity. Authored in `project.json` under `global_entities`. The runtime injects global entities into the active play world whenever an area is built, so they are always present regardless of which area is loaded.

Global entity state is stored separately from area state and is not reset by area resets. Use global scope for entities that need to persist across area transitions: HUD controllers, party/inventory managers, music controllers, or other cross-cutting services. Use area scope for room-specific NPCs, objects, and interactions.

In practice, author global service/controller entities in `project.json`.

### `input_map`

`input_map` lets an entity decide which entity command handles a logical action.

Example:

```json
{
  "input_map": {
    "interact": "interact"
  }
}
```

### How Input Routing Works

Each logical action is routed independently through three layers:

1. the input handler resolves a logical action such as `move_up`, `interact`, or `menu`
2. the world chooses the routed entity for that action from the current `input_targets`, using project defaults plus any area overrides
3. that routed entity's `input_map` decides which entity command to run for that action
4. if there is no mapping for that action, nothing is dispatched
5. the runner enqueues `run_entity_command` on the routed entity

This is what allows dialogue controllers, menus, and other service entities to temporarily own only the inputs they need without a single active-entity focus model.

If an action is absent from both the project and the area routing maps, it is simply unrouted until a runtime command assigns it.

For modal flows, the intended pattern is:

1. `push_input_routes` to save the current routing
2. reroute the borrowed actions to the modal controller
3. later `pop_input_routes` to restore the exact previous routes

The route stack is runtime-only control state. It is not saved.

## Project Commands

Project commands are reusable command chains stored in separate files under `commands/`.

Example:

```json
{
  "params": ["offset_x", "offset_y", "frames_needed"],
  "commands": [
    {
      "type": "set_entity_grid_position",
      "entity_id": "$self_id",
      "x": "$offset_x",
      "y": "$offset_y",
      "mode": "relative"
    },
    {
      "type": "move_entity_world_position",
      "entity_id": "$self_id",
      "x": {
        "$product": [
          "$offset_x",
          "$area.tile_size"
        ]
      },
      "y": {
        "$product": [
          "$offset_y",
          "$area.tile_size"
        ]
      },
      "mode": "relative",
      "frames_needed": "$frames_needed",
      "wait": false
    }
  ]
}
```

Notes:

- project command ids are path-derived typed ids from file location, for example `commands/walk_one_tile`
- do not author a top-level `id`
- use `run_project_command` to call them
- declare `deferred_params` when a specific parameter should remain raw data until a later explicit execution step, such as dialogue hook command arrays

Example with deferred hook params:

```json
{
  "params": ["dialogue_on_start", "dialogue_on_end"],
  "deferred_params": ["dialogue_on_start", "dialogue_on_end"],
  "commands": [
    {
      "type": "set_entity_var",
      "entity_id": "$self_id",
      "name": "dialogue_on_end",
      "value_mode": "raw",
      "value": "$dialogue_on_end"
    },
    {
      "type": "run_commands",
      "commands": "$dialogue_on_start"
    }
  ]
}
```

`deferred_params` keeps the passed hook payloads raw while the project command is instantiated. `value_mode: "raw"` keeps a setter from recursively resolving nested command data when you want to store that payload for later execution.

### How To Read Command JSON

There are three important JSON shapes in authored command files:

- command objects
  These have a `"type"` field and tell the engine to do something.
- runtime token strings
  These look like `$self_id` or `$project.movement.ticks_per_tile` and read a value at runtime.
- structured value sources
  These are single-key objects like `{"$sum": [...]}` or `{"$entity_ref": {...}}` that compute or query a value before a primitive command runs.

Example:

```json
{
  "type": "set_entity_var",
  "entity_id": "$self_id",
  "name": "next_x",
  "value": {
    "$sum": [
      "$self.current_x",
      1
    ]
  }
}
```

How to read it:

- `"type": "set_entity_var"`
  This is the engine-handled primitive command being executed.
- `"entity_id": "$self_id"`
  `$self_id` resolves to the current source entity id at runtime.
- `"value": { "$sum": [...] }`
  `"$sum"` is a helper that computes the value before `set_entity_var` runs.

When one JSON command chain needs to call another JSON command file, use `run_project_command`:

```json
{
  "type": "run_project_command",
  "command_id": "commands/walk_one_tile",
  "offset_x": 1,
  "offset_y": 0
}
```

In the called project command file, `$offset_x` and `$offset_y` resolve from those passed params.

This is a general rule: both `run_project_command` and `run_entity_command` forward any extra fields on the command object into the called flow as runtime parameters. The called commands can then read those values with `$param_name` tokens. This is how the dialogue examples pass `dialogue_path`, `dialogue_on_start`, `segment_hooks`, and other caller-supplied data into the controller's command chain.

Important nuance:

- do not assume every command object accepts arbitrary extra fields
- startup validation now fails on unknown top-level keys for strict primitive commands
- commands that intentionally accept caller-supplied runtime params include `run_project_command`, `run_entity_command`, `run_commands`, `run_parallel`, `spawn_flow`, `run_commands_for_collection`, `if`, `move_in_direction`, `push_facing`, and `interact_facing`

So a typo like `"persitent": true` on `set_visible` is now a startup validation failure, while a field like `"reward_item": "items/key"` on `run_commands` is still valid when child commands need to read `$reward_item`.

## Runtime References and Tokens

Commands often need to refer to the current entity or an explicitly passed related entity.

### `self`, `refs`, And `ref_ids`

Current command flows carry:

- `self`
  The entity that owns the current command chain.
- `entity_refs`
  A named map of explicitly passed related entities.

Use these token surfaces:

- `$self_id`
- `$self.some_value`
- `$refs.some_name.some_value`
- `$ref_ids.some_name`

### Tokens

The command runner also resolves tokens such as:

- `$self_id`
- `$self.some_value`
- `$refs.switch.some_value`
- `$ref_ids.switch`
- `$project.some.path`
- `$area.tile_size`
- `$camera.x`
- `$current_area.some_value`

`$self...` and `$refs.<name>...` read entity `variables`, not built-in entity fields. Use explicit query/value-source helpers with `select` when you need built-in fields like `grid_x` or `pixel_y`.

`$current_area...` reads the live current-area/runtime variable store for the active play session. In normal play, this is the same authored state surface that commands like `set_current_area_var`, `add_current_area_var`, and generic `if` checks over current-area values operate on.

`$area...` exposes the current area's `area_id`, `tile_size`, `width`, `height`, `pixel_width`, `pixel_height`, and `camera`.

`$camera...` exposes `x`, `y`, `follow`, `bounds`, `has_bounds`, `deadzone`, and `has_deadzone`.
Use nested follow fields such as `$camera.follow.mode`, `$camera.follow.entity_id`, `$camera.follow.action`, `$camera.follow.offset_x`, and `$camera.follow.offset_y`.

Example:

```json
{
  "type": "set_entity_var",
  "entity_id": "$ref_ids.caller",
  "name": "toggled",
  "value": true,
  "persistent": true
}
```

For strict primitive entity-target commands, use explicit ids or resolved id tokens such as `$self_id` and `$ref_ids.some_name` rather than symbolic strings.

## Ordinary JSON Dialogue Data

Dialogue/menu definitions are typically kept under `dialogues/`, but that folder is only a convention. These files are ordinary JSON data loaded by controller commands through explicit variable writes with value sources such as `{"$json_file": "dialogues/system/pause_menu.json"}`.

Within one live runtime context, repeated `$json_file` reads reuse a small
cache. Rebuilding runtime context, such as after an area change, `new_game`, or
`load_game`, starts with a fresh cache.

Example:

```json
{
  "segments": [
    {
      "type": "text",
      "text": "This little record shrine can write your progress into a save file."
    },
    {
      "type": "choice",
      "options": [
        {
          "text": "Save the game.",
          "option_id": "save"
        },
        {
          "text": "Keep going.",
          "option_id": "cancel"
        }
      ]
    }
  ]
}
```

### Common fields

- `participants`
  Optional map of participant id to character metadata.
- `segments`
  Required list of `text` and `choice` segments.
- `font_id`
  Optional font override. Font ids are the JSON filename (without extension) of a bitmap font definition under the project's `assets/.../fonts/` folder. See `ENGINE_JSON_INTERFACE.md` for the font definition format.
- `max_lines`
  Optional per-dialogue page height override.
- `text_color`
  Optional RGB color override.

### Bitmap font notes

Dialogue `font_id` values refer to bitmap font definition JSON files under the
project's asset roots, typically somewhere under `assets/.../fonts/`.

Important behavior:

- the atlas is sliced into fixed cells using `cell_width` / `cell_height`
- each glyph is auto-trimmed to its visible non-transparent pixels
- the default glyph advance width comes from that trimmed width
- `minimum_advance` clamps how narrow a glyph can become
- `space_width` controls the width of `" "` explicitly
- `advance_overrides` can force specific characters to use custom widths

So if a narrow glyph such as `I`, `l`, or `.` feels too tight or too loose,
you can override it in the font definition instead of redrawing the atlas.

Example:

```json
{
  "kind": "bitmap",
  "atlas": "project/fonts/pixelbet.png",
  "cell_width": 6,
  "cell_height": 16,
  "columns": 83,
  "line_height": 10,
  "letter_spacing": 1,
  "space_width": 4,
  "minimum_advance": 1,
  "fallback_character": "?",
  "advance_overrides": {
    "I": 4,
    "l": 3,
    ".": 2
  },
  "glyph_order": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.!?\":1234567890,'-/+()=;_[]%#><"
}
```

### Participant fields

Each entry in `participants` supports:

- `name`
  Display name shown in the dialogue UI.
- `portrait_path`
  Asset path to the portrait sprite sheet.
- `portrait_frame_width`
  Width in pixels of each portrait frame.
- `portrait_frame_height`
  Height in pixels of each portrait frame.
- `portrait_frame`
  Frame index to display from the portrait sprite sheet.

Example:

```json
{
  "participants": {
    "guide": {
      "name": "Guide",
      "portrait_path": "assets/project/sprites/portraits.png",
      "portrait_frame_width": 38,
      "portrait_frame_height": 38,
      "portrait_frame": 0
    }
  }
}
```

### Segment fields

- `type`
- `text`
- `pages`
- `options`
- `speaker_id`
- `show_portrait`
- `advance`

`text` is for single-page segments. `pages` is a string array for multi-page segments. Use one or the other.

`advance` is an optional object controlling how the segment progresses:

```json
{
  "advance": {
    "mode": "timer",
    "seconds": 1.2
  }
}
```

When omitted, the segment advances on player interaction (the default). When `mode` is `"timer"`, the segment auto-advances after the specified `seconds`.

## Starting Dialogue

The old authored `run_dialogue` path and the later `start_dialogue_session` / `dialogue_*` / text-session commands are removed. They are not part of the active command surface anymore.

Recommended new pattern:

1. call `open_dialogue_session`
2. let the engine-owned dialogue runtime load the dialogue JSON
3. let the runtime own session state, paging, choice selection, timer advance, and modal input behavior
4. let dialogue content plus hooks decide what commands actually run
5. if one engine-owned dialogue opens another, the parent session is suspended and resumes when the child closes

Example caller command:

```json
{
  "type": "open_dialogue_session",
  "dialogue_path": "dialogues/showcase/runtime_menu.json",
  "dialogue_on_start": [],
  "dialogue_on_end": [],
  "segment_hooks": [],
  "allow_cancel": true,
  "entity_refs": {
    "instigator": "$ref_ids.instigator",
    "caller": "$self_id"
  }
}
```

The engine-owned runtime currently expects:

- named dialogue UI presets under `shared_variables.dialogue_ui`
- ordinary dialogue JSON files, usually under `dialogues/`
- one common `segments` array in each dialogue file
- choice layout rules inside the chosen preset, including `choices.mode`
  (`inline` or `separate_panel`) and `choices.overflow` such as `marquee`

Older controller-owned pattern:

1. call `run_entity_command` on the dialogue controller entity
2. let that entity command load JSON dialogue data and store the session state on the controller entity
3. let controller-owned project commands redraw the UI and react to later input

Detailed lifecycle for the older controller-owned pattern:

1. when opening an outermost session, the controller borrows the needed logical inputs through `push_input_routes` and `route_inputs_to_entity`
2. the controller loads ordinary JSON dialogue data into entity variables and resets its current segment/page/choice state
3. caller-supplied `dialogue_on_start` commands run with those borrowed routes already in place
4. controller-owned commands derive visible text/options and render them through the screen manager
5. controller input routes to normal entity commands like `interact`, `move_up`, `move_down`, and `menu`
6. nested dialogue/menu state is saved into the controller's `dialogue_state_stack` when another dialogue opens on top of the current one
7. when the controller finally closes its outermost dialogue, it restores the borrowed routes through `pop_input_routes`
8. authored `dialogue_on_end` commands can then safely run post-close behavior such as `save_game`, `load_game`, `new_game`, or `quit_game`

Practical rule:

- use `dialogue_on_start` for setup that should happen after the controller borrows input
- use `dialogue_on_end` for behavior that should happen after the controller restores input
- do not rely on implicit engine magic for interaction ownership; pass any needed `entity_refs` explicitly
- modal controllers should use `push_input_routes` / `pop_input_routes`

Controller-path example caller command:

```json
{
  "type": "run_entity_command",
  "entity_id": "dialogue_controller",
  "command_id": "open_dialogue",
  "dialogue_path": "dialogues/system/pause_menu.json",
  "dialogue_on_start": [
    {
      "type": "set_entity_var",
      "entity_id": "$self_id",
      "name": "pending_pause_menu_action",
      "value": ""
    }
  ],
  "dialogue_on_end": [
    {
      "type": "if",
      "left": {
        "$entity_var": {
          "entity_id": "$self_id",
          "name": "pending_pause_menu_action"
        }
      },
      "op": "eq",
      "right": "load",
      "then": [
        {
          "type": "load_game"
        }
      ]
    },
    {
      "type": "if",
      "left": {
        "$entity_var": {
          "entity_id": "$self_id",
          "name": "pending_pause_menu_action"
        }
      },
      "op": "eq",
      "right": "exit",
      "then": [
        {
          "type": "quit_game"
        }
      ]
    }
  ],
  "segment_hooks": [
    {
      "option_commands_by_id": {
        "continue": [
          {
            "type": "run_project_command",
            "command_id": "commands/dialogue/close_current_dialogue"
          }
        ],
        "load": [
          {
            "type": "set_entity_var",
            "entity_id": "$self_id",
            "name": "pending_pause_menu_action",
            "value": "load"
          },
          {
            "type": "run_project_command",
            "command_id": "commands/dialogue/close_current_dialogue"
          }
        ],
        "exit": [
          {
            "type": "set_entity_var",
            "entity_id": "$self_id",
            "name": "pending_pause_menu_action",
            "value": "exit"
          },
          {
            "type": "run_project_command",
            "command_id": "commands/dialogue/close_current_dialogue"
          }
        ]
      }
    }
  ],
  "allow_cancel": true,
  "entity_refs": {
    "instigator": "$self_id",
    "caller": "$self_id"
  }
}
```

### Segment hooks

Each `segment_hooks` entry matches one dialogue segment by index.

They are used by the older controller-owned path today, and they are also the
current caller-hook surface for the newer engine-owned `open_dialogue_session`
runtime.

A hook object can define:

- `on_start`
- `on_end`
- `option_commands_by_id`
- `option_commands`

Use `option_commands_by_id` when your choice options have stable `option_id` values.

Practical note:

- inline option `commands` are often the simplest choice when one menu option should immediately queue a built-in action like `new_game`, `load_game`, or `quit_game`
- use `dialogue_on_end` when you specifically need one shared post-close path or cleanup that should only run after the dialogue session fully closes
- use `option_commands_by_id` / `option_commands` when the caller needs to override or augment the option behavior from outside the dialogue JSON

If an option should launch another dialogue immediately instead of closing, you can still do that directly in the option commands. When you need to preserve cross-entity context, pass named `entity_refs` explicitly at the call site.

Generic per-command lifecycle wrapper fields are removed from the active command model:

- removed: command-level `on_start`
- removed: command-level `on_end`
- use the surrounding sequential `commands: [...]` body when later commands should wait for earlier ones
- use `run_commands` when the next command chain is stored in a variable or passed as raw data
- use `run_parallel` when a grouped set of child commands should start together and the group should complete by an explicit rule
- use `spawn_flow` when work should start and the current sequence should continue immediately

Scheduling model:

- top-level command flows run independently by default
- any `commands: [...]` body runs in order by default
- `run_commands` is the explicit executor for a stored command-list value
- `run_parallel` is the explicit grouped parallel composition command
- `spawn_flow` is the explicit fire-and-forget flow spawner

`run_parallel` completion modes:

- default / omitted: wait for all children
- `{"mode": "any", "remaining": "keep_running"}`: continue when any child finishes and let the others keep running
- `{"mode": "child", "child_id": "move", "remaining": "keep_running"}`: continue when the named child finishes and let the others keep running

`run_parallel` child commands may include an optional top-level `id` field when you want `completion.mode = "child"` to target one specific child.

Generic tile-query value sources are also available for explicit spatial lookup:

- `{"$entity_ref": {"entity_id": "$self_id", "select": {...}, "default": null}}`
- `{"$entities_at": {"x": ..., "y": ..., "where": {...}, "select": {...}}}`
- `{"$entity_at": {"x": ..., "y": ..., "index": 0, "where": {...}, "select": {...}, "default": null}}`
- `{"$entities_query": {"where": {...}, "select": {...}}}`
- `{"$entity_query": {"where": {...}, "index": 0, "select": {...}, "default": null}}`
- `{"$sum": [base_x, delta_x]}`

`$entity_ref` returns one selected plain runtime snapshot for an explicit entity id.
`$entities_at` returns a stable list of selected plain entity refs for that tile.
`$entity_at` returns one selected ref from the same stable ordering, including negative indexes such as `-1` for the last item.
`$entities_query` returns a stable list of selected plain entity refs from one filtered world scan.
`$entity_query` returns one selected ref from the same stable query ordering.
`$sum` is a small numeric helper for explicit authored coordinate math.

Current entity-query helpers all require a `select` block. Example:

```json
{
  "$entity_at": {
    "x": "$self.target_x",
    "y": "$self.target_y",
    "index": 0,
    "select": {
      "fields": ["entity_id", "kind", "solid", "pushable"]
    },
    "default": null
  }
}
```

That returns plain selected data such as:

```json
{
  "entity_id": "box_1",
  "kind": "block",
  "solid": true,
  "pushable": true
}
```

Entity queries now also support an optional `where` block for broad lookups by stable engine fields:

- `kind` or `kinds`
- `tags_any` or `tags_all`
- `space`
- `scope`
- `present`
- `visible`
- `entity_commands_enabled`

Different `where` keys combine with implicit `AND`. Multi-result query helpers return matches in stable runtime order:

1. `render_order`
2. `stack_order`
3. `entity_id`

Example broad query:

```json
{
  "type": "set_entity_var",
  "entity_id": "$self_id",
  "name": "all_levers",
  "value": {
    "$entities_query": {
      "where": {
        "kind": "lever_toggle",
        "scope": "area",
        "present": true
      },
      "select": {
        "fields": ["entity_id", "grid_x", "grid_y"],
        "variables": ["toggled"]
      }
    }
  }
}
```

Use `where` on `$entity_at` or `$entities_at` when you want one tile query to target only certain occupants:

```json
{
  "$entity_at": {
    "x": "$self.target_x",
    "y": "$self.target_y",
    "index": 0,
    "where": {
      "kind": "door"
    },
    "select": {
      "fields": ["entity_id"],
      "variables": ["locked"]
    },
    "default": null
  }
}
```

## Common Authored Patterns

These patterns are worth copying when building new JSON behavior.

### Standard Movement And Collision

The engine now provides a standard grid-physics contract so projects do not
have to rebuild common movement and push logic in JSON by default.

The standard contract uses:

- cell `blocked`
- entity `solid`
- entity `pushable`
- entity `weight`
- entity `push_strength`
- entity `facing`

A typical simple player flow is now:

1. The player entity's `input_map` maps `move_up` to `move_up`.
2. That entity command calls `move_in_direction`.
3. The engine:
   - resolves the actor's facing
   - checks the target cell's `blocked`
   - checks for `solid` blockers
   - optionally attempts one standard push if the actor has enough `push_strength`
   - starts the movement interpolation if the step succeeds

Minimal player `move_up` entity command:

```json
"move_up": {
  "enabled": true,
  "commands": [
    {
      "type": "move_in_direction",
      "entity_id": "$self_id",
      "direction": "up",
      "frames_needed": "$project.movement.ticks_per_tile",
      "wait": false
    }
  ]
}
```

If you want a bump reaction, author `on_blocked` on the mover:

```json
"on_blocked": {
  "enabled": true,
  "commands": [
    {
      "type": "play_audio",
      "path": "assets/project/sfx/bump.wav"
    }
  ]
}
```

If you want the stationary entity to react when something enters or leaves its
tile, author `on_occupant_enter` / `on_occupant_leave` on that entity:

```json
"on_occupant_enter": {
  "enabled": true,
  "commands": [
    {
      "type": "set_entity_field",
      "entity_id": "indicator_light",
      "field_name": "visible",
      "value": true
    }
  ]
},
"on_occupant_leave": {
  "enabled": true,
  "commands": [
    {
      "type": "set_entity_var",
      "entity_id": "$self_id",
      "name": "remaining_occupants",
      "value": {
        "$entities_at": {
          "x": "$from_x",
          "y": "$from_y",
          "exclude_entity_id": "$self_id",
          "select": {
            "fields": ["entity_id"]
          }
        }
      }
    }
  ]
}
```

These occupancy hooks run on the stationary entity, receive the moving entity as
`$ref_ids.instigator`, and expose transition coordinates through runtime params
such as `$from_x`, `$from_y`, `$to_x`, and `$to_y`.

Lower-level authored movement flows are still valid. You can still build custom
movement manually with `$cell_flags_at`, `$entities_at`, `set_entity_grid_position`,
`move_entity_world_position`, and your own puzzle-specific rules. The standard
engine helpers are just the recommended default for ordinary grid movement.

### Standard Facing Interaction

The engine also now provides `interact_facing`.

That command:

- uses the actor's top-level `facing`
- checks the adjacent tile
- filters to world-space entities with `interactable: true`
- chooses the target by `interaction_priority`
- dispatches that target's normal authored `interact` command

Minimal example:

```json
"interact": {
  "enabled": true,
  "commands": [
    {
      "type": "interact_facing",
      "entity_id": "$self_id"
    }
  ]
}
```

### Query Current Position Explicitly

Use `"$entity_ref"` with `select.fields` when a command needs current runtime position fields:

```json
{
  "type": "set_entity_var",
  "entity_id": "$self_id",
  "name": "move_self_position",
  "value": {
    "$entity_ref": {
      "entity_id": "$self_id",
      "select": {
        "fields": ["grid_x", "grid_y", "pixel_x", "pixel_y"]
      },
      "default": null
    }
  }
}
```

Use this when the command needs a stable snapshot of current position data during one authored decision flow.

### Query Tile Occupants Without Copying Whole Entities

Use `"$entities_at"` / `"$entity_at"` for one tile, and `"$entities_query"` / `"$entity_query"` for broader world scans. Keep the `select` narrow:

```json
{
  "type": "set_entity_var",
  "entity_id": "$self_id",
  "name": "move_target_entities",
  "value": {
    "$entities_at": {
      "x": "$self.move_target_x",
      "y": "$self.move_target_y",
      "exclude_entity_id": "$self_id",
      "select": {
        "fields": ["entity_id", "solid", "pushable"]
      }
    }
  }
}
```

That keeps authored queries explicit while avoiding broad full-entity snapshots.

### Keep Primitive Movement Small

For simple movement execution, prefer relative primitives over manually computing absolute end coordinates:

```json
{
  "type": "set_entity_grid_position",
  "entity_id": "$self_id",
  "x": "$offset_x",
  "y": "$offset_y",
  "mode": "relative"
}
```

```json
{
  "type": "move_entity_world_position",
  "entity_id": "$self_id",
  "x": {
    "$product": [
      "$offset_x",
      "$area.tile_size"
    ]
  },
  "y": {
    "$product": [
      "$offset_y",
      "$area.tile_size"
    ]
  },
  "mode": "relative",
  "frames_needed": "$frames_needed",
  "wait": false
}
```

The high-level decision logic can stay in JSON without forcing every movement command to manually reconstruct the entity's absolute target position.

When you do use interpolated movement commands directly, timing precedence is:

1. `frames_needed`
2. `duration`
3. `speed_px_per_second`
4. engine default fallback

So if you need exact authored tile cadence, prefer `frames_needed`.

### Use Small Boolean And Random Helpers

The value-source layer now includes small helpers for readable authored logic:

- `$and`
- `$or`
- `$not`
- `$random_int`
- `$random_choice`

Examples:

```json
{
  "type": "set_current_area_var",
  "name": "both_switches_active",
  "value": {
    "$and": [
      "$entity.switch_a.active",
      "$entity.switch_b.active"
    ]
  }
}
```

```json
{
  "type": "set_entity_var",
  "entity_id": "$self_id",
  "name": "wander_direction",
  "value": {
    "$random_choice": {
      "value": ["up", "down", "left", "right"],
      "default": "down"
    }
  }
}
```

```json
{
  "type": "set_current_area_var",
  "name": "loot_roll",
  "value": {
    "$random_int": {
      "min": 1,
      "max": 100
    }
  }
}
```

### Treat Dialogue As Session State

There are now two valid dialogue models:

1. the newer engine-owned session runtime opened through
   `open_dialogue_session`
2. the older controller-owned path still used by the older sample projects

For new content, prefer the engine-owned runtime when:

- you want a standard modal dialogue or menu
- you want engine-owned paging, choice selection, timer advance, and cancel
  behavior
- you want dialogue UI presets from `shared_variables.json`

The older controller-owned path is still useful when:

- you are working in an older authored project that already uses it heavily
- you want to keep the dialogue flow explicitly authored in project commands

That means dialogue/menu logic can currently be built from either:

- engine-owned sessions plus ordinary JSON dialogue data
- controller entities plus ordinary JSON dialogue data and controller-owned
  project commands

## Area Transfers

`change_area` and `new_game` now support transfer-aware payloads.

Common fields:

- `area_id`
- `entry_id`
- `destination_entity_id`
- `transfer_entity_id`
- `transfer_entity_ids`
- `camera_follow`

Preferred current example using a destination marker entity:

```json
{
  "type": "change_area",
  "area_id": "$target_area",
  "destination_entity_id": "$target_marker",
  "transfer_entity_ids": ["actor"],
  "camera_follow": {
    "mode": "entity",
    "entity_id": "actor"
  }
}
```

Rules:

- use `destination_entity_id` to land on a destination marker entity in the
  target area
- `entry_id` remains supported for older authored content
- use `transfer_entity_ids` when the live entity itself should travel to the new area
- `camera_follow.mode` can be `entity`, `input_target`, or `none`
- `camera_follow.entity_id` supports symbolic `self` / `actor` / `caller` in these high-level transition commands
- transferred entities are tracked as session travelers:
  - a transferred entity keeps one live identity across areas
  - its authored origin placeholder is suppressed while it is away
  - re-entering the origin area does not duplicate it
  - save/load restores the traveler in its current area

A note on travelers: "traveler" is runtime state, not an authored entity type. There is no `"traveler": true` field in JSON. Any live area-scoped entity can become a traveler when it is named in `transfer_entity_ids` during a `change_area`. The engine then tracks that entity's current area for the rest of the session. Only `scope: "area"` entities can be transferred — global entities are already present everywhere and cannot be moved this way.

This is different from global entities. Global entities are project-level and always present in the active world — they don't physically move between areas. A traveler is an entity that was in one area and has been relocated to another; it exists in exactly one area at a time. If you don't include an entity in `transfer_entity_ids`, it simply stays behind in the area it was in.

Recommended marker pattern:

- create one invisible destination marker entity in the destination area
- give that marker a stable authored entity id
- have the transition trigger use `destination_entity_id` to target it

Marker template example:

```json
{
  "kind": "area_transition_target",
  "solid": false,
  "visible": false,
  "interactable": false,
  "facing": "down"
}
```

Transition trigger example:

```json
{
  "kind": "area_transition",
  "solid": false,
  "visible": false,
  "interactable": false,
  "variables": {
    "target_area": "areas/start",
    "destination_entity_id": "spawn_marker"
  },
  "entity_commands": {
    "on_occupant_enter": {
      "enabled": true,
      "commands": [
        {
          "type": "change_area",
          "area_id": "$self.target_area",
          "destination_entity_id": "$self.destination_entity_id",
          "transfer_entity_ids": [
            "$ref_ids.instigator"
          ]
        }
      ]
    }
  }
}
```

## Camera Control

Camera behavior is explicit runtime state controlled by commands.

Useful commands:

- `set_camera_follow`
- `set_camera_state`
- `push_camera_state`
- `pop_camera_state`
- `set_camera_bounds`
- `set_camera_deadzone`
- `move_camera`
- `teleport_camera`

`set_camera_follow` uses one structured follow object, and that object must declare `mode` explicitly. `set_camera_state` updates `follow`, `bounds`, and `deadzone` atomically; omitted sections stay unchanged, and explicit `null` clears that section. `set_camera_bounds` uses `space: "world_pixel"` or `space: "world_grid"`. `set_camera_deadzone` uses `space: "viewport_pixel"` or `space: "viewport_grid"`. `move_camera` and `teleport_camera` use `space: "world_pixel"` or `space: "world_grid"` plus `mode: "absolute"` or `mode: "relative"`. To read camera state, use runtime tokens like `$camera.x`, `$camera.follow.entity_id`, `$camera.bounds`, or `$camera.has_bounds` with normal explicit variable commands.

Example:

```json
{
  "commands": [
    {
      "type": "set_camera_follow",
      "follow": {
        "mode": "entity",
        "entity_id": "$self_id",
        "offset_x": 0,
        "offset_y": -8
      }
    },
    {
      "type": "set_camera_deadzone",
      "x": 4,
      "y": 3,
      "width": 8,
      "height": 6,
      "space": "viewport_grid"
    }
  ]
}
```

That pattern is useful when you want the camera to follow an entity normally, but still allow a small amount of movement inside a deadzone before the camera starts shifting.

## Persistence Notes

If you want a gameplay change to survive save/load, you now have two layers:

- authored entity/template persistence defaults
- command-level `persistent: true` / `persistent: false` overrides

Terms:

- `persistent`
  - the command writes a change into the saved runtime state, so the change survives save/load and room reloads
- `transient`
  - the change only affects the current live session and disappears when the runtime state is rebuilt or the game is reloaded

Entity/template default:

```json
"persistence": {
  "entity_state": true,
  "variables": {
    "shake_timer": false,
    "times_pushed": true
  }
}
```

Meaning:

- `entity_state: true`
  - entity-targeted mutation commands save by default
- `variables.<name>`
  - overrides the default for one specific variable name

Command behavior:

- explicit `persistent: true`
  - force-save the change
- explicit `persistent: false`
  - force the change to stay transient
- omitted `persistent` on entity-targeted mutation commands
  - inherit from the entity/template `persistence` policy
- omitted `persistent` on movement and inventory mutation commands
  - also inherit from the entity/template `persistence` policy
- omitted `persistent` on current-area variable commands
  - still means transient

Area-change rule:

- exact save/load of the currently active area preserves the full live snapshot
- transient entity/traveler state is dropped when the active area changes
- if you need to clear transient state earlier, `reset_transient_state` can now
  target one entity directly with `entity_id` / `entity_ids`

Good examples:

- lever or puzzle progress flags such as `toggled`, `opened`, or `boss_defeated`
  - usually persistent
- temporary controller/UI helpers such as `dialogue_open`, `selected_index`, or scratch movement vars
  - usually transient

Avoid mixing the same variable between persistent and transient writes unless you are doing it intentionally and understand the consequences. Variable-specific persistence overrides can help make that intent explicit.

Common examples:

- `set_current_area_var` with `persistent: true`
- `set_entity_var` with `persistent: true`
- `set_entity_field` with `persistent: true`
- `set_entity_fields` with `persistent: true`
- or an entity/template with `persistence.entity_state: true` so those commands can omit `persistent`

`set_current_area_var` is the current authored surface for live area/runtime state. Use it for room/session flags such as opened chests, current puzzle state, or temporary controller state that belongs to the current play session rather than one specific entity.

A lever/gate puzzle typically uses both: `set_entity_var` or `toggle_entity_var` to remember whether the lever is toggled, and `set_entity_field` or `set_entity_fields` to update the gate's runtime presentation/state. You can still force persistence per command, but if the lever/gate entities already author the right `persistence` defaults, those commands can omit `persistent` cleanly.

`set_entity_fields` is the structured bulk-mutation form. It lets one command update top-level entity fields, ordinary entity variables, and one or more visuals together:

```json
{
  "type": "set_entity_fields",
  "entity_id": "$ref_ids.caller",
  "set": {
    "fields": {
      "visible": true
    },
    "variables": {
      "toggled": false
    },
    "visuals": {
      "main": {
        "offset_y": -1,
        "animation_fps": 8
      }
    }
  },
  "persistent": true
}
```

The command validates the full `set` payload before applying any changes, so invalid visual or field names do not partially mutate the entity.

If you only need one runtime field, `set_entity_field` still works for focused updates. Its visual form now supports `visuals.<visual_id>.flip_x`, `visible`, `current_frame`, `tint`, `offset_x`, `offset_y`, and `animation_fps`.

Cross-area state uses a different surface:

- `set_area_var`
- `set_area_entity_var`
- `set_area_entity_field`

These commands are always persistent. They edit the target area's saved/authored state by `area_id`; they do not run live command chains in unloaded rooms. If the target `area_id` is the area currently loaded right now, the engine also mirrors the change into the live runtime when possible.

Example:

```json
{
  "type": "set_area_entity_var",
  "area_id": "dungeon/room_b",
  "entity_id": "gate_1",
  "name": "opened",
  "value": true
}
```

For cross-area reads, use `$area_entity_ref`. First-pass semantics are intentionally simple: it reads the target area's own authored entities plus that area's persistent overrides. It does not layer in globals or travelers.

```json
{
  "$area_entity_ref": {
    "area_id": "dungeon/room_b",
    "entity_id": "gate_1",
    "select": {
      "fields": ["entity_id", "visible"],
      "variables": ["opened"]
    },
    "default": null
  }
}
```

## Audio Notes

Treat one-shot sounds and background music as separate tools:

- use `play_audio` for one-shot sound effects
- use `play_music` for the current background track
- use `set_sound_volume` for future sound effects
- use `set_music_volume` for the dedicated music channel

Practical rule:

- area `enter_commands` can safely call `play_music` for that area's track
- by default, `play_music` does not restart the same already-playing track
- use `restart_if_same: true` only when you intentionally want a restart

Example area hook:

```json
{
  "type": "play_music",
  "path": "assets/project/music/village_square.ogg"
}
```

Example pause/menu behavior:

```json
[
  { "type": "pause_music" },
  { "type": "resume_music" }
]
```
