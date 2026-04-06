# Codebase Refactor And Docs Catch-Up Plan

## Status: In Progress

Reviewed against the current repository state on 2026-04-06.

This plan is based on:

- a full read-through of the main engine docs and editor docs
- targeted inspection of the runtime, command system, world loading, persistence,
  startup validation, and editor architecture
- current automated verification results

Current verified baseline:

- runtime suite: `180` tests passing
- editor suite: `152` tests passing
- direct project-command validation: `projects/test_project` and
  `projects/game_copy` passing
- short headless boot: `projects/test_project` and `projects/game_copy` passing

This is a refactor-and-stabilization plan, not a "rewrite the engine" plan.

---

## Why This Plan Exists

The project has outgrown the "small engine with a few experiments" phase.

It already has:

- a strong architectural thesis
- a meaningful engine/editor boundary
- a non-trivial JSON command and content contract
- a dedicated external editor
- unusually strong docs for a project of this size

That is good news. The downside is that the next risks are now different:

- maintainability is getting concentrated in a few very large modules
- command-surface safety is not as strict as the project now deserves
- runtime/editor contract logic can drift
- some docs are no longer aligned with implementation reality
- tests are strong but increasingly hard to navigate as one giant runtime suite

The goal of this plan is to fix those issues safely without losing momentum or
breaking the current data-driven direction.

---

## Main Goals

1. Make the command surface safer for content authors.
2. Reduce the maintenance cost of the largest modules.
3. Keep the runtime/editor contract synchronized without collapsing the tool
   boundary.
4. Tighten cache lifetime and validation behavior before future live-authoring
   or hot-reload workflows make current assumptions fragile.
5. Reshape tests so they stay useful as the engine grows.
6. Treat outdated docs as first-class refactor work, not cleanup for "later."

---

## Non-Goals

- Do not rewrite the engine into a different architecture.
- Do not remove the JSON-driven command model.
- Do not merge the editor back into `dungeon_engine/`.
- Do not introduce large authoring-contract changes unless a phase explicitly
  calls for them and sample-project migration is included.
- Do not refactor structure and change semantics in the same step unless the
  semantics change is tiny and fully isolated.

---

## Agent-Friendly Refactor Principles

This codebase has been built heavily through coding-agent iteration, so the
refactor should explicitly optimize for future agent effectiveness as well as
human maintainability.

Agent-friendly refactoring is useful here. It is not a separate architecture
goal from good engineering; it is a practical constraint on how code and docs
should be shaped so future incremental work stays accurate and safe.

### What "agent-friendly" should mean in this repo

- responsibilities are local and discoverable
- public boundaries are explicit
- files are small enough to reason about without dragging in unrelated systems
- tests are close to the subsystem they protect
- docs identify the current source of truth clearly
- refactors reduce ambiguity rather than increasing indirection

### Refactor qualities that should help future agents

- split very large files by domain responsibility, not by arbitrary size alone
- preserve stable entry points even when internals are decomposed
- keep naming direct and literal rather than overly abstract
- reduce duplicated contract logic where drift can cause one-sided fixes
- keep canonical docs current so agents have reliable reference material
- keep verification paths simple and repeatable so agents can run them after
  each step

### Refactor qualities that would hurt future agents

- splitting files into many tiny layers with unclear ownership
- introducing abstraction only for aesthetic cleanliness
- large renames or moves mixed with behavior changes
- creating multiple competing docs that all sound canonical
- preserving giant catch-all files because "agents can handle big context"
- leaving implicit behavior undocumented and expecting future agents to infer it

### Working rule

When choosing between two refactor shapes, prefer the one that improves:

- locality of responsibility
- boundary clarity
- retrieval of the relevant file/doc/test
- confidence of targeted edits

Avoid refactors that merely redistribute code without making the next
incremental change easier to perform safely.

---

## Current Issues This Plan Targets

### 1. Command-surface safety is weaker than the project now needs

Current behavior allows a large subset of command objects to carry unknown
fields without a clean validation error. That is partly intentional for
composition commands such as `run_commands`, `run_parallel`, `spawn_flow`,
`run_entity_command`, and `run_project_command`, because they forward runtime
params into child flows.

