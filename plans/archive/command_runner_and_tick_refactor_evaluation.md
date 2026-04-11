# Evaluation: CommandRunner and Tick Refactor Plan (Tmp)

This document evaluates `command_runner_and_tick_refactor_tmp.md` against the
actual codebase. It also notes how this plan compares to the earlier
`simulation_tick_refactor_plan.md` and the evaluation written for that plan.

---

## Overall Assessment

This plan is a **significant improvement** over the original. It addresses most
of the concerns raised in `simulation_tick_refactor_evaluation.md`:

- It keeps CommandRunner's API change as a thin wrapper first (Stage 2), deferring
  real internal refactoring to Stage 6 — exactly what was recommended.
- It explicitly acknowledges PostActionCommandHandle as a risk.
- It acknowledges that dialogue/inventory waits are state-polled, not dt-driven.
- It acknowledges the existing movement-completion gate in held input instead of
  treating it as an open question.
- It states the idle-check invariant explicitly.
- It acknowledges the staggered deferred transition checks.
- It provides concrete JSON examples for expected semantics, making the contract
  testable.

The plan reads like it was written by someone who either read the previous
evaluation or independently arrived at the same conclusions. Either way, the
quality is noticeably higher.

**There is one significant new risk the plan introduces** that the original did
not have: the `settle()` loop.

---

## The settle() Loop Problem

### What the plan proposes (Stage 6)

```python
def settle(self) -> None:
    while progress_was_made:
        materialize_pending_commands()
        update_root_handles(dt=0.0)
        promote_spawned_root_handles()
```

### Why this is dangerous

The codebase has **no recursion or iteration guards** on command execution.
The only guard that exists is a project-command-stack cycle detector
(`flow.py:536-538`), which prevents the same project command from calling
itself. But that does not protect against:

**1. Infinite immediate chains via branching:**
```json
{ "type": "if", "left": 1, "op": "eq", "right": 1,
  "then": [
    { "type": "if", "left": 1, "op": "eq", "right": 1,
      "then": [ "..." ]
    }
  ]
}
```
Each `if` evaluates immediately and returns a SequenceCommandHandle with
`auto_start=True`. Deeply nested ifs would all execute within a single
`update(0.0)` call. This is already possible today (not introduced by the
refactor), but `settle()` looping makes it worse because spawned flows from
one iteration become new work for the next.

**2. Spawn chains:**
A `spawn_flow` whose child immediately spawns another flow, whose child
immediately spawns another flow. Each settle iteration promotes spawned handles
and finds new work to do.

**3. Parallel completion cascades:**
`run_parallel` with `mode: "any"` completes when the first child finishes. The
completion can trigger spawned follow-up work, which settle would pick up.

### Mitigation needed

The plan should add an explicit iteration limit to `settle()`:

```python
MAX_SETTLE_ITERATIONS = 256  # or whatever feels safe

def settle(self) -> None:
    for _ in range(MAX_SETTLE_ITERATIONS):
        if not self._has_immediate_work():
            return
        self._materialize_pending_commands()
        self._update_root_handles(dt=0.0)
        self._promote_spawned_root_handles()
    raise CommandExecutionError("settle() exceeded iteration limit")
```

This should be documented as a safety net, not a design feature. If authored
content hits the limit, it's a bug in the content, not the engine.

### Note on Stage 2 vs Stage 6

The thin-wrapper approach in Stage 2 (`settle()` just calls `update(0.0)`) is
safe because `update(0.0)` only does two materialization passes, not a loop.
The risk only appears if Stage 6 is implemented. The plan correctly defers
Stage 6, but it should flag this risk explicitly rather than presenting the
loop as a straightforward improvement.

---

## Comparison with the Original Plan

| Concern | Original Plan | This Plan |
|---------|--------------|-----------|
| CommandRunner API split risk | Proposed split, risk understated | Thin wrapper first, deferred internal refactor. Much safer. |
| PostActionCommandHandle | Not mentioned | Listed as a special risk with mitigation |
| Dialogue/inventory wait polling | Not mentioned | Acknowledged, with mitigation |
| Held-input movement gate | Treated as open question | Acknowledges existing gate, focuses on timer policy |
| Idle-check invariant | Listed as risk, no mitigation | Explicitly stated as an invariant with rationale |
| Staggered deferred transitions | Oversimplified | Acknowledged, with "preserve first, simplify later" strategy |
| Zero-dt invariant | Not mentioned | Explicitly listed under Special Risks |
| settle() infinite loop risk | N/A (no settle loop) | Not mentioned — this is the new gap |
| Concrete semantics examples | None | JSON examples with expected outcomes |
| Held-repeat policy options | Not discussed | Three options laid out with a recommendation |

**Verdict:** This plan is strictly better on every dimension except for the new
settle() loop risk, which it introduces but does not address.

---

## Remaining Gaps

### 1. No Definition of "Progress" for settle()

The plan says `settle()` runs "until everything left is waiting." But what
counts as progress? The plan should define this precisely:

- **Pending queue has entries** → progress possible
- **Any root handle completed during the last pass** → progress possible
  (because completion may have unblocked a SequenceCommandHandle child)
- **_pending_spawned_root_handles is non-empty** → progress possible
- **None of the above** → settled

Without this definition, the implementation will have to guess, and different
guesses produce different behavior.

### 2. Dialogue/Inventory in the settle() Loop

