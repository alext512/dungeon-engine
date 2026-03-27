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
    }
  ],
  "startup_area": "title_screen",
  "input_targets": {
    "menu": "pause_controller"
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
  "solid": true,
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
- `solid`
- `pushable`
- `present`
- `visible`
- `layer`
- `stack_order`
- `variables`
- `input_map`
- `events`

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

## Named Commands

Named commands are reusable command chains stored in separate files.

Example:

```json
{
  "params": ["direction", "frames_needed"],
  "commands": [
    {
      "type": "move_entity_one_tile",
      "entity_id": "self",
      "direction": "$direction",
      "frames_needed": "$frames_needed"
    }
  ]
}
```

Notes:

- named-command ids are path-derived from file location
- do not author a top-level `id`
- use `run_named_command` to call them

## Runtime References and Tokens

Commands often need to refer to the current entity or interaction initiator.

### Special `entity_id` values

Use these in commands that accept `entity_id`:

- `self`
- `actor`
- `caller`

Meaning:

- `self`: the entity that owns the current event
- `actor`: the entity that initiated the current input or interaction flow
- `caller`: a caller explicitly forwarded by another command chain

### Tokens

The command runner also resolves tokens such as:

- `$self_id`
- `$actor_id`
- `$caller_id`
- `$self.some_value`
- `$actor.some_value`
- `$caller.some_value`
- `$project.some.path`
- `$world.some_value`

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

For the strict primitive entity-target commands, use explicit ids or resolved tokens such as `$self_id`, `$actor_id`, and `$caller_id` rather than symbolic `self` / `actor` / `caller` strings. This includes the explicit variable primitives plus strict entity/input, camera, movement, and visual/animation primitives such as `set_entity_field`, `set_event_enabled`, `set_input_target`, `route_inputs_to_entity`, `set_camera_follow_entity`, `set_facing`, `move_entity_one_tile`, `move_entity`, `teleport_entity`, `wait_for_move`, `play_animation`, `wait_for_animation`, `stop_animation`, `set_visual_frame`, and `set_visual_flip_x`.

## Ordinary JSON Dialogue Data

The sample project keeps dialogue/menu definitions under `dialogues/`, but that folder is only a convention. These files are ordinary JSON data loaded by controller commands through explicit variable writes with value sources such as `{"$json_file": "dialogues/system/pause_menu.json"}`.

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
  Optional portrait/name map.
- `segments`
  Required list of `text` and `choice` segments.
- `font_id`
  Optional font override.
- `max_lines`
  Optional per-dialogue page height override.
- `text_color`
  Optional RGB color override.

### Segment fields

- `type`
- `text`
- `pages`
- `options`
- `speaker_id`
- `show_portrait`
- `advance_mode`
- `advance_seconds`

## Starting Dialogue

The old authored `run_dialogue` path and the later `start_dialogue_session` / `dialogue_*` / text-session commands are removed. Startup validation rejects them before launch.

Current pattern:

1. call `run_event` on the dialogue controller entity
2. let that event load JSON dialogue data and store the session state on the controller entity
3. let controller-owned named commands redraw the UI and react to later input

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
- use `run_commands` when later commands should wait for an earlier long-running command to finish
- use `run_detached_commands` when work should overlap in the background

Generic tile-query value sources are also available for explicit spatial lookup:

- `{"$entity_ref": {"entity_id": "$self_id"}}`
- `{"$entities_at": {"x": ..., "y": ...}}`
- `{"$entity_at": {"x": ..., "y": ..., "index": 0, "default": null}}`
- `{"$sum": [base_x, delta_x]}`

`$entity_ref` returns one plain runtime snapshot for an explicit entity id.
`$entities_at` returns a stable list of plain entity refs for that tile.
`$entity_at` returns one selected ref from the same stable ordering, including negative indexes such as `-1` for the last item.
`$sum` is a small numeric helper for explicit authored coordinate math.

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
- transferred entities persist as travelers and do not duplicate on re-entry

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

The sample lever/gate puzzle uses both.

## Recommended Reading Order

If you want a concrete example project, inspect these files next:

1. `projects/test_project/project.json`
2. `projects/test_project/areas/title_screen.json`
3. `projects/test_project/entity_templates/dialogue_panel.json`
4. `projects/test_project/entity_templates/player.json`
5. `projects/test_project/entity_templates/sign.json`
6. `projects/test_project/entity_templates/lever_toggle.json`
7. `projects/test_project/dialogues/system/title_menu.json`
8. `projects/test_project/dialogues/system/save_prompt.json`
