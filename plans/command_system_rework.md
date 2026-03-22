# Command System Rework

## Purpose

This document captures the proposed redesign of the command system so the
engine stays minimal, movement and animation stay separate, and higher-level
gameplay behaviors can be authored as reusable JSON commands.

This note is intentionally concrete enough to survive context compression or a
handoff to another agent.

## Current progress

Implemented in the first movement-foundation slice:

- `MovementState` now stores explicit pixel start/end positions in addition to
  grid metadata.
- `MovementSystem` now supports arbitrary transform motion through:
  - `request_move_to_position(...)`
  - `request_move_by_offset(...)`
  - `request_grid_step(...)`
- Grid synchronization is now explicit via policies:
  - `immediate`
  - `on_complete`
  - `none`
- Command specs now support an optional generic `on_complete` command chain.
- Built-in command primitives now include:
  - `move_entity`
  - `teleport_entity`
  - `move_entity_one_tile`
  - `wait_for_move`
- Movement commands can now also be authored with `frames_needed`, matching the
  old project's frame-count style.
- A command-driven one-shot sprite playback layer now exists through:
  - `play_animation`
  - `wait_for_animation`
  - `stop_animation`
  - `set_sprite_frame`
- Command-driven animation can run non-blocking so a move command and an
  animation command can be started back-to-back, like the old project did from
  `player_movement.gd`.
- Entities now support named events with their own enabled state.
- Entities now also support a global `events_enabled` gate that can disable all
  named events on that entity without affecting visibility or solidity.
- Entities now also support a whole-entity `present` flag:
  - `present = false` keeps the entity authored and serializable
  - but removes it from rendering, collision, interaction, animation, and
    movement queries
- Entity authoring/persistence now treats:
  - `x` / `y` as the default logical grid position
  - `pixel_x` / `pixel_y` as optional transform overrides
  - when `pixel_x` / `pixel_y` are omitted, they are derived from `x` / `y`
- Legacy `interact_commands` are auto-wrapped into an `interact` event for
  compatibility.
- Built-in event primitives now include:
  - `run_event`
  - `set_event_enabled`
  - `set_events_enabled`
- Built-in input/control primitives now include:
  - `set_active_entity`
  - `set_input_event_name`
- Built-in entity lifecycle primitives now include:
  - `set_present`
  - `spawn_entity`
  - `destroy_entity`
- Input now drives project-authored player movement events instead of a
  hardcoded engine movement command.
- The world now tracks `active_entity_id`, so inputs are routed to the current
  active entity rather than being inherently player-specific.
- Project manifests now define the default `active_entity_id` and default
  `input_events`, while areas may still override `active_entity_id`.
- Project manifests now also define `command_paths`, and `run_named_command`
  loads reusable JSON command definitions from there on demand.
- Command ids are now path-based relative to `command_paths`, so nested command
  folders stay unambiguous.
- Named-command validation now runs at project startup for both the game and
  editor:
  - malformed command files
  - duplicate command ids
  - literal missing `run_named_command` targets in command files, entity
    templates, and area JSON
  are logged to `logs/error.log` and block launch early.
- Named-command runtime failures still log full detail to `logs/error.log`, and
  active play mode surfaces a short in-game hint to check the log.
- Built-in movement/query primitives now also include:
  - `set_facing`
  - `query_facing_state`
  - `run_facing_event`
- `test_project` now uses:
  - `attempt_move_one_tile` to probe ahead, delegate push behavior, and re-probe
  - `walk_one_tile` as the actual walking half-cycle command
- Pushing in the test project now follows the old project's spirit more closely:
  - the actor delegates to the object in front via directional push events
  - the object decides whether it can move itself
  - the actor only walks after the path becomes free
- The test player's walk recipe now carries a simple alternating `walk_phase`
  variable across successful moves.
- The play loop now runs gameplay on a fixed simulation timestep of
  `1 / FPS` seconds instead of advancing movement directly from variable render
  `dt`.
- Movement interpolation is now tick-counted:
  - movement state stores `elapsed_ticks` / `total_ticks`
  - a 16 px move over 16 ticks advances by exactly 1 px per simulation tick
- Command-driven animation playback is now advanced by simulation ticks as
  well, matching the old project's `_physics_process` style more closely.
- `test_project/entities/player.json` now owns the first project-authored move
  recipes through `move_up`, `move_down`, `move_left`, and `move_right`.