The problem is that strict primitive commands do not yet have an equally strict
schema-level unknown-key validation layer. This makes optional-field typos
easier to miss.

Relevant files:

- `dungeon_engine/commands/registry.py`
- `dungeon_engine/commands/runner.py`
- `dungeon_engine/commands/builtin.py`
- `dungeon_engine/commands/library.py`

### 2. A handful of files have become too large and multi-purpose

High-concentration files now include:

- `dungeon_engine/commands/builtin.py`
- `dungeon_engine/commands/runner.py`
- `dungeon_engine/world/loader.py`
- `dungeon_engine/world/persistence.py`
- `dungeon_engine/engine/game.py`
- `tools/area_editor/area_editor/app/main_window.py`
- `tools/area_editor/area_editor/widgets/tile_canvas.py`
- `tools/area_editor/area_editor/widgets/entity_instance_json_panel.py`

These files are not "bad code" by default, but they are expensive to review,
harder to test in isolation, and more likely to accumulate accidental coupling.

### 3. Runtime/editor contract logic is intentionally duplicated

The editor correctly avoids importing `dungeon_engine`, but the practical
result is duplicated logic for:

- manifest path resolution
- content-id derivation
- shared display dimension reading
- content discovery rules

That duplication is understandable, but it creates drift risk.

Relevant files:

- `dungeon_engine/project.py`
- `tools/area_editor/area_editor/project_io/manifest.py`

### 4. JSON payload caching is session-global and has no explicit invalidation

The command runner caches JSON file reads for value sources. That is currently
fine for static play sessions, but it is fragile for:

- future live-authoring or quick re-test workflows
- any in-session reload behavior
- debugging cases where the content file changes while the process remains open

Relevant file:

- `dungeon_engine/commands/runner.py`

### 5. Runtime tests are strong but too centralized

The runtime suite currently provides real safety, but too much of it lives in a
single giant test file. That hurts:

- discoverability
- reviewability
- targeted debugging
- future contributor onboarding

Relevant file:

- `tests/test_strict_content_ids.py`

### 6. Some docs have drifted out of date

Known example at the time of writing:

- `tools/area_editor/ARCHITECTURE.md` still describes editing/saving/validation
  as planned, while `tools/area_editor/README.md` describes a far more advanced
  implemented editor surface.

There may be more doc drift across:

- engine-facing canonical docs
- author-facing docs
- summary docs
- editor docs
- planning docs that are still being mistaken for active truth

### 7. Static reference validation is useful but heuristic-heavy

The current validation catches real problems, but its key-name heuristics can
become brittle as the JSON surface expands.

Relevant file:

- `dungeon_engine/startup_validation.py`

---

## Refactor Rules

These rules apply across the entire plan.

### Rule 1: Separate semantic changes from structural changes

Do not split a large file and tighten runtime behavior in the same PR unless
the behavior change is tiny, explicit, and very well tested.

### Rule 2: Keep the sample projects valid at every phase

If a phase touches command semantics, content loading, project lookup,
references, or docs describing canonical behavior, the sample projects must be
revalidated directly.

### Rule 3: Update docs as part of the phase that changes reality

Do not defer doc updates to the end of the whole plan if the phase changes the
active truth of the engine/editor contract.

After each concrete implementation step, review the affected docs immediately
and update them before moving on unless the step is explicitly a temporary
internal-only change with no user-facing or contributor-facing impact.

### Rule 4: Preserve the editor/runtime boundary

Do not re-couple the editor by importing large runtime modules.

The default strategy for this plan is separate implementations plus contract
parity tests. If a tiny neutral helper ever becomes obviously worth sharing,
treat that as an explicit exception case that still requires a packaging or
import-path decision and parity-test coverage.

### Rule 5: Prefer warning mode before hard enforcement

When tightening content validation, add a temporary warning or audit mode first
so real projects can be cleaned up before hard failures are introduced.

### Rule 6: Execute one step at a time

This plan is meant to be carried out incrementally.

For each step:

1. make the smallest reasonable change
2. run the relevant checks
3. review and update the affected docs
4. confirm the step is stable
5. only then continue to the next step

