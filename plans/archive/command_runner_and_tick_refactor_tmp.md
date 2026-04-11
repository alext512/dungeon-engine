# Temporary Plan: CommandRunner Settle API and Simulation Tick Refactor

Status: temporary review draft.

This plan supersedes parts of `simulation_tick_refactor_plan.md` by explicitly
including the `CommandRunner` cleanup we now want to do before the animation API.

## Core Decision

The command system should be eager.

That means:

- command chains continue immediately in the same simulation tick
- immediate commands after a completed wait run in the same tick
- a command chain only pauses when a command returns an incomplete async handle
- `spawn_flow` starts its child flow immediately
- parent commands after `spawn_flow` continue immediately
- a spawned child flow also runs immediate commands immediately until it waits

Plain rule:

```text
Run commands now until every remaining command is genuinely waiting.
```

This rule should become explicit in both code and docs.

## Why Refactor CommandRunner

The current game loop calls:

```python
command_runner.update(0.0)
command_runner.update(dt)
command_runner.update(0.0)
```

This works, but the names are unclear:

- `update(0.0)` really means "settle immediate/unblocked command work"
- `update(dt)` means "advance active command handles by one tick"
- after a waited command finishes, immediate follow-up work may run too

The behavior is useful, but the API hides the intent.

We want clearer vocabulary:

```python
runner.settle()
runner.advance_tick(dt)
runner.settle()
```

Where:

- `settle()` runs queued/unblocked command work until everything left is waiting
- `advance_tick(dt)` advances currently waiting command handles by one tick

## Why Refactor The Game Tick

The animation discussion exposed a timing issue:

- movement can finish during a tick
- a command chain can then set an idle visual
- held input can queue the next move
- animation/render should see the final settled state, not an accidental
  intermediate state

The engine should have a clear update contract, similar to common game-engine
phase models:

```text
settle ready commands
advance simulation work
settle commands unblocked by simulation work
process input intent
settle commands caused by input
update animation/presentation
render once
```

## Non-Goals

- Do not implement the named animation API in this refactor.
- Do not change JSON command syntax.
- Do not remove `spawn_flow`, `run_parallel`, `run_sequence`, or `wait=false`.
- Do not change the meaning of sequential command chains.
- Do not add an engine-owned magic `idle` animation concept.
- Do not rewrite the renderer.

## Intended Public Runtime Semantics

### Sequential Command Chains

Given:

```json
[
  { "type": "wait_frames", "frames": 1 },
  { "type": "set_entity_var", "name": "a", "value": true },
  { "type": "set_entity_var", "name": "b", "value": true }
]
```

After `wait_frames` completes, both `set_entity_var` commands should run in the
same tick.

### Movement Waits

Given:

```json
[
  { "type": "move_in_direction", "entity_id": "$self_id", "direction": "up", "wait": true },
  { "type": "set_entity_var", "name": "after_move", "value": true }
]
```

When the move completes, `after_move` should be set in the same tick.

### Non-Waiting Movement

Given:

```json
[
  { "type": "move_in_direction", "entity_id": "$self_id", "direction": "up", "wait": false },
  { "type": "set_entity_var", "name": "continued", "value": true }
]
```

The variable should be set immediately after the movement starts.

### Spawn Flow

Given:

```json
[
  {
    "type": "spawn_flow",
    "commands": [
      { "type": "set_entity_var", "name": "child_started", "value": true },
      { "type": "wait_frames", "frames": 1 },
      { "type": "set_entity_var", "name": "child_done", "value": true }
    ]
  },
  { "type": "set_entity_var", "name": "parent_continued", "value": true }
]
```

Expected:

- `child_started` is set immediately
- `parent_continued` is set immediately
- `child_done` waits for the child flow's wait
- the parent does not wait for the child

## Desired Game Tick Contract

One simulation tick should use this order:

