# Authoring Guide

## Purpose

This document explains how to build project content for the engine without reading the Python code first.

It focuses on:

- `project.json`
- `shared_variables.json`
- area JSON
- entity template JSON
- named command JSON
- dialogue JSON
- the current controller-owned dialogue/menu pattern

Use this guide for authoring patterns. Use `ENGINE_JSON_INTERFACE.md` when you need the exact current command/value-source surface.

## Mental Model

The engine is built from a few content layers:

1. `project.json`
2. `shared_variables.json`
3. `areas/*.json`
4. `entity_templates/*.json`
5. `named_commands/*.json`
6. ordinary project JSON data such as `dialogues/*.json`

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
|-- points to named_commands/
|-- points to assets/
|-- points to shared_variables.json
`-- instantiates global_entities

areas
|-- place entity instances
|-- define entry_points and camera defaults
|-- call commands from enter hooks
`-- override input-target defaults

entity templates
|-- define visuals, events, input maps, variables
|-- call named commands
`-- call controller events to start dialogues

ordinary JSON data
`-- provide reusable dialogue/menu content or any other project-specific payloads

named commands
`-- provide reusable behavior chains
```

## A Minimal Project

Typical layout:

```text
my_project/
    project.json
    shared_variables.json
    areas/
    entity_templates/
    named_commands/
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
  "named_command_paths": ["named_commands/"],
  "shared_variables_path": "shared_variables.json",
  "global_entities": [
    {
      "id": "dialogue_controller",
      "template": "dialogue_panel"
    },
    {
      "id": "pause_controller",
      "template": "pause_controller"
    },
    {
      "id": "debug_controller",
      "template": "debug_controller"
    }
  ],
  "startup_area": "title_screen",
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
- `named_command_paths`
  Folders containing reusable named command JSON files.
- `shared_variables_path`
  Project-wide shared variable file.
- `global_entities`
  Entity instances that should exist in every runtime world.
- `startup_area`
  Default area id to open when only the project is selected.
- `input_targets`
  Default routed entity per logical input action. Areas can override specific actions, and any action omitted by both the project and the area stays unrouted until runtime commands change it.
- `save_dir`
  Directory for save files. Defaults to `saves`.

## `shared_variables.json`

Use this for shared project values.

Good use cases:

- render resolution
- movement timing like `ticks_per_tile`
- dialogue layout defaults
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
  "dialogue": {
    "max_lines": 3
  }
}
```

Read these values with tokens such as:

- `$project.display.internal_width`
- `$project.movement.ticks_per_tile`
- `$project.dialogue.max_lines`

## Areas

An area file defines one room or screen.

Example structure:

```json
{
  "name": "Village Square",
  "tile_size": 16,
  "entry_points": {
    "startup": {
      "x": 8,
      "y": 8,
      "facing": "down"
    }
  },
  "camera": {
    "follow_entity_id": "player"
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

- `name`
  Human-readable area name.
- `tile_size`
  Tile size in pixels.
- `entry_points`
  Named destinations for `change_area` and `new_game`.
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
- do not author `player_id`; the engine now uses explicit input routing, transition payloads, and camera defaults instead
- project-level global entities belong in `project.json`, not inside `entities`
- area `camera` defaults are just initial runtime state; commands can replace them later
- area `entry_points` are the intended targets for transfers instead of hardcoded spawn assumptions

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
  "draw_above_entities": false,
  "grid": [
    [1, 1, 1, 1],
    [1, 2, 2, 1],
    [1, 1, 1, 1]
  ]
}
```