Do not batch multiple risky steps together just because they belong to the same
phase.

### Rule 7: Stop on real blockers and realign explicitly

If execution hits a blocker with non-obvious consequences, stop and discuss
before continuing.

Examples:

- unclear command-surface compatibility tradeoffs
- runtime/editor boundary changes that could introduce coupling
- sample-project content that needs migration but reveals a design conflict
- docs that disagree with each other in a way that suggests the code's intended
  behavior is itself unclear

### Rule 8: End with a full code-and-docs audit

At the end of the plan, do a deliberate final pass over:

- runtime code
- editor code
- canonical docs
- author-facing docs
- summary docs
- editor docs

That final pass should explicitly look for:

- outdated statements
- underdocumented behavior
- contradictory docs
- code paths that changed during the refactor but were never documented clearly

Fix those issues before considering the refactor complete.

---

## Execution Mode For This Plan

This plan should be executed in the following mode:

- work one step at a time
- after every change, review the impacted docs and update them if needed
- after every step, run the relevant verification checks before continuing
- if a step reveals stale docs, fix them as part of that same step rather than
  deferring the update
- continue phase by phase until the work is complete or a real blocker requires
  discussion
- if blocked, stop cleanly, summarize the blocker, and realign before taking on
  the next risky change
- after all planned work, do one thorough whole-repo pass for code and docs and
  fix anything still outdated, unclear, or incorrectly documented

---

## Verification Standard For Every Phase

Unless a phase is explicitly docs-only, use the following verification set.

### Runtime tests

```text
.venv/Scripts/python -m unittest discover -s tests -v
```

### Editor tests

From `tools/area_editor/`:

```text
..\..\.venv/Scripts/python -m unittest discover -s tests -v
```

### Direct project-command validation

```text
@'
from pathlib import Path
from dungeon_engine.project_context import load_project
from dungeon_engine.commands.library import validate_project_commands

for project_json in [
    Path(r"C:\Syncthing\Vault\projects\puzzle_dungeon_v3\python_puzzle_engine\projects\test_project\project.json"),
    Path(r"C:\Syncthing\Vault\projects\puzzle_dungeon_v3\python_puzzle_engine\projects\game_copy\project.json"),
]:
    project = load_project(project_json)
    validate_project_commands(project)
    print(f"{project.project_root.name}: project command validation OK")
'@ | .venv/Scripts/python -
```

### Headless smoke boot

```text
.venv/Scripts/python run_game.py --headless --project projects/test_project --max-frames 5
.venv/Scripts/python run_game.py --headless --project projects/game_copy --max-frames 5
```

### Documentation verification

For phases that change behavior, confirm that all of the following are aligned
before the phase is considered complete:

- `ENGINE_JSON_INTERFACE.md`
- `AUTHORING_GUIDE.md`
- `README.md`
- `CHANGELOG.md`
- relevant editor docs under `tools/area_editor/`

For any individual implementation step, use the same idea at smaller scope:

- identify which docs are affected by the step
- review those docs immediately after the code change
- patch outdated or incomplete statements before moving to the next step
- if the correct wording is unclear because the intended behavior is unclear,
  treat that as a blocker and stop to realign

---

## Workstreams

The plan is organized into parallel workstreams, but the execution order later
in this document intentionally sequences them conservatively.

### Workstream A: Command-Surface Hardening

Goal:

- reject actual typos on strict primitive commands
- preserve intentional passthrough behavior on composition commands

Main idea:

- classify commands instead of treating every command object the same

Suggested command classes:

- `strict`
  Unknown authored fields should be rejected.
- `passthrough`
  Unknown fields are allowed because they are part of runtime-param forwarding.
- `mixed`
  The command has a known public parameter surface, but also intentionally
  carries inherited runtime params into nested child flows.

Expected deliverables:

- command metadata in `CommandRegistry`
- startup validation that can consult command metadata
- tests for positive and negative cases
- content cleanup for sample projects if warnings surface

### Workstream B: Large-Module Decomposition

Goal:

- reduce file size and responsibility sprawl without changing behavior

Candidates:

