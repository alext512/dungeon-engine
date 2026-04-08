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
- template-authored default parameter values that instances can selectively override
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
It now supports active authoring workflows such as:

- tile painting and `cell_flags` editing
- rectangular tile selection on the active layer, including clear/delete plus
  `Ctrl+C` / `Ctrl+X` / `Ctrl+V`
- multi-tile tileset selection that paints as a stamp brush
- tile-layer add/rename/delete/reorder
- area duplication as either a full copy or a layout-only shell copy
- entity placement, selection, deletion, and nudging
- a tabbed right-side area workspace with `Layers` plus `Area Start`
  `enter_commands` helpers for common actions like input routing, dialogue,
  camera follow, and music
- render-property editing
- project manifest, shared-variables, item, and global-entity editing
- reference-aware `Rename/Move...` for file-backed project content
- guarded raw JSON editing for the supported document types

The editor is still not fully caught up with every newer runtime-facing workflow,
but it has moved well beyond the earlier area-only slice. The main remaining gaps
are things like runtime handoff/launch integration, richer visual screen-space
placement, drag-to-move entity manipulation, and broader structured editing for
newer engine-owned fields.

The older built-in editor is archived under [archived_editor](./archived_editor/)
for reference only.

## Repo-Local Example Projects

The repo may contain one or more example projects under `projects/`.

Those folders are convenience content, not part of the runtime package, and
they may change, be replaced, or disappear as the engine evolves. The stable
contract is the manifest-driven project format itself, not any one repo-local
example.

Repo-local examples are still useful because they can show:

- how `project.json` points at areas, templates, commands, items, dialogue data,
  and assets
- how complete authored flows are composed without custom Python scripts
- what real end-to-end JSON authoring looks like for movement, puzzles,
  dialogue, inventory, save/load, and UI routing

If you want to inspect a repo-local example, start with whichever folder
currently contains a `project.json` manifest. Good files to inspect first are
usually:

- `project.json`
- `shared_variables.json`
- `areas/*.json`
- `entity_templates/*.json`
- `commands/*.json`
- `dialogues/*.json`
- `items/*.json`

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
    items/
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

### Run A Project

```bash
python run_game.py --project path/to/project_folder
python run_game.py --project path/to/project_folder areas/start
python run_game.py --project path/to/project.json
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

When you launch a project:

- the manifest's `startup_area` opens unless you pass an explicit area id
- everything after that depends on the authored content in that project
- repo-local example projects often demonstrate title screens, room transitions,
  controller-owned dialogue flows, engine-owned dialogue sessions, inventory
  flows, pause/save prompts, and simple puzzle state

Useful things to try:

- walk with `WASD` or the arrow keys
- press `Space` or `Enter` to interact
- if the active project routes an `inventory` action, press `I`
- if the active project routes a `menu` action, press `Escape`
- inspect the project's JSON when you want to understand why a specific flow
  behaves the way it does

## Project Structure

```text
python_puzzle_engine/
    dungeon_engine/             # Active runtime code
    tools/area_editor/          # External area editor
    archived_editor/            # Old built-in editor kept only for reference
    projects/
        my_game/                # Optional repo-local project content
    tests/                      # Engine unittest suite
    plans/                      # Planning and design documents
    archive/                    # Old documentation kept for reference
    run_game.py
    README.md
```

## Documentation

This repo now also contains a publishable docs site under `docs/`, configured by
`mkdocs.yml`.

Preview it locally with:

```text
pip install -r requirements-docs.txt
mkdocs serve
```

Build static output with:

```text
mkdocs build
```

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
  - the older controller-owned authored flow still supported for projects that
    prefer it
- Projects can route different logical inputs to different entities at runtime.
- Save data stores the current area, current routed input targets, camera state,
  traveler state, visited-area persistent diffs, and the current diff of the
  active area.

## Verification

Useful commands during development:

```text
.venv/Scripts/python -m unittest discover -s tests -v
.venv/Scripts/python run_game.py --project path/to/project --headless --max-frames 2
cd tools/area_editor
..\..\.venv/Scripts/python -m unittest discover -s tests -v
```

Startup validation now also validates known command-bearing JSON surfaces for
strict-command key mismatches. Likely top-level key typos on strict primitive
commands now fail before launch instead of slipping into runtime behavior.

If you keep repo-local example projects under `projects/`, validate each
present `project.json` directly after command-surface or content-authoring
changes.

## Current Limits

- save/load UX works, but is still basic
- external PNG import workflow is not finished
- the external area editor still has a few important gaps, especially runtime handoff, visual screen-space placement, drag-to-move entity manipulation, and broader structured editing for some newer engine-owned fields
- movement/render feel should still be checked periodically on real hardware as
  the project grows

## Suggested Next Steps

- build more real project content and let that pressure guide engine changes
- expand dialogue/menu authoring support
- continue turning the external editor into a fuller authoring tool, especially around runtime handoff, visual screen-space placement, drag manipulation, and broader structured editing of newer engine-owned fields
- keep improving movement/render quality

## License

No license file has been added yet.
