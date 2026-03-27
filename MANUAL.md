# Engine Manual

## Purpose

This is the practical manual for the current Python engine.

It explains:

- how projects are structured
- how runtime entities work
- how input, commands, dialogue, and persistence currently behave
- how the sample project is wired today

This document describes the engine as it exists now.

## Five-Minute Catch-Up

If you are new to the codebase, this is the shortest accurate summary:

- engine code lives in `dungeon_engine/`
- sample project content lives in `projects/test_project/`
- gameplay is command-driven through JSON
- reusable content ids are path-derived from the project's search roots
- entities use `visuals`, `space`, `scope`, `input_map`, events, and variables
- input routes each logical action to its current target entity first
- the sample project has global `dialogue_controller` and `pause_controller` entities declared in `project.json`
- the sample project's dialogue/menu content lives in ordinary JSON files under `dialogues/`
- controller entities own dialogue/menu state and nested restore state in normal variables
- save data records diffs on top of authored area data instead of overwriting project JSON

If you only need the most important files first, read these:

1. `STATUS.md`
2. `MANUAL.md`
3. `projects/test_project/project.json`
4. `projects/test_project/shared_variables.json`
5. `projects/test_project/areas/title_screen.json`
6. `projects/test_project/entity_templates/player.json`
7. `projects/test_project/entity_templates/dialogue_panel.json`
8. `projects/test_project/entity_templates/lever_toggle.json`
9. `projects/test_project/dialogues/system/title_menu.json`
10. `dungeon_engine/commands/builtin.py`
11. `dungeon_engine/commands/runner.py`
12. `dungeon_engine/engine/game.py`

## Project Structure

A project is a folder containing a `project.json` manifest.

Typical layout:

```text
test_project/
    project.json
    shared_variables.json
    areas/
    entity_templates/
    named_commands/
    dialogues/
    assets/
```

The folder names are conventional, not hardcoded. What matters is the manifest.

### `project.json`

Current important fields:

- `entity_template_paths`
- `asset_paths`
- `area_paths`
- `named_command_paths`
- `shared_variables_path`
- `global_entities`
- `startup_area`
- `input_targets`
- `debug_inspection_enabled`
- `input_events`

Example:

```json
{
  "entity_template_paths": ["entity_templates/"],
  "asset_paths": ["assets/"],
  "area_paths": ["areas/"],
  "named_command_paths": ["named_commands/"],
  "shared_variables_path": "shared_variables.json",
  "global_entities": [
    {
      "id": "dialogue_controller",
      "template": "dialogue_panel"
    },
    {
      "id": "pause_controller",
      "template": "pause_controller"
    }
  ],
  "startup_area": "title_screen",
  "input_targets": {
    "menu": "pause_controller"
  },
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

Notes:

- all paths are relative to the folder containing `project.json`
- `global_entities` are instantiated into every runtime world with `scope: "global"`
- `startup_area` must be a path-derived area id such as `title_screen`
- `input_targets` is merged with per-area routing; actions omitted by both the project and the area stay unrouted until runtime commands assign them
- `input_events` are fallback logical actions; routed entities can override them through their own `input_map`

### `shared_variables.json`

This file stores shared project values such as:

- render resolution
- movement timing
- dialogue layout defaults

Example:

```json
{
  "display": {
    "internal_width": 256,
    "internal_height": 192
  },
  "movement": {
    "ticks_per_tile": 16
  },
  "dialogue": {
    "max_lines": 3
  }
}
```

Commands can read these values with tokens such as:

- `$project.display.internal_width`
- `$project.movement.ticks_per_tile`
- `$project.dialogue.max_lines`

## World Content

### Areas

Area JSON stores:

- tile size
- visual tile layers
- walkability data
- optional authored `entry_points`
- optional authored `camera` defaults
- placed entity instances
- area variables
- optional `enter_commands`

Important points:

- area ids are path-derived, not authored in the JSON body
- authored areas must not declare `player_id`; control ownership and camera setup are explicit now
- area entities are serialized from `world.iter_area_entities()`
- project global entities are not authored inside area files

The sample areas show three useful patterns:

- `input_targets` can point at a controller entity instead of a walking player
- `entry_points` can give doors and fresh-session starts stable named destinations
- `enter_commands` can auto-open a dialogue or menu when the area loads

### Entity Templates

Entity templates live under `entity_templates/` and define reusable runtime objects.

Current entity model:

- `visuals`: persistent visual list
- `space`: `world` or `screen`
- `scope`: `area` or `global`
- `input_map`: logical action to event-name mapping
- `events`: named command chains
- `variables`: mutable per-entity data

Important authoring rules:

- legacy `sprite` blocks are rejected
- `space: "world"` entities use `x` / `y`
- `space: "screen"` entities use `pixel_x` / `pixel_y` and must not author `x` / `y`
- `scope: "global"` is intended for project-level controller/service entities

### Named Commands

Reusable project commands live under `named_commands/`.

They are:

- loaded into an in-memory database at startup
- addressed by path-derived id
- executed through `run_named_command`

The sample project uses named commands for both movement logic and controller-owned dialogue/menu behavior.

### Ordinary JSON Dialogue Data

The sample project keeps reusable dialogue/menu data under `dialogues/`, but that folder is only a convention. These files are not a special manifest category anymore. Controllers load them through normal commands such as `set_var_from_json_file`.

Typical dialogue/menu JSON contains:

- optional `participants`
- a required `segments` list
- optional `font_id`, `max_lines`, and `text_color`

Segment types:

- `text`
- `choice`

Each segment can also define:

- `speaker_id`
- `show_portrait`
- `advance_mode`
- `advance_seconds`

These JSON files do not directly own gameplay commands. Controller entities load them, store them in variables, and decide how input advances, branches, or closes.

## Runtime Entity Model

### `visuals`

Each entity owns a list of persistent visuals. Every visual has its own:

- `id`
- `path`
- `frame_width` / `frame_height`
- `frames`
- `animation_fps`
- `animate_when_moving`
- `flip_x`
- `visible`
- `tint`
- `offset_x` / `offset_y`
- `draw_order`

The first visual is treated as the primary visual in many places, but commands can also target a specific visual path such as `visuals.main.tint`.

### `space`

`space` defines the coordinate system:

- `world`: tile-aligned, participates in collision and interaction lookup
- `screen`: positioned directly in screen pixels and rendered in screen space

The dialogue controller is a screen-space entity. The player, signs, levers, and doors are world-space entities.

### `scope`

`scope` defines runtime lifetime:

- `area`: normal area-owned entity
- `global`: project-level entity added to every runtime world

`World` keeps these in separate dictionaries:

- `area_entities`
- `global_entities`

Queries like `world.get_entity()` and `world.get_input_target(action)` look across both sets.

### Routed Input Targets

Each logical action is routed independently.

Current flow:

1. the input handler resolves a logical action such as `move_up`, `interact`, or `menu`
2. the world chooses the routed entity for that action from the current `input_targets`, using project defaults plus any area overrides
3. that routed entity's `input_map` is checked first
4. if no entity-specific mapping exists, the project-level `input_events` fallback is used
5. the runner enqueues `run_event` on the routed entity

This is what allows dialogue controllers, menus, and other service entities to temporarily own only the inputs they need without a single active-entity focus model.

If an action is absent from both the project and the area routing maps, it is simply unrouted until a runtime command assigns it.

For modal flows, the intended pattern is:

1. `push_input_routes`
2. reroute the borrowed actions to the modal controller
3. later `pop_input_routes` to restore the exact previous routes

The route stack is runtime-only control state. It is not saved.

## Commands and Runtime References

Gameplay is built from command chains.

Broad split:

- Python implements primitive engine commands
- project JSON composes those primitives into behavior

Important command families already in the engine:

- event dispatch: `run_event`, `run_named_command`
- movement: `move_entity`, `move_entity_one_tile`, `teleport_entity`
- variables: `set_var`, `increment_var`, `check_var`
- entity mutation: `set_entity_field`, `set_event_enabled`
- persistence/flow: `change_area`, `new_game`, `save_game`, `load_game`, `quit_game`
- input routing: `set_input_target`, `route_inputs_to_entity`, `push_input_routes`, `pop_input_routes`
- generic text/data helpers: `set_var_from_json_file`, `set_var_from_wrapped_lines`, `set_var_from_text_window`, `append_to_var`, `pop_var`
- camera: `set_camera_follow_entity`, `set_camera_follow_input_target`, `clear_camera_follow`, `set_camera_bounds_rect`, `clear_camera_bounds`, `set_camera_deadzone`, `clear_camera_deadzone`, `set_var_from_camera`, `move_camera`, `teleport_camera`

### Special entity references

Many commands that accept `entity_id` also accept:

- `self`: the entity that owns the current event/command chain
- `actor`: the entity that initiated the current interaction/input flow
- `caller`: the caller explicitly forwarded into a deeper command chain

These are resolved by the command system before execution.

### Runtime tokens

The runner also supports tokens such as:

- `$self_id`
- `$actor_id`
- `$caller_id`
- `$self.some_var`
- `$actor.some_var`
- `$caller.some_var`
- `$project.dialogue.max_lines`
- `$world.some_value`

These are especially useful when forwarding context into another entity's event.

## Dialogue Model

### Removed Dialogue Session Commands

The old authored `run_dialogue` path and the later `start_dialogue_session` / `dialogue_*` / text-session commands are intentionally gone. Startup validation rejects authored uses of them, and the runtime names remain only as fail-fast errors.

Current rule:

- start dialogue or menu flow by sending an event to a controller entity
- let controller-owned commands load JSON data, mutate controller vars, and redraw UI

## Session Flow

- `change_area` moves into another authored area while keeping the current runtime session alive. It can target an authored `entry_id`, transfer one or more live entities, and request a post-load camera follow target.
- `new_game` resets the current runtime session state and then enters the requested authored area. It uses the same transition payload shape as `change_area`, including optional `entry_id` and camera follow data.
- `load_game` restores a save slot into the current runtime.
- `save_game` writes the current runtime session to a save slot.
- `quit_game` requests runtime shutdown.

### Controller-owned Dialogue And Menus

The sample project's `dialogue_panel` template is the canonical example.

It does three jobs:

- owns the screen-space visuals used for the panel and portrait
- owns the input map for confirm, cancel, and selection movement
- exposes an `open_dialogue` event that calls controller-owned named commands

That event forwards values such as:

- `dialogue_path`
- `dialogue_on_start`
- `dialogue_on_end`
- `segment_hooks`
- `allow_cancel`
- `actor_entity_id`
- `caller_entity_id`

When a dialogue starts:

1. the controller's `on_start` commands reroute the needed logical inputs to the dialogue controller
2. the controller loads ordinary JSON dialogue data into entity variables
3. controller-owned commands derive visible text/options and render them through the screen manager
4. controller input routes to normal entity events like `interact`, `move_up`, `move_down`, and `menu`
5. nested dialogue/menu state is saved into the controller's `dialogue_state_stack`
6. when the controller finally closes its outermost dialogue, it restores the borrowed routes through `pop_input_routes`
7. authored `dialogue_on_end` commands can then safely run post-close behavior such as `save_game`, `load_game`, `new_game`, or `quit_game`

### Caller-supplied hooks

The sample controller pattern supports three important extension points:

- `on_start`: runs once before the first segment
- `on_end`: runs once after the dialogue fully closes
- `segment_hooks`: one optional hook object per segment

Each segment hook can contain:

- `on_start`
- `on_end`
- `option_commands_by_id`
- `option_commands`

This is how the sample lever, save point, pause menu, and title screen attach gameplay consequences to plain JSON dialogue/menu data.

When a choice needs to trigger something after the dialogue has fully closed, the reliable pattern is:

1. store the selected result in a variable during a segment hook
2. close the dialogue
3. branch on that variable from `dialogue_on_end`

That keeps post-close actions separate from the controller's input-restore bookkeeping.

## Persistence and Area Changes

Persistence stores playthrough-specific differences on top of authored area data.

Key points:

- authored project content stays as the source of truth
- save slots live under the active project's `saves/` folder
- save data records current area, current logical input-target routing, current camera state, traveler session state, per-area overrides, and an exact diff for the current loaded area
- persistent commands can record entity-field and variable changes without rewriting authored JSON

The sample lever/gate puzzle uses persistent field and variable writes to keep the puzzle state across save/load and room re-entry.

### Area Entry Points

Areas can author a top-level `entry_points` object containing named destinations:

```json
"entry_points": {
  "from_house": {
    "x": 8,
    "y": 6,
    "facing": "down"
  }
}
```

These are the stable targets for `change_area` and `new_game`. Each entry point can also provide optional `pixel_x` / `pixel_y` overrides when a transfer should land at a specific transform position.

### Cross-Area Travelers

Transferred entities are tracked as session travelers.

That means:

- a transferred entity keeps one live identity across areas
- its authored origin placeholder is suppressed while it is away
- re-entering the origin area does not duplicate it
- save/load restores the traveler in its current area

The sample door template demonstrates the intended pattern:

```json
{
  "type": "change_area",
  "area_id": "$target_area",
  "entry_id": "$target_entry",
  "transfer_entity_ids": ["actor"],
  "camera_follow_entity_id": "actor"
}
```

### Camera State

Camera behavior is explicit runtime state, not an implicit player default.

Areas can author camera defaults:

```json
"camera": {
  "follow_entity_id": "player"
}
```

Commands can then retarget or refine that state during play:

- follow a specific entity or a routed input target
- apply follow offsets
- clamp the camera to a bounds rectangle
- keep the followed target inside a deadzone rectangle
- query the current follow target, offsets, position, and bounds state into variables through `set_var_from_camera`

Current camera state is saved and restored with the session.

## Controls

### Game

- `WASD` or arrow keys: move
- `Space` or `Enter`: interact, advance dialogue, confirm choice
- `Escape`: open the pause menu in playable areas

If debug inspection is enabled:

- `F6`: pause/resume simulation
- `F7`: step one simulation tick
- `[` / `]`: zoom out/in

### Editor

- `Ctrl+S`: save
- `Tab`: toggle `Paint` / `Select`
- `[` / `]`: cycle the browsed tileset
- `Escape`: cancel editing, deselect, or confirm quit when dirty

## Verification

Useful commands during refactor work:

```text
.venv/Scripts/python -m unittest discover -s tests -v
.venv/Scripts/python run_game.py --project projects/test_project title_screen --headless --max-frames 2
.venv/Scripts/python run_game.py --project projects/test_project village_square --headless --max-frames 2
.venv/Scripts/python run_game.py --project projects/test_project village_house --headless --max-frames 2
```
