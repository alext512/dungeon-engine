# Engine Manual

## Purpose

This is the practical manual for the current Python engine.

It explains:

- what the engine is
- how projects are structured
- how to run the game and editor
- how content is authored
- how commands, movement, dialogue, and screen-space elements currently work

This document is meant to describe the engine as it exists now, not just future
ideas.

## Five-Minute Catch-Up

If you are new to the codebase, this is the shortest accurate summary:

- engine code lives in `dungeon_engine/`
- sample project content lives in `projects/test_project/`
- gameplay is command-driven through JSON
- input triggers entity events like `move_up` and `interact`
- the sample player movement is authored in `entities/player.json` plus named commands in `commands/`
- `variables.json` currently owns shared values like render resolution, dialogue layout, and `movement.ticks_per_tile`
- text sessions are the main dialogue text service:
  - the engine wraps, paginates, and windows text
  - UI entities decide when to read, advance, reset, and render it
- `run_dialogue` still exists as a simple text-only helper
- sample dialogue choices are handled by a focused `dialogue_ui` entity plus named commands under `commands/dialogue/`
- the project starts in `projects/test_project/areas/title_screen.json`
- `New Game` leads into `projects/test_project/areas/village_square.json`
- `village_square` connects to `projects/test_project/areas/village_house.json`
- startup validation blocks launch on malformed/duplicate command-library problems
- named commands are indexed into an in-memory project database at startup
- `logs/error.log` is the main runtime/debug log

If you only need the most important files first, read these:

1. `STATUS.md`
2. `MANUAL.md`
3. `projects/test_project/project.json`
4. `projects/test_project/variables.json`
5. `projects/test_project/areas/title_screen.json`
6. `projects/test_project/entities/player.json`
7. `projects/test_project/areas/village_square.json`
8. `projects/test_project/areas/village_house.json`
9. `projects/test_project/entities/dialogue_ui.json`
10. `dungeon_engine/commands/builtin.py`
11. `dungeon_engine/commands/runner.py`
12. `dungeon_engine/engine/game.py`

## What This Project Is

The engine is a focused Python + `pygame-ce` top-down puzzle/RPG framework.

Important design choices:

- gameplay is command-driven
- projects are data-driven through JSON
- the editor and the game share the same room/entity data model
- the engine package is independent from any one project folder

The active engine code lives in:

- `dungeon_engine/`

The repo-local sample project lives in:

- `projects/test_project/`

The old Godot project is reference only:

- `../dungeon-puzzle-2/`

## Quick Start

From the repo root:

```text
cd python_puzzle_engine
.venv/Scripts/python run_game.py
.venv/Scripts/python run_editor.py
```

Windows launchers also exist:

- `Run_Game.cmd`
- `Run_Editor.cmd`

Launcher behavior:

- if you pass `--project`, that project is used directly
- if you also pass an area path, that area opens directly
- if you pass only a project, the engine uses `startup_area` from `project.json`
- if you pass nothing, the launcher opens file pickers rooted at the last used location

Examples:

```text
.venv/Scripts/python run_game.py --project projects/test_project
.venv/Scripts/python run_game.py --project projects/test_project areas/village_square.json
.venv/Scripts/python run_editor.py --project projects/test_project
```

## Repo Layout

```text
python_puzzle_engine/
    dungeon_engine/             # Engine package
    projects/
        test_project/           # Versioned sample project
    run_game.py
    run_editor.py
    STATUS.md
    architecture.md
    functionality.md
    roadmap.md
    plans/
```

Important boundary:

- `dungeon_engine/` = engine/editor/runtime code
- `projects/<name>/` = project content

Keeping a project inside this repo does not make it engine-owned content. It is
just a convenient versioned project folder.

## Project Structure

A project is a folder containing a `project.json` manifest.

Typical layout:

```text
test_project/
    project.json
    variables.json
    areas/
    entities/
    commands/
    dialogues/
    assets/
```

### `project.json`

Current important fields:

- `entity_paths`
- `asset_paths`
- `area_paths`
- `command_paths`
- `dialogue_paths`
- `variables_path`
- `startup_area`
- `active_entity_id`
- `debug_inspection_enabled`
- `input_events`

Example:

```json
{
  "entity_paths": ["entities/"],
  "asset_paths": ["assets/"],
  "area_paths": ["areas/"],
  "command_paths": ["commands/"],
  "dialogue_paths": ["dialogues/"],
  "variables_path": "variables.json",
  "startup_area": "areas/title_screen.json",
  "active_entity_id": "player",
  "debug_inspection_enabled": true,
  "input_events": {
    "move_up": "move_up",
    "move_down": "move_down",
    "move_left": "move_left",
    "move_right": "move_right",
    "interact": "interact"
  }
}
```

### `variables.json`

This is the project-shared variable file.