- The runtime now also has a generic screen-space element layer with command
  primitives for:
  - `show_screen_image`
  - `show_screen_text`
  - `set_screen_text`
  - `remove_screen_element`
  - `clear_screen_elements`
  - `play_screen_animation`
  - `wait_for_screen_animation`
- The runtime now also has a blocking text-only `run_dialogue` primitive that:
  - uses project-authored dialogue defaults
  - wraps text by measured pixel width
  - paginates wrapped text by configured `max_lines`
  - advances pages on action-button presses
- Projects can now also store reusable dialogue content in `dialogues/` JSON
  files and invoke them by `dialogue_id` from `run_dialogue`.
- The sample project now handles panel images, portraits, and dialogue choices
  outside `run_dialogue` through normal screen-space commands plus a hidden
  `dialogue_controller` entity that receives dialogue input through events.

Not implemented yet in this slice:

- richer player animation recipes such as directional frames and walk-cycle
  phase carry-over
- persistence for dynamically spawned entities that do not exist in authored
  room data
- a final movement/render quality pass to confirm pixel-perfect feel on real
  hardware, especially camera behavior, frame pacing, and any remaining visual
  jitter

## Goals

- Keep only primitive, engine-owned commands in Python.
- Move higher-level behaviors into JSON-defined composite commands.
- Separate movement, animation, interaction, and composition concerns.
- Make movement/animation synchronization easy and exact when desired.
- Preserve enough flexibility that a project can define its own complex
  commands without depending on engine-shipped composites.

## Current Python Runtime

### Current entity position model

See [entity.py](../dungeon_engine/world/entity.py).

Each entity currently stores:

- `grid_x`, `grid_y`: logical tile position
- `pixel_x`, `pixel_y`: visual/interpolated position in pixels
- `movement`: transition state with:
  - `start_grid_x`, `start_grid_y`
  - `target_grid_x`, `target_grid_y`
  - `elapsed`
  - `duration`

### Current movement behavior

See [movement.py](../dungeon_engine/systems/movement.py).

`MovementSystem.request_step(...)` currently:

1. Resolves the target tile from the direction.
2. Checks solid blockers and walkability.
3. Handles simple pushable-block movement.
4. Starts movement interpolation.
5. Immediately updates `entity.grid_x` and `entity.grid_y` to the target tile.

Important consequence:

- During movement, `grid_x/grid_y` already represent the reserved/logical
  destination tile.
- The visual "in-between" position is represented by `pixel_x/pixel_y`.
- The source tile is still available through `movement.start_grid_x/y`.

### Where occupancy is currently queried from

See [world.py](../dungeon_engine/world/world.py).

The runtime currently derives occupancy directly from the entity state above:

- `World.get_entities_at(...)` returns entities whose `grid_x/grid_y` match the
  requested tile.
- There is no separate runtime occupancy array for entities.
- Because `grid_x/grid_y` are updated immediately when movement starts, other
  systems already see the destination tile as occupied while the sprite is still
  visually crossing the gap.

This means the current Python engine does not need a separate "update map
occupancy" command like the old Godot project did, because occupancy is derived
from entity grid coordinates rather than a second map array.

### Current animation behavior

See [animation.py](../dungeon_engine/systems/animation.py).

Animation is already separate from movement at the system level:

- `AnimationSystem` advances sprite frames independently.
- It currently uses elapsed time (`animation_elapsed * animation_fps`).
- If `animate_when_moving` is true, animation resets to frame 0 when movement
  stops.

Current limitation:

- Animation is time-driven, not distance-driven.
- Exact synchronization to tile distance is possible only indirectly by tuning
  `animation_fps` and movement duration.
- Carrying a walk-cycle phase across consecutive moves is awkward.

## Old Godot Reference

The old project split these concerns more explicitly.

Relevant files:

- [player_movement.gd](../../dungeon-puzzle-2/scripts/player_movement.gd)
- [movement_command.gd](../../dungeon-puzzle-2/scripts/commands/movement_command.gd)
- [movement_on_map_command.gd](../../dungeon-puzzle-2/scripts/commands/movement_on_map_command.gd)
- [animation_command.gd](../../dungeon-puzzle-2/scripts/commands/animation_command.gd)
- [execute_commands_command.gd](../../dungeon-puzzle-2/scripts/commands/execute_commands_command.gd)
- [filter_command.gd](../../dungeon-puzzle-2/scripts/commands/filter_command.gd)
- [Player.tscn](../../dungeon-puzzle-2/scenes/Prefabs/For_All_Levels/Player.tscn)

### How the old project handled a move

Input code in `player_movement.gd` orchestrated movement:

1. Start an animation command.
2. Check what is ahead.
3. If free, execute a movement command group.
4. If movable, try to push and then move.

The `Move_Player_*` command groups in `Player.tscn` contained separate nodes for:

- area enter/leave checks
- visual interpolation (`movement_command.gd`)
- logical map occupancy updates (`movement_on_map_command.gd`)

Animation was also separate:

- `Animation_Up`, `Animation_Left`, etc. were command groups
- those groups contained actual animation commands and variable toggles

### How the old project handled walk-cycle continuity

The old player scene alternated between two movement animation groups for the
same direction.

For example, `Animation_Up` toggled between:

- `Animation1` with sprites like `[9, 10]`
- `Animation2` with sprites like `[11, 10]`

This effectively let one tile move play the first half of a walk cycle and the
next tile move play the second half.

That idea is worth keeping. One small disagreement with the literal old setup:
the Python runtime does not need separate disabled/enabled node objects just to
carry phase. The same behavior can be expressed more simply through command data
and variables.

## Proposed Design

## Command tiers

### 1. Primitive engine commands

These are direct wrappers over runtime systems or state mutations. They are the
only commands that must live in Python.

Draft primitive set:

- `sequence`
- `parallel`
- `if_var`
- `wait`
- `set_var`
- `increment_var`
- `clear_var`
- `copy_var`
- `set_facing`
- `move_entity_one_tile`
- `can_move_one_tile`
- `wait_for_move`
- `set_animation_state`
- `start_animation`
- `stop_animation`
- `wait_for_animation`
- `set_visible`
- `set_solid`
- `set_present`
- `set_color`
- `destroy_entity`
- `spawn_entity`
- `teleport_entity`
- `query_facing_target`
- `query_entities_at`
- `set_cell_flag`
- `set_tile`
- `reset_transient_state`
- `reset_persistent_state`

Not all of these need to be implemented at once. The movement/animation subset
is the first important slice.

### 2. Optional engine-library composite commands

These are JSON-defined commands shipped as examples or conveniences.

Examples:

- `player_move_one_tile`
- `interact_facing`
- `push_block_forward`
- `toggle_gate`

These should be optional. Projects may use them, replace them, or ignore them.

### 3. Project-defined composite commands

These live in project JSON and express project logic.

Examples:

- player controls
- enemy behaviors
- puzzle interactions
- cutscene actions
- item usage

## Position and movement semantics

### Recommended movement semantics

Keep the current Python occupancy model:

- `grid_x/grid_y` represent the logical reserved tile once movement starts.
- `pixel_x/pixel_y` represent the exact visual position while moving.
- `movement.start_grid_*` and `movement.target_grid_*` describe the transition.

Reason:

- collision and occupancy queries stay simple
- pushing and reservation stay deterministic
- the engine does not need a second "move on map" primitive just to update
  occupancy bookkeeping

This differs from the old Godot project because the old project had a separate
map-array bookkeeping structure.

### Current limitation: movement is still too grid-specific

The current Python runtime is still narrower than the old project in one
important way:

- authored entity placement is grid-based (`x`, `y` in area JSON)
- runtime movement is currently implemented only as a one-tile grid step
- animation can react to movement, but movement itself is not a general-purpose
  transform command yet

The old Godot `movement_command.gd` was more flexible:

- move from current position to end position
- move from explicit start position to end position
- move by a specific distance
- interpret those values either in tiles or pixels

The redesign should recover that flexibility.

### Recommended split: transform movement vs grid occupancy

Movement should not mean only "step one tile."

The cleaner model is:

1. Transform movement
   Move an entity's actual rendered/runtime position through space.
2. Grid occupancy
   Decide whether the entity participates in tile reservation/collision.
3. Animation
   React to either elapsed time or movement distance.

That means a project should be able to author:

- a freeform slide to any pixel position
- a grid step to an adjacent tile
- a scripted dash by an arbitrary offset
- a knockback move
- a cutscene move along a chosen path

without forcing every case into the same "tile step" primitive.

### Recommended runtime position model

Long-term, the runtime should treat world/pixel position as the authoritative
transform position for movement.

Suggested conceptual model:

- `pixel_x`, `pixel_y`: authoritative runtime position
- `grid_x`, `grid_y`: optional logical grid occupancy / snapped cell
- movement state stores transform movement progress:
  - `start_pixel_x`, `start_pixel_y`
  - `target_pixel_x`, `target_pixel_y`
  - `elapsed`
  - `duration`

For grid actors:

- `grid_x/grid_y` still matter for puzzle logic and occupancy
- but they become one logical layer, not the only movement model

For non-grid or temporarily freeform actors:

- movement can happen entirely in transform space
- grid occupancy can be left unchanged, cleared, or recomputed on completion

### Suggested primitive families

Instead of only a tile-step primitive, use two primitive families.

Transform primitive:

- `move_entity`
- `wait_for_move`

Grid primitives:

- `can_move_to_grid`
- `set_grid_position`
- `reserve_grid_position`
- `clear_grid_occupancy`

Then `move_entity_one_tile` becomes either:

- a thin convenience primitive built on those pieces
- or, preferably, a composite command using them

This preserves the old-project spirit more faithfully than a grid-only move
primitive.

### Primitive movement command shape

Preferred primitive name:

- `move_entity`

Related convenience primitive:

- `move_entity_one_tile`

Suggested parameters:

- `entity_id`
- `space`
- `mode`
- `x`
- `y`
- `duration`

Possible future optional parameters:

- `speed_px_per_second`
- `coordinate_space`
- `easing`
- `on_blocked`
- `allow_push`
- `collision_profile`

The transform primitive should:

1. start interpolation toward a requested target position
2. use either duration or resolved speed
3. expose enough runtime state for a composite command to wait on it

Grid-aware movement should then layer additional logic on top:

1. query/reserve the destination tile
2. start the transform move toward that tile's pixel position
3. coordinate animation separately
4. finalize or maintain grid occupancy according to the selected policy

The old `player_step` / `step_entity` split has been removed. Input now calls
`move_entity_one_tile` directly until project-authored move recipes take over.

### Duration vs speed

Movement should support parameterization, but it should have one canonical
runtime representation.

Recommended rule:

- Internally, movement still runs on a resolved `duration`.
- Authoring may provide either:
  - `duration`
  - or `speed_px_per_second`

If speed is provided, resolve it as:

- `duration = distance_in_pixels / speed_px_per_second`

For a one-tile move:

- `distance_in_pixels = area.tile_size`

This gives projects an intuitive speed-based authoring option while keeping the
runtime interpolation code simple.

### Grid synchronization policies

Once transform movement is separated from grid occupancy, composite commands
need a clear policy for how the grid state should behave.

Useful policies:

- `immediate`
  Reserve/update the destination grid cell as soon as movement starts.
- `on_complete`
  Keep the old cell until the move finishes, then snap/update.
- `none`
  Do not touch grid occupancy during this move.

`immediate` matches the current puzzle-engine behavior and is best for
deterministic Sokoban-style stepping.

`none` is useful for:

- cutscene motion
- particles / props
- decorative entities
- temporary non-grid movement

`on_complete` is useful when a project wants the logical cell to follow the
final resting place without reserving it early.

## Animation synchronization

## Core requirement

The engine should make movement/animation synchronization easy and exact, but
not mandatory.

That means:

- simple projects can still use the existing fallback time-driven animation
- projects that care about exact sync should be able to use the old-project
  style: a movement command and an animation command that share the same frame
  budget

## Old-project-style sync model

The old project did not need a generalized distance-driven animation system for
the player walk cycle. It used two separate ideas:

- movement had a known frame budget
- animation had a known `frames_per_sprite_change`
- both were started together
- the numbers were chosen to line up exactly

That model is now supported directly in the Python runtime too:

- movement commands accept `frames_needed`
- `play_animation` accepts `frame_sequence` and `frames_per_sprite_change`
- `play_animation` can be non-blocking, so the caller can immediately start a
  move command afterward

## Recommended command parameters

Suggested parameters for the old-project-style animation primitive:

- `entity_id`
- `frame_sequence`
- `frames_per_sprite_change`
- `hold_last_frame`
- `wait`

Where:

- `frames_per_sprite_change = 8` means hold each sprite for 8 engine frames
- `wait = false` means "start playback, but do not block the command lane"

Suggested parameters for movement commands:

- `duration`
- `frames_needed`
- `speed_px_per_second`

`frames_needed` is the old-project-friendly option.

## Example: exact synchronization with shared frame budget

If:

- a one-tile move uses `frames_needed = 16`
- the animation uses `frame_sequence = [9, 10]`
- `frames_per_sprite_change = 8`

Then:

- the move finishes in 16 engine frames
- the first sprite is shown for 8 frames
- the second sprite is shown for 8 frames
- both the move and the animation end together

That is the core sync mechanism the old project relied on.

