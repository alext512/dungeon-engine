# Engine JSON Interface

This file is the canonical inventory of the current interface between the Python engine and authored JSON content.

It is intentionally about current implementation, not future plans.

Use it when you need to answer questions like:
- what JSON files does the engine load?
- which fields in those files are engine-known?
- which runtime tokens and value sources can commands use?
- which builtin commands exist right now?

For the philosophy behind this interface, see [PROJECT_SPIRIT.md](./PROJECT_SPIRIT.md). For authoring walkthroughs, see [AUTHORING_GUIDE.md](./AUTHORING_GUIDE.md). This file is the lower-level reference.

## Core Rules

- Projects are loaded through a `project.json` manifest.
- Area ids, entity-template ids, and named-command ids are path-derived. They are not authored `id` fields inside those files.
- Gameplay is driven by JSON command specs. A command spec is a JSON object with a `"type"` field.
- Runtime token strings start with `$...` or `${...}`.
- Structured value sources are single-key objects like `{ "$entity_at": { ... } }`.
- Entity-owned `events` and `input_map` are part of the live engine/JSON contract.

## Content Roots And Path-Derived IDs

`project.json` declares search roots for:
- entity templates
- assets
- areas
- named commands

The engine derives these ids from the relative path under each configured root:
- area id
- entity template id
- named command id

Examples:
- `areas/village_square.json` -> area id `village_square`
- `entity_templates/npcs/guard.json` -> template id `npcs/guard`
- `named_commands/dialogue/open.json` -> command id `dialogue/open`

These files must not author their own path-derived ids internally:
- area files must not contain `area_id`
- named command files must not contain `id`

## Project Manifest: `project.json`

Current manifest fields the engine reads:

- `entity_template_paths: string[]`
- `asset_paths: string[]`
- `area_paths: string[]`
- `named_command_paths: string[]`
- `shared_variables_path: string`
- `save_dir: string`
- `global_entities: object[]`
- `startup_area: string`
- `input_targets: object`
- `debug_inspection_enabled: boolean`

Notes:
- If the path arrays are omitted or empty, the engine falls back to conventional folders inside the project root:
  - `entity_templates/`
  - `assets/`
  - `areas/`
  - `named_commands/`
- `shared_variables_path` falls back to `shared_variables.json` if that file exists.
- `save_dir` defaults to `saves`.
- `global_entities` uses the same instance shape as area `entities`.
- `input_targets` is a project-level logical-action routing table.

Minimal example:

```json
{
  "entity_template_paths": ["entity_templates/"],
  "asset_paths": ["assets/"],
  "area_paths": ["areas/"],
  "named_command_paths": ["named_commands/"],
  "shared_variables_path": "shared_variables.json",
  "global_entities": [
    { "id": "dialogue_controller", "template": "dialogue_panel" }
  ],
  "startup_area": "title_screen",
  "input_targets": {
    "menu": "pause_controller"
  },
  "debug_inspection_enabled": true
}
```

## Shared Variables: `shared_variables.json`

This is an ordinary JSON object loaded once at project startup.

The engine exposes it through runtime tokens:
- `$project.foo`
- `$project.display.internal_width`
- `$project.some_list.0`

Special current use:
- `display.internal_width`
- `display.internal_height`

These influence the runtime internal display size if present.

## Area Files

Current area file fields:

- `name: string`
- `tile_size: number`
- `variables: object`
- `tilesets: object[]`
- `tile_layers: object[]`
- `cell_flags: (boolean | object | null)[][]`
- `enter_commands: command[]`
- `entry_points: object`
- `camera: object`
- `input_targets: object`
- `entities: object[]`

Current engine behavior:
- `tile_layers` is required.
- `cell_flags` falls back to all-walkable cells if omitted.
- `input_targets` is merged on top of project-level `input_targets`.
- `enter_commands` runs when the area is entered.
- `camera` is stored as area camera defaults.

### `tilesets`

Each tileset object currently uses:

- `firstgid`
- `path`
- `tile_width`
- `tile_height`

`path` is an authored asset path like `assets/tiles/basic_tiles.png`.

### `tile_layers`

Each tile layer object currently uses:

- `name`
- `grid`
- `draw_above_entities`

`grid` is a 2D array of integer GIDs.

### `cell_flags`

