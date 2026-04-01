# Agent Onboarding

This file is the starting point for any AI agent working on this project. Read this first, then dive into the files it points to.

## What Is This?

A top-down RPG/puzzle game engine built with Python and `pygame-ce`.

The active repo surface is the standalone game runtime plus the external area editor:

- `run_game.py` / `Run_Game.cmd` for play mode
- `tools/area_editor/` for external authoring tooling

Gameplay logic lives in JSON command chains, not hardcoded Python scripts.

Project content lives outside the runtime package. Runtime code is under `dungeon_engine/`, while versioned project folders can live alongside it, for example `projects/test_project/`. Projects can still live elsewhere too; the important separation is that the engine reads a `project.json` manifest instead of depending on hardcoded bundled content.

The previous built-in editor implementation has been archived under `archived_editor/` and is no longer part of the active codebase. A new external editor now lives under `tools/area_editor/` and now supports active area editing workflows such as tile painting, cell-flag editing, entity placement/nudging, render-property editing, and guarded JSON editing. Some workflows are still deferred, especially screen-space placement, `global_entities` editing, richer reference pickers, and runtime handoff.

## How to Run

```text
cd python_puzzle_engine
.venv/Scripts/python run_game.py
.venv/Scripts/python -m unittest discover -s tests -v
cd tools/area_editor
..\..\.venv/Scripts/python -m unittest discover -s tests -v
```

Or double-click `Run_Game.cmd`.

## Read These Files (In Order)

| File | What It Tells You |
|---|---|
| `PROJECT_SPIRIT.md` | The main spirit of the project, the intended engine behavior, and the design compass for future decisions |
| `README.md` | Current features, sample project behavior, controls, verification commands |
| `AUTHORING_GUIDE.md` | JSON-focused guide for building projects, rooms, entities, commands, and dialogue without reading code |
| `ENGINE_JSON_INTERFACE.md` | Canonical reference for the exact current engine <-> JSON surface: manifests, file shapes, tokens, value sources, builtin commands, and engine-known fields |
| `architecture.md` | Design principles and medium-term architectural direction |
| `CONTRIBUTING.md` | Working rules and project direction |
| `CHANGELOG.md` | Reverse-chronological history of functionality changes |

Optional reference/planning docs:

- `roadmap.md`
- `plans/`
- `tools/area_editor/`

## Project Structure

```text
run_game.py                      # Preferred standalone game entry point
Run_Game.cmd                     # Windows launcher for the game
tools/area_editor/               # External area editor with active area-editing support
archived_editor/                 # Archived editor code and notes kept for reference
tests/                           # Focused unittest coverage for engine behavior regressions
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
        animation.py             # Entity visual animation
    commands/
        registry.py              # Command type registry
        runner.py                # Command chain executor
        builtin.py               # Built-in command implementations
```

## Key Technical Decisions

- **GID-based tilemaps**: Tile grids store integers, not strings. GID `0` = empty. Each tileset has a `firstgid`; a tile's local frame = `gid - firstgid`. See `area.py` for `resolve_gid()`.
- **Command pattern**: All gameplay goes through the command runner. Input queues commands; it never mutates gameplay state directly.
- **Project manifests**: `project.json` defines `entity_template_paths`, `asset_paths`, `area_paths`, `command_paths`, `shared_variables_path`, and project-level settings such as `global_entities`, so the engine stays independent from project content even when a project is versioned inside this repo under `projects/`.
- **Path-derived reusable IDs**: Areas, entity templates, and commands derive identity from their path under the configured search roots instead of authored `id` fields.
- **Project JSON data**: Reusable dialogue/menu data is now just ordinary project-relative JSON. The sample project keeps it under `dialogues/`, but that folder is conventional rather than a manifest-indexed content category.
- **Authoring contract**: JSON area/entity/template files are the stable contract for the runtime and any future external tooling.
- **Entity templates**: Entities are defined in JSON templates and can be specialized with per-instance parameters using `$variable` substitution.

## Common Tasks

**Adding a new command type**: Implement it in `commands/builtin.py` inside `register_builtin_commands()` using the `@registry.register("name")` decorator. Follow the pattern of existing commands.

**Adding a new entity template**: Create a JSON file in the active project's `entity_templates/` folder (or another configured entity-template path), then reference it from authored area data.

**Changing how tiles/areas work**: Core data model is `world/area.py`. Loading is `world/loader.py`. Saving is `world/serializer.py`.

**Changing project asset/content lookup**: Project search-path behavior lives in `project.py` plus `world/loader.py` and `engine/asset_manager.py`.

**Running focused verification**: Use `.venv/Scripts/python -m unittest discover -s tests -v` for the runtime suite. If you touch `tools/area_editor/`, run `..\..\.venv/Scripts/python -m unittest discover -s tests -v` from `tools/area_editor/` for the editor suite.

## Validation Checklist

Engine/unit tests are necessary, but they are **not sufficient** after command-surface or content-authoring refactors.

When you change any of the following:

- command names or command invocation shape
- command-library loading/validation
- entity command naming or lookup
- JSON authoring conventions
- project content under `projects/`

do **all** of the following before declaring the change safe:

1. Run the automated test suite that covers the affected area.
2. Directly validate the example projects, especially:
   - `projects/test_project/`
   - `projects/game_copy/`
3. Prefer validating them through the same startup-style project-command path the app uses, not only through lower-level engine tests.
4. If you changed project-command ids or command references, explicitly re-run project-command validation for each affected example project.
5. If feasible, do a brief manual smoke start of the affected sample project after automated validation passes.

If you change `tools/area_editor/`, also run the editor's own unittest suite from inside that folder so package-relative imports and tool-local assumptions match the intended workflow.

Recommended direct validation snippet:

```text
@'
from pathlib import Path
from dungeon_engine.project import load_project
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

Why this matters:

- A general engine test pass does not guarantee that every example project's startup validation path is clean.
- Literal `run_project_command` references inside project JSON can still fail at startup even when broader tests are green.
- If you touched project content or command ids, validate the actual projects directly.

## Gotchas

- The project uses `pygame-ce` (Community Edition), not vanilla `pygame`.
- Runtime code lives under `dungeon_engine/`. The external editor lives under `tools/area_editor/`. The previous built-in editor lives under `archived_editor/` as disconnected reference material.
- Tilesets are discovered recursively through the active project's `asset_paths`; folders under `assets/` are organizational, not restrictive.
- Tile layers and walkability are independent systems. A tile can exist without a walk flag and vice versa.
- World rendering now uses a unified model across tile layers and entities: `render_order` is the coarse band, `y_sort` controls vertical interleaving inside a band, `sort_y_offset` adjusts the sort pivot, and `stack_order` is the local tie-breaker.
- Multiple entities can still occupy the same grid cell; their stable per-cell query order is `render_order`, then `stack_order`, then `entity_id`.
- The `asset_manager` is passed around widely. It is the central cache for loaded images and sliced frames.
