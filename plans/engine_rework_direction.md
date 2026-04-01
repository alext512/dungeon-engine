# Engine Rework Direction

This document captures the broader direction behind the next engine rework
phase.

It exists so the project does not drift into piecemeal implementation changes
without a shared frame for why those changes are happening.

## Why This Rework Exists

The project has succeeded at making gameplay highly data-driven, but that
success has exposed a second problem:

- too much core engine behavior is currently authored through low-level JSON
  orchestration

This makes the engine powerful, but it also makes it harder for future users to
author content without understanding engine machinery.

The next phase should improve the boundary between:

- engine-owned generic behavior
- project-authored game behavior

## Main Rework Goal

Move the project toward a model where:

- the engine provides a clearer built-in runtime contract
- projects still own templates, content, hooks, and game-specific outcomes
- authors do not need to rebuild core movement/collision/pushing logic through
  low-level JSON by default

This is not a rejection of the data-driven direction.
It is an attempt to make the data-driven direction more usable.

## The Core Shift

The project is moving from:

- "almost all behavior is authored through low-level command chains"

toward:

- "the engine owns generic runtime semantics, while project JSON configures and
  extends them"

This means the engine should become more explicit about things such as:

- grid movement rules
- collision rules
- pushing rules
- generic spatial event hooks
- other truly generic runtime mechanics

without taking over:

- puzzle solutions
- story logic
- dialogue meaning
- quest state
- game-specific flow

## The New Boundary

### The engine should own

- generic runtime semantics
- standard grid movement resolution
- standard collision meaning
- standard push meaning
- generic occupancy and blocked-movement event surfaces
- physical defaults
- runtime validation for those known fields

### Projects should own

- templates
- areas
- tags
- dialogue content
- puzzle hooks
- custom game logic
- project-level conventions built on top of the engine contract

The engine should not own privileged gameplay templates such as `player` or
`crate`.

## Why This Matters

Without this shift, the engine risks staying in an awkward middle state:

- too abstract to be beginner-friendly
- too low-level to be comfortable to author by hand
- too reliant on agents or engine-internal knowledge for ordinary content work

The rework should make the engine easier to understand and easier to use while
keeping the data-driven spirit.

## Short-Term Strategic Priorities

The next rework phase should prioritize:

1. defining a clear physics contract
2. tightening the engine/JSON boundary around that contract
3. documenting the new contract clearly
4. migrating the sample content to the new model
5. adding tests that lock the new semantics down

## What This Rework Is Not

This is not:

- a move toward a fully hardcoded gameplay engine
- a move toward privileged engine-owned content objects
- a move toward free movement or generic physics
- a move away from JSON authoring
- a move toward hardcoded puzzle-specific object behavior

This is also not an attempt to solve every higher-level authoring problem in one
pass.

The immediate target is the physics/collision/movement layer because it is the
clearest place where engine semantics should be explicit.

## Relationship To Higher-Level Authoring

The broader lesson behind this rework is:

- not every repeated low-level JSON pattern should remain low-level forever

Longer term, the same reasoning may apply to other systems such as:

- standard dialogue session handling
- standard menu handling
- common interaction patterns

But this document does not lock those later changes in yet.
For now, it records the architectural direction that the engine should become
clearer and more opinionated about generic runtime behavior.

## Spatial Interaction Boundary

One specific clarification for this rework direction:

- the engine may provide generic spatial hooks such as blocked-movement and
  occupant-enter or occupant-leave events
- reusable world objects such as buttons, holes, traps, and pressure plates
  should own their own authored response logic

So the engine should become better at exposing generic spatial events without
turning puzzle-specific acceptance rules into hardcoded engine systems.

Examples of authored logic that should remain project-owned:

- "this button only presses for weight > 5"
- "this hole accepts only triangle-tagged objects"
- "this trap ignores ghost-tagged entities"

Those are good uses of project logic layered on top of generic engine events.

## Expected Documentation Sequence

Use this general order:

1. planning docs under `plans/`
2. implementation work
3. canonical contract docs such as `ENGINE_JSON_INTERFACE.md`
4. author-facing docs such as `AUTHORING_GUIDE.md`
5. summary docs such as `README.md`, `architecture.md`, and `CHANGELOG.md`

This helps keep the temporary planning truth separate from the active
implementation truth.

## Rework Success Criteria

This rework is succeeding if:

- the engine has an explicit grid physics contract
- the sample project uses fewer low-level JSON workarounds for core movement
- a new author can understand how blocking and pushing work without reading
  engine internals
- tags remain optional for basic use
- advanced behaviors still have room to grow later

## Working Rule

When a new design question appears during this rework, ask:

1. Is this a generic runtime semantic the engine should own?
2. Or is it game-specific behavior the project should author?

If the answer is "generic runtime semantic," prefer making it explicit in the
engine contract.
If the answer is "game-specific behavior," keep it in authored data.
