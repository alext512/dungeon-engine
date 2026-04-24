# Engine JSON Interface

This file is the canonical inventory of the current interface between the Python engine and authored JSON content.

It is intentionally about current implementation, not future plans.

Use it when you need to answer questions like:
- what JSON files does the engine load?
- which fields in those files are engine-known?
- which runtime tokens and value sources can commands use?
- which builtin commands exist right now?

For the philosophy behind this interface, see [Project Spirit](../../project/project-spirit.md). For authoring walkthroughs, see [Authoring Guide](authoring-guide.md). This file is the lower-level reference.

## Core Rules

- Projects are loaded through a `project.json` manifest.
- Area ids, entity-template ids, and project command ids are path-derived. They are not authored `id` fields inside those files.
- Gameplay is driven by JSON command specs. A command spec is a JSON object with a `"type"` field.
- Runtime token strings start with `$...` or `${...}`.
- Structured value sources are single-key objects like `{ "$entity_at": { ... } }`.
- Entity-owned `entity_commands` and `input_map` are part of the live engine/JSON contract.

## Command Chain Rules

- Any `commands: [...]` list is a sequential command body by default.
- This applies to area `enter_commands`, entity-command bodies, project-command bodies, `if.then`, `if.else`, and child command lists under flow/orchestration commands.
- Use `run_parallel` only when child commands should start together.
- Use `run_sequence` only when you want to execute a command-list value explicitly, for example one stored in a variable or passed as a parameter.
- Project command files may declare `deferred_param_shapes` when specific params should remain raw command/data payloads until a later explicit execution step.
- Startup validation validates known command-bearing JSON surfaces for strict-command key mismatches before launch.
- Strict primitive commands fail startup on unknown top-level keys, while mixed flow/helper commands intentionally accept caller-supplied runtime params.
- Builtin command validation mode, allowed authored fields, and deferred nested command payload shapes are defined by the command registry registrations in runtime code.

## Content Roots And Path-Derived IDs

`project.json` declares search roots for:
- entity templates
- assets
- areas
- project commands
- item definitions

The engine derives these ids from the relative path under each configured root:
- area id
- entity template id
- project command id
- item id

Examples:
- `areas/village_square.json` -> area id `areas/village_square`
- `entity_templates/npcs/guard.json` -> template id `entity_templates/npcs/guard`
- `commands/dialogue/open.json` -> command id `commands/dialogue/open`
- `items/light_orb.json` -> item id `items/light_orb`

These files must not author their own path-derived ids internally:
- area files must not contain `area_id`
- project command files must not contain `id`

## Project Manifest: `project.json`

Current manifest fields the engine reads:

- `entity_template_paths: string[]`
- `asset_paths: string[]`
- `area_paths: string[]`
- `command_paths: string[]`
- `item_paths: string[]`
- `shared_variables_path: string`
- `save_dir: string`
- `global_entities: object[]`
- `startup_area: string`
- `input_targets: object`
- `debug_inspection_enabled: boolean`
- `command_runtime: object`

Notes:
- If the path arrays are omitted or empty, the engine falls back to conventional folders inside the project root:
  - `entity_templates/`
  - `assets/`
  - `areas/`
  - `commands/`
  - `items/`
- `shared_variables_path` falls back to `shared_variables.json` if that file exists.
- `save_dir` defaults to `saves`.
- `global_entities` uses the same instance shape as area `entities`. Global entities are project-level runtime entities â€” the runtime injects them into the active play world whenever an area is built. Their persistent state is stored separately from per-area state and is not affected by area resets. Unlike travelers (entities transferred between areas via `change_area`), globals don't physically move â€” the runtime always includes them.
- `input_targets` is a project-level logical-action routing table.
- `command_runtime` is optional; omitted fields use engine defaults.

Minimal example:

```json
{
  "entity_template_paths": ["entity_templates/"],
  "asset_paths": ["assets/"],
  "area_paths": ["areas/"],
  "command_paths": ["commands/"],
  "item_paths": ["items/"],
  "shared_variables_path": "shared_variables.json",
  "global_entities": [
    { "id": "dialogue_controller", "template": "entity_templates/dialogue_panel" }
  ],
  "startup_area": "areas/title_screen",
  "input_targets": {
    "menu": "pause_controller"
  },
  "debug_inspection_enabled": true,
  "command_runtime": {
    "max_settle_passes": 128,
    "max_immediate_commands_per_settle": 8192,
    "log_settle_usage_peaks": false,
    "settle_warning_ratio": 0.75
  }
}
```

Notes:
- Projects are not required to define a `dialogue_controller` global entity.
- The engine-owned dialogue path opens sessions directly through
  `open_dialogue_session`.
- Projects may use a `dialogue_controller` when they want a controller-authored
  dialogue/menu flow.

### `command_runtime`

Optional command-runner safety and diagnostics settings:

- `max_settle_passes: integer`
- `max_immediate_commands_per_settle: integer`
- `log_settle_usage_peaks: boolean`
- `settle_warning_ratio: number`

Defaults:

```json
{
  "max_settle_passes": 128,
  "max_immediate_commands_per_settle": 8192,
  "log_settle_usage_peaks": false,
  "settle_warning_ratio": 0.75
}
```

These limits are safety fuses, not frame budgets. When eager command settling
hits a fuse, the runner logs a command error and clears current command work
instead of silently spilling ready commands into a later tick. If
`log_settle_usage_peaks` is `true`, the runtime logs the largest settle workload
observed so far so you can tune the limits or spot suspicious cascades.

## Shared Variables: `shared_variables.json`

This is an ordinary JSON object loaded once at project startup.

The engine exposes it through runtime tokens:
- `$project.foo`
- `$project.display.internal_width`
- `$project.some_list.0`

Special current use:
- `display.internal_width`
- `display.internal_height`
- `dialogue_ui.default_preset`
- `dialogue_ui.presets`
- `inventory_ui.default_preset`
- `inventory_ui.presets`

These influence the runtime internal display size if present.

For the engine-owned dialogue runtime, `dialogue_ui.presets` is the
current shared-variable convention for named dialogue UI layouts. Current
choice-layout presets may define:

- `choices.mode`: `inline` or `separate_panel`
- `choices.overflow`: `clip`, `wrap`, or `marquee`
- `choices.visible_rows`
- `choices.row_height`
- `choices.panel` plus `choices.x` / `choices.y` / `choices.width` for
  separate-panel choice menus

Current inline-choice behavior:

- if the segment has prompt `text`, the prompt uses exactly one line in the
  main dialogue panel
- long inline prompts continuously marquee inside that one line
- remaining main-panel lines are used for visible choice rows
- if the segment has no prompt `text`, inline choices can use all available
  main-panel lines