- `dungeon_engine/commands/builtin.py`
- `dungeon_engine/commands/runner.py`
- `dungeon_engine/world/loader.py`
- `dungeon_engine/world/persistence.py`
- `dungeon_engine/engine/game.py`
- `tools/area_editor/area_editor/app/main_window.py`
- `tools/area_editor/area_editor/widgets/tile_canvas.py`
- `tools/area_editor/area_editor/widgets/entity_instance_json_panel.py`

Expected deliverables:

- smaller domain modules
- preserved public entry points
- no author-facing contract change during the split phase

### Workstream C: Runtime/Editor Contract Parity Hardening

Goal:

- keep duplicated manifest/content-id logic aligned without violating the
  editor boundary

Scope:

- project-path resolution helpers
- path-derived typed IDs
- shared project display dimension reading
- content discovery rules where safe

Expected deliverables:

- parity tests proving runtime/editor agreement on fixture projects
- clearer naming around the separate runtime/editor contract surfaces
- small readability-focused internal cleanups that do not create shared-code
  coupling

### Workstream D: Cache Lifetime And Reload Safety

Goal:

- replace module-global implicit cache lifetime with explicit session-owned
  behavior

Expected deliverables:

- cache object with explicit ownership
- clear invalidation points
- tests covering "file changed between reads" behavior

### Workstream E: Test Suite Reshaping

Goal:

- keep current coverage while making the test surface easier to work with

Expected deliverables:

- extracted test helpers/fixtures
- smaller subsystem-oriented test files
- unchanged or improved behavioral coverage

### Workstream F: Documentation Audit And Catch-Up

Goal:

- identify outdated docs systematically
- fix active-truth docs in lockstep with refactor phases
- stop planning docs and implementation docs from drifting into each other

Expected deliverables:

- documentation inventory and status map
- explicit "canonical vs summary vs planning vs historical" labels
- quick fixes for known drift
- phased doc updates tied to the relevant implementation work

---

## Documentation Audit And Catch-Up Track

This is a full workstream, not a postscript.

### Step F0: Build a documentation inventory

Create a simple inventory table of repo docs with:

- path
- purpose
- status: canonical / summary / planning / historical / editor-specific
- current owner or responsible area
- whether the doc must match implementation exactly

Initial candidates:

- `PROJECT_SPIRIT.md`
- `README.md`
- `AUTHORING_GUIDE.md`
- `ENGINE_JSON_INTERFACE.md`
- `architecture.md`
- `CONTRIBUTING.md`
- `CHANGELOG.md`
- `roadmap.md`
- all relevant docs in `tools/area_editor/`
- selected active plans in `plans/`

### Step F1: Mark known drift immediately

Before deeper refactors, fix obvious status mismatches and stale statements.

Known current target:

- `tools/area_editor/ARCHITECTURE.md`

Likely follow-ups:

- any editor plan/doc that still describes already-shipped workflows as future
  work
- summary docs that understate or overstate current editor/runtime capability

### Step F2: Define documentation truth order

Adopt and enforce this order when behavior changes:

1. planning doc for the intended change
2. implementation
3. canonical contract docs
4. author-facing docs
5. summary/marketing/status docs
6. changelog entry

The project already gestures toward this order in existing planning docs; this
step makes it explicit and operational.

### Step F3: Add a docs review checklist to contributor guidance

Update `CONTRIBUTING.md` and agent onboarding guidance so that any contract or
workflow change explicitly asks:

- which docs are canonical for this surface?
- which summary docs mention it?
- which editor docs mention it?
- is any planning doc now obsolete or misleading?

### Step F4: Add "doc status" headers where helpful

For docs that are easy to misread, add a short status section such as:

- `Status: Active canonical reference`
- `Status: Summary overview`
- `Status: Planning doc`
- `Status: Historical reference`

This is especially useful for editor docs and older plan files that still read
like active specifications.

### Step F5: Audit docs after every major phase

At the end of each non-trivial phase, run a focused doc audit:

- search for renamed APIs/fields
- search for removed lifecycle patterns
- search for editor capability statements that changed
- search for outdated "planned" language

This should be a checklist item in the phase exit criteria, not a best-effort
reminder.