```text
1. settle runtime command work queued before the tick
2. advance movement and other simulation systems by one tick
3. advance command/dialogue/inventory waits by one tick
4. settle command work unblocked by that advancement
5. process held input after movement completion is known
6. settle commands produced by held input
7. update entity animation/visual playback
8. update screen/presentation/camera
9. apply idle-gated reset/load/new-game/area-change work
10. render once from the settled state
```

Important invariant:

```text
All input queuing and command settling for the tick must happen before any
idle-gated reset/load/new-game/area-change checks.
```

This prevents deferred transitions from observing a half-settled state where
input has queued work but the resulting command has not run yet.

## Staged Implementation

### Stage 0: Checkpoint Existing Non-Tick Work

Before starting, commit or otherwise isolate already-completed unrelated changes:

- `run_commands` renamed to `run_sequence`
- entity command shorthand
- sample project JSON cleanup
- docs/tests for those changes

Reason:

- the tick/runner refactor is behavioral
- it should be reviewable separately

### Stage 1: Add CommandRunner Characterization Tests

Add tests before changing implementation.

Required behavior tests:

- immediate command chains finish in one `settle()`
- `wait_frames` blocks until a real tick advances it
- `wait_seconds` does not advance during settling
- sequences continue immediately after a wait completes
- multiple immediate commands after a wait all run in the same tick
- `move_in_direction(wait=true)` blocks until movement completes
- `move_in_direction(wait=false)` continues immediately
- `spawn_flow` starts the child immediately
- parent continues immediately after `spawn_flow`
- spawned child immediate commands run immediately until a wait
- queued commands created during a command update are materialized predictably
- `PostActionCommandHandle` callbacks can enqueue/follow up without being delayed
- command errors still clear pending/root work and preserve useful trace context

### Stage 2: Add Runner API Names As Thin Wrappers

First implementation should be intentionally boring:

```python
def settle(self) -> None:
    self.update(0.0)

def advance_tick(self, dt: float) -> None:
    self.update(dt)
```

Then update `Game` helper methods to use these names.

Purpose:

- improve readability
- introduce the vocabulary
- avoid changing runner internals too early

Expected result:

- all tests still pass
- no behavior change intended

### Stage 3: Extract Game Tick Phase Helpers Without Reordering

Split `_advance_simulation_tick()` into named helpers, preserving current order.

Possible helper names:

- `_settle_runtime_commands()`
- `_advance_world_motion_tick()`
- `_advance_runtime_waits_tick(dt)`
- `_process_held_input_repeat(dt)`
- `_advance_entity_animation_tick(dt)`
- `_advance_presentation_tick()`
- `_apply_deferred_runtime_work_if_idle()`

Purpose:

- make the later reorder small
- make the phase contract readable in code

Expected result:

- no behavior change intended

### Stage 4: Reorder Game Tick To The Chosen Contract

Move toward:

```python
self._settle_runtime_commands()
self._advance_world_motion_tick()
self._advance_runtime_waits_tick(dt)
self._settle_runtime_commands()
self._process_held_input_repeat(dt)
self._settle_runtime_commands()
self._advance_entity_animation_tick(dt)
self._advance_presentation_tick()
self._apply_deferred_runtime_work_if_idle()
```

Important:

- preserve or intentionally document changes to the current staggered reset/load
  order
- do not run idle-gated transitions before held input has been processed and
  settled
- animation should run after command/input/movement state has settled

### Stage 5: Tighten Held Movement Repeat Policy

Current behavior already gates held movement on movement completion:

```text
if target entity is world-space and movement_state.active:
    do not queue another move
```

So the open question is timer policy, not whether movement completion matters.

Policies to consider:

1. Timer keeps ticking while moving.
   - Current-ish behavior.
   - Can create gaps if repeat delay is longer than movement duration.

2. Timer pauses while moving.
   - Predictable, but can feel sluggish.

3. Movement-completion repeat.
   - If a direction is still held when movement completes, queue the next move
     immediately or on the same tick.
   - Best fit for smooth tile movement.

