# Runtime Architecture

This page is the high-level map of the active codebase.

## Main Runtime Areas

### Runtime package

`dungeon_engine/` is the active runtime package.

Important top-level modules include:

- `project_context.py` for runtime project loading and content resolution
- `items.py` and `inventory.py` for item and inventory data rules
- `startup_validation.py` for project startup checks

### Play-mode engine

`dungeon_engine/engine/` contains the play-mode runtime slices:

- `game.py` for the main loop and runtime wiring
- `game_area_runtime.py` for area loading, transitions, resets, and camera defaults
- `game_save_runtime.py` for save-slot dialogs and session restore
- `renderer.py` for rendering
- `audio.py` for sound and music
- `inventory_runtime.py` and `dialogue_runtime.py` for engine-owned sessions
- `screen.py` and `text.py` for screen-space UI and bitmap text support

### World model

`dungeon_engine/world/` contains authored data loading, runtime world state, and persistence helpers:

- `area.py`
- `entity.py`
- `world.py`
- `loader.py`
- `loader_entities.py`
- `serializer.py`
- `persistence.py`
- `persistence_data.py`
- `persistence_snapshots.py`
- `persistence_travelers.py`

### Systems

`dungeon_engine/systems/` contains focused gameplay systems such as:

- movement
- collision
- interaction
- animation

### Commands

`dungeon_engine/commands/` is one of the most important folders in the project.

Key files:

- `registry.py` for command registration
- `runner.py` for command execution
- `runner_resolution.py` for token and lookup resolution
- `runner_value_utils.py` for general value helpers
- `runner_query_values.py` for entity, area, and inventory queries
- `builtin.py` for public builtin registration
- `builtin_domains/` for grouped builtin implementations
- `library.py` for project command loading and validation

## Architectural Principles

The repo's architecture docs and spirit docs consistently push toward:

- data-driven gameplay
- manifest-driven projects
- JSON as the stable authoring contract
- runtime and editor separation
- engine-owned support for high-boilerplate recurring systems

## Important Runtime Contracts

- areas use GID-based tilemaps
- command flows are the main gameplay mutation path
- project manifests define content roots and project-level settings
- ids for typed content are derived from file paths
- persistence is layered over authored content rather than replacing it

## Engine-Owned Sessions

The engine now directly owns certain recurring modal flows:

- dialogue sessions
- inventory sessions

These are part of the architecture, not just convenience helpers, because they reduce boilerplate without forcing all UI logic into hardcoded one-off menus.

## Where To Change Things

Useful starting points for common changes:

- command value lookup or token behavior: `dungeon_engine/commands/runner.py` and the supporting runner helper modules
- new builtin commands: `dungeon_engine/commands/builtin.py` and the relevant `builtin_domains/` module
- area format or loading behavior: `dungeon_engine/world/area.py`, `dungeon_engine/world/loader.py`, and `dungeon_engine/world/loader_entities.py`
- play-mode transitions and resets: `dungeon_engine/engine/game_area_runtime.py`
- save/load flow: `dungeon_engine/engine/game_save_runtime.py`
- project content lookup: `dungeon_engine/project_context.py`

## Editor Boundary

The external editor intentionally has its own project-layout interpreter and should not import runtime modules. Alignment happens through shared file-format expectations and parity tests, not by collapsing the two codebases together.

## Deeper References

- [Architecture Direction](../project/architecture-direction.md)
- [Project Spirit](../project/project-spirit.md)
- [AGENTS.md](https://github.com/alext512/dungeon-engine/blob/main/AGENTS.md)