### Step F6: Audit docs after every implementation step, not only every phase

The minimum rhythm for this refactor is:

1. code change
2. targeted verification
3. targeted docs review and fix-up
4. continue only if stable

The phase-level audit remains important, but it does not replace per-step doc
maintenance.

---

## Phase Plan

## Phase 0: Baseline Harness And Documentation Census

Purpose:

- lock in the current known-good baseline
- create the inventory needed to prevent doc drift during later work

Work:

- keep a saved verification checklist in-repo or in the plan
- record the current passing command-validation and headless-boot paths
- build the documentation inventory described in Workstream F
- patch obvious doc drift that is already known and low-risk

Success criteria:

- baseline verification commands are documented and repeatable
- documentation inventory exists
- known obvious drift is corrected or explicitly noted

## Phase 1: Command Validation Metadata In Audit Mode

Purpose:

- classify commands before enforcing anything

Work:

- extend `CommandRegistry` metadata to describe strict vs passthrough behavior
- annotate built-in commands with that metadata
- add a validator or audit pass that reports unknown keys on strict primitives
  without failing startup yet
- add tests covering:
  - strict primitive typo
  - passthrough composition command with custom param
  - mixed command carrying inherited runtime params correctly

Success criteria:

- audit output exists
- no sample-project regressions
- warning cases are understandable and actionable

## Phase 2: Content Cleanup And Hard Enforcement For Strict Primitives

Purpose:

- convert the audit results into real authoring safety

Work:

- clean any sample-project or test fixtures that rely on accidental permissive
  behavior
- promote strict-primitive unknown-key warnings into hard validation errors
- keep orchestration and dispatch commands explicitly permissive where needed

Success criteria:

- sample projects validate cleanly
- strict primitive typos fail fast with clear errors
- composition commands still support caller-supplied runtime params

## Phase 3: Cache Ownership And Invalidation

Purpose:

- make JSON payload caching explicit and session-scoped

Work:

- replace module-global cache state with a cache object
- bind cache lifetime to a game/session/runner owner
- clear cache on load/reload/new game boundaries as appropriate
- add file-change tests
- document the intended cache lifetime in engine docs if it becomes part of
  the operational model

Success criteria:

- no behavior regressions in normal play
- explicit invalidation points exist
- future live-authoring workflows are no longer blocked by implicit stale cache
  behavior

## Phase 4: Runtime/Editor Contract Parity Hardening

Purpose:

- stop runtime/editor drift on manifest and content-id rules without forcing a
  shared Python module

Work:

- keep separate runtime/editor implementations for project-layout rules
- add parity tests loading the same fixture through both code paths
- introduce clearer names for those two surfaces:
  - runtime: `dungeon_engine/project_context.py`
  - editor: `tools/area_editor/area_editor/project_io/project_manifest.py`
- allow small internal cleanup on each side if it improves readability, but do
  not turn that into cross-import coupling
- keep the editor decoupled from runtime-only state and systems

Current execution note:

- The first safe slice of this phase is now complete:
  - preferred alias modules exist for the two separate surfaces
  - parity tests cover explicit paths, default conventions, typed IDs, and
    global-entity ordering/template references
- The naming cleanup is now complete on the runtime side as well:
  - `dungeon_engine/project_context.py` now owns the runtime implementation
  - `dungeon_engine/project.py` remains as a compatibility wrapper for older
    imports
- The repo's own runtime-facing callers now prefer `project_context.py`
  directly, so the compatibility wrapper is no longer the default internal path
- Keep future work on this phase focused on parity gaps and readability, not on
  inventing shared-code packaging unless a later need clearly justifies it.

Success criteria:

- editor/runtime agreement is tested
- no `dungeon_engine` import leakage into the editor
- the separate implementations remain understandable and intentionally named

## Phase 5: Runtime Structural Refactors

Purpose:

- split the largest runtime modules without changing author-facing behavior

Current execution note:

- The first safe extraction slice is complete:
  - presentation-oriented builtin commands now live in
    `dungeon_engine/commands/builtin_domains/presentation.py`
  - `dungeon_engine/commands/builtin.py` remains the public registration entry
    point
