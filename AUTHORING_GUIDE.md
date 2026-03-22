# Authoring Guide

## Purpose

This document explains how to use the engine as a content author.

It focuses on:

- project files
- room JSON
- entity JSON
- command JSON
- dialogue JSON
- shared variables

It does not require reading the Python code.

## Mental Model

The engine is built from a few content layers:

1. `project.json`
   Tells the engine where the project folders are.
2. `variables.json`
   Stores project-wide shared values.
3. `areas/*.json`
   Define rooms.
4. `entities/*.json`
   Define reusable entity templates.
5. `commands/*.json`
   Define reusable command chains.
6. `dialogues/*.json`
   Define reusable dialogue text.

Important clarification:

- these category names are meaningful
- the exact folder names are just conventions

The engine does not require literal folders named:

- `areas/`
- `entities/`
- `commands/`
- `dialogues/`
- `assets/`

What it really requires is:

- a valid `project.json`
- valid paths declared inside that manifest

The most important idea is:

- the engine provides primitive commands
- your project combines them into behavior using JSON

## A Minimal Project

Typical layout:

```text
my_project/
    project.json
    variables.json
    areas/
    entities/
    commands/
    dialogues/
    assets/
```

That layout is recommended, but it is not mandatory.

For example, this would also be valid if `project.json` points to it correctly:

```text
my_project/
    project.json
    config/
        shared_values.json
    content/
        rooms/
        objects/
        logic/
        text/
        assets/
```

## `project.json`

This is the project manifest.

Example:

```json
{
  "entity_paths": ["entities/"],
  "asset_paths": ["assets/"],
  "area_paths": ["areas/"],
  "command_paths": ["commands/"],
  "dialogue_paths": ["dialogues/"],
  "variables_path": "variables.json",
  "startup_area": "areas/test_room.json",
  "active_entity_id": "player",
  "debug_inspection_enabled": true,
  "input_events": {
    "move_up": "move_up",
    "move_down": "move_down",
    "move_left": "move_left",
    "move_right": "move_right",
    "interact": "interact"
  }
}
```

### Important fields

- `entity_paths`
  Folders containing entity templates.
- `asset_paths`
  Folders containing images, sounds, fonts, and tilesets.
- `area_paths`
  Folders containing room JSON files.
- `command_paths`
  Folders containing reusable named command JSON files.
- `dialogue_paths`
  Folders containing reusable dialogue JSON files.
- `variables_path`
  Project-wide shared variables file.
- `startup_area`
  Default room to open when only the project is selected.
- `active_entity_id`
  Which entity starts as the direct input receiver.
- `input_events`
  Which event names the engine looks for when input happens.

So the real rule is:

- the engine follows the paths declared in `project.json`
- not a fixed folder layout

## `variables.json`

Use this for shared project values.

Example:

```json
{
  "display": {
    "internal_width": 256,
    "internal_height": 192
  },
  "movement": {
    "_comment_ticks_per_tile": "Recommended to keep this even so the sprite change lands halfway through a tile move.",
    "ticks_per_tile": 16
  },
  "dialogue": {
    "panel_path": "assets/project/ui/dialogue_panel.png",
    "max_lines": 3,
    "plain_box": {
      "x": 8,
      "y": 154,
      "width": 240
    },
    "portrait_box": {
      "x": 56,
      "y": 154,
      "width": 192
    },
    "portrait_position": {
      "x": 8,
      "y": 154
    }
  }
}
```

### When to use shared variables

Good use cases:

- render resolution
- movement timing like `ticks_per_tile`
- dialogue layout values
- common tuning values used by multiple commands

Bad use cases:

- unique per-entity data that only one object needs
- temporary gameplay state
- per-instance puzzle values

## Areas

An area file defines one room.

Example structure:

```json
{
  "area_id": "test_room",
  "name": "Test Room",
  "tile_size": 16,
  "player_id": "player",
  "variables": {},
  "tilesets": [],
  "tile_layers": [],
  "cell_flags": [],
  "entities": []
}
```

### Important fields

- `area_id`
  Stable room id. Important for persistence.
- `name`
  Human-readable room name.
- `tile_size`
  Tile size in pixels.
- `player_id`
  Which entity is the player entity for that room.
- `variables`
  Room-level mutable variables.
- `tilesets`
  Tileset definitions used by this room.
- `tile_layers`
  Visual tile layers.
- `cell_flags`
  Walkability grid.
- `entities`
  Placed entity instances.

### Tilesets

Each tileset entry usually looks like:

```json
{
  "firstgid": 1,
  "path": "assets/project/tiles/basic_tiles.png",
  "tile_width": 16,
  "tile_height": 16
}
```

### Tile layers

Each visual layer has:

- `name`
- `draw_above_entities`
- `grid`

Example:

```json
{
  "name": "layer_1",
  "draw_above_entities": false,
  "grid": [
    [1, 1, 1],
    [1, 0, 1],
    [1, 1, 1]
  ]
}
```

Rules:

- `0` means empty
- nonzero values are GIDs from the room’s tileset list

### Walkability