Use it for values that belong to the project rather than to one specific
entity.

Current sample uses:

- internal render resolution
- dialogue layout values
- movement `ticks_per_tile`

Example:

```json
{
  "display": {
    "internal_width": 256,
    "internal_height": 192
  },
  "movement": {
    "ticks_per_tile": 16
  }
}
```

Commands can read these values through runtime tokens like:

- `$project.display.internal_width`
- `$project.movement.ticks_per_tile`

## World Content

### Areas

Area JSON stores:

- area id
- tile size
- visual tile layers
- walkability data
- placed entity instances
- local/world variables

Areas are authored data, not runtime save-state dumps.

### Entity Templates

Entity JSON files under `entities/` define reusable entity templates.

They can contain:

- sprite info
- flags like `solid`, `visible`, `present`, `pushable`
- variables
- named events
- parameters/placeholders

Placed instances in rooms usually reference a template plus per-instance data.

### Dialogue Assets

Dialogue text lives in dedicated JSON files under `dialogues/`.

Current dialogue assets may define:

- `id`
- `text`
- or `pages`

Example:

```json
{
  "id": "signs/gate_hint",
  "text": "Sign: The old path is sealed. Pull the lever to open the gate."
}
```

### Named Command Assets

Reusable project commands live under `commands/`.

These are JSON command libraries addressed by path-based ids, for example:

- `dialogue/sign_gate_hint`
- `dialogue/blue_guide_open`

The engine loads them through `run_named_command`.

At startup, the project builds an in-memory named-command database so runtime
lookups do not rescan command folders during gameplay.

## Command Model

Gameplay is built out of command chains.

Broad split:

- Python implements primitive engine commands
- project JSON composes those primitives into behavior

Examples of primitive commands already in the engine:

- `run_event`
- `run_named_command`
- `set_var`
- `increment_var`
- `check_var`
- `move_entity`
- `move_entity_one_tile`
- `teleport_entity`
- `change_area`
- `play_animation`
- `stop_animation`
- `set_sprite_frame`
- `show_screen_image`
- `show_screen_text`
- `remove_screen_element`
- `play_audio`
- `run_dialogue`
- `save_game`
- `load_game`
- `quit_game`

### Events

Entities own named events such as:

- `move_up`
- `move_down`
- `interact`
- `push_from_left`

The engine does not hardcode the player’s movement behavior. Input triggers the
configured event names on the current active entity.

## Input Model

The engine routes direct control to `world.active_entity_id`.

By default:

- `Up` / `W` -> active entity event `move_up`
- `Down` / `S` -> `move_down`
- `Left` / `A` -> `move_left`
- `Right` / `D` -> `move_right`
- `Space` / `Enter` -> `interact`

But:

- active entities can define their own `input_map`
- projects define fallback event names in `project.json`
- commands can switch the active entity with `set_active_entity`, `push_active_entity`, and `pop_active_entity`

This lets a room temporarily hand control to something other than the player.

## Movement and Animation

### Fixed Timestep

Gameplay simulation runs on a fixed tick:

- `1 / 60` second per tick

Rendering is separate from simulation timing.

### Player Step Timing

The sample player uses:

- `movement.ticks_per_tile` from `variables.json`

Currently in the sample project:

- `ticks_per_tile = 16`

That means:

- one tile move = 16 simulation ticks
- with a 16 px tile, movement is 1 px per tick

### Where Animation Timing Is Determined

For the player, sprite-change timing is command-driven.

The player move event passes:

- `frames_needed = $project.movement.ticks_per_tile`
- `frames_per_sprite_change = $half:project.movement.ticks_per_tile`

So if `ticks_per_tile = 16`:

- movement lasts 16 ticks
- the walk sprite changes every 8 ticks

### Walk Phase

The sample player alternates between two half-cycles using an entity variable:

- `walk_phase`

That is authored in:

- `commands/walk_one_tile.json`

### Pushing

Current pushing in the sample project works like this:

1. player attempts movement
2. the command chain probes what is ahead
3. if blocked by a movable object, it delegates to that object’s directional
   push event
4. the player re-checks the path
5. only then does the player walk

So the pushed object participates in the behavior instead of being only a
passive hardcoded flag.

## Screen-Space Elements

The engine has a generic screen-space layer for overlays.

Current primitives:

- `show_screen_image`
- `show_screen_text`
- `set_screen_text`
- `remove_screen_element`
- `clear_screen_elements`
- `play_screen_animation`
- `wait_for_screen_animation`

This layer is meant for:

- dialogue panels
- portraits
- title cards
- overlays
- later menu-like elements

## Dialogue

### Current Design

The current engine keeps dialogue intentionally narrow and service-oriented.

Engine-owned part:

- text wrapping by measured pixel width
- pagination by `max_lines`
- single-line marquee windowing for long choice text
- text-session storage and cursor state

Project-authored part:

- showing the panel image
- showing a portrait image
- deciding where the text box is
- creating/removing choice text
- deciding when text advances or resets
- processing menu-like input through events and commands

So the recommended flow is now:

- a UI entity owns dialogue flow
- text-session commands provide processed text
- normal screen-space commands render the result

### Current `run_dialogue`

Important parameters:

- `dialogue_id`
- `text`
- `pages`
- `element_id`
- `x`
- `y`
- `max_width`
- `max_lines`
- `layer`

Use either:

- one long `text` and let the engine paginate it
- or explicit `pages` for manual control

`run_dialogue` is still fine for simple blocking text, but the sample project now
uses `prepare_text_session`, `read_text_session`, `advance_text_session`, and
`reset_text_session` instead.

### Dialogue Layout

The sample project keeps shared dialogue layout values in `variables.json`,
for example:

- `dialogue.panel_path`
- `dialogue.plain_box`
- `dialogue.portrait_box`
- `dialogue.portrait_position`
- `dialogue.max_lines`

That lets command chains reuse one consistent layout without baking that layout
into the engine.

### Choices

Current choices are command-driven in the sample project.

The engine does not own a generic choice-menu command.

Instead:

- the command chain creates separate screen-text elements for each option
- the selected option can start a marquee-style long-text session
- a focused `dialogue_ui` entity becomes the active input receiver
- its `move_up`, `move_down`, and `interact` events run named commands that:
  - update the selected index
  - update scroll offset when there are more than three choices
  - redraw the choice lines
  - confirm the selected branch

## Audio

The engine audio layer is intentionally minimal.

The primitive is:

- `play_audio`

The engine does not currently distinguish between “music” and “sfx” in the
command API.

## Persistence

Persistence is layered over authored data.

Conceptual layers:

- authored content
- transient runtime state
- persistent runtime overrides
- save slot data

Current save/load flow:

- title-screen `Load` opens a native file chooser rooted at the active project's `saves/` folder
- in-level save points open an authored yes/no prompt and then a save-file chooser rooted at the same folder
- the in-level `Escape` menu is just normal dialogue UI and currently exposes `Continue`, `Load`, and `Exit`
- save data records the current area, the current active entity, persistent diffs for visited areas, and the current area's full runtime diff
- when a save is loaded, the active area's temporary changes are restored for that load, but they still reset after the player leaves that area again

## Debug and Inspection

If the project enables `debug_inspection_enabled`, play mode supports:

- `F6` pause/resume simulation
- `F7` advance one simulation tick
- `[` / `]` zoom out/in

This is useful for inspecting movement, animation, and dialogue timing.

## Editor

The editor is a separate application, not an in-game overlay.

Current core use cases:

- paint tiles
- manage layers
- place entities
- inspect/edit a limited set of properties
- save and reload room data

The editor shares the same room/entity JSON model as play mode.

For detailed controls, see `STATUS.md`.

## Validation and Errors

At startup, the engine validates:

- malformed named-command files
- duplicate command ids
- malformed dialogue files
- duplicate dialogue ids when looked up
- literal missing command references where validation can prove they are missing

Errors go to:

- `logs/error.log`

## Current Sample Project

The sample project demonstrates:

- a title screen authored as a normal area with animated screen-space art and button entities
- generic area-to-area travel through a door entity and the `change_area` command
- a tilemap-based outdoor area and a connected tilemap-based house interior
- an authored save point that calls the project-scoped save dialog
- an in-level `Escape` menu built as ordinary dialogue/options JSON
- a persistent lever/gate example
- a non-persistent push block that resets after area exit/re-entry
- project-level variables for resolution, dialogue layout, and movement timing

Useful sample files:

- `projects/test_project/project.json`
- `projects/test_project/variables.json`
- `projects/test_project/areas/title_screen.json`
- `projects/test_project/areas/village_square.json`
- `projects/test_project/areas/village_house.json`
- `projects/test_project/entities/player.json`
- `projects/test_project/entities/area_door.json`
- `projects/test_project/entities/save_point.json`
- `projects/test_project/entities/dialogue_ui.json`
- `projects/test_project/commands/dialogue/`
- `projects/test_project/commands/title/`
- `projects/test_project/dialogues/`

## Current Limits

Important current limitations:

- movement/render feel still needs a dedicated polish pass
- dialogue text is paginated, but there is no typewriter text yet
- choice layout is still authored manually in commands
- there is no visual command editor yet
- editor parameter editing is still basic
- inventory/item systems are still planned work

## Suggested Reading Order

For the repo docs:

1. `STATUS.md`
2. `MANUAL.md`
3. `architecture.md`
4. `functionality.md`
5. `roadmap.md`
6. `plans/`
