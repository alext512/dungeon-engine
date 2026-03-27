# Project Spirit

This file describes the main spirit of the project.

It is not a code walkthrough, and it is not meant to be a perfect frozen specification.
Its purpose is to help future design decisions stay aligned with the actual goals of the engine and the project.

If code, plans, or convenience features start drifting away from these principles, this file should be consulted and, if needed, updated consciously rather than ignored silently.

## What This Project Is Trying To Be

This project is trying to build a game engine where gameplay behavior is genuinely authored in data, not secretly owned by Python systems that merely pretend to be data-driven.

The Python side should provide the runtime substrate:
- command execution
- state storage
- rendering
- input plumbing
- movement/collision/animation primitives
- persistence
- other low-level services

The project content should provide the game behavior:
- what entities do
- what interactions mean
- what menus do
- what dialogue does
- how camera behavior is chosen
- how inputs are routed
- how game-specific flows are composed

The goal is not "make everything configurable."
The goal is "keep authorship in the project data unless something truly belongs to engine infrastructure."

## Core Principles

### 1. Data Should Own Behavior

If a gameplay rule can reasonably live in authored data, it should not be hardcoded into the engine.

This especially applies to:
- dialogue flow
- menu flow
- UI/controller state
- control handoff
- camera choices
- puzzle logic
- scripted interactions

The engine may provide primitives and helpers, but it should not quietly take over the behavior itself.

### 2. The Engine Should Be A Substrate, Not A Secret Co-Author

The engine should run things, not decide the meaning of things.

Good engine responsibilities:
- execute command chains
- update runtime systems
- draw text/images
- move entities
- resolve collisions
- save/load state
- provide low-level camera and input services

Bad engine responsibilities:
- owning game-specific dialogue progression rules
- inventing privileged gameplay concepts without need
- deciding what inputs "really mean" for a project
- hiding important gameplay state in engine-only objects when entities/content should own it

### 3. Entities Should Own Their State

Whenever possible, live gameplay state should belong to entities or other explicit authored state containers.

That includes systems that are often tempting to hide inside engine internals:
- dialogue state
- menu state
- selection state
- nested UI stacks
- control ownership state that belongs to project logic

If something is important to authored behavior, it should usually be visible as explicit state, not buried in a hidden Python object.

### 4. Prefer Explicitness Over Hidden Privilege

The project should avoid special hidden concepts unless they are truly necessary runtime infrastructure.

This is why the project has been moving away from ideas like:
- `active_entity`
- privileged `player`
- engine-owned dialogue sessions
- camera behavior implicitly derived from a special actor

The preferred direction is:
- explicit input routes
- explicit transfers
- explicit camera state
- explicit controller/entity ownership of UI logic

### 5. Primitive Commands Should Be Truly Primitive

Primary/builtin engine commands are the engine API.
They should be narrow, explicit, and direct.

Each primitive command should accept only the data it really needs.
It should not expose a broad magical parameter surface just because other commands happen to need more context.

In spirit, primitive commands should feel like:
- set this value
- move this entity
- change this field
- play this sound
- show this element
- follow this target

They should not feel like mini scripting languages that also resolve every possible symbolic context by themselves.

### 6. Higher-Level Composition Is Still Valuable

The project still needs reusable composition tools.

In particular:
- entity events are useful
- named reusable command chains are useful

These are not the problem.
They are the project's way of composing behavior.

The important distinction is:
- high-level orchestration commands may carry richer context
- low-level primitive commands should stay small and explicit

### 7. Generic Runtime Services Are Good; Game-Specific Runtime Systems Are Suspicious

It is good for the engine to provide generic services such as:
- text measurement and wrapping
- screen element rendering
- command scheduling
- timed waits
- camera math
- persistence

It is suspicious when the engine starts providing game-specific live state machines, such as:
- a hidden dialogue session object that owns page/choice state
- a hidden menu state machine
- a hidden "real controlled entity" concept that content cannot see

Whenever that happens, the project should ask whether the engine has crossed from infrastructure into authorship.

### 8. Predictability Matters More Than Convenience

The user should be able to understand why something happened.

That means:
- behavior should be traceable to explicit commands and state
- the engine should avoid invisible fallback behavior where possible
- convenience abstractions are only acceptable when they do not obscure authorship

This project should prefer a slightly more explicit system over a more magical one if the magical one makes the engine harder to reason about.

### 9. The Project Should Stay Flexible Without Becoming Vague

Data-driven does not mean vague or shapeless.
It means the engine provides clear primitives and the project combines them deliberately.

The system should support:
- different styles of dialogue
- different styles of controllers
- different camera rules
- different interaction flows

without requiring the engine to grow a separate special-purpose subsystem for each one.

## Practical Tests For Future Decisions

When adding a feature, these questions should be asked:

1. Is this true engine infrastructure, or is it project behavior?
2. If the engine owns this state, does that hide authorship from the project?
3. Could this be expressed more explicitly through entities, commands, or authored data?
4. Is this introducing a privileged concept that will later become a design trap?
5. Is this primitive command truly narrow, or is it becoming an overpowered catch-all?
6. Will a future author be able to understand why the system behaved this way?

If a design fails these questions, it should be reconsidered.

## Things The Engine Should Generally Know

These are the kinds of things that reasonably belong to engine infrastructure:
- the live world state container
- the active area
- renderers
- input polling/plumbing
- collision and movement systems
- animation playback systems
- camera runtime state and camera math
- persistence backends
- command scheduling/execution

Knowing about these things is acceptable because they are runtime services.
What should be avoided is letting every primitive command expose or depend on all of them as part of its public contract.

## Things The Engine Should Generally Not Decide

These are the kinds of things that should generally stay in authored logic:
- what a dialogue means
- what confirm/cancel means in a given UI
- how a puzzle is solved
- who should receive control after a modal closes
- which entity should be followed by the camera in a given dramatic situation
- what counts as the "real" player in project logic
- how different gameplay flows are composed

## Anti-Goals

This project is not trying to become:
- a pile of hardcoded special cases hidden behind JSON wrappers
- an engine where "data-driven" only means parameters for Python state machines
- a system where convenience beats clarity every time
- a design where privileged concepts quietly spread across unrelated systems

## Open Questions And Not-Fully-Settled Areas

These are areas where the direction is clear but the exact final form is still evolving:

### 1. How Far Primitive-Command Narrowing Should Go

The direction is clear:
- primitive commands should be narrower and more explicit

What is not fully settled:
- exactly which current builtins should remain higher-level orchestration commands
- exactly how strict dependency injection for engine services should become

### 2. How Generic Project Data Should Ultimately Become

The direction is clear:
- the engine should avoid special gameplay subsystems

What is not fully settled:
- whether some currently conventional content categories should remain convenient conventions
- or be pushed even further toward ordinary generic JSON data everywhere

### 3. Exact Boundaries Between Runtime State And Authored State

The direction is clear:
- authored gameplay/UI state should be explicit

What is not fully settled:
- which transient runtime helpers should remain engine-only implementation details
- and which should become visible/authored state when the system matures further

### 4. Future Input Model Extensions

The direction is clear:
- inputs should be explicit and flexible

What is not fully settled:
- the exact long-term shape of press/hold/release phase routing
- and how much of that should become first-class authored control data

## Working Rule

If future work conflicts with the spirit described here, the correct move is not to ignore the conflict.

The correct move is to pause, identify whether:
- the code is drifting,
- the plan is drifting,
- or this file itself needs revision.

This document should be treated as a living design compass, not as untouchable scripture.
