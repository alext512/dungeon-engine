# Dungeon Engine

A command-driven 2D puzzle/RPG engine in Python with JSON-authored gameplay, a standalone level editor, reusable entity templates, and entity-owned dialogue/menu flow.

## What It Is

This project is a focused top-down puzzle/RPG engine built with `pygame-ce`.

Core ideas:

- gameplay is authored through JSON command chains instead of one-off Python scripts
- entities own named events such as `move_up`, `interact`, and custom behaviors
- projects live outside the engine package and are loaded through `project.json`
- the game and the editor share the same area/entity data model

The repo includes a working sample project under [projects/test_project](./projects/test_project/).

## Current Features

- standalone game launcher and standalone level editor
- project manifests with configurable search paths for areas, entity templates, named commands, assets, shared variables, and project-level `global_entities`
- path-derived IDs for areas, entity templates, and named commands
- layered tilemaps with separate walkability data
- reusable entity templates with per-instance parameters
- entities with `visuals`, `space`, `scope`, `input_map`, events, and variables
- command-driven movement, interaction, pushing, animation, and persistence
- controller-driven dialogue and menu flow using entity-owned state, ordinary project JSON data, generic text helpers, and stack-based input restore
- per-action input routing through project/area `input_targets` plus runtime `set_input_target`, `route_inputs_to_entity`, `push_input_routes`, and `pop_input_routes`
- transfer-aware `change_area` and `new_game` flow using authored area `entry_points`
- traveler persistence so transferred entities exist in one area at a time and do not duplicate on re-entry
- explicit camera runtime state with authored area defaults, follow offsets, bounds, deadzones, and save/load restore
- save-slot persistence layered on top of authored room data
- standalone editor with paint/select workflow, tileset browser, layer management, and entity inspection

## Sample Project

The included sample project currently demonstrates:

- a `title_screen` area that auto-opens a choice dialogue through an area `enter_commands` hook
- connected showcase areas: `village_square` and `village_house`
- project-level global `dialogue_controller` and `pause_controller` entities defined in `project.json`
- player movement with authored walk animation timing
- pushable blocks
- lever/gate interaction with persistent puzzle state
- authored area `entry_points` and door-driven actor transfer between showcase areas
- explicit per-area camera defaults that follow the transferred gameplay entity
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
python run_game.py --project projects/test_project village_square
```

### Run The Editor

```bash
python run_editor.py --project projects/test_project
```

On Windows, you can also use:

- `Run_Game.cmd`
- `Run_Editor.cmd`

## Controls

### Game

- `WASD` or arrow keys: move
- `Space` or `Enter`: interact, advance dialogue, confirm choice
- `Escape`: open the pause menu in playable areas

If debug inspection is enabled in the active project's `project.json`:

- `F6`: pause/resume simulation
- `F7`: step one simulation tick
- `[` / `]`: zoom out/in

### Editor

- `Ctrl+S`: save
- `Tab`: toggle `Paint` / `Select`
- `[` / `]`: cycle the browsed tileset
- arrow keys: pan the camera
- middle mouse drag: pan the camera
- mouse wheel over the left panel: scroll the tileset view
- mouse wheel over the map: pan vertically
- toolbar buttons: `Save`, `Reload`, `Paint`, `Select`
- left click in `Paint`: paint the selected tile or walkability brush
- right click in `Paint`: erase tile data or apply the inverse walkability brush
- left click in `Select`: select a cell
- `Delete`: remove the selected entity in `Select` mode
- `Escape`: cancel editing, deselect, or confirm quit when dirty

## Project Structure

```text
python_puzzle_engine/
    dungeon_engine/             # Engine/runtime/editor code
    projects/
        test_project/           # Example project content
    run_game.py
    run_editor.py
    README.md
```

Typical project content layout:

```text
my_project/
    project.json
    shared_variables.json
    areas/
    entity_templates/
    named_commands/
    dialogues/                  # Optional ordinary JSON data used by your commands/controllers
    assets/
```

## Documentation

If you want the deeper docs, start here:

- [PROJECT_SPIRIT.md](./PROJECT_SPIRIT.md)
- [STATUS.md](./STATUS.md)
- [MANUAL.md](./MANUAL.md)
- [AUTHORING_GUIDE.md](./AUTHORING_GUIDE.md)
- [CONTENT_TYPES.md](./CONTENT_TYPES.md)
- [architecture.md](./architecture.md)

## Current Limits

- inventory and usable-item systems are still planned
- save/load UX is functional but still basic
- editor parameter editing is still minimal
- external PNG import flow is not finished
- movement/render feel should still be checked periodically on real hardware as the project grows

## License

No license file has been added yet.
