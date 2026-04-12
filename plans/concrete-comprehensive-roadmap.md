# Concrete Comprehensive Roadmap

This roadmap turns the higher-level "revised next steps" direction into a
concrete execution plan. It is intentionally not a copy of any outside
evaluation. External feedback can be useful input, but the priorities here are
based mainly on what would create the strongest final engine.

The bias of this roadmap is:

- optimize for the best eventual engine and authoring experience
- keep progress manageable and verifiable
- preserve user-authored JSON unless we deliberately decide to evolve the
  public contract later
- treat runtime, validation, docs, editor behavior, and sample content as one
  system
- remove retired paths and alternate import surfaces rather than preserving them
- favor the most effective refactor path even when it is heavier

## North Star

The target end state is:

- one clear engine contract for what authored JSON means
- one strict and understandable boundary between command code and runtime code
- one external editor that behaves like a real peer to the runtime
- one verification story that proves real projects still work
- one set of docs and sample content that match the actual engine behavior

## What "Success" Looks Like

At the end of this roadmap, the project should feel like:

- a stable authored engine rather than a collection of implementation details
- a runtime whose behavior is easier to predict and safer to refactor
- an editor workflow that is aligned with the runtime instead of trailing it
- a codebase where real project validation carries as much weight as unit tests
- a repo where contributors can tell which files define the public contract

## Roadmap Rules

These rules apply across every phase:

- Prefer behavior-preserving contract clarification before contract expansion.
- Do not change end-user JSON casually.
- If we want to evolve authored JSON, do it as an explicit contract change with
  docs, validation, migration notes, and project updates together.
- Every phase should leave the docs better than they were before.
- Every phase should add or tighten verification, not just move code around.
- Treat repo-local projects as contract fixtures, not as optional demos.
- Remove retired paths and alternate import surfaces instead of keeping them around.
- Do not let refactor difficulty push us into weaker, less effective outcomes.

## Recommended Execution Order

The best sequencing is:

1. Phase 0: establish the truth map and working safety rails
2. Phase 1: make the engine contract authoritative
3. Phase 2: finish hardening the command/runtime boundary
4. Phase 3: strengthen real-project verification
5. Phase 4: make the external editor a true first-class peer
6. Phase 5: pressure-test with canonical sample content
7. Phase 6: keep maintainer and contributor clarity strong

This is the execution order, not the value order. In value terms, the contract
work is still the center of gravity. Phase 0 exists only to make the rest of
the roadmap safer and more deliberate.

## Phase 0: Truth Map And Safety Rails

### Purpose

Create a precise map of where the real engine contract currently lives, and add
enough verification scaffolding that later work does not drift or regress.

### Why Start Here

Without this, later cleanup turns into guesswork. With it, every later phase
has a stronger baseline and a clearer definition of "done."

### Concrete Deliverables

- a "contract truth map" doc that points to the authoritative runtime, docs,
  validation, serialization, and editor entry points
- a short inventory of known drift-prone surfaces
- a repeatable validation checklist for contract-sensitive changes
- a current-state gap list: "documented but not enforced," "enforced but not
  documented," and "editor/runtime mismatch"

### Concrete Work

- Trace the contract surface across:
  - `dungeon_engine/commands/`
  - `dungeon_engine/world/`
  - `dungeon_engine/startup_validation.py`
  - `dungeon_engine/project_context.py`
  - `tools/area_editor/area_editor/project_io/`
  - `docs/authoring/manuals/engine-json-interface.md`
- Record which file is authoritative for each contract area.
- Mark where runtime behavior is inferred rather than explicit.
- Identify engine-owned fields whose validation or docs are scattered.
- Capture this in a durable planning/reference doc rather than leaving it in
  discussion history.

### Validation Gate

- Runtime unit tests still pass.
- The current repo-local project validation path still passes.
- The truth-map doc is detailed enough that a contributor can answer "where is
  this contract actually defined?" without code archaeology.

### Done Means

- We have a concrete map of contract ownership.
- We know where the likely drift points are.
- We have a reliable baseline for the next phases.

## Phase 1: Make The Engine Contract Authoritative

### Purpose

Turn the engine/JSON contract into an explicit, authoritative, maintained
surface instead of something spread across runtime behavior, validators, docs,
and editor assumptions.

### Important Plain-Language Clarification

This phase does not need to change authored JSON for end users.

The default plan is:

- clarify the contract
- centralize the contract
- enforce the contract more consistently
- document the contract more clearly

Only later, and only deliberately, would we change the contract itself.

### Desired Outcome

A contributor should be able to answer all of these quickly:

