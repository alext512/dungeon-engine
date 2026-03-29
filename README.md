# Dungeon Engine

A command-driven 2D puzzle/RPG engine in Python with JSON-authored gameplay, reusable entity templates, and entity-owned dialogue/menu flow.

## What It Is

This project is a focused top-down puzzle/RPG engine built with `pygame-ce`.

Core ideas:

- gameplay is authored through JSON command chains instead of one-off Python scripts
- entities own named events such as `move_up`, `interact`, and custom behaviors
- projects live outside the engine package and are loaded through `project.json`
- JSON area/entity data is the contract for the runtime and future external tooling

The repo includes a working sample project under [projects/test_project](./projects/test_project/).

## Current Features

- standalone game launcher
- project manifests with configurable search paths for areas, entity templates, project commands, assets, shared variables, and project-level `global_entities`
- path-derived typed IDs for areas, entity templates, and project commands, for example `areas/village_square`
- layered tilemaps with separate walkability data
- reusable entity templates with per-instance parameters
- entities with `visuals`, `space`, `scope`, `input_map`, events, and variables
- command-driven movement, interaction, pushing, animation, and persistence
- controller-driven dialogue and menu flow using entity-owned state, ordinary project JSON data, generic text helpers, and stack-based input restore
- per-action input routing through project/area `input_targets` plus runtime `set_input_target`, `route_inputs_to_entity`, `push_input_routes`, and `pop_input_routes`
- transfer-aware `change_area` and `new_game` flow using authored area `entry_points`
- traveler persistence so transferred entities exist in one area at a time and do not duplicate on re-entry
- explicit camera runtime state with structured `follow` / `bounds` / `deadzone` state, camera-state stack support, and save/load restore
- save-slot persistence layered on top of authored room data

The previous built-in editor implementation now lives under [archived_editor](./archived_editor/) for reference only and is not part of the active runtime surface.

A new external editor now lives under [tools/area_editor](./tools/area_editor/). Its current Phase 1 implementation is a read-only project browser and area viewer built around the same JSON contract as the runtime.

## Sample Project

The included sample project currently demonstrates:

- a `title_screen` area that auto-opens a choice dialogue through an area `enter_commands` hook
- connected showcase areas: `village_square` and `village_house`
- project-level global `dialogue_controller`, `pause_controller`, and `debug_controller` entities defined in `project.json`
- player movement with authored walk animation timing
- pushable blocks that respect room walkability and blockers
- lever/gate interaction with persistent puzzle state
- authored area `entry_points` and door-driven actor transfer between showcase areas
- explicit per-area structured camera defaults that follow the transferred gameplay entity
- signs, save prompts, pause menus, and title menus routed through controller entities with stack-based input restore

Useful files to inspect:

- [projects/test_project/project.json](./projects/test_project/project.json)
- [projects/test_project/shared_variables.json](./projects/test_project/shared_variables.json)
- [projects/test_project/areas/title_screen.json](./projects/test_project/areas/title_screen.json)
- [projects/test_project/areas/village_square.json](./projects/test_project/areas/village_square.json)
- [projects/test_project/areas/village_house.json](./projects/test_project/areas/village_house.json)
- [projects/test_project/entity_templates/player.json](./projects/test_project/entity_templates/player.json)
- [projects/test_project/entity_templates/dialogue_panel.json](./projects/test_project/entity_templates/dialogue_panel.json)
- [projects/test_project/entity_templates/pause_controller.json](./projects/test_project/entity_templates/pause_controller.json)
- [projects/test_project/entity_templates/lever_toggle.json](./projects/test_project/entity_templates/lever_toggle.json)
- [projects/test_project/dialogues/system/title_menu.json](./projects/test_project/dialogues/system/title_menu.json)
- [projects/test_project/dialogues/system/pause_menu.json](./projects/test_project/dialogues/system/pause_menu.json)

## Quick Start

### Requirements

- Python 3.11+
- Windows is the current primary development environment

Install dependencies:

```bash
pip install -e .
```

Or directly:

```bash
pip install pygame-ce
```

### Run The Game

```bash
python run_game.py --project projects/test_project
python run_game.py --project projects/test_project areas/village_square
```

