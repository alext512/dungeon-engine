# CommandRunner Settle API and Simulation Tick Refactor Plan

## Purpose

This plan defines the command-runner and simulation-tick refactor we agreed to
do before the named animation API.

The goal is to make command execution eager, make the simulation tick easy to
reason about, and ensure rendering sees one settled state per tick.

## Core Contract

Commands are eager.

That means:

- command chains continue immediately in the same simulation tick
- immediate commands after a completed wait run in the same tick
- a command chain only pauses when a command returns an incomplete async handle
- `spawn_flow` starts its child flow immediately
- parent commands after `spawn_flow` continue immediately
- a spawned child flow also runs immediate commands immediately until it waits

Plain rule:

```text
Run ready commands now until every remaining command is genuinely waiting.
```

Ready command work must not silently spill into a future tick. If settling cannot
complete within the safety limits, that is a command/runtime error, not a
throttling mechanism.

## Non-Goals

- Do not implement the named animation API in this refactor.
- Do not change JSON command syntax.
- Do not remove `spawn_flow`, `run_parallel`, `run_sequence`, or `wait=false`.
- Do not add an engine-owned magic `idle` animation concept.
- Do not rewrite the renderer.
- Do not add preserved/global command flows across scene changes yet.

## Desired Game Tick Contract

One simulation tick should use this generic order:

```text
1. settle ready runtime work
2. advance simulation systems by one tick
3. settle runtime work unblocked by simulation advancement
4. process input intent against the updated world state
5. settle runtime work caused by input
6. update visual/presentation state
7. apply scene-boundary changes requested this tick
8. render once, unless the scene-boundary change intentionally skips this render
```

Important notes:

- The loop should not mention movement as a special case. Movement is just one
  simulation system.
- Input is checked every tick. Debounce, repeat delay, modal routing, and action
  eligibility belong to input/controller logic, not to the tick loop itself.
- Visual/presentation updates happen after command/input/simulation state is
  settled for the tick.
- Rendering should observe the final settled state, not intermediate immediate
  command states.

## Scene-Boundary Semantics

Scene-changing requests such as area changes, save loads, and new-game requests
should be treated as scene boundaries.

For this refactor:

- a scene-boundary command requests a scene change
- the old scene continues settling only to the defined boundary point
- when the boundary applies, old scene command work is cancelled
- commands after the scene-boundary command in the old scene should not continue
- preserving flows across scene changes is out of scope for now

Future API work may add explicit preserved/global flows, for example for music
fades or cross-scene screen effects. That should be opt-in, not implicit.

Render behavior:

- Prefer simplicity for now.
- If applying a scene-boundary change would risk rendering a half-initialized new
  scene, skip rendering for that frame.
- Do not render an old half-torn scene.
- Do not add special "settle new scene startup immediately" behavior unless a
  visible issue proves we need it.

## CommandRunner API Target

The current game loop uses:

```python
command_runner.update(0.0)
command_runner.update(dt)
command_runner.update(0.0)
```

The clearer vocabulary is:

```python
command_runner.settle()
command_runner.advance_tick(dt)
command_runner.settle()
```

Where:

- `settle()` means run queued/unblocked command work until everything left is
  waiting
- `advance_tick(dt)` means advance waiting handles by one simulation tick

## Safety Limits

True settling needs guardrails. These are safety fuses, not frame budgets.

Initial defaults:

```text
max_settle_passes = 128
max_immediate_commands_per_settle = 8192
settle_warning_ratio = 0.75
log_settle_usage_peaks = false
```

If a safety limit is exceeded:

- raise/log a command execution error
- stop current command work cleanly
- do not silently defer remaining ready commands to a future tick

The project may later override these through `project.json`:

```json
{
  "command_runtime": {
    "max_settle_passes": 128,
    "max_immediate_commands_per_settle": 8192,
    "log_settle_usage_peaks": false,
    "settle_warning_ratio": 0.75
  }
}
```

`log_settle_usage_peaks` means logging the largest settle workload observed so
far during a run. This helps tune limits and detect suspicious command cascades.

Example diagnostic:

```text
Command settle usage peak: tick=531 passes=7 immediate_commands=142
```

## Progress Definition For True Settling

Before implementing a deeper `settle()` loop, define progress precisely.

Possible progress signals:

- pending command queue was consumed
- a root handle completed
- a root handle count changed
- spawned root handles were promoted
- immediate command execution count increased

If no progress signal occurs and waiting handles remain, settling is complete.

If progress keeps happening until a safety limit is exceeded, authored content
likely produced a runaway immediate command loop and should fail loudly.

## Runtime Settle Scope

Keep two concepts separate:

- `CommandRunner.settle()` settles command-runner work only.
- `Game._settle_runtime_work()` may settle the command runner plus dialogue and
  inventory runtime zero-dt work.

This distinction keeps the command runner focused while allowing the game loop
to preserve current dialogue/inventory polling behavior.

## Intended Runtime Semantics

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

### Waiting Movement

Given:

```json
[
  {
    "type": "move_in_direction",
    "entity_id": "$self_id",
    "direction": "up",
    "wait": true
  },
  { "type": "set_entity_var", "name": "after_move", "value": true }
]
```

When the move completes, `after_move` should be set in the same tick.

### Non-Waiting Movement

Given:

```json
[
  {
    "type": "move_in_direction",
    "entity_id": "$self_id",
    "direction": "up",
    "wait": false
  },
  { "type": "set_entity_var", "name": "continued", "value": true }
]
```