- Presentation now also owns entity animation/visual playback commands, so
  screen-space presentation and entity-facing visual commands live in one
  domain instead of being split between modules.
- The second safe extraction slice is also complete:
  - camera-oriented builtin commands now live in
    `dungeon_engine/commands/builtin_domains/camera.py`
- Movement-oriented builtin commands now also live in
  `dungeon_engine/commands/builtin_domains/movement.py`, including position
  setters, interpolated movement, push/facing interactions, and `wait_for_move`
  handling.
- Another safe extraction slice is now complete:
  - flow/orchestration builtin commands now live in
    `dungeon_engine/commands/builtin_domains/flow.py`
  - `dungeon_engine/commands/builtin.py` still owns shared helper utilities
    and remains the public registration entry point
  - shared camera normalizers still live in `builtin.py` for reuse by
    `change_area` and `new_game`, and are injected into the camera registration
    helper explicitly to avoid circular imports
- The third safe extraction slice is also complete:
  - runtime-control builtin commands now live in
    `dungeon_engine/commands/builtin_domains/runtime_controls.py`
  - that domain now owns input routing, area/session transitions, save/load and
    quit hooks, and debug runtime-control commands without changing the public
    registration entry point
- The fourth safe extraction slice is also complete:
  - inventory-oriented builtin commands now live in
    `dungeon_engine/commands/builtin_domains/inventory.py`
  - inventory-only helper logic moved with them, while shared persistence and
    child-runtime wiring are still injected from `builtin.py` to keep the split
    behavior-neutral
- Inventory session open/close commands now live in the same inventory domain,
  keeping inventory UI/runtime entry points next to inventory-state commands.
- Keep the next slices behavior-neutral and domain-based so the registration
  flow stays easy for both humans and agents to follow.
- As part of the ongoing cleanup, unused nested movement helpers in
  `dungeon_engine/commands/builtin.py` have been removed once test coverage
  confirmed they were dead code.
- The next remaining hotspot is the entity-state / persistence-heavy portion of
  `builtin.py`; treat the next split there as a careful design step rather than
  another purely mechanical extraction.

Recommended order:

1. `dungeon_engine/commands/builtin.py`
2. `dungeon_engine/commands/runner.py`
3. `dungeon_engine/world/loader.py`
4. `dungeon_engine/world/persistence.py`
5. `dungeon_engine/engine/game.py`

Suggested submodule targets:

- command domains: flow, movement, interaction, dialogue, inventory, audio,
  screen, camera, state, save/game
- runner domains: tokens, value sources, execution, handles
- loader domains: area parsing, entity parsing, template resolution, validation
- persistence domains: data model, capture, apply, travelers, reset helpers

Success criteria:

- same public entry points remain
- behavior stays green under the full verification suite
- file size and review burden drop materially

## Phase 6: Editor Structural Refactors

Purpose:

- reduce central editor-window sprawl without changing workflows

Recommended order:

1. `tools/area_editor/area_editor/app/main_window.py`
2. `tools/area_editor/area_editor/widgets/tile_canvas.py`
3. `tools/area_editor/area_editor/widgets/entity_instance_json_panel.py`

Likely extraction targets:

- project open/load lifecycle
- content file operations
- rename/move/delete reference update helpers
- dock construction and signal wiring
- area-tab lifecycle
- canvas selection/brush state
- entity panel field parsing/building helpers

Success criteria:

- editor tests remain green
- file responsibilities are clearer
- future editor catch-up work becomes easier to land safely

## Phase 7: Test Suite Restructuring

Purpose:

- keep current coverage while making the suite maintainable

Work:

- extract common fixture builders and fake runtime helpers from the giant
  runtime test file
- split by subsystem:
  - command execution and flow
  - content loading and validation
  - persistence and travelers
  - input, renderer, and runtime services
  - startup validation and sample-project behavior
- keep editor tests grouped by surface but factor any repeated setup

Current execution note:

- The runtime suite has already been partially decomposed without behavior
  changes by extracting dedicated modules for:
  - command authoring and runtime cache coverage
  - authored content contract coverage
  - input/camera runtime coverage
  - inventory/item runtime coverage
