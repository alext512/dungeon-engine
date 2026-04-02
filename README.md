# Dungeon Engine

A 2D top-down puzzle/RPG engine in Python where most gameplay is authored in
JSON files instead of hardcoded Python scripts.

## In Plain English

This project is for building Zelda-like puzzle/adventure gameplay with:

- rooms made from tiles
- characters and objects placed in those rooms
- reusable entity templates
- switches, doors, blocks, signs, and other interactables
- dialogue and menus
- command chains that describe what happens when something is used or triggered

The main idea is:

- the Python code provides the engine
- the project files provide the game behavior

So instead of writing a custom Python script for every lever, gate, NPC, or
menu, you describe most of that behavior in JSON.

If you are not a programmer, it may help to think of JSON here as:

- plain text files that describe game content and logic in a structured way

## What This Project Is Trying To Do

This engine is trying to keep game behavior in project data instead of hiding it
inside engine code.

That means the project files decide things like:

- what happens when the player presses interact
- what a lever does
- how a gate opens or closes
- what a dialogue menu shows
- where a door sends the player
- which entity currently receives certain inputs
- how a controller entity manages a menu or dialogue flow

The engine itself handles lower-level jobs such as:

- rendering
- input polling
- movement
- collision
- animation playback
- command execution
- save/load

For the design spirit behind those choices, see [PROJECT_SPIRIT.md](./PROJECT_SPIRIT.md).

## What You Can Do Today

The current engine already supports:

- standalone play mode
- project manifests through `project.json`
- tile-based rooms with separate walkability data
- item definitions through `item_paths`
- reusable entity templates with per-instance parameters
- entities with visuals, variables, inventories, input mappings, named behaviors, and engine-known runtime fields
- command-driven movement, interaction, pushing, animation, and persistence
- standard engine-owned grid movement, pushing, and facing interaction helpers
- Inventory V1 with entity-owned stack inventories, authored item definitions,
  `add_inventory_item` / `remove_inventory_item` / `use_inventory_item`,
  inventory value sources, and the first engine-owned inventory UI session
- dialogue and menu flow handled either by controller entities or by the newer
  engine-owned dialogue session runtime
- area changes through authored entry points
- camera follow, bounds, deadzones, and saved camera state
- save slots layered on top of authored room data

There is also a new external area editor under [tools/area_editor](./tools/area_editor/).
It now supports active area-editing workflows such as tile painting, cell-flag editing,
entity placement and nudging, render-property editing, and guarded JSON editing.
Some editor workflows are still deferred, especially screen-space placement,
`global_entities` editing, richer reference pickers, and runtime handoff.

The older built-in editor is archived under [archived_editor](./archived_editor/)
for reference only.

## What The Sample Project Demonstrates

The repo includes a working sample project in
[projects/test_project](./projects/test_project/).

That sample currently shows:

- a title screen with a menu
- connected rooms you can walk between
- player movement with authored animation timing
- pushable blocks
- lever-and-gate puzzle state that can persist
- signs and prompts
- save/load prompts
- pause menu flow
- controller entities that manage dialogue and UI behavior

The repo also includes a focused contract demo project in
[projects/physics_contract_demo](./projects/physics_contract_demo/).

That smaller demo exists specifically to show the newer canonical movement /
interaction contract and the newer engine-owned dialogue session path:

- top-level `facing`, `solid`, `pushable`, `weight`, `push_strength`
- cell `blocked`
- `move_in_direction`
- `push_facing`
- `interact_facing`
- Inventory V1 item definitions, entity-owned inventory state, pickup templates,
  item-gated doors, direct item use, and the first engine-owned inventory UI
- `on_blocked`, `on_occupant_enter`, and `on_occupant_leave`
- `open_dialogue_session` and `close_dialogue_session`
- `open_inventory_session` and `close_inventory_session`
- nested engine-owned dialogue sessions that suspend and resume cleanly
- preset-driven inline or separate-panel choice layouts, including marquee overflow

The older sample projects remain useful examples of lower-level authored JSON
flows. They still work on the current engine, but they are not the canonical
reference for the newer built-in movement/interaction contract.

Good files to inspect first:

- [projects/test_project/project.json](./projects/test_project/project.json)
- [projects/test_project/shared_variables.json](./projects/test_project/shared_variables.json)
- [projects/test_project/areas/title_screen.json](./projects/test_project/areas/title_screen.json)
- [projects/test_project/areas/village_square.json](./projects/test_project/areas/village_square.json)
- [projects/test_project/areas/village_house.json](./projects/test_project/areas/village_house.json)
- [projects/test_project/entity_templates/player.json](./projects/test_project/entity_templates/player.json)
- [projects/test_project/entity_templates/lever_toggle.json](./projects/test_project/entity_templates/lever_toggle.json)
- [projects/test_project/dialogues/system/title_menu.json](./projects/test_project/dialogues/system/title_menu.json)
- [projects/test_project/dialogues/system/pause_menu.json](./projects/test_project/dialogues/system/pause_menu.json)

## How To Think About Authoring

At a high level, a project usually consists of:

- `project.json`
  - tells the engine where to find your project content
- `areas/`
  - rooms, tiles, entries, and placed entities
- `entity_templates/`
  - reusable definitions for players, doors, switches, controllers, and so on
- `commands/`
  - reusable project-level command chains
- `dialogues/`
  - ordinary JSON data used by dialogue/menu controllers