Each cell can currently be:
- `true` / `false`
- an object like `{ "walkable": false, "terrain": "water" }`
- `null`

The engine currently gives built-in meaning to:
- `walkable`

Other keys are stored as ordinary cell metadata.

### `entry_points`

Each entry point object currently uses:

- `x`
- `y`
- `facing`
- `pixel_x`
- `pixel_y`

Notes:
- `facing` on an area entry point remains supported.
- On arrival, the runtime maps that value into the traveler's `variables.direction`.

### `camera`

The engine stores this object as-is as `camera_defaults`. Current authored examples use it for follow mode, offsets, bounds, and deadzones.

### `input_targets`

This is an action -> entity id mapping, for example:

```json
{
  "menu": "pause_controller",
  "interact": "dialogue_controller"
}
```

### `entities`

Each entry is either:
- a full entity definition
- or an instance that references a reusable template with `template` and `parameters`

## Entity Templates And Entity Instances

The engine resolves area entities and `project.json` `global_entities` through the same instance-expansion path.

An instance can contain:
- `template`
- `parameters`
- any overriding entity fields

The engine:
1. loads the template JSON by path-derived id
2. deep-merges the instance over the template
3. applies `$name` / `${name}` template-parameter substitution
4. validates the resulting entity object

### Template Parameter Substitution

This is distinct from runtime tokens.

Template parameter substitution happens when a template is instantiated, before the runtime command system exists.

Inside template JSON:
- `$foo`
- `${foo}`

will be replaced by `parameters.foo` if present.

### Current Entity Fields

Current engine-known entity fields:

- `id`
- `kind`
- `x`
- `y`
- `pixel_x`
- `pixel_y`
- `space`
- `scope`
- `present`
- `visible`
- `events_enabled`
- `layer`
- `stack_order`
- `color`
- `tags`
- `visuals`
- `events`
- `variables`
- `input_map`

Template-only / instance metadata that the engine also tracks:
- `template`
- `parameters`

Runtime-only fields not authored directly:
- movement state
- animation playback state
- session/origin ids

### World-Space vs Screen-Space

- `space: "world"`
  - entity uses `x` / `y`
- `space: "screen"`
  - entity must not declare `x` / `y`
  - use `pixel_x` / `pixel_y` or visual offsets instead

### Scope

- `scope: "area"`
- `scope: "global"`

### Visuals

Each `visuals[]` entry currently uses:

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

### Events

Current `events` forms:

Simple list form:

```json
"events": {
  "interact": [
    { "type": "run_named_command", "command_id": "dialogue/open" }
  ]
}
```

Object form:

```json
"events": {
  "interact": {
    "enabled": true,
    "commands": [
      { "type": "run_named_command", "command_id": "dialogue/open" }
    ]
  }
}
```

### Input Map

`input_map` is an entity-owned mapping from logical input actions to event names:

```json
"input_map": {
  "move_up": "move_up",
  "move_down": "move_down",
  "interact": "interact",
  "menu": "menu"
}
```

The engine routes a logical action to an entity through `input_targets`, then uses that entity's `input_map` to find the event name to run.

## Named Command Files

Named command files are JSON objects with:

- `params: string[]`
- `commands: command[]`

Example:

```json
{
  "params": ["target_id"],
  "commands": [
    {
      "type": "run_event",
      "entity_id": "$target_id",
      "event_id": "interact"
    }
  ]
}
```

Current rules:
- command id is path-derived from the file path
- file must not declare `id`
- `params` is optional and defaults to `[]`
- `commands` is required

## Ordinary Project JSON Data

The engine does not need every project data file to be declared in `project.json`.

Any ordinary JSON file under the project root can be loaded through the `$json_file` value source, for example dialogue data under `dialogues/`.

## Command Specs

A command spec is a JSON object with a `"type"` field.

Examples:

```json
{ "type": "set_world_var", "name": "opened", "value": true }
```

```json
{
  "type": "run_sequence",
  "commands": [
    { "type": "play_audio", "path": "assets/project/sfx/open.wav" },
    { "type": "set_world_var", "name": "opened", "value": true }
  ]
}
```

Command arrays currently appear in:
- entity event command lists
- area `enter_commands`
- named command `commands`
- `run_sequence.commands`
- `run_parallel.commands`
- `spawn_flow.commands`
- `run_commands_for_collection.commands`
- `check_world_var.then`
- `check_world_var.else`
- `check_entity_var.then`
- `check_entity_var.else`