- Keep further extractions responsibility-based rather than line-count-based.

Success criteria:

- no coverage loss
- failures are easier to localize
- contributors can find the right test file quickly

## Phase 8: Static Reference Validation Tightening

Purpose:

- reduce heuristic brittleness as the JSON surface grows

Work:

- introduce a declarative registry of known reference-bearing fields
- keep heuristic fallback temporarily with logging for misses
- add tests for both canonical reference keys and intentional non-reference
  keys
- update author docs so reference-bearing fields are clearly documented

Success criteria:

- fewer false positives and false negatives
- validator logic is easier to extend deliberately

## Phase 9: Final Documentation Synchronization Pass

Purpose:

- ensure the refactor is reflected clearly and consistently

Work:

- update canonical docs first:
  - `ENGINE_JSON_INTERFACE.md`
  - `AUTHORING_GUIDE.md`
- then summary docs:
  - `README.md`
  - `architecture.md`
  - `CONTRIBUTING.md`
- then editor docs:
  - `tools/area_editor/README.md`
  - `tools/area_editor/ARCHITECTURE.md`
  - any still-active planning/status docs that could mislead readers
- add a concise `CHANGELOG.md` summary of the refactor outcome
- perform a final code-and-docs audit to find anything still underdocumented,
  incorrect, contradictory, or stale after the earlier phase-by-phase updates

Success criteria:

- no known doc contradictions remain in active docs
- planning docs are clearly marked as plans, not active contract
- no significant refactor-touched area remains poorly documented or obviously
  outdated after the final audit
- onboarding order stays coherent

---

## Suggested PR / Task Breakdown

Keep the refactor incremental. One reasonable slicing is:

1. baseline verifier note + docs inventory + obvious editor-doc drift fixes
2. command metadata plumbing
3. command audit mode + tests
4. strict-command enforcement + fixture cleanup
5. JSON cache ownership + invalidation tests
6. runtime/editor contract parity hardening
7. runtime refactor slice 1: builtins
8. runtime refactor slice 2: runner
9. runtime refactor slice 3: loader
10. runtime refactor slice 4: persistence/game
11. editor refactor slice 1: main window
12. editor refactor slice 2: canvas/entity panels
13. test suite split
14. static reference registry
15. final docs synchronization pass

Each PR should state clearly whether it is:

- structural only
- behavior tightening
- docs only
- mixed, with an explanation of why the mix is safe

---

## Risks And Mitigations

### Risk: strict validation breaks real authored content

Mitigation:

- add audit/warning mode first
- classify commands carefully before enforcement
- revalidate sample projects directly, not only through unit tests

### Risk: refactors cause hidden behavior changes

Mitigation:

- keep structural refactors behavior-neutral
- use the full verification set after each slice
- avoid changing author-facing docs until the implementation slice is stable

### Risk: runtime/editor contract cleanup re-couples the editor to runtime code

Mitigation:

- keep the default strategy as separate implementations plus parity tests
- keep UI/runtime systems separate
- add explicit boundary checks in review

### Risk: docs still drift even after the plan

Mitigation:

- create the docs inventory early
- add status labels to ambiguous docs
- add docs review to contributor rules
- make doc updates part of phase exit criteria

---

## Success Criteria For The Whole Plan

This plan succeeds if, at the end:

- strict primitive command typos fail clearly and early
- intentional runtime-param forwarding still works where designed
- the runtime/editor contract is covered by explicit parity tests and clearer
  surface naming without collapsing the editor/runtime boundary
- the largest modules are materially easier to review and change
- tests remain strong but are no longer dominated by one giant runtime file
- active docs are visibly current and planning docs are clearly labeled as such
- `projects/test_project` and `projects/game_copy` still validate and boot
  cleanly through the same startup-style paths the engine uses in practice

---

## Recommended Starting Point

If this plan is executed in stages, start here:

1. docs inventory and immediate doc-drift fixes
2. command metadata plus audit-mode validation
3. cache ownership cleanup

That sequence gives the project safer authoring feedback and cleaner project
documentation before the heavier structural splits begin.
