# Agent Onboarding

This file is the starting point for any AI agent working on this project. Read this first, then dive into the files it points to.

## What Is This?

A top-down RPG/puzzle game engine built with Python and `pygame-ce`.

The project now has two standalone applications:

- `run_game.py` / `Run_Game.cmd` for play mode
- `run_editor.py` / `Run_Editor.cmd` for the standalone level editor

Both apps share the same JSON area/entity data model. Gameplay logic lives in JSON command chains, not hardcoded Python scripts.

Project content lives outside the engine package. The engine/editor code is under `dungeon_engine/`, while versioned project folders can live alongside it, for example `projects/test_project/`. Projects can still live elsewhere too; the important separation is that the engine reads a `project.json` manifest instead of depending on hardcoded bundled content.

## How to Run

```text
cd python_puzzle_engine
.venv/Scripts/python run_game.py
.venv/Scripts/python run_editor.py
```

Or double-click `Run_Game.cmd` or `Run_Editor.cmd`.

`main.py` still exists as a thin legacy entry point that forwards into `run_game.py`, but the standalone launchers are the preferred workflow.

## Read These Files (In Order)

| File | What It Tells You |
|---|---|
| `STATUS.md` | What's implemented, current controls, current test room, known gaps |
| `MANUAL.md` | Practical guide for running the engine and authoring project content |
| `AUTHORING_GUIDE.md` | JSON-focused guide for building projects, rooms, entities, commands, and dialogue without reading code |
| `functionality.md` | Plain-language feature list by priority tier |
| `architecture.md` | Design philosophy, tech stack, command system, entity/component model |
| `CONTRIBUTING.md` | Working rules and project direction |
| `roadmap.md` | Planned features and phases |
| `CHANGELOG.md` | Reverse-chronological history of functionality changes |
| `plans/` folder | Detailed implementation plans for specific tasks |

## Project Structure

```text
main.py                          # Legacy quick-launch game entry point
run_game.py                      # Preferred standalone game entry point
run_editor.py                    # Preferred standalone editor entry point
Run_Game.cmd                     # Windows launcher for the game
Run_Editor.cmd                   # Windows launcher for the editor
dungeon_engine/
    config.py                    # Paths, constants, window sizes
    logging_utils.py             # Rotating error log setup
    project.py                   # project.json loading and search-path resolution
    engine/
        game.py                  # Play-mode runtime loop
        renderer.py              # Play-mode rendering
        asset_manager.py         # PNG loading, frame slicing, caching
        camera.py                # Camera positioning and snapping
        input_handler.py         # Play-mode input polling
        text.py                  # Bitmap font rendering
    editor/
        editor_app.py            # Standalone resizable editor UI
        level_editor.py          # Editor document model, tile/entity operations
    world/
        area.py                  # Area data model (tilesets, tile layers, walkability, entity grid)
        entity.py                # Entity data model
        world.py                 # World state container
        loader.py                # JSON -> Area/World
        serializer.py            # Area/World -> JSON
    systems/
        movement.py              # Grid movement execution
        collision.py             # Collision checks
        interaction.py           # Entity interaction resolution
        animation.py             # Sprite animation
    commands/
        registry.py              # Command type registry
        runner.py                # Command chain executor
        builtin.py               # Built-in command implementations
```

## Key Technical Decisions

- **GID-based tilemaps**: Tile grids store integers, not strings. GID `0` = empty. Each tileset has a `firstgid`; a tile's local frame = `gid - firstgid`. See `area.py` for `resolve_gid()`.
- **Command pattern**: All gameplay goes through the command runner. Input queues commands; it never mutates gameplay state directly.
- **Shared data model across apps**: The standalone game and standalone editor both read the same area/entity JSON format.
- **Project manifests**: `project.json` defines `entity_paths`, `asset_paths`, and `area_paths`, so the engine stays independent from project content even when a project is versioned inside this repo under `projects/`.
- **Tileset discovery**: The editor browses PNG assets recursively from the active project's asset paths, but a room only stores the tilesets it actually uses.
- **Entity templates**: Entities are defined in JSON templates and can be specialized with per-instance parameters using `$variable` substitution.

## Common Tasks

**Adding a new command type**: Implement it in `commands/builtin.py` inside `register_builtin_commands()` using the `@registry.register("name")` decorator. Follow the pattern of existing commands.

**Adding a new entity template**: Create a JSON file in the active project's `entities/` folder (or another configured entity path), then place it through the editor.

**Editing the editor UI**: Layout and input flow live in `editor/editor_app.py`. Editor data/document operations live in `editor/level_editor.py`.

**Changing how tiles/areas work**: Core data model is `world/area.py`. Loading is `world/loader.py`. Saving is `world/serializer.py`.

**Changing project asset/content lookup**: Project search-path behavior lives in `project.py` plus `world/loader.py` and `engine/asset_manager.py`.

## Gotchas

- The project uses `pygame-ce` (Community Edition), not vanilla `pygame`.
- The game and editor are separate applications now. There is no longer an in-game F1 editor toggle.
- Each app opens its own single pygame window. The old browser-window-based editor has been replaced by `editor_app.py`.
- Tilesets are discovered recursively through the active project's `asset_paths`; folders under `assets/` are organizational, not restrictive.
- Tile layers and walkability are independent systems. A tile can exist without a walk flag and vice versa.
- Entity stacking: multiple entities can occupy the same grid cell, ordered by `stack_order`.
- The `asset_manager` is passed around widely. It is the central cache for loaded images and sliced frames.