`cell_flags` uses the same `[row][col]` layout. `true` means walkable, `false` means blocked:

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
  "x": 4,
  "y": 2,
  "template": "lever_toggle",
  "parameters": {
    "target_gate": "gate"
  }
}
```

## Entity Templates

Entity templates define reusable gameplay objects.

Example:

```json
{
  "kind": "sign",
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
  "events": {
    "interact": {
      "enabled": true,
      "commands": [
        {
          "type": "run_event",
          "entity_id": "dialogue_controller",
          "event_id": "open_dialogue",
          "dialogue_path": "$dialogue_path",
          "dialogue_on_start": [],
          "dialogue_on_end": [],
          "segment_hooks": [],
          "allow_cancel": false,
          "actor_entity_id": "$actor_id",
          "caller_entity_id": "$self_id"
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
- `layer`
- `stack_order`
- `tags`
- `variables`
- `input_map`
- `events`

Gameplay flags such as `blocks_movement`, `pushable`, `toggled`, and project-specific state like `dialogue_path` should live under `variables`. Top-level `facing`, `solid`, and `pushable` fields are removed.

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

### `scope`

`scope` controls lifetime:

- `area`
  Normal area-local entity.
- `global`
  Project-level entity available in every runtime world.

In practice, author global service/controller entities in `project.json`.

### `input_map`

`input_map` lets an entity decide which event handles a logical action.

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
3. that routed entity's `input_map` decides which event to run for that action
4. if there is no mapping for that action, nothing is dispatched
5. the runner enqueues `run_event` on the routed entity

This is what allows dialogue controllers, menus, and other service entities to temporarily own only the inputs they need without a single active-entity focus model.

If an action is absent from both the project and the area routing maps, it is simply unrouted until a runtime command assigns it.

For modal flows, the intended pattern is:

1. `push_input_routes` to save the current routing
2. reroute the borrowed actions to the modal controller
3. later `pop_input_routes` to restore the exact previous routes

The route stack is runtime-only control state. It is not saved.

## Named Commands

Named commands are reusable command chains stored in separate files.

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

- named-command ids are path-derived from file location
- do not author a top-level `id`
- use `run_named_command` to call them

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

When one JSON command chain needs to call another JSON command file, use `run_named_command`:

```json
{
  "type": "run_named_command",
  "command_id": "walk_one_tile",
  "offset_x": 1,
  "offset_y": 0
}
```

In the called named command file, `$offset_x` and `$offset_y` resolve from those passed params.

This is a general rule: both `run_named_command` and `run_event` forward any extra fields on the command object into the called flow as runtime parameters. The called commands can then read those values with `$param_name` tokens. This is how the dialogue examples pass `dialogue_path`, `dialogue_on_start`, `segment_hooks`, and other caller-supplied data into the controller's event.

## Runtime References and Tokens

Commands often need to refer to the current entity or interaction initiator.

### Context Roles vs Strict Primitive IDs

These are the three runtime context roles:

- `self`
- `actor`
- `caller`

Meaning:

- `self`: the entity that owns the current event
- `actor`: the entity that initiated the current input or interaction flow
- `caller`: a caller explicitly forwarded by another command chain

Use the raw symbolic ids `self`, `actor`, and `caller` only in higher-level orchestration commands that explicitly support them.

For strict primitive commands, use resolved id tokens instead:

- `$self_id`
- `$actor_id`
- `$caller_id`

### Tokens

The command runner also resolves tokens such as:

- `$self_id`
- `$actor_id`
- `$caller_id`
- `$self.some_value`
- `$actor.some_value`
- `$caller.some_value`
- `$entity.<entity_id>.some_value`
- `$project.some.path`
- `$area.tile_size`
- `$camera.x`
- `$world.some_value`

`$self...`, `$actor...`, `$caller...`, and `$entity.<id>...` read entity `variables`, not built-in entity fields. Use `$entity_ref` with a `select` block when you need built-in fields like `grid_x` or `pixel_y`.

`$world...` reads the live world/runtime variable store for the active play session. In normal play, this is the same authored state surface that commands like `set_world_var`, `add_world_var`, `toggle_world_var`, and `check_world_var` operate on.

`$area...` exposes the current area's `tile_size`, `width`, `height`, `pixel_width`, `pixel_height`, and `name`.

`$camera...` exposes `x`, `y`, `follow_entity_id`, `follow_mode`, `follow_offset_x`, `follow_offset_y`, `bounds`, `has_bounds`, `deadzone`, and `has_deadzone`.

Example:

```json
{
  "type": "set_entity_var",
  "entity_id": "$caller_id",
  "name": "toggled",
  "value": true,
  "persistent": true
}
```

For strict primitive entity-target commands, use explicit ids or resolved tokens such as `$self_id`, `$actor_id`, and `$caller_id` rather than symbolic `self` / `actor` / `caller` strings. This includes the explicit variable primitives plus strict entity/input, camera, movement, and visual/animation primitives such as `set_entity_field`, `set_entity_fields`, `set_event_enabled`, `set_input_target`, `route_inputs_to_entity`, `set_camera_follow_entity`, `set_entity_grid_position`, `set_entity_world_position`, `set_entity_screen_position`, `move_entity_world_position`, `move_entity_screen_position`, `wait_for_move`, `play_animation`, `wait_for_animation`, `stop_animation`, `set_visual_frame`, and `set_visual_flip_x`.

## Ordinary JSON Dialogue Data

Dialogue/menu definitions are typically kept under `dialogues/`, but that folder is only a convention. These files are ordinary JSON data loaded by controller commands through explicit variable writes with value sources such as `{"$json_file": "dialogues/system/pause_menu.json"}`.

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

Current pattern:

1. call `run_event` on the dialogue controller entity
2. let that event load JSON dialogue data and store the session state on the controller entity
3. let controller-owned named commands redraw the UI and react to later input

Detailed lifecycle when a dialogue starts:

1. when opening an outermost session, the controller borrows the needed logical inputs through `push_input_routes` and `route_inputs_to_entity`
2. the controller loads ordinary JSON dialogue data into entity variables and resets its current segment/page/choice state
3. caller-supplied `dialogue_on_start` commands run with those borrowed routes already in place
4. controller-owned commands derive visible text/options and render them through the screen manager
5. controller input routes to normal entity events like `interact`, `move_up`, `move_down`, and `menu`
6. nested dialogue/menu state is saved into the controller's `dialogue_state_stack` when another dialogue opens on top of the current one
7. when the controller finally closes its outermost dialogue, it restores the borrowed routes through `pop_input_routes`
8. authored `dialogue_on_end` commands can then safely run post-close behavior such as `save_game`, `load_game`, `new_game`, or `quit_game`

Practical rule:

- use `dialogue_on_start` for setup that should happen after the controller borrows input
- use `dialogue_on_end` for behavior that should happen after the controller restores input
- do not rely on `actor` to restore input ownership
- modal controllers should use `push_input_routes` / `pop_input_routes`

Example caller command:

```json
{
  "type": "run_event",
  "entity_id": "dialogue_controller",
  "event_id": "open_dialogue",
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
      "type": "check_entity_var",
      "entity_id": "$self_id",
      "name": "pending_pause_menu_action",
      "op": "eq",
      "value": "load",
      "then": [
        {
          "type": "load_game"
        }
      ]
    },
    {
      "type": "check_entity_var",
      "entity_id": "$self_id",
      "name": "pending_pause_menu_action",
      "op": "eq",
      "value": "exit",
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
            "type": "run_named_command",
            "command_id": "dialogue/close_current_dialogue"
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
            "type": "run_named_command",
            "command_id": "dialogue/close_current_dialogue"
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
            "type": "run_named_command",
            "command_id": "dialogue/close_current_dialogue"
          }
        ]
      }
    }
  ],
  "allow_cancel": true,
  "actor_entity_id": "$self_id",
  "caller_entity_id": "$self_id"
}
```

### Segment hooks

Each `segment_hooks` entry matches one dialogue segment by index.

A hook object can define:

- `on_start`
- `on_end`
- `option_commands_by_id`
- `option_commands`

Use `option_commands_by_id` when your choice options have stable `option_id` values.

If an option should launch another dialogue immediately instead of closing, you can still do that directly in the option commands. Optional `actor_entity_id` and `caller_entity_id` parameters can be passed at the call site when you need to preserve or override semantic context across dialogue-to-dialogue calls.

Generic per-command lifecycle wrapper fields are removed from the active command model:

- removed: command-level `on_start`
- removed: command-level `on_end`
- use `run_sequence` when later commands should wait for an earlier long-running command to finish
- use `run_parallel` when a grouped set of child commands should start together and the group should complete by an explicit rule
- use `spawn_flow` when work should start and the current sequence should continue immediately

Scheduling model:

- top-level command flows run independently by default
- `run_sequence` is the explicit ordered composition command
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
      "fields": ["entity_id", "kind"],
      "variables": ["pushable", "blocks_movement"]
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
  "variables": {
    "pushable": true,
    "blocks_movement": true
  }
}
```

Entity queries now also support an optional `where` block for broad lookups by stable engine fields:

- `kind` or `kinds`
- `tags_any` or `tags_all`
- `space`
- `scope`
- `present`
- `visible`
- `events_enabled`

Different `where` keys combine with implicit `AND`. Multi-result query helpers return matches in stable runtime order:

1. `layer`
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

### Movement And Collision Are JSON-Authored

The engine does **not** automatically block movement against entities. It only provides tile walkability through `cell_flags`. Everything else — checking whether another entity blocks the target tile, pushing blocks, playing bump sounds — is authored in your project's named commands.

A typical movement flow:

1. The player entity's `input_map` maps `move_up` to a `move_up` event.
2. That event calls a named command like `attempt_move_one_tile` with the direction offset.
3. The named command:
   - computes the target tile using `$sum` with the current position and the offset
   - checks `$cell_flags_at` for walkability
   - checks `$entities_at` for entities with `blocks_movement: true`
   - if the tile is clear, calls `set_entity_grid_position` (instant grid update) and `move_entity_world_position` (smooth pixel animation)
   - if blocked, optionally plays a bump animation or pushes a pushable entity

Minimal player `move_up` event:

```json
"move_up": {
  "commands": [
    {
      "type": "run_named_command",
      "command_id": "attempt_move_one_tile",
      "direction": "up",
      "offset_x": 0,
      "offset_y": -1
    }
  ]
}
```

Gate-style blocking works the same way: a gate entity has `variables.blocks_movement: true`. The movement named command queries `$entities_at` at the target tile and finds the gate. When the lever toggles the gate, it sets `blocks_movement: false` and hides the gate visual, both with `persistent: true`.

This approach keeps all movement logic visible in your project's JSON instead of hidden inside the engine.

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
        "fields": ["entity_id"],
        "variables": ["blocks_movement", "pushable"]
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
  "type": "set_world_var",
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
  "type": "set_world_var",
  "name": "loot_roll",
  "value": {
    "$random_int": {
      "min": 1,
      "max": 100
    }
  }
}
```

### Treat Dialogue As Controller-Owned State

The current dialogue model is:

1. another entity sends an event to the dialogue controller
2. the controller loads dialogue JSON data
3. the controller stores session state on itself
4. controller-owned named commands redraw the screen-space UI and handle later input

That means dialogue/menu logic should usually be built by composing:

- one controller entity
- ordinary JSON dialogue data
- controller-owned named commands
- explicit `push_input_routes` / `pop_input_routes`
- explicit `dialogue_on_start` / `dialogue_on_end` hooks when callers need setup or cleanup

## Area Transfers

`change_area` and `new_game` now support transfer-aware payloads.

Common fields:

- `area_id`
- `entry_id`
- `transfer_entity_id`
- `transfer_entity_ids`
- `camera_follow_entity_id`
- `camera_follow_input_action`
- `camera_offset_x`
- `camera_offset_y`

Typical door example:

```json
{
  "type": "change_area",
  "area_id": "$target_area",
  "entry_id": "$target_entry",
  "transfer_entity_ids": ["actor"],
  "camera_follow_entity_id": "actor"
}
```

Rules:

- use `entry_id` to land on an authored area entry point
- use `transfer_entity_ids` when the live entity itself should travel to the new area
- use one camera follow field or the other, not both
- transferred entities are tracked as session travelers:
  - a transferred entity keeps one live identity across areas
  - its authored origin placeholder is suppressed while it is away
  - re-entering the origin area does not duplicate it
  - save/load restores the traveler in its current area

## Camera Control

Camera behavior is explicit runtime state controlled by commands.

Useful commands:

- `set_camera_follow_entity`
- `set_camera_follow_input_target`
- `clear_camera_follow`
- `set_camera_bounds_rect`
- `clear_camera_bounds`
- `set_camera_deadzone`
- `clear_camera_deadzone`
Follow commands support `offset_x` and `offset_y`. Bounds and deadzone commands accept `space: "pixel"` or `space: "grid"`. To read camera state, use runtime tokens like `$camera.x`, `$camera.follow_entity_id`, `$camera.bounds`, or `$camera.has_bounds` with normal explicit variable commands.

## Persistence Notes

If you want a gameplay change to survive save/load, use `persistent: true` on the relevant command when supported.

Common examples:

- `set_world_var` with `persistent: true`
- `set_entity_var` with `persistent: true`
- `set_entity_field` with `persistent: true`
- `set_entity_fields` with `persistent: true`

`set_world_var` is the current authored surface for live area/runtime state. Use it for room/session flags such as opened chests, current puzzle state, or temporary controller state that belongs to the current play session rather than one specific entity.

A lever/gate puzzle typically uses both: `set_entity_var` or `toggle_entity_var` with `persistent: true` to remember whether the lever is toggled, and `set_entity_field` or `set_entity_fields` with `persistent: true` to update the gate's runtime presentation/state.

`set_entity_fields` is the structured bulk-mutation form. It lets one command update top-level entity fields, ordinary entity variables, and one or more visuals together:

```json
{
  "type": "set_entity_fields",
  "entity_id": "$caller_id",
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
