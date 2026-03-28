# Area Editor

This folder is reserved for a future external area editor for the puzzle dungeon project.

It is intentionally separate from the runtime in `dungeon_engine/`.

## Why This Exists

The project still benefits from tooling for common authoring tasks, but the previous built-in editor became too coupled to runtime code and runtime assumptions.

The new direction is:

- keep the runtime focused on playing the game
- keep authoring tools outside the runtime package
- use the same JSON files as the shared contract

## Current State

Right now this folder contains planning and onboarding docs only.

There is no editor implementation here yet.

## Expected Responsibilities

The future tool is expected to help with:

- tile painting
- layer-oriented map editing
- cell flag editing
- entity placement
- editing common per-instance values
- selecting other entity ids when parameters reference them
- preserving room JSON without forcing the user to hand-edit common cases

## Explicit Non-Goals For The Scaffold

This scaffold does not:

- define a UI framework choice
- create any app skeleton
- create any runtime bridge
- add editor code
- revive the archived built-in editor

## Folder Intent

This folder should eventually host:

- tool-specific code
- tool-specific tests
- tool-specific notes and decisions

But only after the user asks for implementation work.

## Related Runtime Docs

- [../../AUTHORING_GUIDE.md](../../AUTHORING_GUIDE.md)
- [../../ENGINE_JSON_INTERFACE.md](../../ENGINE_JSON_INTERFACE.md)
- [../../architecture.md](../../architecture.md)

## Historical Reference

The old built-in editor lives under:

- [../../archived_editor/README.md](../../archived_editor/README.md)

That folder is reference material, not the new architecture.