## Walk-cycle continuity

The old project carried a 4-frame walk cycle across repeated moves by
alternating between two separate animation commands, for example:

- first move: `[9, 10]`
- second move: `[11, 10]`

The Python runtime can support that same pattern without extra engine magic:

- the project can choose which `frame_sequence` to call next
- a project variable can toggle between the first and second half-cycle

This keeps the engine simple and stays faithful to the old workflow.

### Important implementation note

This does not require movement to be authored as 16 tiny per-pixel commands.

The split should be:

- one primitive command starts a transform movement interpolation
- one primitive command starts a frame-sequence animation clip
- optional grid primitives handle reservation/sync
- callers coordinate them by starting both with matching frame budgets

That keeps authored JSON readable while preserving exact synchronization.

## JSON composite command example

This is a conceptual example for a one-tile player move implemented as a
composite command. It is not current engine syntax.

```json
{
  "id": "player_move_one_tile",
  "params": ["actor", "direction"],
  "steps": [
    {
      "type": "set_facing",
      "entity_id": "$actor",
      "direction": "$direction"
    },
    {
      "type": "can_move_one_tile",
      "entity_id": "$actor",
      "direction": "$direction",
      "store_var": "move_allowed"
    },
    {
      "type": "if_var",
      "scope": "local",
      "name": "move_allowed",
      "op": "eq",
      "value": true,
      "then": [
        {
          "type": "play_animation",
          "entity_id": "$actor",
          "frame_sequence": "$walk_half_cycle",
          "frames_per_sprite_change": 8,
          "wait": false
        },
        {
          "type": "move_entity_one_tile",
          "entity_id": "$actor",
          "direction": "$direction",
          "frames_needed": 16
        }
      ],
      "else": [
        {
          "type": "set_sprite_frame",
          "entity_id": "$actor",
          "frame": "$idle_frame"
        }
      ]
    }
  ]
}
```

## Notes on this example

- The movement primitive owns logical tile reservation and pixel interpolation.
- The animation primitive does not move the entity.
- Exact sync is achieved because movement and animation share the same frame
  budget.
- If the move is blocked, the actor still turns to face the direction, but does
  not start walking.

## Example: arbitrary non-grid movement

This is the kind of move the redesigned system should also support.

```json
{
  "id": "slide_entity_to_marker",
  "params": ["actor", "target_x", "target_y"],
  "steps": [
    {
      "type": "play_animation",
      "entity_id": "$actor",
      "frame_sequence": [12, 13],
      "frames_per_sprite_change": 6,
      "wait": false
    },
    {
      "type": "move_entity",
      "entity_id": "$actor",
      "space": "pixel",
      "mode": "absolute",
      "x": "$target_x",
      "y": "$target_y",
      "frames_needed": 12,
      "grid_sync": "none"
    }
  ]
}
```

In that example:

- the move is not tied to tile coordinates
- animation still stays synchronized because it shares the same frame budget
- no grid occupancy change is required unless the project explicitly adds it

## Recommended next design slice

To keep the redesign manageable, the next concrete slice should define only the
minimum needed for one clean player move:

1. One primitive movement command, replacing `player_step` / `step_entity`.
2. One primitive facing command.
3. One primitive animation command that supports old-project-style frame
   playback.
4. One project-authored way to alternate the two half-cycles of the walk.
5. One project-authored move recipe that starts animation and movement together.

That would be enough to prove:

- project-authored complex commands
- frame-budget synchronization
- walk-cycle continuity across repeated moves

## Immediate implementation direction

### Phase 1

- Keep `move_entity` as the canonical transform primitive and
  `move_entity_one_tile` as the grid/push convenience command.
- Keep animation separate.
- Add a minimal composite-command JSON format.
- Add `sequence`, `parallel`, and `if_var`.

### Phase 2

- Rebuild player movement around frame-budgeted move + animation commands.
- Add project-authored walk-cycle continuity using alternating sequences.

### Phase 3

- Broaden command-library tooling and editor awareness.
- Keep moving project control flow onto reusable composite commands instead of
  ad-hoc inline event chains where that improves reuse.

## Open questions

- Final primitive names:
  - `move_entity_one_tile` vs `start_tile_move` vs `move_entity`
- Whether movement should keep all 3 authoring styles:
  - `duration`
  - `frames_needed`
  - `speed_px_per_second`
- Exact JSON schema for:
  - local variables
  - composite command parameters
- Whether the project should express walk half-cycle alternation with:
  - explicit command ids
  - or entity/world variables plus branching

