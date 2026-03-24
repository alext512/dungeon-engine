# Dungeon Engine

A command-driven 2D puzzle/RPG engine in Python with JSON-authored gameplay, a built-in level editor, dialogue tools, and reusable entity/event systems.

## What It Is

This project is a focused top-down puzzle/RPG engine built with `pygame-ce`.

It is designed around a few core ideas:

- gameplay is authored through JSON command chains instead of hardcoded one-off scripts
- entities own reusable named events like `move_up`, `interact`, and custom behaviors
- projects live outside the engine package and are loaded through `project.json`
- the game and the editor share the same room/entity data model

The repo includes a working sample project under [projects/test_project](./projects/test_project/).

## Current Features

- standalone game launcher and standalone level editor
- project manifests with configurable search paths for areas, entities, commands, dialogues, and assets
- layered tilemaps with separate walkability data
- reusable entity templates with per-instance parameters
- command runner with primitive engine commands plus reusable project-level named commands
- command-driven grid movement, interaction, pushing, and animation
- dialogue assets, screen-space UI elements, and entity-driven dialogue flow
- text sessions for paged dialogue text and marquee-style long option text
- entity-owned input maps plus active-entity focus handoff
- startup validation for named command libraries
- persistence foundation with save-slot overrides layered on top of authored room data
- standalone editor with paint/select workflow, tileset browser, layer management, and entity inspection

## Sample Project

The included sample room currently demonstrates:

- player movement with authored walk animation timing
- pushable blocks
- lever/gate interaction
- sign dialogue
- portrait-backed NPC dialogue
- dialogue choices, long-choice marquee text, and scrolling menus with more than three options

Useful files to inspect:

- [projects/test_project/project.json](./projects/test_project/project.json)
- [projects/test_project/variables.json](./projects/test_project/variables.json)
- [projects/test_project/areas/test_room.json](./projects/test_project/areas/test_room.json)
- [projects/test_project/entities/player.json](./projects/test_project/entities/player.json)
- [projects/test_project/entities/dialogue_ui.json](./projects/test_project/entities/dialogue_ui.json)
- [projects/test_project/commands/dialogue](./projects/test_project/commands/dialogue)

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
- `Space` / `Enter`: interact
- `F5`: write the current persistent state to the save slot
- `F9`: reload persistent state from the save slot

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
- left panel top arrows: cycle available tilesets
- toolbar buttons: `Save`, `Reload`, `Paint`, `Select`
- left click in `Paint`: paint the selected tile or walkability brush
- right click in `Paint`: erase tile data or apply the inverse walkability brush
- drag with left/right mouse in `Paint`: paint continuously
- left panel `Walkable` / `Blocked`: switch to walkability painting
- left click in `Select`: select a cell
- `Delete`: remove selected entity in `Select` mode
- `Escape`: cancel editing, deselect, or confirm quit when dirty
- right panel in `Paint`: select layers, rename layers, toggle above/below-entity draw order, add/remove layers
- right panel in `Select`: select, reorder, move, remove, or add entities on the selected cell
- property rows in `Select`: toggle booleans, cycle facing, and edit simple parameter values

## Editor Capabilities

The current editor is intentionally simple.

Right now it is mainly for:

- creating and editing tilemaps
- painting walkability
- placing already-authored entity templates into a room
- selecting, reordering, moving, and deleting placed entities
- changing a few basic entity properties and template parameters
- choosing from existing tilesets and room layers
- saving and reloading room data

It is not yet meant to be the main tool for creating new gameplay systems.

More complex authoring is still primarily done directly in JSON files:

- new entity templates
- reusable command chains
- dialogue assets
- richer event logic
- broader project structure changes

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
    variables.json
    areas/
    entities/
    commands/
    dialogues/
    assets/
```

## Documentation

If you want the deeper internal docs, start here:

- [STATUS.md](./STATUS.md)
- [MANUAL.md](./MANUAL.md)
- [AUTHORING_GUIDE.md](./AUTHORING_GUIDE.md)
- [architecture.md](./architecture.md)
- [roadmap.md](./roadmap.md)

## Current Limits

- inventory and usable-item systems are still planned
- game-facing save/load UX is still minimal
- editor parameter editing is still basic
- the editor is intentionally focused on room/tile/entity placement, not full high-level content authoring
- external PNG import flow is not finished
- movement/render feel should still be checked periodically on real hardware as the project grows

## Roadmap Direction

The next intended phase is to build a fuller playable project on top of the current engine:

- title screen / intro flow
- stronger example levels and cinematics
- more authored entities and interactions
- fuller save system and game-facing progression flow

## License

No license file has been added yet.