The variable should be set immediately after movement starts.

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

## Implementation Steps

### Step 0: Checkpoint Existing Non-Tick Work

Commit or otherwise isolate already-completed unrelated changes first:

- `run_commands` renamed to `run_sequence`
- entity command shorthand
- sample project JSON cleanup
- docs/tests for those changes

Reason:

- this refactor is behavioral and should be reviewable separately.

### Step 1: Add Characterization Tests

Add tests before changing implementation.

Required behavior tests:

- immediate command chains finish in one settle
- `wait_frames` blocks until a real tick advances it
- `wait_seconds` does not advance during settling
- sequences continue immediately after a wait completes
- multiple immediate commands after a wait all run in the same tick
- `move_in_direction(wait=true)` blocks until movement completes
- `move_in_direction(wait=false)` continues immediately
- `spawn_flow` starts the child immediately
- parent continues immediately after `spawn_flow`
- spawned child immediate commands run immediately until a wait
- queued commands created during command execution are materialized predictably
- `PostActionCommandHandle` callbacks can enqueue/follow up without being
  delayed
- command errors still clear pending/root work and preserve useful trace context
- safety-limit overflow raises/logs a command error instead of deferring work

### Step 2: Add Thin Runner API Wrappers

Start with behavior-preserving wrappers:

```python
def settle(self) -> None:
    self.update(0.0)

def advance_tick(self, dt: float) -> None:
    self.update(dt)
```

Then use these names from `Game` helpers.

Purpose:

- introduce the vocabulary
- improve readability
- avoid changing runner internals before tests are in place

### Step 3: Extract Game Tick Phase Helpers Without Reordering

Split `_advance_simulation_tick()` into named helpers while preserving current
behavior.

Possible helper names:

- `_settle_runtime_work()`
- `_advance_simulation_systems_tick(dt)`
- `_advance_runtime_waits_tick(dt)`
- `_process_input_intent(dt)`
- `_advance_visual_presentation_tick(dt)`
- `_apply_scene_boundary_changes_if_requested()`

This should be behavior-preserving.

### Step 4: Implement True Guarded Settle

Replace the thin `settle()` wrapper with the real guarded implementation.

Requirements:

- settle ready command work until blocked
- preserve spawned-flow semantics
- preserve same-tick continuation after waits
- preserve zero-dt behavior for waits and timers
- enforce `max_settle_passes`
- enforce `max_immediate_commands_per_settle`
- track/log settle usage peaks when enabled
- raise/log an error on overflow

If this step reveals hidden runner coupling, stop and strengthen tests before
continuing.

### Step 5: Reorder Game Tick To The Chosen Contract

Move toward:

```python
self._settle_runtime_work()
self._advance_simulation_systems_tick(dt)
self._advance_runtime_waits_tick(dt)
self._settle_runtime_work()
self._process_input_intent(dt)
self._settle_runtime_work()
self._advance_visual_presentation_tick(dt)
self._apply_scene_boundary_changes_if_requested()
```

Rendering remains outside `_advance_simulation_tick()` in the frame-level loop,
but it should only happen after this settled tick state is available. If a
scene-boundary change requests a skipped render, the frame loop should respect
that.

### Step 6: Implement Scene-Boundary Cancellation

Update area/load/new-game handling so scene-boundary changes:

- are applied at the scene-boundary phase
- cancel old scene command work
- do not wait forever for background-style flows
- do not allow remaining old-scene commands after the boundary to continue

Keep preserved/global flows out of scope.

### Step 7: Documentation

Update docs to explain:

- command chains are eager
- immediate commands run in the same tick
- sequences pause only at incomplete async handles
- `wait=true` blocks the current sequence
- `wait=false` starts work and continues immediately
- `spawn_flow` starts a child flow immediately and parent continues immediately
- settle safety limits are error guardrails, not throttling budgets
- the tick loop settles command/input/simulation state before visuals/render
- scene-changing commands are scene boundaries

Likely docs:

- `docs/authoring/command-system.md`
- `docs/authoring/manuals/engine-json-interface.md`
- `docs/authoring/reference/builtin-commands.md`
- a development or architecture note for the tick contract

## Special Risks

### CommandRunner Ordering

Changing materialization order can alter behavior.

Watch for:

- queued root commands vs existing root handles
- child flows spawned while root handles are being iterated
- immediate commands created after an async command completes
- errors raised after partial progress

### Runaway Immediate Work

True settling can expose or amplify runaway content.

Mitigation:

- pass limit
- immediate command count limit
- clear overflow error
- no silent next-tick spillover

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

- keep dialogue/inventory update calls in game-level runtime settle/tick helpers
- add tests if existing coverage is weak

### Zero-Dt Invariant

Settling must not advance time.

Must preserve:

- `wait_frames` does not advance during `settle()`
- `wait_seconds` does not advance during `settle()`
- simulation systems do not advance during `settle()`
- visual animation does not advance during `settle()`

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

- run a headless held-input scenario for many ticks
- assert pre-render state stays consistent
- inspect settle usage peak logs

## Clean Execution Order

1. Checkpoint existing non-tick changes.
2. Add characterization tests.
3. Add `settle()` / `advance_tick()` as thin wrappers.
4. Extract game tick helpers without reordering.
5. Implement true guarded `settle()`.
6. Reorder the game tick to the chosen contract.
7. Implement scene-boundary cancellation.
8. Update docs.
9. Run full validation.
10. Resume animation API design.
