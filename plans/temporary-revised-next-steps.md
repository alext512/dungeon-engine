# Temporary Revised Next-Steps Plan

This is a temporary planning note capturing the current "best final state"
direction after the `CommandContext` cleanup work.

This plan is intentionally not just a copy of external evaluation suggestions.
It takes outside feedback into account, but prioritizes changes based mainly on
how beneficial the end result would be for the engine.

## Planning Principles

- Prioritize the best final architecture, not just the easiest cleanup.
- Prefer changes that improve the engine's long-term clarity and usefulness.
- Optimize for real runtime + authoring quality, not only for type neatness.
- Treat the runtime, docs, validator, editor, and sample content as one system.
- Keep license work out of scope for now.

## North Star

The target end state is:

- a focused puzzle/RPG engine with an explicit JSON authoring contract
- a strict, understandable command/runtime boundary
- an external editor that acts as a true peer to the runtime
- docs, validators, tests, and example content that all describe the same system
- a codebase that is pressure-tested through real project content, not just
  isolated unit tests

## Recommended Priorities

## 1. Make The Engine Contract Authoritative

This is the highest-value next step.

The engine's real value lives in the contract between:

- authored JSON
- builtin commands
- validators
- runtime behavior
- editor behavior
- public docs

That contract is better than it used to be, but key knowledge still lives in
multiple places.

### Goals

- strengthen `docs/authoring/manuals/engine-json-interface.md` as the canonical
  public contract
- centralize builtin command metadata where practical
- reduce duplication around engine-owned JSON fields and authored surfaces
- make it harder for docs, runtime, validator, and editor to drift apart

### Likely Areas

- `dungeon_engine/commands/registry.py`
- `dungeon_engine/commands/builtin.py`
- `dungeon_engine/world/loader.py`
- `dungeon_engine/world/serializer.py`
- `dungeon_engine/startup_validation.py`
- `tools/area_editor/area_editor/project_io/`
- `docs/authoring/manuals/engine-json-interface.md`

### Why This Matters

- improves architectural coherence more than pure typing work
- makes docs more trustworthy
- makes future refactors cheaper
- strengthens the project as an authored engine, not just a runtime

## 2. Finish Hardening The Command/Runtime Boundary

The big `CommandContext` problem is solved architecturally. The next step is to
make the new boundary feel finished and intentional.

### Goals

- tighten runtime hook signatures
- reduce semantically invalid service states where practical
- distinguish flexible test assembly from stricter production assembly
- improve safety without turning the code into a type-gymnastics exercise

### Concrete Directions

- replace generic runtime hook types with stronger signatures where possible
- consider stricter constructors/helpers for production runtime wiring
- keep partial service bundles available where tests genuinely benefit from them
- only chase `Any` removal where it creates real value

### Likely Areas

- `dungeon_engine/commands/context_services.py`
- `dungeon_engine/commands/registry.py`
- `dungeon_engine/commands/runner.py`
- `dungeon_engine/engine/game.py`

### Why This Matters

- improves refactor safety
- reduces accidental invalid states
- makes command code easier to trust and extend

## 3. Strengthen Real-Project Verification

This is more important than squeezing out the last bit of static type precision.

The engine should keep being validated through actual project content and real
startup paths.

### Goals

- expand repo-local project validation
- increase confidence in startup-style verification, not only unit tests
- add more smoke coverage for core authored flows

### Coverage Worth Strengthening

- startup validation
- project command validation
- area transitions
- dialogue flow
- inventory flow
- save/load restoration
- input routing
- runtime handoff points

### Likely Areas

- `dungeon_engine/startup_validation.py`
- `dungeon_engine/commands/library.py`
- `tests/`
- `projects/`

### Why This Matters

- keeps abstractions honest
- catches content-facing regressions earlier
- makes aggressive refactoring much safer

## 4. Make The External Editor A True First-Class Peer

This is not just tooling polish. For this engine, the editor is part of the
real product surface.

### Goals

- strengthen parity between runtime and editor project interpretation
- expand editor coverage for engine-owned authored fields
- improve reference-picking and direct-manipulation workflows
- improve runtime handoff and author feedback loops
- strengthen round-trip confidence between authoring and runtime loading

### Likely Areas

- `tools/area_editor/`
- `tools/area_editor/area_editor/project_io/manifest.py`
- parity tests between runtime/editor manifest handling

### Why This Matters

- improves real usability, not just architecture aesthetics
- pressure-tests the authoring contract
- raises the project's value as an engine workflow, not only a codebase

## 5. Pressure-Test With Canonical Sample Content

The project should have sample content whose job is to exercise the engine's
important authored surfaces, not merely serve as a demo.

### Goals

- maintain one or more canonical sample projects
- deliberately exercise the core authored systems
- use them as living contract fixtures

### Important Systems To Exercise

- dialogue
- area transitions
- camera state
- inventory
- persistence
- entity refs
- global entities
- input routing
- editor/runtime round-trip behavior

### Why This Matters

- grounds abstractions in real content
- improves docs and examples
- raises confidence in future refactors

## 6. Keep Maintainer And Contributor Clarity Strong

This matters, but it should follow the contract/editor/verification work rather
than replace it.

### Goals

- keep onboarding docs aligned with the real code
- strengthen "if you change X, also check Y/Z" guidance
- maintain a clear truth map for the engine surface

### Likely Areas

- `AGENTS.md`
- `README.md`
- `docs/development/engine-in-10-minutes.md`
- contributor/developer guidance docs

### Why This Matters

- reduces hidden system knowledge
- lowers maintenance cost
- improves long-term sustainability

## What To De-Prioritize

These should not drive the roadmap right now:

- maximizing type purity at the generic injection edge
- refactors that mostly improve elegance but not the engine contract
- broad generic-product packaging work
- genericizing the engine away from its current focused identity
- historical cleanup in archived planning/history docs
- license work for now

## Priority Order By End-State Benefit

1. Make the engine contract authoritative.
2. Finish hardening the command/runtime boundary.
3. Strengthen real-project verification.
4. Make the external editor a true first-class peer.
5. Pressure-test with canonical sample content.
6. Keep maintainer/contributor clarity strong.

## Short Version

If only a few things move forward next, the best-value direction is:

1. Consolidate and centralize the engine's authored contract.
2. Tighten the new command/runtime boundary where it truly matters.
3. Verify the engine more through real project content and startup paths.
4. Keep the external editor moving toward full parity with the runtime.
