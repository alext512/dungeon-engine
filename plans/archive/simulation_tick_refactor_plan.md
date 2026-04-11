# Simulation Tick Refactor Plan

## Purpose

This document proposes a focused refactor of the play-mode simulation tick so
movement, command resumption, held input, animation, and rendering happen in a
predictable order.

The immediate motivation is the upcoming animation API work. Directional
movement and idle/walk animation switching exposed that the current tick loop
works, but its phase contract is not explicit enough to reason about subtle
"who wins before render?" cases.

This plan is intended for review before implementation.

## Problem Statement

The engine already uses a fixed simulation tick, but several concepts are
currently interleaved in a way that makes behavior depend on incidental order:

- queued commands are flushed more than once per tick
- movement completion can unblock command chains
- held directional input can enqueue a new move after movement state changes
- animation updates read whatever visual state exists at that moment
- rendering happens after all of this, but the final state is not described by a
  formal contract

The concrete animation example:

- A project command may set `walk_up`, run `move_in_direction(wait=true)`, then
  set `idle_up`.
- If the player is still holding up, the next `move_up` may be queued around the
  same time as the old command finishes.
- We want a predictable rule for whether render sees the idle state, the next
  walk state, or a transient one-tick artifact.

This same class of issue can appear later for other asynchronous work:

- movement followed by scripted state changes
- screen animations followed by UI updates
- camera movement followed by transitions
- spawned flows that complete during the same tick as input or movement

## Current Runtime Facts

The current play tick is centered in
`dungeon_engine/engine/game.py::_advance_simulation_tick()`.

At the time this plan was written, the relevant order is approximately:

1. Flush command work with `command_runner.update(0.0)`.
2. Flush dialogue and inventory runtime work with `update(0.0)`.
3. Advance movement with `movement_system.update_tick()`.
4. Process held directional repeat with `input_handler.update_held_direction_repeat(dt)`.
5. Advance animation with `animation_system.update_tick(dt)`.
6. Advance command work with `command_runner.update(dt)`.
7. Advance dialogue and inventory runtime work with `update(dt)`.
8. Advance screen animations with `screen_manager.update_tick()`.
9. Advance camera with `camera.update(..., advance_tick=True)`.
10. Apply pending reset/load/new-game/area-change work when idle.
11. Flush command work again with `command_runner.update(0.0)`.
12. Apply pending transition work again.

That order is functional, but it is difficult to explain as an intentional
contract. In particular, animation updates happen before the later command
flush, so a command that resumes after a wait may change visuals after animation
has already advanced for that tick.

## Goals

- Make the simulation tick phase order explicit and documented.
- Ensure render observes one settled state per tick.
- Keep command chains sequential and readable.
- Preserve the meaning of `wait=true` on long-running commands.
- Preserve `wait=false`, `spawn_flow`, `run_parallel`, and `run_sequence`
  semantics.
- Make held movement predictable when a move finishes and the direction is still
  held.
- Provide a stable foundation for named visual animations and later locomotion
  authoring.
- Keep this refactor small enough to review independently from the animation API
  implementation.

## Non-Goals

- Do not implement the new animation API in this refactor.
- Do not add a magic engine-owned `idle` animation concept.
- Do not introduce a full ECS scheduler.
- Do not change JSON command syntax except where tests reveal a necessary
  contract clarification.
- Do not remove `spawn_flow` or `wait=false`.
- Do not rewrite the renderer.

## Proposed Tick Contract

Each simulation tick should have a clear settle-before-render shape:

1. **Pre-tick command flush**
   - Materialize queued commands.
   - Run immediate command chains until they block on an async handle or finish.
   - This handles input events queued before the simulation tick.

2. **Async system advance**
   - Advance movement interpolation.
   - Advance command handles that consume real tick time, timers, or async state.
   - Advance dialogue/inventory handles that consume tick time.
   - This is where long-running work progresses.

3. **Completion flush**
   - Run command chains that became unblocked because async work completed.
   - Example: `move_in_direction(wait=true)` finishes, then the next command in
     that chain runs.

4. **Input repeat after movement completion**
   - Evaluate held directional repeat after movement completion is known.
   - If an entity is now free to move and the held-repeat timer allows it, enqueue
     the next movement command in the same simulation tick.

5. **Post-input command flush**
   - Materialize commands produced by held input.
   - Run immediate work until blocked again.
   - This lets a newly queued `move_up` set the next walk animation before the
     frame is rendered.