The proposed tick contract (line 164-175) shows `settle runtime command work`
as one phase and `advance command/dialogue/inventory waits` as another. But the
current code always pairs command runner updates with dialogue/inventory runtime
updates (lines 171-175, 179-183, 187-191 in game.py).

The plan doesn't clarify whether `_settle_runtime_commands()` should also call
`dialogue_runtime.update(0.0)` and `inventory_runtime.update(0.0)`. If it
doesn't, a dialogue session that closes between settle passes won't be detected
until the next advance_tick. If it does, the settle loop needs to include their
state in the "progress" check.

**Suggestion:** Explicitly state that runtime settling includes
dialogue/inventory flushes, and that `_settle_runtime_commands()` wraps all
three.

### 3. The Staggered Reset Check

The plan says "first preserve the existing staggered behavior where possible"
under Deferred Transition Handling. But the proposed tick contract (Stage 4)
shows a single `_apply_deferred_runtime_work_if_idle()` call. That's a
simplification from the current two-pass reset check.

This is probably fine — the double reset check seems like a safety measure
rather than an intentional design choice. But it should be called out as a
conscious simplification, with a test proving that the single check is
sufficient.

### 4. Camera Following After Movement

The proposed tick has camera update in phase 8, after animation. The current
code also has camera after animation, so this is unchanged. But the plan
doesn't discuss whether camera should see the settled movement position or the
interpolated position. Since movement is grid-based with pixel interpolation,
this matters for smoothness.

This is minor and may not need to be solved in this refactor, but it's worth
noting.

### 5. What Happens When Stage 6 Is Skipped

The plan correctly says "if this stage becomes risky, postpone it." But it
doesn't say what the long-term plan is if it's permanently skipped. Is
`settle()` = `update(0.0)` acceptable forever? The plan positions Stage 6 as
the "real" refactor, but Stage 2's thin wrappers might be good enough. Worth
stating explicitly.

---

## Stage-by-Stage Assessment

### Stage 0: Checkpoint — Good
Standard practice. No concerns.

### Stage 1: Characterization Tests — Excellent
The test list is comprehensive and covers the right behaviors. The addition of
PostActionCommandHandle and error-handling tests compared to the original plan
is a clear improvement.

**One missing test:** A test that `settle()` / `update(0.0)` does NOT advance
`wait_frames` or `wait_seconds` counters. The plan lists this invariant under
Special Risks but doesn't include it in the test list.

### Stage 2: Thin Wrappers — Excellent
This is the right approach. No behavior change, just vocabulary. The original
plan's evaluation recommended exactly this.

### Stage 3: Extract Phase Helpers — Good
Same as the original plan's Slice 2. No concerns.

### Stage 4: Reorder — Good, with one gap
The proposed order is sound. The gap is that the single
`_apply_deferred_runtime_work_if_idle()` call is a simplification from the
current staggered checks. Should be tested.

### Stage 5: Held Movement Repeat — Good
The three-policy analysis is clear. Policy 3 (movement-completion repeat) is
the right choice for grid-based movement. The recommendation to keep timer
details for non-movement actions is sensible.

### Stage 6: CommandRunner Internals — Risky
As discussed above, the settle loop needs an iteration limit and a precise
progress definition. This stage should not be attempted until those are
specified.

### Stage 7: Documentation — Good
The doc list is appropriate. The command eagerness principle ("run commands now
until every remaining command is genuinely waiting") is a good one-liner to
anchor the docs around.

---

## Specific Suggestions

### A. Add Iteration Limit to settle() Spec

Even if Stage 6 is deferred, the spec should say what the safety behavior is.
A limit of 256 or 512 iterations with an error on overflow is reasonable.

### B. Define "Progress" Explicitly

Add a section defining what settle() checks to determine if more work exists:
pending queue, completed handles, spawned handles.

### C. Include Dialogue/Inventory in Settle

State explicitly that `_settle_runtime_commands()` includes dialogue and
inventory runtime flushes, not just the command runner.

### D. Add Zero-Dt Test to Stage 1

Add a test that `settle()` does not advance frame or second counters.

### E. Test the Single-Pass Deferred Transition

If Stage 4 simplifies the staggered reset checks to a single call, add a test
proving that deferred transitions still fire correctly when a reset is
requested during a command chain that completes in the same tick.

### F. State the Thin-Wrapper Escape Hatch

Explicitly say: "If Stage 6 proves too risky, the thin wrapper from Stage 2 is
an acceptable permanent solution. The vocabulary improvement alone is worth the
change."

---

## Risk Summary

| Risk | Severity | Plan Covers It? |
|------|----------|-----------------|
| settle() infinite loop (Stage 6 only) | High | Not mentioned |
| "Progress" definition missing | Medium | Not mentioned |
| Dialogue/inventory in settle scope | Medium | Ambiguous |
| Staggered reset simplification | Low-Medium | Mentioned but not tested |
| Camera interpolation timing | Low | Not mentioned |
| WaitSecondsHandle zero-dt | Low | Mentioned in risks, not in tests |

---

## Verdict

**This plan is ready to execute through Stage 5.** The thin-wrapper approach,
the explicit idle-check invariant, the concrete semantics examples, and the
honest risk assessment make it a solid plan.

**Stage 6 should not be attempted as written.** It needs an iteration limit,
a progress definition, and consideration of dialogue/inventory inclusion in
the settle scope. These are addressable, but they should be specified before
implementation.

Overall, this is a well-written plan that learned the right lessons from the
earlier draft. The staging strategy — thin wrappers first, internal refactor
later behind tests — is exactly the right engineering call.
