# Camera Commands

Camera commands change the runtime camera policy or move the camera directly.

Use this page with:

- [Command System](../command-system.md) for command-chain timing
- [Runtime Tokens](../reference/runtime-tokens.md) for values like `$camera.x`
- [Built-in Commands](../reference/builtin-commands.md) for the quick command inventory

## Built-In Camera Primitives

The built-in camera primitives are:

- [`set_camera_policy`](#set_camera_policy)
- [`move_camera`](#move_camera)
- `push_camera_state`
- `pop_camera_state`

Common author-friendly shortcuts such as `clear_camera_follow` and
`set_camera_bounds` should usually be project commands that wrap these
primitives.

## set_camera_policy

Patches the camera's follow, bounds, and deadzone policy.

Use this when one command should update one or more camera-policy sections
atomically.

Patch behavior:

- omitted section: keep the existing value
- `null`: clear that section
- object: set that section

Important fields:

- `follow`: `null` or an object with `mode`
- `bounds`: `null` or a world-space rectangle
- `deadzone`: `null` or a viewport-space rectangle

`follow.mode` can be:

- `entity`: follow one explicit `entity_id`
- `input_target`: follow whichever entity currently owns one routed input `action`

Example:

```json
{
  "type": "set_camera_policy",
  "follow": null,
  "bounds": {
    "x": 0,
    "y": 0,
    "width": 20,
    "height": 15,
    "space": "world_grid"
  },
  "deadzone": null
}
```

Follow an input route:

```json
{
  "type": "set_camera_policy",
  "follow": {
    "mode": "input_target",
    "action": "move_up",
    "offset_x": 0,
    "offset_y": -8
  }
}
```

Related project-command presets:

- [`commands/camera/clear_camera_follow`](#clear_camera_follow-project-command)
- [`commands/camera/set_camera_bounds`](#set_camera_bounds-project-command)
- [`commands/camera/clear_camera_bounds`](#clear_camera_bounds-project-command)
- [`commands/camera/set_camera_deadzone`](#set_camera_deadzone-project-command)
- [`commands/camera/clear_camera_deadzone`](#clear_camera_deadzone-project-command)

## move_camera

Moves the camera in world coordinates and clears active camera follow.

Use this for direct camera motion, pans, and scripted shifts. Set
`frames_needed` to `0` when you want an instant move.

Important fields:

- `x`: target x coordinate or delta
- `y`: target y coordinate or delta
- `space`: `world_pixel` or `world_grid`
- `mode`: `absolute` or `relative`
- `duration`: optional duration in seconds
- `frames_needed`: optional duration in simulation frames
- `speed_px_per_second`: optional movement speed

Example:

```json
{
  "type": "move_camera",
  "x": 4,
  "y": 0,
  "space": "world_grid",
  "mode": "relative",
  "frames_needed": 12
}
```

Instant movement:

```json
{
  "type": "move_camera",
  "x": 0,
  "y": 0,
  "space": "world_grid",
  "mode": "absolute",
  "frames_needed": 0
}
```

Related project-command preset:

- [`commands/camera/teleport_camera`](#teleport_camera-project-command)

## Camera Project Command Presets

The sample project keeps common camera authoring shapes under
`commands/camera/`. Use them through `run_project_command`.

### clear_camera_follow Project Command

Clears camera follow without changing bounds or deadzone.

```json
{
  "type": "run_project_command",
  "command_id": "commands/camera/clear_camera_follow"
}
```

### set_camera_bounds Project Command

Sets camera bounds using a shorter author-facing command shape.

```json
{
  "type": "run_project_command",
  "command_id": "commands/camera/set_camera_bounds",
  "x": 0,
  "y": 0,
  "width": 20,
  "height": 15,
  "space": "world_grid"
}
```

### clear_camera_bounds Project Command

Clears camera bounds without changing follow or deadzone.

```json
{
  "type": "run_project_command",
  "command_id": "commands/camera/clear_camera_bounds"
}
```

### set_camera_deadzone Project Command

Sets the viewport-space deadzone used while following an entity.

```json
{
  "type": "run_project_command",
  "command_id": "commands/camera/set_camera_deadzone",
  "x": 4,
  "y": 3,
  "width": 8,
  "height": 6,
  "space": "viewport_grid"
}
```

### clear_camera_deadzone Project Command

Clears the follow deadzone without changing follow or bounds.

```json
{
  "type": "run_project_command",
  "command_id": "commands/camera/clear_camera_deadzone"
}
```

### teleport_camera Project Command

Moves the camera instantly by wrapping `move_camera` with `frames_needed: 0`.

```json
{
  "type": "run_project_command",
  "command_id": "commands/camera/teleport_camera",
  "x": 0,
  "y": 0,
  "space": "world_grid",
  "mode": "absolute"
}
```