Lifecycle wrapper fields are no longer valid:
- `on_start`
- `on_end`
- `on_complete`

Use:
- `run_sequence`
- `run_parallel`
- `spawn_flow`

### Reading Command JSON

There are three important authored JSON shapes:

- command objects
  These have a `"type"` field and are executed by the engine.
- runtime token strings
  These look like `$self_id` or `$project.dialogue.max_lines` and resolve to a value at runtime.
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
  This is the primary engine-handled command being executed.
- `"entity_id": "$self_id"`
  `$self_id` resolves from the current runtime context.
- `"value": { "$sum": [...] }`
  `"$sum"` is a helper that computes the value before `set_entity_var` runs.

When one command chain needs to call another JSON command file, use `run_named_command` and pass the named-command params as ordinary extra fields on that command object.

## Runtime Tokens

Runtime tokens resolve inside command data at execution time.

String forms:
- `$token`
- `${token}`

Special numeric helper:
- `$half:token`

### Current Token Heads

Exact current token families:

- `$self_id`
- `$actor_id`
- `$caller_id`
- `$project...`
- `$area...`
- `$camera...`
- `$world...`
- `$entity.<entity_id>...`
- `$self...`
- `$actor...`
- `$caller...`
- `$<runtime_param>`

Meaning:

- `$self_id`
  - source entity id for the current flow
- `$actor_id`
  - actor entity id for the current flow
- `$caller_id`
  - caller entity id for the current flow
- `$project.foo.bar`
  - lookup in `shared_variables.json`
- `$area.tile_size`
  - lookup in current area state
- `$camera.x`
  - lookup in current camera state
- `$world.some_var`
  - lookup in the current live world/runtime variable store
- `$entity.some_entity.some_var`
  - lookup in another entity's `variables`
- `$self.some_var`
  - lookup in source entity `variables`
- `$actor.some_var`
  - lookup in actor entity `variables`
- `$caller.some_var`
  - lookup in caller entity `variables`
- `$some_named_param`
  - lookup in runtime params passed by named commands, collection loops, or composition commands

Important limitation:
- `$entity.<id>...`, `$self...`, `$actor...`, and `$caller...` read entity `variables`, not built-in entity fields

Current area token state exposes:
- `area_id`
- `name`
- `tile_size`
- `width`
- `height`
- `pixel_width`
- `pixel_height`
- `camera`

Current camera token state exposes:
- `follow_mode`
- `follow_entity_id`
- `follow_input_action`
- `x`
- `y`
- `follow_offset_x`
- `follow_offset_y`
- `bounds`
- `deadzone`
- `has_bounds`
- `has_deadzone`
- `mode`

## Structured Value Sources

Structured value sources are single-key objects that the runner resolves before primitive execution.

Current value sources:

- `$json_file`
- `$wrapped_lines`
- `$text_window`
- `$entity_ref`
- `$cell_flags_at`
- `$entities_at`
- `$entity_at`
- `$entities_query`
- `$entity_query`
- `$collection_item`
- `$sum`
- `$product`
- `$join_text`
- `$slice_collection`
- `$wrap_index`
- `$and`
- `$or`
- `$not`
- `$random_int`
- `$random_choice`
- `$find_in_collection`
- `$any_in_collection`

### `$json_file`

Loads any JSON file. Relative paths resolve from the active project root.

Example:

```json
{
  "$json_file": "dialogues/system/title_menu.json"
}
```

### `$wrapped_lines`

Wraps text through the active bitmap text renderer.

Shape:

```json
{
  "$wrapped_lines": {
    "text": "Hello world",
    "max_width": 120,
    "font_id": "default"
  }
}
```

### `$text_window`

Builds a visible slice from a list of lines.

Shape:

```json
{
  "$text_window": {
    "lines": "$self.lines",
    "start": 0,
    "max_lines": 3,
    "separator": "\n"
  }
}
```

Return shape:
- `visible_lines`
- `visible_text`
- `has_more`
- `total_lines`

### `$entity_ref`

Returns one plain-data entity reference by explicit id.

Shape:

```json
{
  "$entity_ref": {
    "entity_id": "crate_1",
    "select": {
      "fields": ["entity_id", "grid_x", "grid_y"],
      "variables": ["pushable"],
      "visuals": [
        {
          "id": "main",
          "fields": ["visible", "flip_x"]
        }
      ]
    },
    "default": null
  }
}
```

Notes:

- `select` is required.
- with `select`, missing entities return `default`.

### `$entities_at`

Returns all world-space entities at one tile.

Shape:

```json
{
  "$entities_at": {
    "x": 5,
    "y": 7,
    "exclude_entity_id": "player",
    "include_hidden": false,
    "include_absent": false,
    "where": {
      "kind": "door",
      "present": true
    },
    "select": {
      "fields": ["entity_id"],
      "variables": ["blocks_movement", "pushable"]
    }
  }
}
```

Ordering is the current runtime tile-query order:
- sorted by `(layer, stack_order, entity_id)`
- `select` is required.

### `$entity_at`

Returns one entity ref selected from `$entities_at`.

Shape:

```json
{
  "$entity_at": {
    "x": 5,
    "y": 7,
    "index": 0,
    "where": {
      "kind": "door"
    },
    "select": {
      "fields": ["entity_id"],
      "variables": ["pushable"]
    },
    "default": null
  }
}
```

Negative indexes are supported through the shared collection lookup helper:
- `index: -1` means last item

### `$entities_query`

Returns all selected entities from one filtered world scan.

Shape:

```json
{
  "$entities_query": {
    "include_hidden": false,
    "include_absent": false,
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
```

Ordering is stable and deterministic:
- sorted by `(layer, stack_order, entity_id)`
- `select` is required.

### `$entity_query`

Returns one entity selected from `$entities_query`.

Shape:

```json
{
  "$entity_query": {
    "include_hidden": false,
    "include_absent": false,
    "where": {
      "tags_any": ["save_point"]
    },
    "index": 0,
    "select": {
      "fields": ["entity_id", "grid_x", "grid_y"]
    },
    "default": null
  }
}
```

### Shared Entity-Query `select` Shape

`$entity_ref`, `$entities_at`, `$entity_at`, `$entities_query`, and `$entity_query` all use the same `select` object, and all five currently require it.

Current shape:

```json
{
  "select": {
    "fields": ["entity_id", "grid_x", "grid_y"],
    "variables": ["pushable", "blocks_movement"],
    "visuals": [
      {
        "id": "main",
        "fields": ["visible", "flip_x", "current_frame"],
        "default": null
      }
    ]
  }
}
```

Allowed `select.fields` values:
- `entity_id`
- `kind`
- `space`
- `scope`
- `grid_x`
- `grid_y`
- `pixel_x`
- `pixel_y`
- `present`
- `visible`
- `events_enabled`
- `layer`
- `stack_order`
- `tags`

`select.variables` is a list of variable keys to copy into a `variables` object on the returned result. Keys that do not exist are omitted.

`select.visuals` is a list of visual selectors. Each entry currently supports:
- `id`
- `fields`
- `default`

Allowed `select.visuals.fields` values:
- `id`
- `path`
- `frame_width`
- `frame_height`
- `frames`
- `animation_fps`
- `animate_when_moving`
- `current_frame`
- `animation_elapsed`
- `flip_x`
- `visible`
- `tint`
- `offset_x`
- `offset_y`
- `draw_order`

Selected visuals are returned under a `visuals` object keyed by the requested visual id.

Example selected result:

```json
{
  "entity_id": "box_1",
  "grid_x": 6,
  "grid_y": 4,
  "variables": {
    "pushable": true,
    "blocks_movement": true
  },
  "visuals": {
    "main": {
      "visible": true,
      "flip_x": false
    }
  }
}
```

### Shared Entity-Query `where` Shape

`$entities_at`, `$entity_at`, `$entities_query`, and `$entity_query` all support the same optional `where` object.

Current shape:

```json
{
  "where": {
    "kind": "lever_toggle",
    "kinds": ["lever_toggle", "switch"],
    "tags_any": ["interactive", "save_point"],
    "tags_all": ["interactive", "powered"],
    "space": "world",
    "scope": "area",
    "present": true,
    "visible": true,
    "events_enabled": true
  }
}
```

Rules:
- different keys are combined with implicit `AND`
- `kind` and `kinds` are mutually exclusive
- unknown keys are invalid
- empty `kinds`, `tags_any`, and `tags_all` lists are invalid

