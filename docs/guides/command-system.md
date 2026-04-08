# Command System

The command runner is the main gameplay orchestration layer in this engine.

## Why Commands Matter

Instead of hardcoding a Python script for every NPC, switch, or menu, the engine expects most gameplay behavior to be expressed as JSON command chains.

That gives you:

- reusable authored behavior
- data-driven puzzle logic
- less hidden one-off game code
- a stable content contract that tools can target

## Where Commands Show Up

Commands can appear in several places:

- entity `entity_commands`
- area `enter_commands`
- project command files under `commands/`
- item `use_commands`
- dialogue hooks such as `dialogue_on_start`, `dialogue_on_end`, and segment hooks
- inline dialogue option commands for simple direct actions

## Basic Shape

A typical command object has a `type` plus fields specific to that command:

```json
{
  "type": "move_in_direction",
  "entity_id": "$self_id",
  "direction": "up",
  "frames_needed": "$project.movement.ticks_per_tile",
  "wait": false
}
```

Command arrays run in order unless you explicitly use a flow-composition command.

## Example: Player Input Commands

The repo-local player template uses entity commands for input-driven behavior:

```json
{
  "move_up": {
    "enabled": true,
    "commands": [
      {
        "type": "set_entity_fields",
        "entity_id": "$self_id",
        "set": {
          "visuals": {
            "up": { "visible": true, "current_frame": 1 }
          }
        }
      },
      {
        "type": "move_in_direction",
        "entity_id": "$self_id",
        "direction": "up",
        "frames_needed": "$project.movement.ticks_per_tile",
        "wait": false
      }
    ]
  }
}
```

That pattern is very common:

- adjust entity state or visuals
- call a built-in movement or interaction command
- let runtime tokens fill in per-instance or per-session values

## Main Command Families

### Movement and interaction

Use commands such as:

- `move_in_direction`
- `push_facing`
- `interact_facing`
- `set_entity_grid_position`
- `move_entity_world_position`

### Flow composition

Use commands such as:

- `run_commands`
- `spawn_flow`
- `run_parallel`
- `run_commands_for_collection`
- `if`

### Dispatch

Use commands such as:

- `run_entity_command`
- `run_project_command`

### Runtime/session control

Use commands such as:

- `change_area`
- `new_game`
- `save_game`
- `load_game`
- `open_dialogue_session`
- `open_inventory_session`

## `run_entity_command` vs `run_project_command`

Use `run_entity_command` when the behavior belongs to a specific entity or template.

Use `run_project_command` when the behavior is project-wide reusable logic that should not live on one particular entity instance.

Both commands can forward extra fields as runtime params, which the called flow can read through `$param_name` tokens.

## Flow Composition Patterns

### Sequential work

Just place commands in one array.

### Parallel work

Use `run_parallel` when multiple flows should start together.

### Conditional work

Use `if` when one branch depends on current values.

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

## Runtime Tokens And Value Sources

Commands can reference runtime data through tokens such as:

- `$self_id`
- `$current_area.some_var`
- `$project.some_value`
- `$param_name`
- `$entity_refs.some_name`

The engine also supports richer structured value-source objects. See [Runtime Tokens](../reference/runtime-tokens.md) for the quick map and the repo's JSON interface doc for the exhaustive surface.

## Validation Matters

If you change command names, command ids, or command-bearing JSON surfaces:

- run the relevant tests
- validate repo-local projects directly
- prefer startup-style validation paths

This project already treats command-surface drift as a serious risk because a generic engine test pass does not guarantee that every authored project still validates.

## Exact Reference

For the complete built-in inventory, signatures, deferred nested command fields, and command-chain rules, use:

- [Built-in Commands](../reference/builtin-commands.md)
- [ENGINE_JSON_INTERFACE.md](https://github.com/alext512/dungeon-engine/blob/main/ENGINE_JSON_INTERFACE.md)
