# Agent Onboarding

This file is the starting point for any AI agent working on this project. Read this first, then dive into the files it points to.

## What Is This?

A top-down RPG/puzzle game engine built with Python and `pygame-ce`. It has an in-app level editor with a dual-window layout (map window + browser/tools window). The game is command-driven and data-driven — gameplay logic lives in JSON command chains, not hardcoded Python scripts.

## How to Run

```
cd python_puzzle_engine
.venv/Scripts/python main.py
```

Or double-click `Run_Python_Puzzle.cmd`.

## Read These Files (In Order)

| File | What It Tells You |
|---|---|
| `STATUS.md` | What's implemented, editor controls, current test room, known issues |
| `architecture.md` | Design philosophy, tech stack, command system, entity/component model |
| `CONTRIBUTING.md` | Working rules and project direction |
| `roadmap.md` | Planned features and phases |
| `plans/` folder | Detailed implementation plans for specific tasks |

## Project Structure

```
main.py                          # Entry point
puzzle_dungeon/
    config.py                    # Paths, constants, window sizes
    engine/
        game.py                  # Main game loop, mode switching (editor/play)
        renderer.py              # All rendering (tiles, entities, editor overlays)
        asset_manager.py         # PNG loading, frame slicing, caching
        camera.py                # Camera positioning and snapping
        input_handler.py         # Input polling
        text.py                  # Bitmap font rendering
    editor/
        level_editor.py          # Editor state, tools, tile/entity operations
        browser_window.py        # Second pygame window (tileset view, layers, entities, properties)
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
    data/
        areas/test_room.json     # The current test level
        entities/*.json          # Entity templates (player, block, lever, gate)
        assets/tiles/            # Tileset PNGs
        assets/sprites/          # Sprite sheet PNGs
        fonts/                   # Bitmap font atlases
```

## Key Technical Decisions

- **GID-based tilemaps**: Tile grids store integers, not strings. GID 0 = empty. Each tileset has a `firstgid`; a tile's local frame = `gid - firstgid`. This matches the industry standard (Tiled, Godot, RPG Maker). See `area.py` for `resolve_gid()`.
- **Command pattern**: All gameplay (movement, interaction, triggers) goes through the command runner. Input queues commands; it never mutates game state directly.
- **Editor document model**: The editor keeps an authoritative copy of the area. Play-testing clones it, so play never corrupts the editor state.
- **Dual-window editor**: Main window shows the map. A second pygame window (`browser_window.py`) shows tools, tileset images, layers, entity palettes, and property inspectors. The browser layout changes based on the active mode (tile/walkability/entity).
- **Entity templates**: Entities are defined in `data/entities/*.json` as templates. Placed instances can override parameters using `$variable` substitution.

## Common Tasks

**Adding a new command type**: Register it in `commands/registry.py`, implement in `commands/builtin.py`.

**Adding a new entity template**: Create a JSON file in `data/entities/`, place it in a room via the editor.

**Editing the editor UI**: Browser window layout is in `browser_window.py`. Editor logic/state is in `level_editor.py`. Rendering of editor overlays (hover preview, grid, selection) is in `renderer.py`.

**Changing how tiles/areas work**: Core data model is `area.py`. Loading is `loader.py`, saving is `serializer.py`.

## Gotchas

- The project uses `pygame-ce` (Community Edition), not vanilla `pygame`. Install with `pip install pygame-ce`.
- Two separate pygame display windows are active simultaneously. The browser window runs on a separate surface.
- Tile layers and walkability are independent systems — a tile can exist without a walk flag and vice versa.
- Entity stacking: multiple entities can occupy the same grid cell, ordered by `stack_order`.
- The `asset_manager` is passed around to many constructors — it's the central cache for all loaded images and frames.