Allowed `where` keys:
- `kind`
- `kinds`
- `tags_any`
- `tags_all`
- `space`
- `scope`
- `present`
- `visible`
- `events_enabled`

Allowed `where.space` values:
- `world`
- `screen`

Allowed `where.scope` values:
- `area`
- `global`

`include_hidden` and `include_absent` widen the candidate set before `where` filtering. A query with `where.visible: false` or `where.present: false` automatically widens that candidate set so hidden or absent entities can match.

### `$collection_item`

Returns one item from a list/tuple by `index`, or one value from a dict by `key`.

Shape:

```json
{
  "$collection_item": {
    "value": "$self.targets_here",
    "index": 0,
    "default": null
  }
}
```

or:

```json
{
  "$collection_item": {
    "value": "$self.window",
    "key": "visible_text",
    "default": ""
  }
}
```

### `$sum`

Returns the numeric sum of a small value list.

Example:

```json
{ "$sum": ["$self.grid_x", 1] }
```

### `$product`

Returns the numeric product of a small value list.

Example:

```json
{ "$product": ["$offset_x", "$area.tile_size"] }
```

### `$join_text`

Joins a small authored value list into one text string.

Example:

```json
{ "$join_text": [">", "$item.text"] }
```

### `$slice_collection`

Returns one bounded list slice from a list/tuple value.

Shape:

```json
{
  "$slice_collection": {
    "value": "$self.dialogue_current_segment_options",
    "start": "$self.dialogue_choice_scroll_offset",
    "count": "$self.visible_choice_rows"
  }
}
```

Notes:
- `start` defaults to `0`
- `count` is optional; when omitted the slice runs to the end
- negative `start` values are supported and clamp against the collection length

### `$wrap_index`

Wraps one integer index around a positive collection size.

Shape:

```json
{
  "$wrap_index": {
    "value": {
      "$sum": ["$self.dialogue_choice_index", "$delta"]
    },
    "count": "$self.dialogue_current_option_count",
    "default": 0
  }
}
```

Notes:
- when `count <= 0`, the helper returns `default`
- otherwise the result is the wrapped modulo index

### `$and`, `$or`, `$not`

Small authored boolean helpers.

Shapes:

```json
{ "$and": [true, "$self.flag_a", "$self.flag_b"] }
```

```json
{ "$or": ["$self.choice_a", "$self.choice_b"] }
```

```json
{ "$not": "$self.dialogue_open" }
```

Notes:
- `$and` and `$or` resolve every authored child value first, then apply normal truthiness
- `$not` negates one resolved value's truthiness

### `$random_int`

Returns one inclusive random integer.

Shape:

```json
{
  "$random_int": {
    "min": 1,
    "max": 6
  }
}
```

Notes:
- `min` and `max` are required
- the range is inclusive

### `$random_choice`

Returns one random item from a list/tuple.

Shape:

```json
{
  "$random_choice": {
    "value": ["left", "right", "up", "down"],
    "default": "idle"
  }
}
```

Notes:
- `default` is returned when `value` is empty or `null`
- the selected item is copied before being returned

### `$cell_flags_at`

Returns plain cell-flag data for one explicit tile coordinate.

Shape:

```json
{
  "$cell_flags_at": {
    "x": 5,
    "y": 7,
    "default": { "walkable": false }
  }
}
```

### `$find_in_collection`

Returns the first matching item from a list/tuple, or the supplied `default`.

Shape:

```json
{
  "$find_in_collection": {
    "value": "$self.targets_here",
    "field": "variables.blocks_movement",
    "op": "eq",
    "match": true,
    "default": null
  }
}
```

### `$any_in_collection`

Returns `true` when any item in a list/tuple matches the supplied predicate.

Shape:

```json
{
  "$any_in_collection": {
    "value": "$self.targets_here",
    "field": "variables.pushable",
    "op": "eq",
    "match": true
  }
}
```

### Selected Entity Result Shape

`$entity_ref`, `$entities_at`, `$entity_at`, `$entities_query`, and `$entity_query` now always return the exact selected subset described by `select`.

## Logical Input Surface

Current keyboard-to-action mapping in the engine:

- `WASD` / arrow keys -> `move_up`, `move_down`, `move_left`, `move_right`
- `Space`, `Enter`, keypad Enter -> `interact`
- `Escape` -> `menu`

