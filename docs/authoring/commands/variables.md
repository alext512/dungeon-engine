# Variable Commands

Variable commands read or write authored runtime state. Use this page with:

- [Command System](../command-system.md) for command-chain timing
- [Runtime Tokens](../reference/runtime-tokens.md) for values like `$self_id`
- [Built-in Commands](../reference/builtin-commands.md) for the quick command inventory

## Built-In Variable Primitives

The direct variable-write primitives are:

- [`set_current_area_var`](#set_current_area_var)
- [`set_entity_var`](#set_entity_var)

These are the core commands. Common numeric add, boolean toggle, and
value-length shortcuts should usually be project commands that wrap these
primitives with structured value sources.

The remaining variable helpers stay built in because they have specific runtime
contracts:

- `append_current_area_var` and `append_entity_var` copy and append to list
  variables
- `pop_current_area_var` and `pop_entity_var` mutate a list and can also store
  the popped value

## set_current_area_var

Writes one current-area runtime variable.

Important fields:

- `name`: variable name
- `value`: JSON value, runtime token, or structured value source
- `persistent`: optional save-state override; omitted means transient
- `value_mode`: optional advanced value mode; `raw` stores the value without
  resolving nested runtime tokens

Example:

```json
{
  "type": "set_current_area_var",
  "name": "gate_open",
  "value": true,
  "persistent": true
}
```

## set_entity_var

Writes one variable on one entity.

Important fields:

- `entity_id`: target entity id or token
- `name`: variable name
- `value`: JSON value, runtime token, or structured value source
- `persistent`: optional save-state override; omitted follows the entity's save
  rules
- `value_mode`: optional advanced value mode; `raw` stores the value without
  resolving nested runtime tokens

Example:

```json
{
  "type": "set_entity_var",
  "entity_id": "gate_1",
  "name": "open",
  "value": true
}
```

## Variable Project Command Presets

The sample project keeps common variable shortcuts under `commands/variables/`.
Use them through `run_project_command`.

### add_current_area_var Project Command

Adds a numeric amount to one current-area runtime variable. Missing variables
start from `0`.

```json
{
  "type": "run_project_command",
  "command_id": "commands/variables/add_current_area_var",
  "name": "score",
  "amount": 5
}
```

This is equivalent to:

```json
{
  "type": "set_current_area_var",
  "name": "score",
  "value": {
    "$add": [
      {
        "$current_area_var": {
          "name": "score",
          "default": 0
        }
      },
      5
    ]
  }
}
```

### add_entity_var Project Command

Adds a numeric amount to one entity variable. Missing variables start from `0`.

```json
{
  "type": "run_project_command",
  "command_id": "commands/variables/add_entity_var",
  "entity_id": "$self_id",
  "name": "current_count",
  "amount": 1
}
```

This is equivalent to:

```json
{
  "type": "set_entity_var",
  "entity_id": "$self_id",
  "name": "current_count",
  "value": {
    "$add": [
      {
        "$entity_var": {
          "entity_id": "$self_id",
          "name": "current_count",
          "default": 0
        }
      },
      1
    ]
  }
}
```

### toggle_current_area_var Project Command

Flips one current-area boolean variable. Missing or `null` means `false`, so
the first toggle stores `true`.

```json
{
  "type": "run_project_command",
  "command_id": "commands/variables/toggle_current_area_var",
  "name": "alarm_on"
}
```

This is equivalent to:

```json
{
  "type": "set_current_area_var",
  "name": "alarm_on",
  "value": {
    "$boolean_not": {
      "$current_area_var": {
        "name": "alarm_on"
      }
    }
  },
  "persistent": false
}
```

### toggle_entity_var Project Command

Flips one entity boolean variable. Missing or `null` means `false`, so the
first toggle stores `true`.

```json
{
  "type": "run_project_command",
  "command_id": "commands/variables/toggle_entity_var",
  "entity_id": "$self_id",
  "name": "enabled"
}
```

This is equivalent to:

```json
{
  "type": "set_entity_var",
  "entity_id": "$self_id",
  "name": "enabled",
  "value": {
    "$boolean_not": {
      "$entity_var": {
        "entity_id": "$self_id",
        "name": "enabled"
      }
    }
  },
  "persistent": null
}
```

### set_current_area_var_length Project Command

Stores the length of a supplied value into one current-area variable. `null`
has length `0`.

```json
{
  "type": "run_project_command",
  "command_id": "commands/variables/set_current_area_var_length",
  "name": "visited_room_count",
  "value": "$current_area.visited_rooms"
}
```

This is equivalent to:

```json
{
  "type": "set_current_area_var",
  "name": "visited_room_count",
  "value": {
    "$length": "$current_area.visited_rooms"
  },
  "persistent": false
}
```

### set_entity_var_length Project Command

Stores the length of a supplied value into one entity variable. `null` has
length `0`.

```json
{
  "type": "run_project_command",
  "command_id": "commands/variables/set_entity_var_length",
  "entity_id": "$self_id",
  "name": "history_count",
  "value": "$self.history"
}
```

This is equivalent to:

```json
{
  "type": "set_entity_var",
  "entity_id": "$self_id",
  "name": "history_count",
  "value": {
    "$length": "$self.history"
  },
  "persistent": null
}
```