`cell_flags` is a grid of booleans:

- `true` = walkable
- `false` = blocked

This is separate from visual tiles.

That means:

- a tile may exist without blocking movement
- a cell may block movement even if no visible tile is there

### Placed entities

Each room instance usually looks like:

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

Common fields:

- `id`
  Stable entity id inside the room.
- `x`, `y`
  Grid position.
- `template`
  Which entity template to instantiate.
- `parameters`
  Template parameter values.
- `pixel_x`, `pixel_y`
  Optional starting transform override.

## Entity Templates

Entity templates define reusable object types.

Example:

```json
{
  "kind": "sign",
  "solid": true,
  "sprite": {
    "path": "assets/project/sprites/sign.png",
    "frame_width": 16,
    "frame_height": 16,
    "frames": [0]
  },
  "events": {
    "interact": {
      "enabled": true,
      "commands": [
        {
          "type": "run_named_command",
          "command_id": "dialogue/sign_gate_hint"
        }
      ]
    }
  }
}
```

### Common entity fields

- `kind`
  Descriptive label for the entity type.
- `solid`
  Whether it blocks movement.
- `visible`
  Whether it is drawn.
- `present`
  Whether it exists in the current scene at all.
- `pushable`
  Whether it can be pushed by movement logic.
- `variables`
  Entity-local mutable variables.
- `sprite`
  Visual setup.
- `events`
  Named command chains.

### Sprite block

Example:

```json
{
  "path": "assets/project/sprites/npc_blue.png",
  "frame_width": 16,
  "frame_height": 16,
  "frames": [0]
}
```

Important note:

- command-driven animation usually controls the visible frame directly
- built-in sprite animation is still possible, but the sample player currently uses command-driven animation instead

### Variables

Use entity variables for:

- entity-local state
- toggles
- walk phase
- puzzle state that belongs to that entity

Example:

```json
"variables": {
  "walk_phase": 0
}
```

### Events

Events are named command chains owned by the entity.

Examples:

- `move_up`
- `move_down`
- `interact`
- `push_from_left`
- `push`

Each event usually looks like:

```json
"interact": {
  "enabled": true,
  "commands": [
    {
      "type": "run_named_command",
      "command_id": "dialogue/sign_gate_hint"
    }
  ]
}
```

## Named Commands

Reusable command chains live under `commands/`.

They are identified by path relative to the command root, without `.json`.

Examples:

- `walk_one_tile`
- `attempt_move_one_tile`
- `dialogue/blue_guide_open`

### Example named command

```json
{
  "id": "walk_one_tile",
  "params": [
    "direction",
    "phase_a_frames",
    "phase_b_frames",
    "idle_frame",
    "frames_per_sprite_change",
    "frames_needed"
  ],
  "commands": [
    {
      "type": "check_var",
      "scope": "entity",
      "entity_id": "self",
      "name": "walk_phase",
      "op": "eq",
      "value": 1,
      "then": [
        {
          "type": "play_animation",
          "entity_id": "self",
          "frame_sequence": "$phase_b_frames",
          "frames_per_sprite_change": "$frames_per_sprite_change",
          "wait": false
        }
      ],
      "else": [
        {
          "type": "play_animation",
          "entity_id": "self",
          "frame_sequence": "$phase_a_frames",
          "frames_per_sprite_change": "$frames_per_sprite_change",
          "wait": false
        }
      ]
    }
  ]
}
```

### Important rules

- command ids are path-based
- duplicate command ids are validation errors
- command files are meant for reusable behavior, not single-instance content

## Runtime Tokens

Commands can use `$...` tokens.

Common examples:

- `$direction`
- `$idle_frame`
- `$project.movement.ticks_per_tile`
- `$world.dialogue_choice_index`
- `$self.walk_phase`
- `$actor.some_value`

The special helper currently used in the sample project is:

- `$half:project.movement.ticks_per_tile`

That means:

- resolve the value
- divide by 2

## Dialogue Assets

Dialogue text lives under `dialogues/`.

Simple example:

```json
{
  "id": "signs/gate_hint",
  "text": "Sign: The old path is sealed. Pull the lever to open the gate."
}
```

Manual paging example:

```json
{
  "id": "npcs/example",
  "pages": [
    "Guide: First page.",
    "Guide: Second page."
  ]
}
```

Rules:

- use `text` for one long block that should be auto-paginated
- use `pages` when you want exact page boundaries
- do not define both

## `run_dialogue`

Current `run_dialogue` is text-only.

It:

- loads dialogue text
- wraps by pixel width
- paginates by `max_lines`
- advances when the action button is pressed

It does not:

- create the panel image
- create a portrait
- create choice UI

### Example

```json
{
  "type": "run_dialogue",
  "element_id": "dialogue_text",
  "dialogue_id": "signs/gate_hint",
  "x": "$project.dialogue.plain_box.x",
  "y": "$project.dialogue.plain_box.y",
  "max_width": "$project.dialogue.plain_box.width",
  "max_lines": "$project.dialogue.max_lines",
  "layer": 101
}
```

## Screen-Space Commands