On Windows, you can also use:

- `Run_Game.cmd`

## Controls

### Game

- `WASD` or arrow keys: move
- `Space` or `Enter`: interact, advance dialogue, confirm choice
- `Escape`: open the pause menu in playable areas

If debug inspection is enabled in the active project's `project.json`:

- `F6`: pause/resume simulation
- `F7`: step one simulation tick
- `[` / `]`: zoom out/in

## Project Structure

```text
python_puzzle_engine/
    dungeon_engine/             # Active runtime code
    tools/area_editor/          # External area editor (Phase 1 read-only browser/viewer)
    archived_editor/            # Archived built-in editor kept for reference
    projects/
        test_project/           # Example project content
    run_game.py
    README.md
```

Typical project content layout:

```text
my_project/
    project.json
    shared_variables.json
    areas/
    entity_templates/
    commands/
    dialogues/                  # Optional ordinary JSON data used by your commands/controllers
    assets/
```

## Documentation

Primary docs for authoring JSON content:

- [AUTHORING_GUIDE.md](./AUTHORING_GUIDE.md): how to author content in JSON without reading Python code
- [ENGINE_JSON_INTERFACE.md](./ENGINE_JSON_INTERFACE.md): exact current JSON surface and builtin command/value-source signatures

Supporting docs:

- [PROJECT_SPIRIT.md](./PROJECT_SPIRIT.md): project intent and design compass
- [AGENTS.md](./AGENTS.md): AI agent onboarding and reading order
- [architecture.md](./architecture.md): medium-term direction and tradeoffs
- [CONTRIBUTING.md](./CONTRIBUTING.md): working rules
- [CHANGELOG.md](./CHANGELOG.md): reverse-chronological change history
- [roadmap.md](./roadmap.md): phased development plan

## Expected Behavior

When you run the sample project:

- move with arrows or `WASD`
- interact and advance dialogue with `Space` or `Enter`
- from the title screen, choose `New Game`, `Load Game`, or `Exit`
- in `village_square`, face the save point and press `Space` to open an authored save prompt
- face the house door and press `Space` to enter `village_house`
- in `village_house`, face the lever and press `Space` to toggle the gate open or closed
- leave and return to confirm the lever/gate state persisted
- push the house block, leave the house, and return to confirm the block reset to its authored position
- press `Escape` in a playable area to open the controller-driven pause menu with `Continue`, `Load`, and `Exit`

## Important Design Notes

- Movement is command-driven. Input requests events; it does not mutate positions directly.
- Interaction is also command-driven. The player triggers a top-level interact command, which resolves a target and runs that target's command chain.
- Dialogue is not a special engine-owned runtime session. The supported flow is: send an event to a controller entity, let controller-owned commands load ordinary JSON dialogue data, mutate controller variables, and redraw the UI.
- Modal controllers should borrow and restore routes through `push_input_routes` / `pop_input_routes` instead of returning input through `actor`.
- Save data stores the current area, the current logical input-target routing, the current camera state, traveler session state, persistent diffs for visited areas, and the full current diff of the active area at save time.
- The transient input-route stack is runtime-only and is intentionally not written into save files.

## Verification

Useful commands during development:

```text
.venv/Scripts/python -m unittest discover -s tests -v
.venv/Scripts/python run_game.py --project projects/test_project areas/title_screen --headless --max-frames 2
.venv/Scripts/python run_game.py --project projects/test_project areas/village_square --headless --max-frames 2
.venv/Scripts/python run_game.py --project projects/test_project areas/village_house --headless --max-frames 2
```

## Current Limits

- save/load UX is functional but still basic
- external PNG import flow is not finished
- the external area editor is still read-only; editing/saving workflows are not finished yet
- movement/render feel should still be checked periodically on real hardware as the project grows

## Suggested Next Steps

- expand dialogue authoring with stronger data-validation and authoring support
- build more real JSON content and let authoring pressure reveal the next engine changes
- continue expanding the external area editor into a full authoring workflow around the current JSON contract
- revisit movement/render feel and finish the pixel-perfect quality pass

## License

No license file has been added yet.