6. **Visual/animation update**
   - Update visual animation state after command and movement state have settled.
   - Rendering should see the final visual choice for this tick, not an
     intermediate command-chain state.

7. **Presentation and camera update**
   - Advance screen-space animations.
   - Advance camera motion/follow.
   - Keep this after world movement settles so camera/render state reflects the
     final tick state.

8. **Deferred runtime transitions**
   - Apply pending resets, load requests, new-game requests, and area transitions
     only after command/movement work has settled and the runtime is idle enough.

9. **Render**
   - Render once from the settled state.

## Expected Movement/Animation Outcome

For a future explicit project command shaped roughly like this:

```json
{
  "params": ["direction", "walk_animation", "idle_animation"],
  "commands": [
    {
      "type": "set_visual_animation",
      "entity_id": "$self_id",
      "visual_id": "body",
      "animation": "$walk_animation"
    },
    {
      "type": "move_in_direction",
      "entity_id": "$self_id",
      "direction": "$direction",
      "frames_needed": "$project.movement.ticks_per_tile",
      "wait": true
    },
    {
      "type": "set_visual_animation",
      "entity_id": "$self_id",
      "visual_id": "body",
      "animation": "$idle_animation"
    }
  ]
}
```

The tick contract should make the behavior predictable:

- If no direction is held when the move finishes, render can see `idle_*`.
- If the same direction is still held and the repeat policy queues another move
  in that tick, the next `walk_*` command can run before render.
- If the animation API later preserves animation phase when setting the same
  animation again, repeated `walk_*` commands do not restart the gait cycle.

This contract does not require a special locomotion controller. It only makes the
order of ordinary commands and input repeat predictable.

## Proposed Implementation Slices

### Slice 0: Checkpoint Existing Work

Before starting this refactor, commit or otherwise isolate any already-completed
grammar/content changes, especially:

- `run_commands` to `run_sequence`
- named entity command shorthand
- sample project JSON updates
- docs/tests for those changes

Reason: the tick refactor touches runtime behavior and should be reviewable on
its own.

### Slice 1: Add Characterization Tests

Add focused tests that describe current and desired behavior before reshaping
the loop.

Recommended tests:

- A command chain with `move_in_direction(wait=true)` does not continue until the
  move completes.
- A command chain with `move_in_direction(wait=false)` continues immediately.
- A movement-completion command can run before render-equivalent observation.
- Held movement does not enqueue another move while `movement_state.active` is
  true.
- Held movement can enqueue the next move after the previous move completes.
- `spawn_flow` remains fire-and-forget.
- `run_parallel` still waits according to its completion mode.
- `run_sequence` still executes its child list in order.

For the held-input/render-facing behavior, prefer a direct unit-style runtime
test over a full pygame frame test if possible. A test helper can call the same
phase methods that `_advance_simulation_tick()` uses.

### Slice 2: Extract Named Phase Helpers Without Behavior Change

Refactor `_advance_simulation_tick()` into small private methods while preserving
current order.

Example helper names:

- `_flush_immediate_runtime_work()`
- `_advance_world_motion_tick()`
- `_advance_command_runtime_tick(dt)`
- `_process_held_input_repeat(dt)`
- `_advance_visual_animation_tick(dt)`
- `_advance_presentation_tick()`
- `_apply_deferred_runtime_work_if_idle()`

This slice should be behavior-preserving. Its purpose is to make the next slice
small and reviewable.

### Slice 3: Clarify Command Runner Phases If Needed

The current `CommandRunner.update(dt)` does several things:

- materializes queued root commands
- advances existing root handles
- materializes commands queued during that update
- attaches spawned root handles
- handles errors

That is convenient, but the game loop is using `update(0.0)` as a de facto
"flush immediate work" primitive.

Consider adding explicit methods, while keeping `update(dt)` as a compatibility
wrapper:

- `flush_immediate()`
  - equivalent to a zero-dt settle pass
  - should run newly unblocked immediate work
  - should not advance tick-based timers

- `advance_tick(dt)`
  - advances async handles that should consume real simulation time
  - may materialize queued work before and after, matching current behavior

Only add these methods if they reduce ambiguity. If they cause more churn than
value, keep `update(0.0)` / `update(dt)` internally but wrap them behind named
`Game` phase helpers.

### Slice 4: Reorder the Tick Around Settling

