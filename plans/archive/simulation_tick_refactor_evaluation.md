# Evaluation: Simulation Tick Refactor Plan

This document evaluates `simulation_tick_refactor_plan.md` against the actual
codebase. It identifies strengths, weaknesses, risks, and suggestions.

---

## Overall Assessment

The plan is **solid and well-motivated**. It correctly identifies a real problem
(implicit tick ordering that will bite harder as animation gets richer), proposes
a reasonable phased approach, and stays disciplined about scope. The slicing
strategy (characterization tests first, extract helpers, then reorder) is
textbook good practice.

That said, the plan has several gaps where it either oversimplifies the current
behavior or underestimates the coupling inside the command runner. These are
fixable, but they should be addressed before implementation.

---

## What the Plan Gets Right

### 1. The Problem Is Real

The current tick does work, but its ordering is incidental rather than
intentional. The specific concern about animation seeing intermediate states
(idle set by a completing command, then immediately overridden by held-input
re-queuing a walk) is a genuine race that will surface with richer animation
authoring.

### 2. The Proposed Phase Order Is Sound

The settle-before-render shape (flush → advance → flush → input → flush →
animate → present → transitions → render) is the right architecture. Most
production game engines use a similar phase contract.

### 3. Non-Goals Are Well-Chosen

Not introducing ECS, not changing JSON syntax, not implementing the animation
API in this PR, not removing spawn_flow. These prevent scope creep. Good.

### 4. Slicing Is Smart

Starting with characterization tests, then extracting named helpers without
behavior change, then reordering is the safest path. Slice 0 (checkpoint
existing work) shows discipline.

### 5. The Review Questions Are Honest

The plan doesn't pretend to have all the answers. The open questions about
held-repeat policy, animation-vs-camera ordering, and whether to split the
command runner are the right questions to ask.

---

## Weaknesses and Gaps

### 1. The Current Tick Description Is Incomplete

The plan describes 12 steps. The actual code at `game.py:160-196` has a more
nuanced structure that the plan partially obscures:

**What the plan misses:**

- `_apply_pending_reset_if_idle()` is called TWICE (lines 186 and 192), not
  once. The first call happens before the second command flush, the second after.
  This is not cosmetic — it means reset can happen in two different windows.

- Load, new-game, and area-change checks (lines 193-195) happen AFTER the
  second command flush, not grouped with reset. The plan lumps them all as one
  "deferred transitions" phase, but the actual code deliberately staggers them.

- The second dialogue/inventory flush (lines 188-191) happens between the two
  reset checks. This matters if dialogue commands trigger a reset request.

**Why this matters:** The proposed reordering needs to preserve this staggering
or explicitly decide to change it. Treating all deferred work as one block risks
changing transition timing.

### 2. The Command Runner Split Is Riskier Than Presented

The plan's Slice 3 suggests adding `flush_immediate()` and `advance_tick(dt)` to
`CommandRunner`. This sounds clean but fights the runner's internal design.

**The two-pass materialization pattern** (`runner.py:336-354`):

```
Pass 1: _materialize_pending_commands()
Loop:   update each root handle with dt
        (handles may spawn new root handles via spawn_root_handle)
        (spawned handles go to _pending_spawned_root_handles, not root_handles)
Pass 2: promote _pending_spawned_root_handles into root_handles
        _materialize_pending_commands() again
```

This is not a cosmetic detail. It exists because:

- Commands can spawn child flows during execution
- Those child flows must NOT be added to `root_handles` during iteration
- They must be materialized after the current update pass finishes

**If you split into two methods:**

- `flush_immediate()` would materialize and run immediate work
- `advance_tick(dt)` would advance time-based handles
- But a handle that completes during `advance_tick()` may trigger a
  SequenceCommandHandle to auto-start the next command in its chain
  (SequenceCommandHandle line 277). That next command might be immediate
  and need materialization — which won't happen until the next
  `flush_immediate()` call.

**SequenceCommandHandle is the crux:** It calls `execute_command_spec()`
internally when a child completes (line 275-284), which immediately creates and
initializes a new handle with `update(0.0)`. This means command materialization
is deeply interleaved with handle advancement. Splitting them into separate
methods breaks this interleaving.

**Suggestion:** Don't split the CommandRunner's public API. Instead, keep
`update(dt)` as-is and add the phase structure at the Game level via named
wrapper methods. The plan already mentions this as a fallback — it should be the
primary approach.

### 3. PostActionCommandHandle Creates Hidden Re-Entrancy

`PostActionCommandHandle` (`builtin.py:59-78`) runs a callback when its inner
handle completes. That callback can enqueue more commands. If the tick is
reordered and this callback fires in a different phase than expected, those
commands materialize at a different time.

The plan doesn't mention PostActionCommandHandle at all. It should be listed
as a risk.

### 4. Dialogue/Inventory Session Handles Are Not Frame-Counted

`DialogueSessionWaitHandle` and `InventorySessionWaitHandle` ignore dt entirely.
They poll `is_session_live()` — a boolean on the runtime object that changes
when external input closes the session.