For the engine-owned inventory runtime, `inventory_ui.presets` is the current
shared-variable convention for named inventory UI layouts. Current presets may
define:

- `list_panel`
- `list`
- `detail_panel`
- `portrait_slot`
- `text`
- `action_popup`
- `deny_sfx_path`
- `font_id`
- `text_color`
- `choice_text_color`
- `ui_layer`
- `text_layer`

## Item Files

Item definitions are plain JSON files discovered through `item_paths`.

Current item file fields:

- `name: string`
- `description: string`
- `icon: object`
- `portrait: object`
- `max_stack: integer`
- `consume_quantity_on_use: integer`
- `use_commands: command[]`

Current rules:

- item ids are path-derived and the file must not author `id`
- `max_stack` must be `>= 1`
- `consume_quantity_on_use` must be `>= 0`
- `use_commands` is optional
- `use_inventory_item` only consumes after the use commands finish cleanly

Example:

```json
{
  "name": "Light Orb",
  "description": "Feeds the nearby beacon terminal once.",
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

## Area Files

Current area file fields:

- `tile_size: number`
- `variables: object`
- `tilesets: object[]`
- `tile_layers: object[]`
- `cell_flags: (object | null)[][]`
- `enter_commands: command[]`
- `entry_points: object`
- `camera: object`
- `input_targets: object`
- `entities: object[]`

Current engine behavior:
- `tile_layers` is required.
- `cell_flags` falls back to all-unblocked cells if omitted.
- `input_targets` is merged on top of project-level `input_targets`.
- `enter_commands` runs when the area is entered.
- area files must not declare a top-level `name`.
- `camera` is stored as area camera defaults.
- authored entity ids must be unique across the whole project, including across different areas and `project.json` globals.

### `tilesets`

Each tileset object currently uses:

- `firstgid`
- `path`
- `tile_width`
- `tile_height`

`path` is an authored asset path like `assets/tiles/basic_tiles.png`.

### `tile_layers`

Each tile layer object uses:

- `name`
- `grid`
- `render_order`
- `y_sort`
- `sort_y_offset`
- `stack_order`

`grid` is a 2D array of integer GIDs.

Current authored meaning:

- `render_order` is the coarse render band
- `y_sort: true` makes the layer participate in per-tile vertical interleaving
- `sort_y_offset` adjusts the y-sort pivot in pixels
- `stack_order` is the tie-breaker inside the same band / sort position

### `cell_flags`

Each cell can currently be:
- an object like `{ "blocked": true, "tags": ["water"] }`
- `null`

The engine currently gives built-in meaning to:
- `blocked` (whether the cell blocks movement)

Conventions:
- `tags` is an optional list of strings intended for authored logic.
- Other keys are stored as ordinary cell metadata (but only `blocked` and `tags`
  are part of the recommended authored contract).

`null` is treated the same as an empty object (`{"blocked": false}`).

### `entry_points`

Each entry point object currently uses:

- `grid_x`
- `grid_y`
- `facing`
- `pixel_x`
- `pixel_y`

Notes:
- Prefer destination marker entities plus `destination_entity_id` on
  `change_area` / `new_game` when a transfer should land on a specific entity.
- Use `entry_points` when the area needs named coordinate/facing entry data.
- `facing` on an area entry point remains supported.
- On arrival, the runtime maps that value into the traveler's top-level `facing`.

### `camera`

The engine stores this object as-is as `camera_defaults`. Current authored examples use the same structured sections as the runtime camera commands:

- `follow`
- `bounds`
- `deadzone`

Example:

```json
{
  "follow": {
    "mode": "entity",
    "entity_id": "player"
  },
  "bounds": {
    "x": 0,
    "y": 0,
    "width": 20,
    "height": 15,
    "space": "world_grid"
  }
}
```

### `input_targets`

This is an action -> entity id mapping, for example:

```json
{
  "menu": "pause_controller",
  "interact": "dialogue_controller"
}
```

Target ids in `input_targets` must refer to authored entity ids that are unique across the whole project, not just within one area.

### `entities`

Each entry is either:
- a full entity definition
- or an instance that references a reusable template with `template` and `parameters`

Authored entity `id` values are project-wide identities. Reusing the same entity id in multiple authored areas is invalid.

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

Templates may also author top-level `parameters` defaults. The engine merges
template defaults with instance `parameters` before substitution, so instances
can override only the values they need to change.

### Template Parameter Specs

Entity templates may also author top-level `parameter_specs`. This is template
metadata for validation and editor browsing. Entity instances must not define
`parameter_specs`.

If a template declares `parameter_specs`:

- every authored instance parameter must be listed in `parameter_specs`
- template default values are type-checked
- required parameters must resolve to non-blank values when an instance is
  loaded
- unknown instance parameters are rejected

Templates without `parameter_specs` keep the older untyped behavior.

Example:

```json
{
  "parameters": {
    "target_area": "areas/start",
    "destination_entity_id": "spawn_marker",
    "target_entity_id": "",
    "target_command_id": "open_now",
    "required_count": 1,
    "sprite_path": ""
  },
  "parameter_specs": {
    "target_area": {
      "type": "area_id"
    },
    "target_entity_id": {
      "type": "entity_id",
      "scope": "area",
      "space": "world"
    },
    "destination_entity_id": {
      "type": "entity_id",
      "area_parameter": "target_area",
      "scope": "area",
      "space": "world"
    },
    "target_command_id": {
      "type": "entity_command_id",
      "entity_parameter": "target_entity_id"
    },
    "required_count": {
      "type": "int",
      "min": 1
    },
    "sprite_path": {
      "type": "asset_path",
      "asset_kind": "image"
    }
  }
}
```

Supported `type` values:

- `string`
- `text`
- `bool`
- `int`
- `number`
- `enum`
- `array`
- `json`
- `entity_id`
- `entity_command_id`
- `area_id`
- `item_id`
- `dialogue_path`
- `dialogue_definition`
- `project_command_id`
- `entity_template_id`
- `asset_path`
- `color_rgb`

Supported constraints:

- `required`: boolean
- `min` / `max`: numeric bounds for `int` and `number`
- `values`: allowed values for `enum`
- `items`: item spec for `array`
- `scope`: `area` or `global`, only for `entity_id`
- `space`: `world` or `screen`, only for `entity_id`
- `area_parameter`: names the `area_id` parameter whose selected area should
  constrain an `entity_id` picker
- `entity_parameter`: names the `entity_id` parameter whose command list is
  used for an `entity_command_id`
- `asset_kind`: `image`, `audio`, `json`, or `font`, only for `asset_path`

Entity ids are still authored as plain ids. `area_parameter` only tells tools
and validation which area the id must come from, for cases such as
`target_area` plus `destination_entity_id` on an area transition.
`dialogue_definition` parameters must be JSON objects with a `segments` array,
using the same dialogue schema as file-backed dialogue JSON.

### Current Entity Fields

Current engine-known entity fields:

- `id`
- `kind`
- `grid_x`
- `grid_y`
- `pixel_x`
- `pixel_y`
- `space`
- `scope`
- `facing`
- `present`
- `visible`
- `entity_commands_enabled`
- `solid`
- `pushable`
- `weight`
- `push_strength`
- `collision_push_strength`
- `interactable`
- `interaction_priority`
- `render_order`
- `y_sort`
- `sort_y_offset`
- `stack_order`
- `color`
- `tags`
- `visuals`
- `entity_commands`
- `dialogues`
- `variables`
- `persistence`
- `inventory`
- `input_map`

Render-field defaults may be omitted from authored entity JSON when they match
the entity's space:

- world-space entities default to `render_order: 10`, `y_sort: true`, `sort_y_offset: 0`, `stack_order: 0`
- screen-space entities default to `render_order: 0`, `y_sort: false`, `sort_y_offset: 0`, `stack_order: 0`

That applies to both inline entities and template instances. Serializers should
only write these fields back out when the authored value differs from the
default or from the referenced template.

Template-only / instance metadata that the engine also tracks:
- `template`
- `parameters`

Runtime-only fields not authored directly:
- movement state
- animation playback state
- traveler origin-area bookkeeping

### Entity Persistence Policy

Entities and templates can now author persistence defaults directly:

```json
"persistence": {
  "entity_state": true,
  "variables": {
    "shake_timer": false,
    "times_pushed": true
  }
}
```

Current rules:

- `persistence.entity_state` is the default save policy for entity-targeted state mutations such as `set_entity_field`, `set_visible`, `destroy_entity`, and `spawn_entity`
- `persistence.variables.<name>` overrides that default for one specific variable name
- omitting `persistence` means the entity is transient by default
- explicit command `persistent: true` / `persistent: false` still overrides the entity policy when a command supports it

### Inventory

Inventories are entity-owned. Current authored shape:

```json
"inventory": {
  "max_stacks": 4,
  "stacks": [
    {
      "item_id": "items/light_orb",
      "quantity": 1
    }
  ]
}
```

Current rules:

- `inventory.max_stacks` limits the number of stacks
- each stack uses `item_id` plus `quantity`
- authored stack quantities must be positive and must not exceed the item's
  `max_stack`
- authored content rejects missing item definitions
- saved inventories preserve unresolved item ids with a warning instead of
  silently deleting them

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
- `default_animation`
- `default_animation_by_facing`
- `animations`
- `animation_fps`
- `animate_when_moving`
- `flip_x`
- `visible`
- `tint`
- `offset_x`
- `offset_y`
- `draw_order`

`frames` is the visual's default/free-running frame list. When a visual is
driven by named clips, `frames` may be omitted and the loader will derive it
from `default_animation` or the first authored clip.

Named clips live under `animations`:

```json
{
  "id": "body",
  "path": "assets/used_tilesets_sprites/main_character.png",
  "frame_width": 16,
  "frame_height": 16,
  "default_animation": "idle_down",
  "default_animation_by_facing": {
    "up": "idle_up",
    "down": "idle_down",
    "left": "idle_left",
    "right": "idle_right"
  },
  "animations": {
    "idle_down": { "frames": [0] },
    "idle_up": { "frames": [1] },
    "idle_right": { "frames": [2], "flip_x": false },
    "idle_left": { "frames": [2], "flip_x": true },
    "walk_down": { "frames": [0, 3, 6, 3], "preserve_phase": true },
    "walk_up": { "frames": [1, 4, 7, 4], "preserve_phase": true },
    "walk_right": { "frames": [2, 5, 8, 5], "flip_x": false, "preserve_phase": true },
    "walk_left": { "frames": [2, 5, 8, 5], "flip_x": true, "preserve_phase": true }
  }
}
```

`default_animation` names the visual's default clip. If top-level `frames` are
omitted, the loader derives the visual's free-running frame list from
`default_animation` or the first authored clip. `default_animation_by_facing`
is optional and lets one visual explicitly map `up`, `down`, `left`, and
`right` facings to different default clips when the entity is instantiated or
when transferred visuals are reset after an area change.

Clip fields:

- `frames`
  Required. Sprite frame indexes inside the visual's sprite sheet.
- `flip_x`
  Optional. When present, `play_animation` applies this horizontal flip before
  playback. This lets `walk_left` reuse right-facing frames without a special
  engine concept like `side`.
- `preserve_phase`
  Optional boolean. When `true`, repeated plays of this clip continue from the
  next clip-local frame instead of restarting from the first frame. This is
  useful for walk cycles such as `[0, 3, 6, 3]`, where each tile step may only
  consume two sprite frames but the next step should use the opposite leg.

For gameplay-coupled animation timing, prefer command `duration_ticks` plus
structured value sources such as `$divide` over `animation_fps`. Free-running
`animation_fps` remains useful for decorative loops that do not need to align
with command or movement timing.

### Entity Commands

Current `entity_commands` form:

```json
"entity_commands": {
  "interact": [
    {
      "type": "run_project_command",
      "command_id": "commands/dialogue/open"
    }
  ],
  "disabled_example": {
    "enabled": false,
    "commands": [
      {
        "type": "run_project_command",
        "command_id": "commands/dialogue/open"
      }
    ]
  }
}
```

Notes:
- `entity_commands.<name>` accepts either:
  - an array shorthand, which means the command body is enabled by default
  - a long object form with `enabled` and `commands`
- Use the array shorthand for ordinary enabled commands.
- Use the long object form when you need metadata such as `enabled: false`.
- There is no supported middle form like `{ "commands": [...] }` without `enabled`.
- The command body runs sequentially by default in either form.
- Another command chain can invoke one named entity command with `run_entity_command`.
- Standard engine-dispatched hook names currently include `interact`, `on_blocked`,
  `on_occupant_enter`, and `on_occupant_leave`.

### Entity-Owned Dialogue Variants

Entities and templates may also own a named dialogue set directly:

```json
"dialogues": {
  "intro": {
    "dialogue_path": "dialogues/npcs/greeter_intro.json"
  },
  "repeat": {
    "dialogue_definition": {
      "segments": [
        {
          "type": "text",
          "text": "Back again?"
        }
      ]
    }
  }
},
"variables": {
  "active_dialogue": "intro"
}
```

Current rules:

- `dialogues` is a JSON object keyed by dialogue id
- each dialogue entry must define exactly one of:
  - `dialogue_path`
  - `dialogue_definition`
- `dialogue_definition` entries use the same `segments` schema as ordinary
  dialogue JSON files
- authored entry order is preserved and used by the order-based helper commands
- `variables.active_dialogue`, when used, is an ordinary entity variable whose
  value should be one of the keys in `dialogues`
- dialogue selection is stable by name; order-based helpers still store the
  chosen dialogue id back into `variables.active_dialogue`

### Input Map

`input_map` is an entity-owned mapping from logical input actions to entity-command names:

```json
"input_map": {
  "move_up": "move_up",
  "move_down": "move_down",
  "interact": "interact",
  "menu": "menu"
}
```

The engine routes a logical action to an entity through `input_targets`, then uses that entity's `input_map` to find the event name to run.

## Project Command Files

Project command files are JSON objects with:

- `params: string[]`
- `deferred_param_shapes: object`
- `commands: command[]`

Example:

```json
{
  "params": ["target_id"],
  "commands": [
    {
      "type": "run_entity_command",
      "entity_id": "$target_id",
      "command_id": "interact"
    }
  ]
}
```

Current rules:
- command id is a path-derived typed id from the file path, for example `commands/dialogue/open`
- file must not declare `id`
- unknown top-level fields fail project-command validation
- `params` is optional and defaults to `[]`
- `deferred_param_shapes` is optional and defaults to `{}`
- `commands` is required

`deferred_param_shapes` maps a project-command param name to one of these shapes:

- `raw_data` - keep the parameter raw during `run_project_command` resolution without treating it as a command-bearing payload
- `command_payload` - keep the parameter raw and audit it as one command object or a list of command objects
- `dialogue_definition` - keep one inline dialogue definition raw and audit its command-bearing segment and option fields
- `dialogue_segment_hooks` - keep the parameter raw and audit it as a dialogue segment-hook list

## Ordinary Project JSON Data

The engine does not need every project data file to be declared in `project.json`.

Any ordinary JSON file under the project root can be loaded through the `$json_file` value source, for example dialogue data under `dialogues/`.

`$json_file` reads are cached within the current live runtime command context.
Rebuilding runtime context, such as during area changes, `new_game`, or
`load_game`, starts with a fresh cache.

## Command Specs

A command spec is a JSON object with a `"type"` field.

Command execution is eager. A ready command chain continues in the same
simulation tick until it reaches a real wait. This means immediate commands
after other immediate commands run immediately, and immediate commands after a
completed wait resume in the tick where that wait completes.

Important timing rules:

- a plain command array is sequential
- `wait=true` on a time-taking command blocks the current sequence until that
  work finishes
- `wait=false` starts that work and lets the current sequence continue
  immediately
- `spawn_flow` starts a child flow immediately and lets the parent continue
  immediately
- ready command work does not intentionally defer to a later tick unless a real
  async handle is still waiting

Examples:

```json
{ "type": "set_current_area_var", "name": "opened", "value": true }
```

```json
{
  "type": "run_sequence",
  "commands": [
    { "type": "play_audio", "path": "assets/project/sfx/open.wav" },
    { "type": "set_current_area_var", "name": "opened", "value": true }
  ]
}
```

Command arrays currently appear in:
- entity command shorthand arrays
- area `enter_commands`
- project command `commands`
- long-form entity command `commands`
- `run_sequence.commands`
- `run_parallel.commands`
- `spawn_flow.commands`
- `run_commands_for_collection.commands`
- `if.then`
- `if.else`

Lifecycle wrapper fields are no longer valid:
- `on_start`
- `on_end`
- `on_complete`

Use:
- plain sequential `commands: [...]` bodies
- `run_sequence`
- `run_parallel`
- `spawn_flow`

### Reading Command JSON

There are four important authored JSON shapes:

- command objects
  These have a `"type"` field and are executed by the engine.
- command arrays
  These are ordered lists of command objects. A bare `commands: [...]` array is
  the engine's default sequential-flow form, and named entity commands may also
  use the array shorthand directly.
- runtime token strings
  These look like `$self_id` or `$project.dialogue.max_lines` and resolve to a value at runtime.
- structured value sources
  These are single-key objects like `{"$add": [...]}` or `{"$entity_ref": {...}}` that compute or query a value before a primitive command runs.

Example:

```json
{
  "type": "set_entity_var",
  "entity_id": "$self_id",
  "name": "next_x",
  "value": {
    "$add": [
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
- `"value": { "$add": [...] }`
  `"$add"` is a helper that computes the value before `set_entity_var` runs.

When one command chain needs to call another JSON command file, use `run_project_command` and pass the project command params as ordinary extra fields on that command object.

Do not assume every command object accepts arbitrary extra fields. Current mixed commands that intentionally allow caller-supplied runtime params include:

- `run_sequence`
- `run_parallel`
- `spawn_flow`
- `run_commands_for_collection`
- `run_entity_command`
- `run_project_command`
- `if`
- `step_in_direction`
- `push_facing`
- `interact_facing`

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
- `$refs.<name>...`
- `$ref_ids.<name>`
- `$project...`
- `$area...`
- `$camera...`
- `$current_area...`
- `$self...`
- `$<runtime_param>`

Meaning:

- `$self_id`
  - source entity id for the current flow
- `$refs.some_name.some_var`
  - lookup in one named referenced entity's `variables`
- `$ref_ids.some_name`
  - lookup of one named referenced entity id
- `$project.foo.bar`
  - lookup in `shared_variables.json`
- `$area.tile_size`
  - lookup in current area state
- `$camera.x`
  - lookup in current camera state
- `$current_area.some_var`
  - lookup in the current live current-area/runtime variable store
- `$self.some_var`
  - lookup in source entity `variables`
- `$some_named_param`
- lookup in runtime params passed by project commands, collection loops, or composition commands

Important split:
- `entity_refs` is only the explicit named-ref map you pass in JSON
- engine-owned context such as `instigator_id`, `direction`, or `from_x` arrives as ordinary runtime params and is read through `$<runtime_param>`

Important limitation:
- `$self...` and `$refs.<name>...` read entity `variables`, not built-in entity fields

Current area token state exposes:
- `area_id`
- `tile_size`
- `width`
- `height`
- `pixel_width`
- `pixel_height`
- `camera`

Current camera token state exposes:
- `x`
- `y`
- `follow`
  - `follow.mode`
  - `follow.entity_id`
  - `follow.action`
  - `follow.offset_x`
  - `follow.offset_y`
- `bounds`
- `deadzone`
- `has_bounds`
- `has_deadzone`

## Structured Value Sources

Structured value sources are single-key objects that the runner resolves before primitive execution.
If a single-key object uses a `$`-prefixed key that is not listed here, the runner treats it as an unknown value source and raises an error.

Current value sources:

- `$json_file`
- `$wrapped_lines`
- `$text_window`
- `$entity_ref`
- `$area_entity_ref`
- `$cell_flags_at`
- `$entities_at`
- `$entity_at`
- `$entities_query`
- `$entity_query`
- `$inventory_item_count`
- `$inventory_has_item`
- `$collection_item`
- `$add`
- `$subtract`
- `$multiply`
- `$divide`
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

Within one live runtime context, repeated reads of the same file reuse a small
in-memory cache. Rebuilding the runtime context starts fresh.

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

### `$area_entity_ref`

Returns one plain-data area-owned entity reference from another area by explicit `area_id` plus `entity_id`.

Shape:

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

Notes:

- `select` is required.
- missing entities in the target area return `default`.
- first-pass semantics are intentionally simple:
  - read the target area's own authored entities
  - apply that area's persistent overrides
  - do not layer in globals or travelers

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
      "fields": ["entity_id", "solid", "pushable"]
    }
  }
}
```

Ordering is the current runtime tile-query order:
- sorted by `(render_order, stack_order, entity_id)`
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
- sorted by `(render_order, stack_order, entity_id)`
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

### `$inventory_item_count`

Returns the total quantity of one item across an entity inventory.

Shape:

```json
{
  "$inventory_item_count": {
    "entity_id": "player",
    "item_id": "items/apple"
  }
}
```

### `$inventory_has_item`

Returns whether an entity inventory contains at least the requested quantity.

Shape:

```json
{
  "$inventory_has_item": {
    "entity_id": "player",
    "item_id": "items/copper_key",
    "quantity": 1
  }
}
```

### Shared Entity-Query `select` Shape

`$entity_ref`, `$entities_at`, `$entity_at`, `$entities_query`, and `$entity_query` all use the same `select` object, and all five currently require it.

Current shape:

```json
{
  "select": {
    "fields": ["entity_id", "grid_x", "grid_y", "solid", "pushable"],
    "variables": ["custom_state"],
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
- `facing`
- `solid`
- `pushable`
- `weight`
- `push_strength`
- `collision_push_strength`
- `interactable`
- `interaction_priority`
- `entity_commands_enabled`
- `render_order`
- `y_sort`
- `sort_y_offset`
- `stack_order`
- `tags`
- `inventory`

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
  "solid": true,
  "pushable": true,
  "variables": {
    "custom_state": "ready"
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
    "entity_commands_enabled": true
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
- `entity_commands_enabled`

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

### Arithmetic value sources

Arithmetic helpers resolve numeric values before a primitive command runs. Inline math strings such as `"$project.movement.ticks_per_tile / 2"` are not supported; use these structured value sources instead.

Examples:

```json
{ "$add": ["$self.grid_x", 1] }
```

```json
{ "$subtract": ["$self.grid_x", 1] }
```

```json
{ "$multiply": ["$offset_x", "$area.tile_size"] }
```

```json
{ "$divide": ["$project.movement.ticks_per_tile", 2] }
```

Notes:
- `$add` accepts zero or more numbers and returns their sum
- `$subtract` runs left-to-right and requires at least two numbers
- `$multiply` requires at least one number and returns their product
- `$divide` runs left-to-right, requires at least two numbers, and rejects division by zero
- prefer `$divide` over FPS when a clip should align to gameplay ticks, such as splitting `$project.movement.ticks_per_tile` across a fixed number of animation frames

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
      "$add": ["$self.dialogue_choice_index", "$delta"]
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
    "default": { "blocked": true }
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
    "field": "solid",
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
    "field": "pushable",
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

- `set_entity_grid_position(entity_id, x, y, mode?, persistent?)`
- `set_entity_world_position(entity_id, x, y, mode?, persistent?)`
- `set_entity_screen_position(entity_id, x, y, mode?, persistent?)`
- `step_in_direction(entity_id, direction?, push_strength?, duration?, frames_needed?, speed_px_per_second?, wait?, persistent?)`
- `push_facing(entity_id, direction?, push_strength?, duration?, frames_needed?, speed_px_per_second?, wait?, persistent?)`
- `move_entity_world_position(entity_id, x, y, mode?, duration?, frames_needed?, speed_px_per_second?, wait?, persistent?)`
- `move_entity_screen_position(entity_id, x, y, mode?, duration?, frames_needed?, speed_px_per_second?, wait?, persistent?)`
- `wait_for_move(entity_id)`

### Interaction

- `interact_facing(entity_id, direction?)`

Occupancy hooks are ordinary named entity commands on the stationary entity, not
standalone builtin commands:
- `on_occupant_enter`
- `on_occupant_leave`

Those hooks receive:
- runtime param `instigator_id`
- runtime params `from_x`, `from_y`, `to_x`, `to_y` when the relevant endpoints exist

`interact_facing` also supplies `instigator_id` to the target entity's `interact`
command.

### Dialogue

- `open_dialogue_session(dialogue_path? | dialogue_definition?, dialogue_on_start?, dialogue_on_end?, segment_hooks?, allow_cancel?, actor_id?, caller_id?, ui_preset?, entity_refs?)`
- `open_entity_dialogue(entity_id, dialogue_id?, dialogue_on_start?, dialogue_on_end?, segment_hooks?, allow_cancel?, actor_id?, caller_id?, ui_preset?, entity_refs?)`
- `close_dialogue_session()`

Current engine-owned dialogue runtime behavior:
- accepts exactly one dialogue source: either ordinary dialogue JSON by
  `dialogue_path`, or an inline `dialogue_definition` object with the same
  `segments` schema as a dialogue file
- reads named UI presets from `shared_variables.dialogue_ui`
- owns current segment, page, choice index, choice scroll, timer advance, and
  modal input behavior
- honors preset-driven choice layouts, including inline menus, separate choice
  panels, and marquee overflow for long selected options
- supports caller hooks through `dialogue_on_start`, `dialogue_on_end`, and
  `segment_hooks`
- dialogue command flows use `$self_id` as the dialogue owner/source entity and
  receive `$instigator_id` when that acting entity context exists
- explicit `entity_refs` are preserved as explicit named refs only; the runtime
  no longer invents implicit `caller` / `instigator` refs
- `actor_id` remains an explicit override, but when it is omitted and runtime
  `instigator_id` exists, the runtime uses that value as the dialogue actor
- `open_entity_dialogue` defaults `caller_id` to the target entity id when the
  caller does not override it
- currently also supports inline segment `on_start` / `on_end` and inline
  option `commands`
- choice options may also author exactly one first-class child branch through
  `next_dialogue_path` or `next_dialogue_definition`
- segments and choice options may author `end_dialogue: true` to make a path
  terminal without reaching later sibling segments
- when a choice option authors both side effects and a child branch, the
  runtime runs the option `commands` first, then opens the child branch, then
  resumes the parent and finishes the original segment after the child closes
- text segments with `end_dialogue: true` close after that segment finishes
- choice segments with `end_dialogue: true` close after the chosen option path
  finishes, including any child branch that option opens
- choice options with `end_dialogue: true` run their `commands` first and then
  close immediately without opening `next_dialogue_path` or
  `next_dialogue_definition`
- opening a child engine-owned dialogue suspends the parent session and
  resumes it after the child closes
- when both caller-provided hooks and inline dialogue commands exist for the
  same segment/option scope, caller hooks win and inline commands act as the
  default fallback

Practical note:
- inline option `commands` are appropriate for simple direct actions, including queued built-ins such as `new_game`, `load_game`, and `quit_game`
- `next_dialogue_path` / `next_dialogue_definition` are the preferred way for a
  choice option to continue into another dialogue branch without hiding that
  branch inside generic command JSON
- `end_dialogue: true` is the preferred way to mark a segment or option as a
  terminal authored path when the conversation should stop there
- `dialogue_on_end` is better when you need one shared post-close branch or cleanup after the session is fully closed

Controller-owned dialogue flows are valid advanced authored content for
projects that want custom orchestration. Engine-owned sessions are the standard
low-boilerplate path.

Movement timing precedence for interpolated move commands is:
- `frames_needed`
- `duration`
- `speed_px_per_second`
- engine default fallback

### Inventory

- `add_inventory_item(entity_id, item_id, quantity?, quantity_mode, result_var_name?, persistent?)`
- `remove_inventory_item(entity_id, item_id, quantity?, quantity_mode, result_var_name?, persistent?)`
- `use_inventory_item(entity_id, item_id, quantity?, result_var_name?, persistent?)`
- `set_inventory_max_stacks(entity_id, max_stacks, persistent?)`
- `open_inventory_session(entity_id, ui_preset?, wait?)`
- `close_inventory_session()`

Current inventory rules:

- `quantity_mode` is required on `add_inventory_item` and `remove_inventory_item`
- allowed modes are `"atomic"` and `"partial"`
- `result_var_name`, when provided, writes the result payload to
  `$self_id.variables[result_var_name]`
- current result shape is:
  - `success`
  - `item_id`
  - `requested_quantity`
  - `changed_quantity`
  - `remaining_quantity`
- if authored logic cares whether inventory state changed, it should check
  `changed_quantity > 0`
- `use_inventory_item` only consumes after the item's `use_commands` finish
  cleanly
- `open_inventory_session` opens the engine-owned inventory browser for one
  entity-owned inventory
- `open_inventory_session(wait=false)` returns immediately instead of waiting
  for the inventory session to close

### Animation, Audio, And Entity Visuals

- `play_animation(entity_id, visual_id?, animation, frame_count?, duration_ticks?, wait?)`
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
- `play_animation` plays a named clip from the target visual's `animations`
  object. It does not accept raw `frame_sequence`; author frame lists once on
  the visual clip and call them by name.
- `frame_count` limits how many sprite frames are consumed by this play. When
  omitted, the full clip is consumed.
- `duration_ticks` is the total simulation ticks this play should last. The
  engine distributes the selected sprite frames across that duration. If
  omitted, multi-frame clips use one simulation tick per selected frame, and a
  one-frame clip is applied immediately without becoming an active wait.
- `wait` defaults to `true` for active multi-tick playback. If the chosen clip
  resolves immediately, such as a one-frame idle clip with no `duration_ticks`,
  the command completes immediately either way.
- if the clip has `preserve_phase: true`, the next play starts where the
  previous play left off inside that clip
- use `$divide`, `$multiply`, `$add`, and `$subtract` value sources for timing
  math; inline math strings are not supported

Example movement-oriented command chain:

```json
{
  "params": ["direction", "walk_animation", "idle_animation"],
  "commands": [
    {
      "type": "play_animation",
      "entity_id": "$self_id",
      "visual_id": "body",
      "animation": "$walk_animation",
      "frame_count": 2,
      "duration_ticks": "$project.movement.ticks_per_tile",
      "wait": false
    },
    {
      "type": "step_in_direction",
      "entity_id": "$self_id",
      "direction": "$direction",
      "frames_needed": "$project.movement.ticks_per_tile",
      "wait": true
    },
    {
      "type": "play_animation",
      "entity_id": "$self_id",
      "visual_id": "body",
      "animation": "$idle_animation"
    }
  ]
}
```

- `play_audio` is one-shot sound-effect playback
- `set_sound_volume` affects future `play_audio` calls
- `play_music` uses the dedicated music channel and defaults to `loop = true`
- `play_music` does not restart the same already-playing track unless `restart_if_same` is `true`

### Screen-Space UI Elements

- `show_screen_image(element_id, path, x, y, frame_width?, frame_height?, frame?, layer?, anchor?, flip_x?, tint?, visible?)` â€” `anchor` defaults to `"topleft"`; valid values: `topleft`, `top`, `topright`, `left`, `center`, `right`, `bottomleft`, `bottom`, `bottomright`
- `show_screen_text(element_id, text, x, y, layer?, anchor?, color?, font_id?, max_width?, visible?)` â€” `anchor` values same as `show_screen_image`
- `set_screen_text(element_id, text)`
- `remove_screen_element(element_id)`
- `clear_screen_elements(layer?)`
- `play_screen_animation(element_id, frame_sequence, ticks_per_frame?, hold_last_frame?, wait?)`
- `wait_for_screen_animation(element_id)`

### Time And Flow Composition

- `wait_frames(frames)`
- `wait_seconds(seconds)`
- `spawn_flow(commands?, source_entity_id?, entity_refs?, refs_mode?)`
- `run_sequence(commands?, source_entity_id?, entity_refs?, refs_mode?)`
- `run_parallel(commands?, completion?, source_entity_id?, entity_refs?, refs_mode?)`
- `run_commands_for_collection(value?, commands?, item_param?, index_param?, source_entity_id?, entity_refs?, refs_mode?)` â€” iterates a list/tuple and runs `commands` once per item, injecting the current item and index as runtime params

Timing notes:

- `wait_frames` and `wait_seconds` are real waits; zero-dt settling does not
  advance them
- `run_sequence` runs its child list eagerly until a child command waits
- `spawn_flow` starts its child flow eagerly and returns immediately to the
  parent flow
- `run_parallel` starts children together; completion policy controls when the
  parent continues

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

### Entity And Project Command Dispatch

- `run_entity_command(entity_id, command_id, source_entity_id?, entity_refs?, refs_mode?, ...extra_params)`
- `run_project_command(command_id, source_entity_id?, entity_refs?, refs_mode?, ...extra_params)`

Both commands forward any additional fields on the command object into the called flow as runtime parameters. The called commands can read those values with `$param_name` tokens. For example, passing `"dialogue_path": "dialogues/system/pause_menu.json"` on a `run_entity_command` makes `$dialogue_path` available inside the target entity-command chain.

### Entity-Command/Input Routing

- `set_entity_command_enabled(entity_id, command_id, enabled, persistent?)`
- `set_entity_commands_enabled(entity_id, enabled, persistent?)`
- `set_input_target(action, entity_id?)`
- `route_inputs_to_entity(entity_id?, actions?)`
- `push_input_routes(actions?)`
- `pop_input_routes()`

Notes:
- `set_entity_command_enabled` targets one named entity command on one entity
- `set_entity_commands_enabled` gates the entity's command system as a whole
- `push_input_routes` stores the current routed target ids for the selected actions on a runtime stack
- `pop_input_routes` restores the most recently pushed routing snapshot for those actions

### Area / Save / Game Flow

- `change_area(area_id?, entry_id?, destination_entity_id?, transfer_entity_id?, transfer_entity_ids?, camera_follow?, allowed_instigator_kinds?, source_entity_id?, entity_refs?, refs_mode?)`
- `new_game(area_id?, entry_id?, destination_entity_id?, camera_follow?, source_entity_id?, entity_refs?, refs_mode?)`
- `load_game(save_path?)`
- `save_game(save_path?)`
- `quit_game()`

Notes:
- `camera_follow` uses the same structured follow object as `set_camera_policy.follow`
- omit `camera_follow` to leave the destination area's camera defaults alone
- set `camera_follow: null` to clear destination-area follow after load
- in `change_area` / `new_game`, `camera_follow.entity_id` may use runtime
  params/tokens such as `$instigator_id` when the command runs from a
  higher-level entity command
- `destination_entity_id` lets transferred entities land on a world-space entity
  in the destination area instead of only using an authored `entry_id`
- if both `destination_entity_id` and `entry_id` are provided,
  `destination_entity_id` wins
- `allowed_instigator_kinds` is an optional `change_area` guard for occupancy
  hooks. When present, the command only queues the active scene transition if
  runtime `instigator_id` exists in the current world and its `kind` is in
  the list. For direct occupancy-triggered uses, standard grid movement and
  push commands also treat that trigger cell as closed to entrants whose kind
  is not listed.
- `change_area`, `new_game`, and `load_game` are scene boundaries; once one of
  these requests runs, old-scene command work is cancelled and later commands in
  the same old-scene sequence do not continue

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
- `set_camera_policy(follow?, bounds?, deadzone?)`
- `push_camera_state()`
- `pop_camera_state()`
- `set_camera_bounds(x, y, width, height, space?)`
- `clear_camera_bounds()`
- `set_camera_deadzone(x, y, width, height, space?)`
- `clear_camera_deadzone()`
- `move_camera(x, y, space?, mode?, duration?, frames_needed?, speed_px_per_second?)`
- `teleport_camera(x, y, space?, mode?)`

Notes:
- authored `follow.mode` can be `entity` or `input_target`
- `set_camera_policy` uses patch semantics:
  - omitted section = unchanged
  - `null` section = clear
  - object = set
- use `clear_camera_follow`, `clear_camera_bounds`, and `clear_camera_deadzone`
  when you want the focused single-purpose clear commands
- `set_camera_bounds` uses `space: "world_pixel"` or `space: "world_grid"`
- `set_camera_deadzone` uses `space: "viewport_pixel"` or `space: "viewport_grid"`
- `move_camera` and `teleport_camera` use `space: "world_pixel"` or `space: "world_grid"`

### Entity State

- `set_entity_field(entity_id, field_name, value, persistent?)` - supported field names: `present`, `visible`, `facing`, `solid`, `pushable`, `weight`, `push_strength`, `collision_push_strength`, `interactable`, `interaction_priority`, `entity_commands_enabled`, `render_order`, `y_sort`, `sort_y_offset`, `stack_order`, `color`, `input_map`, `input_map.<action>`, and `visuals.<visual_id>.<field>`
- `set_visible(entity_id, visible, persistent?)`
- `visuals.<visual_id>.<field>` supports `flip_x`, `visible`, `current_frame`, `tint`, `offset_x`, `offset_y`, and `animation_fps`
- `set_entity_fields(entity_id, set, persistent?)` - structured batch mutation for `fields`, `variables`, and `visuals`; validates the full payload before applying any changes
- `set_present(entity_id, present, persistent?)`
- `set_color(entity_id, color, persistent?)`
- `destroy_entity(entity_id, persistent?)`
- `spawn_entity(entity?, entity_id?, template?, kind?, x?, y?, parameters?, present?, persistent?)` - two forms: pass a full `entity` dict, or pass individual fields (`entity_id`, `x`, `y`, and optionally `template`, `kind`, `parameters`)

### Current-Area And Entity Variables

- `set_current_area_var(name, value, persistent?)`
- `set_entity_var(entity_id, name, value, persistent?)`
- `set_entity_active_dialogue(entity_id, dialogue_id, persistent?)`
- `step_entity_active_dialogue(entity_id, delta?, wrap?, persistent?)`
- `set_entity_active_dialogue_by_order(entity_id, order, wrap?, persistent?)`
- `add_current_area_var(name, amount?, persistent?)`
- `value_mode: "raw"` is a valid authored top-level field on `set_current_area_var`, `set_entity_var`, `append_current_area_var`, and `append_entity_var`. It stores the supplied `value` without recursively resolving nested runtime tokens or value-source objects. Use this when storing command-list payloads or hook data that should later be executed with `run_sequence`.
- `add_entity_var(entity_id, name, amount?, persistent?)`
- `toggle_current_area_var(name, persistent?)`
- `toggle_entity_var(entity_id, name, persistent?)`
- `set_current_area_var_length(name, value?, persistent?)`
- `set_entity_var_length(entity_id, name, value?, persistent?)`
- `append_current_area_var(name, value, persistent?)`
- `append_entity_var(entity_id, name, value, persistent?)`
- `pop_current_area_var(name, store_var?, default?, persistent?)`
- `pop_entity_var(entity_id, name, store_var?, default?, persistent?)`
- `if(left, op?, right, then?, else?)`
- `set_area_var(area_id, name, value)`
- `set_area_entity_var(area_id, entity_id, name, value)`
- `set_area_entity_field(area_id, entity_id, field_name, value)`

Current comparison operators:
- `eq`
- `neq`
- `gt`
- `gte`
- `lt`
- `lte`

Notes:
- `set_current_area_var` and related current-area-variable commands operate on the live current-area/runtime variable store for the active play session
- in normal play, this is the authored surface for current area/runtime state that can also be persisted
- `open_entity_dialogue` resolves a named entry from the target entity's
  `dialogues` map; when `dialogue_id` is omitted it reads
  `entity.variables.active_dialogue`
- `set_entity_active_dialogue` writes one named dialogue id into the target
  entity's `active_dialogue` variable
- `step_entity_active_dialogue` moves forward/backward through the target
  entity's authored dialogue order; `delta` defaults to `1`
- `set_entity_active_dialogue_by_order` uses human-facing 1-based order; with
  `wrap: true`, out-of-range values wrap around the available dialogue list
- `toggle_current_area_var` / `toggle_entity_var` treat missing or `null` as `false`, then flip the value; non-boolean existing values raise an error
- entity-targeted mutation commands (`set_entity_var`, `add_entity_var`, `toggle_entity_var`, `set_entity_var_length`, `append_entity_var`, `pop_entity_var`, `set_entity_field`, `set_entity_fields`, `set_visible`, `set_present`, `set_color`, `destroy_entity`, `spawn_entity`, `set_entity_command_enabled`, `set_entity_commands_enabled`) inherit from the target entity's authored `persistence` block when `persistent` is omitted
- movement/position commands (`set_entity_grid_position`, `set_entity_world_position`, `set_entity_screen_position`, `step_in_direction`, `push_facing`, `move_entity_world_position`, `move_entity_screen_position`) also follow that same override-or-inherit rule
- inventory mutation commands (`add_inventory_item`, `remove_inventory_item`, `use_inventory_item`, `set_inventory_max_stacks`) treat inventory as coarse entity state and also follow that same override-or-inherit rule
- on those entity-targeted commands, explicit `persistent: true` / `persistent: false` overrides the entity policy
- current-area variable commands still use command-level persistence only; omitted `persistent` there means transient
- `set_area_var`, `set_area_entity_var`, and `set_area_entity_field` are always persistent cross-area writes
- cross-area writes target area-owned authored state plus overrides for the named `area_id`; they do not run live commands in unloaded rooms
- when a cross-area write targets the currently loaded area, the engine also mirrors the change into live runtime when possible

Example:

```json
{
  "type": "if",
  "left": "$current_area.gate_open",
  "op": "eq",
  "right": true,
  "then": [
    {
      "type": "set_entity_field",
      "entity_id": "gate",
      "field_name": "present",
      "value": false,
      "persistent": true
    }
  ],
  "else": [
    {
      "type": "set_entity_field",
      "entity_id": "gate",
      "field_name": "present",
      "value": true,
      "persistent": true
    }
  ]
}
```

### Reset / Persistence Helpers

- `reset_transient_state(entity_id?, entity_ids?, include_tags?, exclude_tags?, apply?)`
- `reset_persistent_state(include_tags?, exclude_tags?, apply?)`

Terms:
- `transient` - live session state that is not stored in persistence and disappears when runtime state is rebuilt
- `persistent` - saved runtime state that survives save/load and area rebuilds

`apply` controls when the reset takes effect:
- `apply: "immediate"` - clear matching state now and rebuild/apply the result immediately
- `apply: "on_reentry"` - clear matching state now, but do not rebuild the affected area until it is next loaded

## Deferred Nested Command Fields

Some command params intentionally defer nested command specs instead of resolving all nested `$...` values immediately.

Builtin deferred command fields are declared in the command registry with an explicit payload shape:

- `command_payload` - the value is one command object or a list of command objects
- `dialogue_definition` - the value is one inline dialogue definition whose command-bearing fields run later
- `dialogue_segment_hooks` - the value is a dialogue segment-hook list with command-bearing hook fields

Deferred builtin command params with `dialogue_definition` shape:

- `run_entity_command.dialogue_definition`
- `open_dialogue_session.dialogue_definition`

Deferred builtin command params with `command_payload` shape:

- `spawn_flow.commands`
- `run_sequence.commands`
- `run_parallel.commands`
- `run_commands_for_collection.commands`
- `if.then`
- `if.else`
- `run_entity_command.dialogue_on_start`
- `run_entity_command.dialogue_on_end`
- `open_dialogue_session.dialogue_on_start`
- `open_dialogue_session.dialogue_on_end`

Deferred builtin command params with `dialogue_segment_hooks` shape:

- `run_entity_command.segment_hooks`
- `open_dialogue_session.segment_hooks`

These are part of the active dialogue/controller surface.

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
- entity `entity_commands_enabled`
- entity `render_order`
- entity `y_sort`
- entity `sort_y_offset`
- entity `stack_order`
- entity `color`
- entity `input_map`
- entity `visuals`

### Grid Notes

Current grid blocking comes from:
- `cell_flags.blocked`
- solid world-space entities in the destination tile

Tile art itself does not define collision.

## Reserved Runtime Entity IDs

These names are reserved runtime references and should not be used as authored entity ids:

- `self`

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
- any `commands: [...]` body executes child commands in order by default
- `run_sequence` executes an explicit stored command-list value
- `run_parallel` executes child commands together with an explicit completion policy
- `spawn_flow` starts a separate flow and returns immediately

Routed input entity commands are ordinary root-flow dispatches, not a special busy-state exception.

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
- `advance_overrides`: optional object mapping specific characters to explicit pixel advances
- `glyph_order`: string listing each glyph in atlas order (left to right, top to bottom)

Current runtime behavior:

- The atlas is sliced into fixed `cell_width x cell_height` cells.
- Each glyph cell is trimmed to its non-transparent pixel bounds.
- By default, each glyph's advance width is the trimmed pixel width, clamped to at least `minimum_advance`.
- If `advance_overrides` contains a character, that override wins over the auto-measured width.
- The space character does not use atlas bounds; it always advances by `space_width`.
- Unknown characters fall back to `fallback_character` if that glyph exists.

Current defaults when optional fields are omitted:

- `columns` defaults to `len(glyph_order)`
- `line_height` defaults to `cell_height`
- `letter_spacing` defaults to `1`
- `space_width` defaults to `cell_width // 2`
- `fallback_character` defaults to `"?"`
- `minimum_advance` defaults to `1`

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

Font ids are the JSON filename without extension. The engine looks for `{font_id}.json` under `fonts/` in the project's asset paths, and also finds matching files recursively under those asset roots. For example, `assets/project/fonts/pixelbet.json` has font id `pixelbet`. Commands reference fonts through `font_id` parameters.

## Suggested Use

Use the docs together like this:

1. [Project Spirit](../../project/project-spirit.md)
   Read for philosophy and design intent.
2. [Authoring Guide](authoring-guide.md)
   Read for normal authoring workflow.
3. This file
   Read when you need exact current engine/JSON contract details.