Move toward this order:

```text
flush immediate command/dialogue/inventory work
advance movement
advance command/dialogue/inventory async work
flush newly unblocked immediate work
process held directional repeat
flush commands produced by held input
update entity visual animations
update screen animations
update camera
apply deferred transitions/resets/loads when idle
```

Important detail:

- If a command resumes after movement completes and sets an idle animation, held
  input should still get a chance to enqueue and run the next movement command
  before visual animation and render.

### Slice 5: Tighten Held-Input Semantics

Review held movement repeat timing in `dungeon_engine/engine/input_handler.py`.

Current defaults:

- initial held-repeat delay: `0.18s`
- held-repeat interval: `0.12s`
- default movement duration: `0.14s`

Questions to answer during implementation:

- Should the first held repeat be tied to movement completion rather than a
  standalone timer?
- Should held movement use "repeat when free and interval elapsed" or "repeat
  immediately when free after the initial pressed move"?
- Should this be project-configurable?

Do not bury these choices inside animation code. They belong to input/movement
repeat semantics.

### Slice 6: Move Animation Update Later

Animation should read final settled visual state for the tick.

That likely means:

- run animation after command completion flushes
- run animation after held input has had a chance to enqueue and flush commands
- avoid updating animation before a command can still change the active visual in
  the same tick

This is especially important before adding named visual animations, because
`set_visual_animation` should not accidentally display or advance a clip that is
immediately superseded later in the same tick.

### Slice 7: Documentation

Update author-facing and developer-facing docs after behavior is tested.

Likely docs:

- `docs/authoring/manuals/engine-json-interface.md`
- `docs/authoring/command-system.md`
- `docs/project/architecture-direction.md` or a development note if a better
  fit exists

Docs should explain:

- command lists are sequential
- long-running commands may support `wait`
- `wait=true` means the current command chain resumes only after that async work
  completes
- `wait=false` means the command starts work and the chain continues immediately
- `spawn_flow` starts a whole child command chain independently
- render observes the settled result of the tick, not every intermediate
  immediate command state

### Slice 8: Regression Validation

Run the normal validation checklist because this touches command execution,
input, movement, and project content behavior.

Required:

```text
.venv/Scripts/python -m unittest discover -s tests -v
```

If editor files are touched:

```text
cd tools/area_editor
..\..\.venv/Scripts/python -m unittest discover -s tests -v
```

Also validate repo-local project manifests and command libraries:

```text
@'
from pathlib import Path
from dungeon_engine.project_context import load_project
from dungeon_engine.commands.library import validate_project_commands

project_manifests = sorted(Path("projects").glob("*/project.json"))
if not project_manifests:
    print("No repo-local project manifests found under projects/.")
else:
    for project_json in project_manifests:
        project = load_project(project_json)
        validate_project_commands(project)
        print(f"{project.project_root.name}: project command validation OK")
'@ | .venv/Scripts/python -
```

And do a headless smoke start:

```text
.venv/Scripts/python run_game.py --project projects/new_project --headless --max-frames 2
```

## Risks

- Reordering command flushes can change exact behavior of existing command chains.
- Dialogue/inventory modal input may depend on current update timing.
- Pending area transitions and resets may rely on command runner idle checks.
- `wait_seconds` and `wait_frames` must not be advanced by zero-dt flush passes.
- Camera follow may look subtly different if camera updates after a different
  phase.
- Tests that observe exact tick counts may need careful adjustment.

## Review Questions

- Is the proposed phase order too command-runner-specific, or should more of it
  live in `Game` as orchestration?
- Should held movement repeat be timer-driven, movement-completion-driven, or a
  hybrid?
- Should command runner expose explicit `flush_immediate()` and `advance_tick()`
  methods, or is wrapping `update(0.0)` and `update(dt)` in named game phases
  enough?
- Should animation update happen before or after screen/camera updates? The plan
  proposes before screen/camera, but after all world command/input settling.
- Should render ever expose intermediate immediate command states? This plan says
  no.

## Recommended Next Step

Do not start the named animation API until this tick contract is implemented and
tested.

The safest sequence is:

1. Commit the already-completed command grammar/content cleanup.
2. Implement the tick refactor in behavior-preserving and then behavior-changing
   slices.
3. Document the tick contract.
4. Re-run runtime/project/headless validation.
5. Resume animation API design on top of the new phase contract.