- What JSON shapes are actually supported?
- Which fields are engine-owned?
- Which values are author-authored versus runtime-populated?
- Which command shapes are valid?
- Which parts are stable public contract versus implementation detail?

### Concrete Deliverables

- a strengthened `docs/authoring/manuals/engine-json-interface.md` that is
  clearly treated as the public contract reference
- tighter alignment between builtin command registration and documented command
  shape
- clearer ownership of engine-known special fields and special JSON surfaces
- reduced duplication between loader, serializer, startup validation, and
  editor-side project interpretation

### Concrete Work

#### 1. Contract inventory

- Enumerate the major public contract categories:
  - project manifest shape
  - area/entity/template/item file shapes
  - builtin commands
  - value sources and tokens
  - engine-known entity fields
  - runtime-owned versus authored fields
  - save/persistence-facing authored assumptions
- For each category, record:
  - runtime authority
  - validation authority
  - documentation authority
  - editor-side interpretation point

#### 2. Builtin command metadata pass

- Review whether builtin commands have enough structured metadata to support:
  - validation
  - documentation alignment
  - future editor assistance
- Where practical, consolidate command-shape knowledge so it is not duplicated
  in several ad hoc places.
- Avoid turning this into over-abstract generic metadata if it does not produce
  real payoff.

#### 3. Engine-owned field clarification pass

- Audit engine-known entity and area fields.
- Separate:
  - stable public authoring fields
  - runtime-populated/transient fields
  - internal implementation details that should not leak into authoring docs
- Make that distinction explicit in docs and validation comments.

#### 4. Loader/serializer/validator/editor alignment pass

- Review high-risk areas where contract drift is likely:
  - project manifest interpretation
  - entity field acceptance
  - area camera/input field handling
  - command file loading rules
  - permissive versus strict handling of optional fields
- Tighten mismatches where the engine currently accepts one thing, documents
  another, or the editor assumes a third.

#### 5. Public contract documentation pass

- Update `docs/authoring/manuals/engine-json-interface.md` to reflect the
  actual intended contract after the clarification work.
- Cross-link supporting docs so the interface doc is clearly the canonical
  reference, while guides remain explanatory rather than authoritative.

### Files Most Likely Involved

- `dungeon_engine/commands/builtin.py`
- `dungeon_engine/commands/registry.py`
- `dungeon_engine/commands/library.py`
- `dungeon_engine/world/loader.py`
- `dungeon_engine/world/serializer.py`
- `dungeon_engine/startup_validation.py`
- `dungeon_engine/project_context.py`
- `tools/area_editor/area_editor/project_io/`
- `docs/authoring/manuals/engine-json-interface.md`
- `docs/authoring/manuals/authoring-guide.md`

### Validation Gate

- Runtime tests pass.
- Repo-local project validation passes.
- Any editor tests covering interpreted contract behavior pass.
- Documentation and runtime behavior agree on the touched contract surfaces.

### Done Means

- The project has a visibly more authoritative engine contract.
- The main contract surfaces have named owners.
- The docs are more trustworthy.
- Future command/editor/runtime work has a clearer foundation.

## Phase 2: Finish Hardening The Command/Runtime Boundary

### Purpose

Finish the architectural cleanup that started with `CommandContext` so the new
boundary feels fully intentional rather than merely "good enough."

### Desired Outcome

Commands depend on clearly defined services, runtime wiring is explicit, and
invalid service states are harder to construct accidentally.

### Concrete Deliverables

- stronger service bundle invariants for production runtime assembly
- tighter runtime hook typing
- less ambiguous injection behavior
- fewer semantically invalid states hidden behind optional fields and `Any`

### Concrete Work

#### 1. Split flexible assembly from strict assembly

- Keep test-friendly assembly tools where they are genuinely useful.
- Add stricter production constructors/helpers that build known-valid service
  bundles.
- Make the "loose for tests" path visibly different from the "runtime wiring"
  path.

#### 2. Tighten runtime hooks

- Replace remaining broad hook signatures such as `Callable[[Any], None]` with
  specific intent-bearing types where possible.
- Clarify what data each hook accepts and which runtime component owns it.
- Keep command-visible request payloads in `dungeon_engine/commands/context_types.py`
  so service typing does not depend on runner internals.
- Use named callback aliases for runtime actions such as load, save, quit,
  debug pause, simulation stepping, and output scaling.

#### 3. Tighten service bundle semantics

- Review optional world/runtime service fields and decide which ones are:
  - truly optional
  - only optional in tests
  - required in production
- Encode that more clearly in constructors, helpers, or distinct bundle types.

#### 4. Improve injection precision where it matters