Debug-only raw key mappings:

- `F6` -> `debug_toggle_pause`
- `F7` -> `debug_step_tick`
- `[` -> `debug_zoom_out`
- `]` -> `debug_zoom_in`

These debug actions only matter if:
- the project maps them through `input_targets`
- the target entity maps them through `input_map`
- debug inspection is enabled for the project

The world currently knows these default logical actions:
- `move_up`
- `move_down`
- `move_left`
- `move_right`
- `interact`
- `menu`

But entity `input_map` and project/area `input_targets` can also use additional arbitrary action strings.

## Builtin Command Inventory

Current builtin commands, grouped by role.

### Movement And Position

- `set_entity_grid_position(entity_id, x, y, mode?)`
- `set_entity_world_position(entity_id, x, y, mode?)`
- `set_entity_screen_position(entity_id, x, y, mode?)`
- `move_entity_world_position(entity_id, x, y, mode?, duration?, frames_needed?, speed_px_per_second?, wait?)`
- `move_entity_screen_position(entity_id, x, y, mode?, duration?, frames_needed?, speed_px_per_second?, wait?)`
- `wait_for_move(entity_id)`

Movement timing precedence for interpolated move commands is:
- `frames_needed`
- `duration`
- `speed_px_per_second`
- engine default fallback

### Animation, Audio, And Entity Visuals

- `play_animation(entity_id, visual_id?, frame_sequence, frames_per_sprite_change?, hold_last_frame?, wait?)`
- `wait_for_animation(entity_id, visual_id?)`
- `stop_animation(entity_id, visual_id?, reset_to_default?)`
- `set_visual_frame(entity_id, visual_id?, frame)`
- `set_visual_flip_x(entity_id, visual_id?, flip_x)`
- `play_audio(path, volume?)`
- `set_sound_volume(volume)`
- `play_music(path, loop?, volume?, restart_if_same?)`
- `stop_music(fade_seconds?)`
- `pause_music()`
- `resume_music()`
- `set_music_volume(volume)`

Notes:
- `play_audio` is one-shot sound-effect playback
- `set_sound_volume` affects future `play_audio` calls
- `play_music` uses the dedicated music channel and defaults to `loop = true`
- `play_music` does not restart the same already-playing track unless `restart_if_same` is `true`

### Screen-Space UI Elements

- `show_screen_image(element_id, path, x, y, frame_width?, frame_height?, frame?, layer?, anchor?, flip_x?, tint?, visible?)` — `anchor` defaults to `"topleft"`; valid values: `topleft`, `top`, `topright`, `left`, `center`, `right`, `bottomleft`, `bottom`, `bottomright`
- `show_screen_text(element_id, text, x, y, layer?, anchor?, color?, font_id?, max_width?, visible?)` — `anchor` values same as `show_screen_image`
- `set_screen_text(element_id, text)`
- `remove_screen_element(element_id)`
- `clear_screen_elements(layer?)`
- `play_screen_animation(element_id, frame_sequence, ticks_per_frame?, hold_last_frame?, wait?)`
- `wait_for_screen_animation(element_id)`

### Time And Flow Composition

- `wait_frames(frames)`
- `wait_seconds(seconds)`
- `spawn_flow(commands?, source_entity_id?, actor_entity_id?, caller_entity_id?)`
- `run_sequence(commands?, source_entity_id?, actor_entity_id?, caller_entity_id?)`
- `run_parallel(commands?, completion?, source_entity_id?, actor_entity_id?, caller_entity_id?)`
- `run_commands_for_collection(value?, commands?, item_param?, index_param?, source_entity_id?, actor_entity_id?, caller_entity_id?)` — iterates a list/tuple and runs `commands` once per item, injecting the current item and index as runtime params

Current `run_parallel` completion shape:

```json
{
  "completion": {
    "mode": "all"
  }
}
```

Supported current completion modes:
- `all`
- `any`
- `child`

For `child`, current shape is:

```json
{
  "completion": {
    "mode": "child",
    "child_id": "move",
    "remaining": "keep_running"
  }
}
```

Current remaining policy:
- `keep_running`

Each `run_parallel.commands[]` child may also declare an optional `id` field, used by `completion.mode = "child"`.

`run_commands_for_collection` example:

```json
{
  "type": "run_commands_for_collection",
  "value": "$self.targets_here",
  "item_param": "item",
  "index_param": "index",
  "commands": [
    {
      "type": "set_entity_var",
      "entity_id": "$item.entity_id",
      "name": "activated",
      "value": true
    }
  ]
}
```

Inside `commands`, `$item` resolves to the current list element and `$index` resolves to its zero-based position. The param names default to `item` and `index` but can be overridden with `item_param` and `index_param`.

### Event And Named-Command Dispatch

- `run_event(entity_id, event_id, source_entity_id?, actor_entity_id?, caller_entity_id?, ...extra_params)`
- `run_named_command(command_id, source_entity_id?, actor_entity_id?, caller_entity_id?, ...extra_params)`

Both commands forward any additional fields on the command object into the called flow as runtime parameters. The called commands can read those values with `$param_name` tokens. For example, passing `"dialogue_path": "dialogues/system/pause_menu.json"` on a `run_event` makes `$dialogue_path` available inside the target event's command chain.

### Event/Input Routing

- `set_event_enabled(entity_id, event_id, enabled, persistent?)`
- `set_events_enabled(entity_id, enabled, persistent?)`
- `set_input_target(action, entity_id?)`
- `route_inputs_to_entity(entity_id?, actions?)`
- `push_input_routes(actions?)`
- `pop_input_routes()`

### Area / Save / Game Flow

- `change_area(area_id?, entry_id?, transfer_entity_id?, transfer_entity_ids?, camera_follow_entity_id?, camera_follow_input_action?, camera_offset_x?, camera_offset_y?, source_entity_id?, actor_entity_id?, caller_entity_id?)`
- `new_game(area_id?, entry_id?, camera_follow_entity_id?, camera_follow_input_action?, camera_offset_x?, camera_offset_y?, source_entity_id?, actor_entity_id?, caller_entity_id?)`
- `load_game(save_path?)`
- `save_game(save_path?)`
- `quit_game()`

### Debug Runtime

- `set_simulation_paused(paused)`
- `toggle_simulation_paused()`
- `step_simulation_tick()`
- `adjust_output_scale(delta)`

These commands are gated by project `debug_inspection_enabled`.

### Camera

- `set_camera_follow_entity(entity_id, offset_x?, offset_y?)`
- `set_camera_follow_input_target(action, offset_x?, offset_y?)`
- `clear_camera_follow()`
- `set_camera_bounds_rect(x, y, width, height, space?)`
- `clear_camera_bounds()`
- `set_camera_deadzone(x, y, width, height, space?)`
- `clear_camera_deadzone()`
- `move_camera(x, y, space?, mode?, duration?, frames_needed?, speed_px_per_second?)`
- `teleport_camera(x, y, space?, mode?)`

### Entity State

- `set_entity_field(entity_id, field_name, value, persistent?)` - supported field names: `present`, `visible`, `events_enabled`, `layer`, `stack_order`, `color`, `input_map`, `input_map.<action>`, and `visuals.<visual_id>.<field>`
- `set_visible(entity_id, visible, persistent?)`
- `visuals.<visual_id>.<field>` supports `flip_x`, `visible`, `current_frame`, `tint`, `offset_x`, `offset_y`, and `animation_fps`
- `set_entity_fields(entity_id, set, persistent?)` - structured batch mutation for `fields`, `variables`, and `visuals`; validates the full payload before applying any changes
- `set_present(entity_id, present, persistent?)`
- `set_color(entity_id, color, persistent?)`
- `destroy_entity(entity_id, persistent?)`
- `spawn_entity(entity?, entity_id?, template?, kind?, x?, y?, parameters?, present?, persistent?)` - two forms: pass a full `entity` dict, or pass individual fields (`entity_id`, `x`, `y`, and optionally `template`, `kind`, `parameters`)

### World And Entity Variables

- `set_world_var(name, value, persistent?)`
- `set_entity_var(entity_id, name, value, persistent?)`
- `add_world_var(name, amount?, persistent?)`
- `add_entity_var(entity_id, name, amount?, persistent?)`
- `toggle_world_var(name, persistent?)`
- `toggle_entity_var(entity_id, name, persistent?)`
- `set_world_var_length(name, value?, persistent?)`
- `set_entity_var_length(entity_id, name, value?, persistent?)`
- `append_world_var(name, value, persistent?)`
- `append_entity_var(entity_id, name, value, persistent?)`
- `pop_world_var(name, store_var?, default?, persistent?)`
- `pop_entity_var(entity_id, name, store_var?, default?, persistent?)`
- `check_world_var(name, op?, value?, then?, else?)`
- `check_entity_var(entity_id, name, op?, value?, then?, else?)`

