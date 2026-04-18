# Agent Onboarding

This file is the starting point for any AI agent working on this project. Read this first, then dive into the files it points to.

## What Is This?

A top-down RPG/puzzle game engine built with Python and `pygame-ce`.

The active repo surface is the standalone game runtime plus the external area editor:

- `run_game.py` / `Run_Game.cmd` for play mode
- `tools/area_editor/` for external authoring tooling

Gameplay logic lives in JSON command chains, not hardcoded Python scripts.

Project content lives outside the runtime package. Runtime code is under `dungeon_engine/`, while versioned project folders can live alongside it, for example `projects/my_game/`. Projects can still live elsewhere too; the important separation is that the engine reads a `project.json` manifest instead of depending on hardcoded bundled content.

The archived built-in editor implementation lives under `archived_editor/` and is no longer part of the active codebase. A new external editor now lives under `tools/area_editor/` and already supports active area editing plus broader project-authoring workflows such as tile painting, cell-flag editing, entity placement/nudging, render-property editing, project manifest and shared-variable editing, item/global-entity editing, and guarded JSON editing. The main remaining gaps are broader coverage for some engine-owned fields, richer reference pickers, stronger screen-space direct manipulation, and runtime handoff.

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
| `docs/project/project-spirit.md` | The main spirit of the project, the intended engine behavior, and the design compass for future decisions |
| `README.md` | Current features, project-authoring expectations, controls, verification commands |
| `docs/authoring/manuals/authoring-guide.md` | JSON-focused guide for building projects, rooms, entities, commands, and dialogue without reading code |
| `docs/authoring/manuals/engine-json-interface.md` | Canonical reference for the exact current engine <-> JSON surface: manifests, file shapes, tokens, value sources, builtin commands, and engine-known fields |
| `docs/project/architecture-direction.md` | Design principles and medium-term architectural direction |
| `docs/development/engine-contract-truth-map.md` | Active contract ownership map across runtime, validation, editor, docs, tests, and sample content |
| `docs/development/sample-content-coverage.md` | What the canonical repo-local sample project currently proves and how to keep it aligned |
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
    display_setup.py             # Display/window initialization
    inventory.py                 # Inventory data model and stack operations
    items.py                     # Item definition loading and validation
    launcher_state.py            # Launcher state management
    logging_utils.py             # Rotating error log setup
    project_context.py           # Runtime project-context implementation and import surface
    startup_validation.py        # Project startup checks
    engine/
        game.py                  # Play-mode runtime loop and runtime-wiring entry point
        game_area_runtime.py     # Area loading, transitions, resets, and camera defaults used by game.py
        game_save_runtime.py     # Save-slot dialogs and session restore helpers used by game.py
        renderer.py              # Play-mode rendering
        asset_manager.py         # PNG loading, frame slicing, caching
        audio.py                 # Sound/music playback
        camera.py                # Camera positioning and snapping
        dialogue_runtime.py      # Engine-owned dialogue sessions
        input_handler.py         # Play-mode input polling
        inventory_runtime.py     # Engine-owned inventory UI
        screen.py                # Screen-space UI element management
        text.py                  # Bitmap font rendering
    world/
        area.py                  # Area data model (tilesets, tile layers, walkability, entity grid)
        entity.py                # Entity data model
        world.py                 # World state container
        loader.py                # Area loading/validation surface
        loader_entities.py       # Entity/template parsing and validation helpers used by loader.py
        serializer.py            # Area/World -> JSON
        persistence.py           # Live persistence runtime
        persistence_data.py      # Save-data models and JSON codec helpers
        persistence_snapshots.py # Persistent apply/capture/snapshot helpers
        persistence_travelers.py # Traveler lifecycle helpers used by persistence.py
    systems/
        movement.py              # Grid movement execution
        collision.py             # Collision checks
        interaction.py           # Entity interaction resolution
        animation.py             # Entity visual animation
    commands/
        registry.py              # Command type registry
        runner.py                # Public command execution surface and root-flow orchestrator
        runner_resolution.py     # Runtime token/value/spec resolution helpers
        runner_value_utils.py    # Generic JSON/collection/math/text/random value helpers
        runner_query_values.py   # Entity/area/world query and snapshot-backed value helpers
        builtin.py               # Built-in command registration entry point
        builtin_domains/         # Focused builtin command domain modules
        library.py               # Project command loading and validation