- Review `resolve_service_injection(...)` and related registry flow.
- Reduce `Any` where it produces real safety and readability wins.
- Do not chase type purity in places where it adds ceremony without practical
  value.

#### 5. Re-check builtin command usage assumptions

- Confirm command implementations are consuming context/services through the
  intended boundary rather than smuggling old runtime assumptions back in.

### Files Most Likely Involved

- `dungeon_engine/commands/context_services.py`
- `dungeon_engine/commands/registry.py`
- `dungeon_engine/commands/runner.py`
- `dungeon_engine/engine/game.py`
- builtin command modules under `dungeon_engine/commands/builtin_domains/`

### Validation Gate

- Runtime tests pass.
- Focused tests for command injection/service construction pass.
- Repo-local project validation still passes.
- No alternate-path backsliding is reintroduced.

### Done Means

- The command/runtime boundary is no longer the obvious architectural weak spot.
- Production wiring is stricter and easier to trust.
- Tests can still assemble partial contexts without forcing production looseness.

## Phase 3: Strengthen Real-Project Verification

### Purpose

Make sure the engine is continuously validated through real project content and
startup-style execution paths, not only through isolated unit tests.

### Desired Outcome

The project can catch content-facing regressions earlier, especially after
contract or command-surface changes.

### Concrete Deliverables

- a stronger repo-local project validation path
- startup-style validation that is easy to run and hard to forget
- more smoke coverage for high-value authored workflows

### Concrete Work

#### 1. Raise project validation to first-class status

- Formalize the direct project validation snippet into a clearer, named
  workflow.
- Decide whether it should remain a documented snippet, become a test helper,
  or become a dedicated validation command.
- Keep the dedicated validation command covered by focused tests so its
  startup-validation behavior and exit codes stay reliable.

#### 2. Expand startup-style checks

- Ensure project manifests, command libraries, and referenced content are
  validated through the same paths the app uses at startup.
- Add targeted checks for known fragile surfaces like:
  - project command references
  - input-target routing
  - area transition targets
  - persistence-related assumptions

#### 3. Add smoke tests for authored flows

- Prefer a few meaningful integration-style tests over many shallow unit tests.
- Target flows such as:
  - dialogue
  - inventory mutations
  - area transitions
  - save/load restoration
  - runtime handoff points
- Keep the documented headless startup command covered by a smoke test for
  repo-local canonical content where practical.

#### 4. Make verification expectations more visible

- Update docs so contract-sensitive work always points people toward:
  - unit tests
  - repo-local project validation
  - editor tests when applicable
  - optional smoke start when feasible

### Files Most Likely Involved

- `dungeon_engine/startup_validation.py`
- `dungeon_engine/commands/library.py`
- `tests/`
- `README.md`
- `AGENTS.md`
- possibly repo-local validation helpers/scripts if we add them

### Validation Gate

- The expanded verification flow itself is documented and exercised.
- Runtime tests pass.
- Repo-local projects validate cleanly.
- Newly added smoke coverage passes.

### Done Means

- Refactors are safer because they are checked against real content.
- Contributors have a clearer idea of what "safe to merge" actually means.

## Phase 4: Make The External Editor A True First-Class Peer

### Purpose

Treat the editor as part of the engine product surface rather than as optional
tooling that loosely follows the runtime.

### Desired Outcome

The editor and runtime interpret project content consistently, expose the same
important engine-owned fields, and support a healthier authoring workflow.

### Concrete Deliverables

- stronger runtime/editor parity on shared project interpretation
- better editor coverage for engine-owned authored fields
- improved reference-picking and guardrails for JSON-backed authoring
- clearer runtime handoff points

### Concrete Work

#### 1. Runtime/editor parity audit

- Compare runtime and editor handling of:
  - manifest search roots
  - area/entity/item/shared-variable discovery
  - command discovery
  - engine-known fields
  - validation assumptions
- Turn mismatches into a named parity backlog.

#### 2. Fill the most important authoring gaps

- Prioritize editor coverage for fields that most affect correctness rather than
  cosmetic polish first.
- Especially consider:
  - newer engine-owned fields
  - command/reference pickers
  - manifest-backed references
  - safer structured editing for common authored surfaces

#### 3. Improve round-trip confidence

- Verify that what the editor writes is what the runtime expects.
- Add parity or round-trip tests where drift has been common or costly.

#### 4. Improve runtime handoff

- Clarify how authored changes move from editor to runtime testing.
- Reduce friction around validating edited content in the actual engine.

### Files Most Likely Involved