Recommended:

- Use policy 3 for directional grid movement.
- Keep timer details for initial press buffering and non-movement actions if
  needed.
- Document this separately from animation.

### Stage 6: Refactor CommandRunner Internals Behind Tests

Only after Stage 1-5 are green, consider replacing the thin wrappers with a
clearer internal structure.

Potential internal shape:

```python
def settle(self) -> None:
    while progress_was_made:
        materialize_pending_commands()
        update_root_handles(dt=0.0)
        promote_spawned_root_handles()

def advance_tick(self, dt: float) -> None:
    materialize_pending_commands()
    update_root_handles(dt)
    promote_spawned_root_handles()
```

But preserve the public semantics:

- `settle()` runs until blocked
- `advance_tick(dt)` advances waits once
- game loop calls `settle()` after `advance_tick(dt)`

If this stage becomes risky, postpone it. The thin wrapper API is already an
improvement.

### Stage 7: Documentation

Update author/developer docs:

- command chains are eager
- immediate commands run in the same tick
- sequences pause only at incomplete async handles
- `wait=true` blocks the current sequence
- `wait=false` starts work and continues immediately
- `spawn_flow` starts a child flow immediately and parent continues immediately
- render observes the settled tick state
- held grid movement repeats on movement completion when the direction is still
  held, if that policy is implemented

Likely docs:

- `docs/authoring/command-system.md`
- `docs/authoring/manuals/engine-json-interface.md`
- `docs/authoring/reference/builtin-commands.md`
- a development note or architecture doc for the tick contract

## Deferred Transition Handling

The current runtime applies deferred work in a staggered way:

- reset can be checked before and after a late command flush
- load/new-game/area-change checks happen later
- all are gated by `_has_blocking_runtime_work()`

During the refactor:

- first preserve the existing staggered behavior where possible
- if simplifying to one deferred phase, add tests proving behavior is acceptable
- never check idle-gated transitions before input/commands have settled for the
  tick

## Special Risks

### CommandRunner Ordering

Changing materialization order can alter behavior.

Watch for:

- queued root commands vs existing root handles
- child flows spawned while root handles are being iterated
- immediate commands created after an async command completes
- errors raised after partial progress

### PostActionCommandHandle

Some commands run callbacks after an inner handle completes.

Risk:

- callback timing can shift if handle advancement moves to a different phase
- callback may enqueue or trigger follow-up work

Mitigation:

- add characterization tests before changing runner internals

### Dialogue and Inventory Waits

Dialogue/inventory waits are state-polled, not purely dt-driven.

Risk:

- changing when these runtimes are polled relative to input can shift completion
  by one tick

Mitigation:

- keep dialogue/inventory update calls wrapped in the same runtime settle/tick
  helpers
- add tests if existing coverage is weak

### Zero-Dt Invariant

Settling must not advance real-time or frame-count waits.

Must preserve:

- `wait_frames` does not advance during `settle()`
- `wait_seconds` does not advance during `settle()`
- movement does not advance during `settle()`

## Validation

Runtime:

```text
.venv/Scripts/python -m unittest discover -s tests -v
```

Editor, if touched:

```text
cd tools/area_editor
..\..\.venv/Scripts/python -m unittest discover -s tests -v
```

Project command validation:

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

Headless smoke:

```text
.venv/Scripts/python run_game.py --project projects/new_project --headless --max-frames 2
```

Optional stress test:

- run a headless held-movement scenario for many ticks
- assert pre-render visual/movement state stays consistent

## Recommended Execution Order

1. Checkpoint existing non-tick changes.
2. Add characterization tests.
3. Add `settle()` / `advance_tick()` as thin wrappers.
4. Extract game tick helpers without reordering.
5. Reorder the game tick.
6. Decide and implement held movement repeat policy.
7. Optionally refactor `CommandRunner` internals behind the same tests.
8. Update docs.
9. Run full validation.
10. Resume animation API design.
