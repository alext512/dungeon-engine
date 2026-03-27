# Content Types Reference

## Purpose

This document explains how the engine connects to project JSON files, which
content categories exist, and how they relate to one another in the current
runtime.

## Project Entry Point

Every project starts with a `project.json` manifest. It declares the search
roots the engine should use for each content category.

Example:

```json
{
  "entity_template_paths": ["entity_templates/"],
  "asset_paths": ["assets/"],
  "area_paths": ["areas/"],
  "named_command_paths": ["named_commands/"],
  "dialogue_paths": ["dialogues/"],
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
  ]
}
```

All paths are relative to the folder containing `project.json`.

## Fixed Keys, Flexible Folders

The engine expects these manifest keys:

| Key | What it configures |
|---|---|
| `entity_template_paths` | Where to find entity template JSON files |
| `area_paths` | Where to find area JSON files |
| `named_command_paths` | Where to find named command JSON files |
| `dialogue_paths` | Where to find dialogue JSON files |
| `asset_paths` | Where to find images, sounds, and fonts |
| `shared_variables_path` | The shared variable JSON file |
| `global_entities` | Project-level entity instances installed into every runtime world |

The keys are fixed, but the folders they point to are configurable.

## Path-Derived IDs

Areas, entity templates, named commands, and dialogues derive identity from
their file path under the configured search roots.

Examples if `named_command_paths` includes `named_commands/`:

| File path | Derived ID |
|---|---|
| `named_commands/push_one_tile.json` | `push_one_tile` |
| `named_commands/ui/title/open_menu.json` | `ui/title/open_menu` |

Rules:

- do not author top-level `id` fields for named commands or dialogues
- do not author `area_id` inside area files
- moving a file within a search root changes its id
- duplicate ids across search roots are reported at startup

## Content Overview

The current project model is easiest to understand as seven categories:

| Category | Config key | Path-derived ID | Purpose |
|---|---|---|---|
| Project manifest | n/a | n/a | Declares search roots and global project settings |
| Shared variables | `shared_variables_path` | n/a | Stores project-wide values used by commands |
| Areas | `area_paths` | Yes | Tilemaps, room variables, entry markers, placed entities, enter hooks |
| Entity templates | `entity_template_paths` | Yes | Reusable entity definitions |
| Named commands | `named_command_paths` | Yes | Reusable command chains |
| Dialogues | `dialogue_paths` | Yes | Reusable segmented text/choice definitions |
| Assets | `asset_paths` | Asset path string | PNGs, fonts, sounds, tilesets |

## Areas

### What They Are

An area is a playable map or screen containing:

- tile layers
- walkability data
- area variables
- placed area-local entities
- optional `entry_points`
- optional `camera` defaults
- optional `enter_commands`

Example:

```json
{
  "name": "Village Square",
  "tile_size": 16,
  "entry_points": {
    "startup": {
      "x": 8,
      "y": 8,
      "facing": "down"
    },
    "from_house": {
      "x": 8,
      "y": 6,
      "facing": "down"
    }
  },
  "camera": {
    "follow_entity_id": "player"
  },
  "input_targets": {
    "move_up": "player",
    "move_down": "player",
    "move_left": "player",
    "move_right": "player",
    "interact": "player"
  },
  "variables": {},
  "tilesets": [],
  "tile_layers": [],
  "cell_flags": [],
  "enter_commands": [],
  "entities": []
}
```

Important area rules:

- area ids are path-derived
- `entities` only store area-scoped instances
- project-level global entities do not live in area files
- `entry_points` are authored destinations for transfer-aware `change_area` and `new_game`
- `camera` stores initial camera runtime state for the area
- `input_targets` are area overrides layered on top of project defaults
- actions omitted by both project and area routing maps stay unrouted until runtime commands assign them
- authored areas must not declare `player_id`; control ownership and camera setup are fully explicit now

## Entity Templates

### What They Are

Entity templates define reusable runtime objects such as:

- players
- signs
- levers
- gates
- doors
- blocks
- UI/controller entities

### Current Entity Shape

Entity templates now center on:

- `visuals`
- `space`
- `scope`
- `variables`
- `input_map`
- `events`