The plan treats dialogue and inventory flushes as analogous to command flushes.
They are similar but not identical: their "completion" is driven by user input
processed elsewhere in the tick, not by dt advancement. Reordering when they're
polled relative to when input is processed could change when they detect
completion.

### 5. Held-Input Already Has a Movement-Completion Gate

The plan's Slice 5 asks "should the first held repeat be tied to movement
completion rather than a standalone timer?" The answer is already partially yes:

`input_handler.py:166-178`:
```python
if (
    action_name.startswith("move_")
    and target_entity.is_world_space()
    and target_entity.movement_state.active
):
    return False
```

The repeat timer fires, but the actual re-queue is gated on movement not being
active. The plan should acknowledge this existing behavior rather than treating
the question as open.

### 6. The "Idle" Check Is Load-Bearing

The deferred transition methods (`_apply_pending_*_if_idle`) all call
`_has_blocking_runtime_work()`, which checks:

- `command_runner.has_pending_work()`
- `dialogue_runtime.has_pending_work()`
- `inventory_runtime.has_pending_work()`

If the tick reorder causes commands to be queued but not yet materialized at the
point where idle is checked, the idle gate will give a different answer. The plan
lists this as a risk ("Pending area transitions and resets may rely on command
runner idle checks") but doesn't propose a specific mitigation.

**Concrete scenario:**
- Movement completes, command chain resumes and sets idle animation
- Held input fires and queues a new move command
- If idle is checked between the queue and the flush, the system looks busy
  and blocks an area transition that should have fired
- If idle is checked after the flush, the new move is already running and
  the transition is correctly blocked

The proposed tick order puts held input (phase 4) before the idle check (phase
8), which is correct. But the plan should explicitly state this invariant:
**all input queuing must complete before any idle check that gates transitions.**

### 7. Missing Risk: WaitSecondsHandle

The plan mentions `wait_frames` must not be advanced by zero-dt passes. The same
applies to `WaitSecondsHandle` if one exists. The codebase should be checked for
any second-based wait handle that also needs this invariant.

### 8. Characterization Tests Could Be More Specific

Slice 1's test list is good but could be sharper. Specifically missing:

- A test that a command chain resuming after movement completion can set entity
  visuals before animation runs (the core motivating scenario).
- A test that `PostActionCommandHandle` callbacks enqueue commands that
  materialize in the same tick.
- A test that deferred transitions only fire when all three runtimes report
  no pending work.

---

## Suggestions

### A. Keep Command Runner's API Unchanged

Wrap `update(0.0)` and `update(dt)` in named Game-level phase methods. Don't add
`flush_immediate()` and `advance_tick()` to CommandRunner itself. The internal
two-pass materialization is too tightly coupled to safely split.

### B. Document the Idle-Check Invariant Explicitly

Add a comment or docstring that states: all input queuing and command flushing
must complete before any `_apply_pending_*_if_idle()` call. This is the most
likely thing to break in future tick changes.

### C. Add PostActionCommandHandle to the Risk List

Its callback-based re-entrancy is a real coupling point that the reorder needs
to handle.

### D. Acknowledge the Existing Movement Gate in Held-Input

Slice 5 can be simplified by noting that movement-completion gating already
exists. The remaining design question is just about the timer policy (should
the repeat timer pause while movement is active, or keep ticking and just
skip the re-queue?).

### E. Consider Adding a Tick Phase Enum or Comment Block

After the refactor, `_advance_simulation_tick()` should have a comment block at
the top listing the phase contract. This prevents future drift — anyone editing
the method can see at a glance what order is intentional.

### F. Don't Merge Slice 4 and Slice 6

The plan currently has "Reorder the Tick" (Slice 4) and "Move Animation Update
Later" (Slice 6) as separate slices. This is correct and should stay separate.
Moving animation is the behavior change; the rest of the reorder should be
verifiable as behavior-preserving.

### G. Add a Headless Stress Test

Beyond the existing headless smoke start, consider a test that runs 100+ frames
of held movement, verifying that animation state is always consistent at the
render boundary. This is the kind of subtle timing bug that one-frame tests miss.

---

## Risk Summary

| Risk | Severity | Plan Covers It? |
|------|----------|-----------------|
| Command runner split breaks two-pass materialization | High | Mentioned as optional, but risk understated |
| PostActionCommandHandle callback timing | Medium | Not mentioned |
| Idle-check sensitivity to phase order | Medium | Listed as risk, no specific mitigation |
| Dialogue/inventory handles ignore dt | Low-Medium | Not mentioned |
| Held-input already gates on movement | Low | Treated as open question |
| Staggered reset/load/transition checks | Low | Oversimplified in description |
| WaitSecondsHandle zero-dt invariant | Low | Not mentioned |

---

## Verdict

**Proceed with caution.** The plan's overall direction is correct and the
slicing strategy is good. The main adjustment needed is to not split the
CommandRunner API (keep the phase structure at the Game level) and to be more
explicit about the idle-check invariant and the staggered deferred-transition
checks.

The characterization tests in Slice 1 are the right starting point. If those
tests are thorough enough, they'll catch any reorder regressions. Prioritize
writing tests for the motivating scenario (command-sets-visual-before-render)
and for deferred transition timing.