Use these for dialogue panels, portraits, and overlays.

### Show an image

```json
{
  "type": "show_screen_image",
  "element_id": "dialogue_panel",
  "path": "$project.dialogue.panel_path",
  "x": 0,
  "y": "$project.display.internal_height",
  "anchor": "bottomleft",
  "layer": 100
}
```

### Show text

```json
{
  "type": "show_screen_text",
  "element_id": "dialogue_choice_0",
  "text": "- Tell me about the lever.",
  "x": "$project.dialogue.portrait_box.x",
  "y": "$project.dialogue.portrait_box.y",
  "layer": 101
}
```

### Remove an element

```json
{
  "type": "remove_screen_element",
  "element_id": "dialogue_panel"
}
```

## How The Sample Sign Works

The sign template:

- owns an `interact` event
- that event runs a named command

The named command:

1. shows the panel image
2. runs text-only `run_dialogue`
3. removes the text element
4. removes the panel image

So the dialogue presentation is authored in project commands, not hardcoded in
the engine.

## How The Sample NPC Dialogue Works

The blue NPC flow is slightly richer.

It does this:

1. show panel image
2. show portrait image
3. run the intro text with `run_dialogue`
4. remove the intro text
5. draw three choice lines with `show_screen_text`
6. set `dialogue_controller` as the active entity
7. let that controller handle `move_up`, `move_down`, and `interact`
8. redraw the choices whenever the selected index changes
9. run the selected follow-up dialogue
10. remove portrait/panel/text
11. restore the previous active entity

This is the current pattern for command-driven dialogue choices.

## Dialogue Controller Pattern

`dialogue_controller` is just a hidden entity template.

Its events do not own the dialogue directly. They dispatch to named commands.

That means:

- menu flow stays in JSON
- the engine does not need a special baked choice-menu subsystem

The controller currently also uses:

- `wait_for_direction_release`

so a held arrow does not keep scrolling through choices.

## Movement Authoring Pattern

The sample player does not duplicate full movement logic four times.

Current pattern:

- `move_up`, `move_down`, `move_left`, `move_right`
  only pass direction-specific data
- a shared `move` event calls the common movement command
- shared speed comes from `variables.json`

Example idea:

```json
{
  "type": "run_event",
  "entity_id": "self",
  "event_id": "move",
  "direction": "up",
  "phase_a_frames": [5, 2],
  "phase_b_frames": [8, 2],
  "idle_frame": 2
}
```

Then the common event handles:

- flipping
- movement timing
- calling `attempt_move_one_tile`

## Pushing Pattern

The block template owns directional push events:

- `push_from_left`
- `push_from_right`
- `push_from_up`
- `push_from_down`

Each one forwards into a shared `push` event that calls a named command.

This means:

- the actor delegates push behavior to the object in front
- the pushed object decides how to respond

This follows the spirit of the old Godot project.

## Common Commands You Will Use A Lot

Flow and state:

- `run_event`
- `run_named_command`
- `set_var`
- `increment_var`
- `check_var`
- `set_event_enabled`
- `set_active_entity`

Movement and animation:

- `set_facing`
- `move_entity_one_tile`
- `move_entity`
- `teleport_entity`
- `play_animation`
- `stop_animation`
- `set_sprite_frame`
- `wait_for_move`

Screen-space and dialogue:

- `show_screen_image`
- `show_screen_text`
- `set_screen_text`
- `remove_screen_element`
- `play_screen_animation`
- `run_dialogue`

Audio:

- `play_audio`

Lifecycle and presence:

- `set_present`
- `destroy_entity`
- `spawn_entity`

## Good Authoring Habits

- Keep shared tuning values in `variables.json`
- Keep reusable behavior in `commands/`
- Keep plain text content in `dialogues/`
- Keep room files focused on layout and placed instances
- Keep entity templates focused on reusable object behavior
- Prefer events and named commands over duplicating long inline chains

## Common Mistakes To Avoid

- putting large dialogue text directly into entity files when it belongs in `dialogues/`
- duplicating identical command chains in many entities instead of moving them to `commands/`
- storing one-off runtime state in `variables.json`
- treating room JSON as save data
- baking screen layout into the engine when it belongs in project commands

## Current Limits

Important current limitations:

- movement/render feel still needs a dedicated polish pass
- there is not yet a typewriter-style text reveal
- choice layout is still authored manually
- there is not yet a visual command-chain editor
- inventory/item systems are still planned
- editor-side parameter editing is still basic

## Recommended Reading Order For Authors

If you want to learn by example, read:

1. `projects/test_project/project.json`
2. `projects/test_project/variables.json`
3. `projects/test_project/areas/test_room.json`
4. `projects/test_project/entities/player.json`
5. `projects/test_project/entities/sign.json`
6. `projects/test_project/entities/npc_blue.json`
7. `projects/test_project/entities/dialogue_controller.json`
8. `projects/test_project/commands/attempt_move_one_tile.json`
9. `projects/test_project/commands/walk_one_tile.json`
10. `projects/test_project/commands/dialogue/`
11. `projects/test_project/dialogues/`