Current comparison operators:
- `eq`
- `neq`
- `gt`
- `gte`
- `lt`
- `lte`

Notes:
- `set_world_var` and related world-variable commands currently operate on the live world/runtime variable store for the active play session
- in normal play, this is the authored surface for current area/runtime state that can also be persisted
- `toggle_world_var` / `toggle_entity_var` treat missing or `null` as `false`, then flip the value; non-boolean existing values raise an error

### Reset / Persistence Helpers

- `reset_transient_state(include_tags?, exclude_tags?, apply?)`
- `reset_persistent_state(include_tags?, exclude_tags?, apply?)`

## Deferred Nested Command Fields

Some command params intentionally defer nested command specs instead of resolving all nested `$...` values immediately.

Current deferred command params:

- `spawn_flow.commands`
- `run_sequence.commands`
- `run_parallel.commands`
- `run_commands_for_collection.commands`
- `check_world_var.then`
- `check_world_var.else`
- `check_entity_var.then`
- `check_entity_var.else`

Current special deferred params on `run_event`:
- `dialogue_on_start`
- `dialogue_on_end`
- `segment_hooks`

Those are part of the current dialogue/controller surface.

## Current Engine-Known Special Fields

These fields are currently engine-known and actively interpreted, not just stored as opaque data.

### Broadly Acceptable Infrastructure

- area `tile_layers`
- area `cell_flags`
- area `entry_points`
- entity `space`
- entity `scope`
- entity `present`
- entity `visible`
- entity `events_enabled`
- entity `layer`
- entity `stack_order`
- entity `color`
- entity `input_map`
- entity `visuals`

### Grid Notes

Current grid blocking comes from:
- `cell_flags.walkable`

Tile art itself does not define collision.

## Reserved Runtime Entity IDs

These names are reserved runtime references and should not be used as authored entity ids:

- `self`
- `actor`
- `caller`

Strict primitive commands must not use raw symbolic ids like:

```json
{ "type": "set_entity_var", "entity_id": "self", "name": "x", "value": 1 }
```

Use:

```json
{ "type": "set_entity_var", "entity_id": "$self_id", "name": "x", "value": 1 }
```

## Current Root-Flow Scheduling Model

The current command runner model is:

- top-level dispatches become independent root flows
- `run_sequence` executes child commands in order
- `run_parallel` executes child commands together with an explicit completion policy
- `spawn_flow` starts a separate flow and returns immediately

Routed input events are ordinary root-flow dispatches, not a special busy-state exception.

## Bitmap Font Definition

Font JSON files live under the project's asset paths and define bitmap fonts for text rendering.

Current fields:

- `kind`: must be `"bitmap"`
- `atlas`: asset-relative path to the font atlas PNG
- `cell_width`: pixel width of each glyph cell in the atlas
- `cell_height`: pixel height of each glyph cell in the atlas
- `columns`: number of glyph columns in the atlas
- `line_height`: pixel height per rendered line
- `letter_spacing`: pixel gap between characters
- `space_width`: pixel width of the space character
- `minimum_advance`: minimum pixel advance per character
- `fallback_character`: character to render for unknown glyphs
- `glyph_order`: string listing each glyph in atlas order (left to right, top to bottom)

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
  "glyph_order": "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.!?\":1234567890,'-/+()=;_[]%#><"
}
```

Font ids are the JSON filename without extension. The engine looks for `{font_id}.json` under `fonts/` in the project's asset paths. For example, `assets/project/fonts/pixelbet.json` has font id `pixelbet`. Commands reference fonts through `font_id` parameters.

## Suggested Use

Use the docs together like this:

1. [PROJECT_SPIRIT.md](./PROJECT_SPIRIT.md)
   Read for philosophy and design intent.
2. [AUTHORING_GUIDE.md](./AUTHORING_GUIDE.md)
   Read for normal authoring workflow.
3. This file
   Read when you need exact current engine/JSON contract details.
