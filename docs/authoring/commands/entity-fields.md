# Entity Field Commands

Entity field commands change engine-owned entity state. Use this page with:

- [Command System](../command-system.md) for command-chain timing
- [Built-in Commands](../reference/builtin-commands.md) for the quick command inventory
- [Engine JSON Interface](../manuals/engine-json-interface.md) for the exact contract

## Built-In Entity Field Primitives

The direct entity-field primitives are:

- [`set_entity_field`](#set_entity_field)
- [`set_entity_fields`](#set_entity_fields)

Common author-friendly shortcuts such as `set_visible`, `set_present`,
`set_color`, `set_visual_frame`, `set_visual_flip_x`, and
`set_entity_commands_enabled` should usually be project commands that wrap
these primitives.

## set_entity_field

Changes one supported engine-owned field on one entity.

Important fields:

- `entity_id`: target entity id or token
- `field_name`: one supported entity field path
- `value`: new value for that field
- `persistent`: optional save-state override

Supported top-level field names include `present`, `visible`, `facing`,
`solid`, `pushable`, `weight`, `push_strength`, `collision_push_strength`,
`interactable`, `interaction_priority`, `entity_commands_enabled`,
`render_order`, `y_sort`, `sort_y_offset`, `stack_order`, and `color`.

Visual field paths use `visuals.<visual_id>.<field>`. Supported visual fields
are `flip_x`, `visible`, `current_frame`, `tint`, `offset_x`, `offset_y`, and
`animation_fps`.

Changing `present` through this command uses the normal occupancy transition
path, so occupant enter/leave hooks can run.

Example:

```json
{
  "type": "set_entity_field",
  "entity_id": "gate_1",
  "field_name": "visible",
  "value": false
}
```

Color example:

```json
{
  "type": "set_entity_field",
  "entity_id": "crate_1",
  "field_name": "color",
  "value": [120, 80, 40]
}
```

## set_entity_fields

Changes several entity fields, variables, and visual fields in one validated
batch.

Important fields:

- `entity_id`: target entity id or token
- `set.fields`: top-level engine-owned fields
- `set.variables`: ordinary entity variables
- `set.visuals.<visual_id>`: visual field changes
- `persistent`: optional save-state override

The full payload is validated before any change is applied. Use this when a
single authored action needs multiple state changes to happen together.

Example:

```json
{
  "type": "set_entity_fields",
  "entity_id": "gate_1",
  "set": {
    "fields": {
      "present": false
    },
    "variables": {
      "opened": true
    },
    "visuals": {
      "main": {
        "visible": false
      }
    }
  }
}
```

## Entity Field Project Command Presets

The sample project keeps common entity-field shortcut shapes under
`commands/entity/`. Use them through `run_project_command`.

### set_visible Project Command

Sets one entity's `visible` field.

```json
{
  "type": "run_project_command",
  "command_id": "commands/entity/set_visible",
  "entity_id": "gate_1",
  "visible": false
}
```

### set_present Project Command

Sets one entity's `present` field. This still uses the built-in
`set_entity_field` behavior underneath, including occupancy enter/leave hooks.

```json
{
  "type": "run_project_command",
  "command_id": "commands/entity/set_present",
  "entity_id": "pickup_1",
  "present": false
}
```

### set_color Project Command

Sets one entity's RGB debug/fallback render color.

```json
{
  "type": "run_project_command",
  "command_id": "commands/entity/set_color",
  "entity_id": "crate_1",
  "red": 120,
  "green": 80,
  "blue": 40
}
```

### set_visual_frame Project Command

Sets one visual's `current_frame` field. Unlike the older built-in shortcut,
this project command asks for an explicit `visual_id`.

```json
{
  "type": "run_project_command",
  "command_id": "commands/entity/set_visual_frame",
  "entity_id": "gate_1",
  "visual_id": "main",
  "frame": 2
}
```

### set_visual_flip_x Project Command

Sets one visual's `flip_x` field. Use this when the authoring intent is
"mirror this named visual" rather than "edit an arbitrary visual field."

```json
{
  "type": "run_project_command",
  "command_id": "commands/entity/set_visual_flip_x",
  "entity_id": "player",
  "visual_id": "main",
  "flip_x": true
}
```

### set_entity_commands_enabled Project Command

Sets the entity-wide `entity_commands_enabled` field. Use this to temporarily
gate all named entity commands on one entity without editing each command entry.

```json
{
  "type": "run_project_command",
  "command_id": "commands/entity/set_entity_commands_enabled",
  "entity_id": "old_miner",
  "enabled": false
}
```