```

## Key Technical Decisions

- **GID-based tilemaps**: Tile grids store integers, not strings. GID `0` = empty. Each tileset has a `firstgid`; a tile's local frame = `gid - firstgid`. See `area.py` for `resolve_gid()`.
- **Command pattern**: All gameplay goes through the command runner. Input queues commands; it never mutates gameplay state directly.
- **Project manifests**: `project.json` defines `entity_template_paths`, `asset_paths`, `area_paths`, `command_paths`, `item_paths`, `shared_variables_path`, and project-level settings such as `global_entities` and `input_targets`, so the engine stays independent from project content even when a project is versioned inside this repo under `projects/`.
- **Separate project-layout interpreters**: Runtime code prefers `dungeon_engine/project_context.py`, while the external editor prefers `tools/area_editor/area_editor/project_io/project_manifest.py`. They intentionally stay separate and are kept aligned with parity tests rather than by importing each other.
- **Path-derived reusable IDs**: Areas, entity templates, and commands derive identity from their path under the configured search roots instead of authored `id` fields.
- **Project JSON data**: Reusable dialogue/menu data is now just ordinary project-relative JSON. The sample project keeps it under `dialogues/`, but that folder is conventional rather than a manifest-indexed content category.
- **Authoring contract**: JSON area/entity/template files are the stable contract for the runtime and any future external tooling.
- **Entity templates**: Entities are defined in JSON templates and can be specialized with per-instance parameters using `$variable` substitution.
- **JSON notes headers**: When creating an authored JSON data file (`.json` or
  `.json5`), start it with the standard file-level notes header:

  ```json5
  /*
    NOTES

    Add file-level notes here.
  */
  ```

  The engine/editor JSON loader accepts file-level comments for both `.json`
  and `.json5` authored data. Use that header, and other file-level comments,
  the way you would use comments in source code: explain intent, non-obvious
  decisions, and useful authoring context. If a user removes those comments,
  respect that choice; do not force the header back into existing files unless
  asked.

## Common Tasks

**Adding a new command type**: Keep `commands/builtin.py` as the public registration entry point, but prefer placing clustered command implementations in a focused module under `commands/builtin_domains/` when a domain already exists. Use `@registry.register("name")` in the relevant registration helper, declare `deferred_param_shapes` for nested command-bearing params, and wire that helper through `register_builtin_commands()`.

**Adding a new entity template**: Create a JSON file in the active project's `entity_templates/` folder (or another configured entity-template path), then reference it from authored area data.

**Changing how tiles/areas work**: Core data model is `world/area.py`. Area parsing and validation stay in `world/loader.py`, while entity/template expansion now lives in `world/loader_entities.py`. Saving is `world/serializer.py`.

**Changing save/load persistence**: Live persistence mutation and reset queues stay in `world/persistence.py`, save-slot models/JSON codec helpers live in `world/persistence_data.py`, persistent apply/capture/snapshot helpers live in `world/persistence_snapshots.py`, and traveler lifecycle helpers now live in `world/persistence_travelers.py`.

**Changing play-mode transitions or room resets**: `engine/game_area_runtime.py` now owns area loading, transition application, deferred load/new-game switching, occupancy hook spawning, and authored camera defaults. `engine/game.py` keeps the main loop and runtime wiring entry point.

**Changing play-mode save/load flow**: `engine/game_save_runtime.py` now owns save-slot dialogs plus save/load session restore. `engine/game.py` remains the main loop/runtime wiring entry point, while `engine/game_area_runtime.py` handles the deferred transition side that save/load feeds into.

**Changing project asset/content lookup**: Runtime search-path behavior lives in `project_context.py`. Related consumers live in `world/loader.py` and `engine/asset_manager.py`. Editor-side project discovery stays separate in `tools/area_editor/area_editor/project_io/project_manifest.py`.

**Changing command value lookup or runtime token behavior**: Start in `commands/runner.py`, but expect the supporting logic to be split between `commands/runner_resolution.py`, `commands/runner_value_utils.py`, and `commands/runner_query_values.py`.

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
2. Directly validate every changed project manifest and any repo-local example
   projects currently present under `projects/`.
3. Prefer validating them through the same startup-style project-command path the app uses, not only through lower-level engine tests.
4. If you changed project-command ids or command references, explicitly re-run project-command validation for each affected project manifest.
5. If feasible, do a brief manual smoke start of the affected project after automated validation passes.

If you change `tools/area_editor/`, also run the editor's own unittest suite from inside that folder so package-relative imports and tool-local assumptions match the intended workflow.

Recommended direct project validation:

```text
.venv/Scripts/python tools/validate_projects.py
.venv/Scripts/python tools/validate_projects.py --headless-smoke
```

If you touch repo docs, pointer files, or onboarding docs, also run:

```text
.venv/Scripts/python tools/check_markdown_links.py
```

Why this matters:

- A general engine test pass does not guarantee that every example project's startup validation path is clean.
- Literal `run_project_command` references inside project JSON can still fail at startup even when broader tests are green.
- If you touched project content or command ids, validate the actual projects directly.
- Some end-to-end runtime tests use optional repo-local example projects and
  skip when those fixtures are not present. Treat those as bonus integration
  coverage, not as the only safety net.

## Low-Risk Documentation Fixes

Do not ignore clearly broken, low-risk documentation defects just because they
are adjacent to another task.

Safe opportunistic fixes include:

- broken local Markdown links or pointer-file targets
- stale filenames or moved-doc paths
- obviously wrong read-order references
- straightforward typos that do not change technical meaning

Only make those fixes when the correction is unambiguous and easy to verify.

Do not casually rewrite canonical behavior docs, architecture docs, or planning
history unless the underlying truth is clear and you are updating the matching
implementation/tests/docs bundle on purpose.

## Architectural Debt Guardrails

When making changes that affect the active runtime, editor, validation, or
authored JSON contract, use these rules to avoid slowly rebuilding drift or
debt:

- Do not add compatibility layers, legacy code paths, or shim surfaces unless a
  maintainer explicitly asks for them. Prefer updating the real callers and
  removing dead paths.
- If you change a public authored surface, update the whole contract bundle in
  the same pass:
  - runtime behavior
  - startup validation
  - editor-side interpretation if applicable
  - canonical docs
  - focused tests and parity tests
  - repo-local sample content or sample-coverage docs when relevant
- Every new authored field should be classified explicitly:
  - stable author-authored contract
  - runtime-owned/transient state
  - internal implementation detail that should stay out of authoring docs
- If runtime and editor both interpret the same file shape, keep them separate
  in code but prove parity with tests. Do not rely on “they probably still
  match.”
- For focused editor surfaces, preserve fields the editor does not own. If a
  widget edits only part of a JSON object, add or update a regression test that
  proves the untouched engine-used subtrees survive a save.
- Avoid permissive silent fallbacks for alternate JSON shapes unless that
  behavior is intentional, documented, and tested. Convenience parsing that
  nobody owns turns into long-term debt.
- Do not let plans or past discussions become de facto truth. If a plan and the
  implementation differ, either update the code or fix the docs/plan language.
- Prefer one authoritative path over parallel “old vs new” behavior. When a
  cleanup is complete, remove the obsolete route instead of carrying both.

## Gotchas

- The project uses `pygame-ce` (Community Edition), not vanilla `pygame`.
- Runtime code lives under `dungeon_engine/`. The external editor lives under `tools/area_editor/`. The archived built-in editor lives under `archived_editor/` as disconnected reference material.
- Tilesets are discovered recursively through the active project's `asset_paths`; folders under `assets/` are organizational, not restrictive.
- Tile layers and walkability are independent systems. A tile can exist without a walk flag and vice versa.
- World rendering now uses a unified model across tile layers and entities: `render_order` is the coarse band, `y_sort` controls vertical interleaving inside a band, `sort_y_offset` adjusts the sort pivot, and `stack_order` is the local tie-breaker.
- Multiple entities can still occupy the same grid cell; their stable per-cell query order is `render_order`, then `stack_order`, then `entity_id`.
- The `asset_manager` is passed around widely. It is the central cache for loaded images and sliced frames.