Example:

```json
{
  "kind": "system",
  "space": "screen",
  "solid": false,
  "visible": false,
  "layer": 100,
  "input_map": {
    "interact": "interact",
    "menu": "menu",
    "move_up": "move_up",
    "move_down": "move_down"
  },
  "visuals": [
    {
      "id": "panel",
      "path": "assets/project/ui/dialogue_panel.png",
      "frame_width": 256,
      "frame_height": 44,
      "frames": [0],
      "visible": false,
      "offset_x": 0,
      "offset_y": 148,
      "draw_order": 0
    }
  ],
  "events": {
    "open_dialogue": {
      "enabled": true,
      "commands": [
        {
          "type": "start_dialogue_session",
          "dialogue_id": "$dialogue_id",
          "controller_entity_id": "self"
        }
      ]
    }
  }
}
```

Key entity rules:

- the old single `sprite` block is gone; author `visuals` instead
- `space: "world"` uses tile coordinates
- `space: "screen"` uses screen pixel coordinates
- `scope: "global"` is intended for project-level services such as controller entities
- global entities are usually instantiated from `project.json`, not area JSON

## Named Commands

Named commands are reusable command chains loaded from `named_command_paths`.

They are:

- indexed at startup
- stored in memory
- executed through `run_named_command`

Example:

```json
{
  "params": ["direction"],
  "commands": [
    {
      "type": "move_entity_one_tile",
      "entity_id": "self",
      "direction": "$direction"
    }
  ]
}
```

They are useful when:

- several entities share the same behavior
- a longer behavior should be split out of an event
- you want one stable, testable behavior id

## Dialogues

Dialogue files define reusable segmented text and choice flow. They do not
directly mutate gameplay state by themselves.

Top-level fields:

- `participants`
- `segments`
- `font_id`
- `max_lines`
- `text_color`

Segment fields:

- `type`
- `text`
- `pages`
- `options`
- `speaker_id`
- `show_portrait`
- `advance_mode`
- `advance_seconds`

The supported dialogue flow is:

1. send an event to a controller entity
2. that event calls `start_dialogue_session`
3. the caller passes optional `on_start`, `on_end`, and `segment_hooks`
4. the controller borrows its needed inputs through `push_input_routes`
5. the controller restores those routes through `pop_input_routes`
6. post-close behavior such as `save_game`, `load_game`, or `new_game` runs from `dialogue_on_end`

The old authored `run_dialogue` path is intentionally removed.

## Shared Variables

`shared_variables.json` is not path-derived content, but it is still a core
category in practice.

Use it for:

- display settings
- movement tuning
- dialogue defaults

It is read through `$project...` tokens at runtime.

## Assets

Assets are resolved by path string through the project's `asset_paths`.

Examples:

- `assets/project/sprites/sign.png`
- `assets/project/ui/dialogue_panel.png`
- `assets/project/tiles/showcase_tiles.png`

Assets are not assigned path-derived ids. Their authored identity is the asset
path string used by content.

## Runtime References Across Content

The categories connect through a few common references:

| Source | Refers to | Example |
|---|---|---|
| Area entity instance | Entity template id | `"template": "lever_toggle"` |
| Command | Named command id | `"command_id": "attempt_move_one_tile"` |
| Command | Dialogue id | `"dialogue_id": "system/pause_menu"` |
| Entity visual | Asset path | `"path": "assets/project/sprites/sign.png"` |
| Command token | Shared variable path | `"$project.movement.ticks_per_tile"` |

Commands can also pass runtime context using:

- `self`
- `actor`
- `caller`
- `$self_id`
- `$actor_id`
- `$caller_id`

## Runtime Session Layers

Some important runtime state does not live in authored content files:

- current logical `input_targets`
- current camera state
- traveler session entities transferred across areas

Those are session/save concerns layered over authored project data, not extra
authored content categories.

## Relationship Summary

```text
project.json
|-- points to areas/
|-- points to entity_templates/
|-- points to named_commands/
|-- points to dialogues/
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

dialogues
`-- provide reusable text/choice content

named commands
`-- provide reusable behavior chains
```