- `tools/area_editor/`
- `tools/area_editor/area_editor/project_io/project_manifest.py`
- editor tests under `tools/area_editor/tests/`
- runtime/editor parity tests if added

### Validation Gate

- Editor tests pass.
- Runtime tests still pass where shared contract surfaces were touched.
- Parity-sensitive scenarios have explicit test or validation coverage.

### Done Means

- The editor is a more reliable authoring peer.
- Contract drift between editor and runtime is less likely.
- Real author workflow quality improves.

## Phase 5: Pressure-Test With Canonical Sample Content

### Purpose

Use sample content as living contract fixtures that deliberately exercise the
engine's most important authored systems.

### Desired Outcome

The repo contains content that proves the engine contract in practice and
continues to protect it during future refactors.

### Concrete Deliverables

- one or more canonical sample projects with intentional coverage goals
- documented coverage expectations for what each sample project exercises
- sample content that is useful both for testing and for onboarding

### Concrete Work

#### 1. Define the sample-content role

- Decide which repo-local project is the main contract fixture.
- Optionally split responsibilities across more than one sample project if that
  keeps each one understandable.

#### 2. Cover the highest-value authored systems

- Make sure canonical sample content exercises:
  - dialogue
  - area transitions
  - camera defaults/state
  - inventory
  - persistence
  - entity references
  - global entities
  - input routing
  - command chaining/composition

#### 3. Align docs and validation with sample content

- Point onboarding and validation docs at the sample projects deliberately.
- Use the sample content to demonstrate the intended contract, not just to show
  something playable.

### Files Most Likely Involved

- `projects/`
- validation docs in `README.md` and `docs/`
- tests that use repo-local sample projects as fixtures

### Validation Gate

- Canonical sample projects validate cleanly.
- They exercise the intended authored surfaces.
- Docs accurately describe what they are proving.

### Done Means

- The engine is pressure-tested through real authored content.
- Examples and tests reinforce each other instead of drifting apart.

## Phase 6: Keep Maintainer And Contributor Clarity Strong

### Purpose

Make sure the project stays understandable after the deeper contract/runtime
work lands.

### Desired Outcome

Contributors can tell where to make changes, what counts as public contract,
and which validation paths matter after a refactor.

### Concrete Deliverables

- cleaner contributor guidance around contract ownership
- updated onboarding docs that match the current architecture
- explicit "if you change X, also check Y" guidance for drift-prone areas

### Concrete Work

- Update `AGENTS.md` when file ownership or validation expectations change.
- Update `README.md` so the repo entry points and verification advice remain
  accurate.
- Keep `docs/development/engine-in-10-minutes.md` aligned with the real engine
  shape, not an older mental model.
- Add short truth-map references where contributors are likely to need them.

### Files Most Likely Involved

- `AGENTS.md`
- `README.md`
- `docs/development/engine-in-10-minutes.md`
- any contributor/developer guidance touched by earlier phases

### Validation Gate

- The docs point to the same architecture we actually have.
- A new contributor can locate the main public-contract files without guesswork.

### Done Means

- Maintenance burden stays lower after the deeper changes.
- Knowledge is stored in the repo, not only in discussion history.

## Cross-Phase Decision Rules

When tradeoffs come up, use these rules:

- Prefer explicit contract ownership over clever abstraction.
- Prefer real project verification over theoretical neatness.
- Prefer editor/runtime parity over one-sided convenience.
- Prefer removing ambiguity over preserving vague flexibility.
- Prefer a small number of high-value contract fixtures over a large number of
  shallow examples.

## Things Not Worth Driving The Roadmap

These may still happen opportunistically, but they should not be the main
reason for a phase:

- chasing maximal `Any` removal everywhere
- genericizing the engine into an abstract framework
- large elegance-only refactors with weak user-facing payoff
- polishing archived/history/planning docs before active surfaces are aligned
- license work for now
- preserving retired paths or transitional adapter layers

## Suggested Implementation Cadence

The roadmap is large, so the right way to execute it is in bounded slices.

A good cadence is:

1. complete Phase 0 and the first slice of Phase 1
2. update docs/tests immediately with each slice
3. re-run runtime tests plus repo-local project validation after each
   contract-sensitive slice
4. only then move deeper into Phase 2 and later phases

In other words: do not wait until the end to update docs or verification.

## Best Immediate Starting Slice

If we begin right now, the strongest first slice is:

1. write the contract truth map
2. inventory the public contract categories
3. identify the highest-risk runtime/docs/editor drift points
4. tighten `engine-json-interface.md` around those points
5. add or formalize the matching verification path

That gives every later phase a clearer target and reduces the chance that we do
good refactor work against a fuzzy public contract.
