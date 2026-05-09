# Movement Commands

Movement commands change entity position directly or run the standard grid
movement rules.

Use this page with:

- [Command System](../command-system.md) for command-chain timing
- [Runtime Tokens](../reference/runtime-tokens.md) for values like `$self_id`
- [Built-in Commands](../reference/builtin-commands.md) for the quick command inventory

## Built-In Position Primitives

The direct position primitives are:

- [`set_entity_position`](#set_entity_position)
- [`move_entity_position`](#move_entity_position)

Common author-friendly shortcuts such as `set_entity_grid_position` and
`move_entity_screen_position` should usually be project commands that wrap these
primitives.

For normal gameplay walking, prefer `step_in_direction`. It applies the engine's
grid collision, push, facing, and occupancy hook rules. The direct position
primitives are for authored placement, scripted slides, UI motion, special
puzzle logic, or custom movement rules.

## set_entity_position

Instantly changes one entity's position.

Important fields:

- `entity_id`: target entity id or token
- `space`: `world_grid`, `world_pixel`, or `screen_pixel`
- `x`: coordinate or delta
- `y`: coordinate or delta
- `mode`: `absolute` or `relative`
- `persistent`: optional save-state override

`world_grid` changes logical grid occupancy. It does not snap the entity's
pixel position to the grid. Use it when you intentionally want grid state and
visual position to remain separate.

`world_pixel` requires a world-space entity and changes its world pixel
position. `screen_pixel` requires a screen-space entity and changes its screen
pixel position.

Example:

```json
{
  "type": "set_entity_position",
  "entity_id": "door_1",
  "space": "world_grid",
  "x": 5,
  "y": 8,
  "mode": "absolute"
}
```

Screen-space example:

```json
{
  "type": "set_entity_position",
  "entity_id": "title_logo",
  "space": "screen_pixel",
  "x": 12,
  "y": -4,
  "mode": "relative"
}
```

Related project-command presets:

- [`commands/entity/set_entity_grid_position`](#set_entity_grid_position-project-command)
- [`commands/entity/set_entity_world_position`](#set_entity_world_position-project-command)
- [`commands/entity/set_entity_screen_position`](#set_entity_screen_position-project-command)

## move_entity_position

Moves one entity through pixel space over time.

Important fields:

- `entity_id`: target entity id or token
- `space`: `world_pixel` or `screen_pixel`
- `x`: target coordinate or delta
- `y`: target coordinate or delta
- `mode`: `absolute` or `relative`
- `duration`: optional duration in seconds
- `frames_needed`: optional duration in simulation frames
- `speed_px_per_second`: optional movement speed
- `wait`: whether the parent command flow waits for movement to finish
- `persistent`: optional save-state override

Example:

```json
{
  "type": "move_entity_position",
  "entity_id": "title_logo",
  "space": "screen_pixel",
  "x": 0,
  "y": -24,
  "mode": "relative",
  "frames_needed": 20,
  "wait": true
}
```

Related project-command presets:

- [`commands/entity/move_entity_world_position`](#move_entity_world_position-project-command)
- [`commands/entity/move_entity_screen_position`](#move_entity_screen_position-project-command)

## Movement Project Command Presets

The sample project keeps common position-command shapes under
`commands/entity/`. Use them through `run_project_command`.

### set_entity_grid_position Project Command

Sets a world entity's logical grid position.

```json
{
  "type": "run_project_command",
  "command_id": "commands/entity/set_entity_grid_position",
  "entity_id": "crate_1",
  "x": 4,
  "y": 6,
  "mode": "absolute"
}
```

### set_entity_world_position Project Command

Sets a world entity's pixel position.

```json
{
  "type": "run_project_command",
  "command_id": "commands/entity/set_entity_world_position",
  "entity_id": "spark",
  "x": 128,
  "y": 64,
  "mode": "absolute"
}
```

### set_entity_screen_position Project Command

Sets a screen-space entity's pixel position.

```json
{
  "type": "run_project_command",
  "command_id": "commands/entity/set_entity_screen_position",
  "entity_id": "title_logo",
  "x": 0,
  "y": -12,
  "mode": "relative"
}
```

### move_entity_world_position Project Command

Moves a world entity through world-pixel space.

```json
{
  "type": "run_project_command",
  "command_id": "commands/entity/move_entity_world_position",
  "entity_id": "spark",
  "x": 32,
  "y": 0,
  "mode": "relative",
  "frames_needed": 12,
  "wait": false
}
```

### move_entity_screen_position Project Command

Moves a screen-space entity through screen-pixel space.

```json
{
  "type": "run_project_command",
  "command_id": "commands/entity/move_entity_screen_position",
  "entity_id": "title_logo",
  "x": 0,
  "y": 0,
  "duration": 1.1,
  "wait": false
}
```