- `shared_variables.json`
  - project-wide shared data
- `assets/`
  - images, fonts, and related project assets

Typical layout:

```text
my_project/
    project.json
    shared_variables.json
    areas/
    entity_templates/
    commands/
    dialogues/
    assets/
```

The stable authoring contract is the JSON data, not hidden engine-side behavior.

## Quick Start

### Requirements

- Python 3.11+
- `pygame-ce`
- Windows is the current primary development environment

Install dependencies:

```bash
pip install -e .
```

Or directly:

```bash
pip install pygame-ce
```

### Run The Sample Project

```bash
python run_game.py --project projects/test_project
python run_game.py --project projects/test_project areas/village_square
```

On Windows, you can also double-click:

- `Run_Game.cmd`

## Controls

### Game

- `WASD` or arrow keys: move
- `Space` or `Enter`: interact, advance dialogue, confirm a choice
- `I`: open inventory directly when the active project routes the `inventory` action
- `Escape`: open the pause menu in playable areas

If debug inspection is enabled in the active project's `project.json`:

- `F6`: pause or resume simulation
- `F7`: step one simulation tick
- `[` / `]`: zoom out or in

## What To Expect When You Run It

When you launch the sample project:

- the title screen opens an authored menu
- choosing `New Game` moves you into the sample rooms
- in `village_square`, you can explore, read signs, save, and enter the house
- in `village_house`, you can toggle the lever and see the gate react
- the pause menu is handled by controller logic rather than a hardcoded engine UI

Useful things to try:

- walk with `WASD` or the arrow keys
- press `Space` or `Enter` to interact
- press `I` in `physics_contract_demo` to open the inventory
- stand by the house door and enter `village_house`
- toggle the lever in the house
- leave and return to confirm the lever/gate state persisted
- push the house block, leave the house, and return to confirm the block reset
- press `Escape` in a playable area to open the pause menu

If you want to inspect the cleaner movement/interaction contract directly, run:

```bash
python run_game.py --project projects/physics_contract_demo
```

## Project Structure

```text
python_puzzle_engine/
    dungeon_engine/             # Active runtime code
    tools/area_editor/          # External area editor
    archived_editor/            # Old built-in editor kept only for reference
    projects/
        test_project/           # Example project content
    run_game.py
    README.md
```

## Documentation

If you want the practical authoring docs, start here:

- [AUTHORING_GUIDE.md](./AUTHORING_GUIDE.md)
  - explains how to author content in JSON without needing to read much Python
- [ENGINE_JSON_INTERFACE.md](./ENGINE_JSON_INTERFACE.md)
  - the exact current JSON surface, commands, tokens, and value sources

Other useful docs:

- [PROJECT_SPIRIT.md](./PROJECT_SPIRIT.md)
  - the design compass for what this project is trying to be
- [architecture.md](./architecture.md)
  - medium-term technical direction and tradeoffs
- [roadmap.md](./roadmap.md)
  - phased development plan
- [CHANGELOG.md](./CHANGELOG.md)
  - reverse-chronological history of changes
- [CONTRIBUTING.md](./CONTRIBUTING.md)
  - working rules for contributing
- [AGENTS.md](./AGENTS.md)
  - AI agent onboarding and doc reading order

## Important Design Notes

- Movement is still command-driven, but the engine now also exposes standard
  built-ins such as `move_in_direction` and `push_facing` so projects do not
  have to rebuild the common grid-physics contract by default.
- Occupancy-triggered puzzle reactions can now live on the stationary entity
  through ordinary `entity_commands` such as `on_occupant_enter` and
  `on_occupant_leave`, instead of requiring a separate controller flow.
- Interaction is command-driven too. The engine now also exposes
  `interact_facing` as the standard facing-target lookup, while target behavior
  remains authored on the target's normal `interact` command.
- Inventory now has two layers:
  - gameplay/data through item definitions plus inventory builtins
  - a newer engine-owned inventory session opened through
    `open_inventory_session`
- Dialogue now has two valid authoring paths:
  - the newer engine-owned session runtime, opened through
    `open_dialogue_session`
  - the older controller-owned authored flow still used by the older sample
    projects
- Projects can route different logical inputs to different entities at runtime.
- Save data stores the current area, current routed input targets, camera state,
  traveler state, visited-area persistent diffs, and the current diff of the
  active area.

## Verification

Useful commands during development:

```text
.venv/Scripts/python -m unittest discover -s tests -v
.venv/Scripts/python run_game.py --project projects/test_project areas/title_screen --headless --max-frames 2
.venv/Scripts/python run_game.py --project projects/test_project areas/village_square --headless --max-frames 2
.venv/Scripts/python run_game.py --project projects/test_project areas/village_house --headless --max-frames 2
cd tools/area_editor
..\..\.venv/Scripts/python -m unittest discover -s tests -v
```

## Current Limits

- save/load UX works, but is still basic
- external PNG import workflow is not finished
- the external area editor still has some deferred workflows, especially screen-space placement, `global_entities` editing, richer reference pickers, and runtime handoff
- movement/render feel should still be checked periodically on real hardware as
  the project grows

## Suggested Next Steps

- build more real project content and let that pressure guide engine changes
- expand dialogue/menu authoring support
- continue turning the external editor into a full authoring tool
- keep improving movement/render quality

## License

No license file has been added yet.
