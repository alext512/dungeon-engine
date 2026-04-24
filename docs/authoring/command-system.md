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
  "type": "step_in_direction",
  "entity_id": "$self_id",
  "direction": "up",
  "frames_needed": "$project.movement.ticks_per_tile",
  "wait": false
}
```

There are two common authored shapes:

- one command object with a `type`
- one `commands: [...]` array, which means "run these commands in sequence"

There is no separate `type: "sequence"` wrapper today. The JSON array itself is
the default sequential-flow container.

Command arrays run in order unless you explicitly use a flow-composition command.

## Execution Timing

The command runner is eager. When a command chain is ready, it keeps running in
the same simulation tick until it reaches a real wait.

In practice:

- immediate commands after another immediate command run in the same tick
- immediate commands after a completed wait also run in that same tick
- a sequence only pauses when a command returns an incomplete async handle
- `wait=true` on a time-taking command blocks the current sequence until that
  work finishes
- `wait=false` starts the work and lets the current sequence continue
  immediately
- `spawn_flow` starts a child flow immediately and the parent sequence also
  continues immediately

The engine has command-runtime safety fuses for runaway immediate command
cascades. Those limits are error guardrails, not per-frame throttles. If ready
command work cannot settle within the configured limits, the runner logs a
command error instead of silently pushing ready work into a later tick.

## Example: Player Input Commands

The repo-local player template uses entity commands for input-driven behavior:

```json
{
  "move_up": [
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
      "type": "step_in_direction",
      "entity_id": "$self_id",
      "direction": "up",
      "frames_needed": "$project.movement.ticks_per_tile",
      "wait": false
    }
  ]
}
```

That pattern is very common:

- adjust entity state or visuals
- call a built-in movement or interaction command
- let runtime tokens fill in per-instance or per-session values

For entity commands specifically, prefer the array shorthand shown above. Use
the long object form only when you need metadata such as `enabled: false`.

## Main Command Families

### Movement and interaction

Use commands such as:

- `step_in_direction`
- `push_facing`
- `interact_facing`
- `set_entity_grid_position`
- `move_entity_world_position`

### Flow composition

Use commands such as:

- `run_sequence`
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

They can also forward named entity refs through `entity_refs`, which is one of the cleanest ways to keep authored flows reusable without hardcoding one concrete entity id.

Example:

```json
{
  "type": "run_project_command",
  "command_id": "commands/open_gate",
  "entity_refs": {
    "instigator": "$self_id",
    "gate": "gate_a"
  }
}
```

Inside the called flow:

- use `$ref_ids.gate` when a command field expects an entity id
- use `$refs.gate.some_var` when you want to read that referenced entity's variables
- use `refs_mode` on flow-composition commands when a child flow should inherit, merge, or replace the current named-ref map

## Flow Composition Patterns

### Sequential work

Just place commands in one array.

The array runs eagerly: if the first command completes immediately, the next
command starts immediately in the same tick. If the first command waits, the
sequence resumes immediately in the tick where that wait completes.

### Parallel work

Use `run_parallel` when multiple flows should start together.

Use `spawn_flow` instead when you want a fire-and-forget child flow: the child
starts now, and the parent does not wait for it.

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

## Scene Boundaries

Commands that change the active scene/session, such as `change_area`,
`new_game`, and `load_game`, are scene boundaries.

When a scene-boundary command runs:

- the request is applied at the scene-boundary phase of the current tick
- old-scene command work is cancelled
- commands after the boundary command in that old scene do not continue
- preserving a flow across a scene change is not implicit; that would need a
  future explicit API

## Runtime Tokens And Value Sources

Commands can reference runtime data through tokens such as:

- `$self_id`
- `$ref_ids.some_name`
- `$refs.some_name.some_var`
- `$current_area.some_var`
- `$project.some_value`
- `$param_name`

Author-facing `entity_refs` inputs populate the runtime `$refs...` and `$ref_ids...` token families.

The engine also supports richer structured value-source objects. See [Runtime Tokens](reference/runtime-tokens.md) for the quick map and the repo's JSON interface doc for the exhaustive surface.

One practical rule matters a lot: strict primitive commands still expect real entity ids in fields like `entity_id`, so use `$self_id` or `$ref_ids.some_name` there instead of inventing your own symbolic string format.

## Validation Matters

If you change command names, command ids, or command-bearing JSON surfaces, relaunch early and often.

This project treats command-surface drift as a serious risk because one renamed command id or moved reference can break authored content long before you notice it in gameplay.

The exact startup audit surface is documented in [Startup Checks](startup-checks.md). If you are changing Python code or maintaining repo-local example projects, the contributor workflow lives in [Verification and Validation](../development/verification-and-validation.md).

## Exact Reference

For the complete built-in inventory, signatures, deferred nested command fields, and command-chain rules, use:

- [Built-in Commands](reference/builtin-commands.md)
- [Engine JSON Interface](manuals/engine-json-interface.md)
