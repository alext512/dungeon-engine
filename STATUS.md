# Project Status

## Current State

This folder contains the active Python project built with `pygame-ce`.

Run it with:

- `Run_Game.cmd` for play mode
- `Run_Editor.cmd` for the standalone editor
- or `.venv/Scripts/python run_game.py`
- or `.venv/Scripts/python run_editor.py`

The project uses standalone game/editor applications plus `project.json` manifests for asset, area, entity-template, named-command, and shared-variable lookup. Reusable dialogue/menu data is now just ordinary project-relative JSON loaded by commands. The repo includes a versioned sample project at `projects/test_project/`, but the engine remains independent from any specific project folder.

## Fast Catch-Up

If you only need the current reality quickly:

- engine code is under `dungeon_engine/`
- sample content is under `projects/test_project/`
- gameplay behavior is authored in JSON commands and entity events
- area, entity-template, and named-command ids are path-derived from project search roots
- entities now use a `visuals` array instead of a single `sprite` block
- entities also declare `space` (`world` or `screen`) and `scope` (`area` or `global`)
- project-level global entities are authored in `project.json` under `global_entities`
- input resolves per logical action through `input_targets`, then the routed entity's explicit `input_map`
- area changes can target authored `entry_points` and optionally transfer one or more live entities
- the runtime persists transferred travelers and the current camera state across save/load
- the sample project's shared dialogue UI is a global `dialogue_controller` entity from `entity_templates/dialogue_panel.json`
- the sample project's reusable dialogue/menu JSON lives in `projects/test_project/dialogues/`
- reusable named command libraries live in `projects/test_project/named_commands/`
- shared project values live in `projects/test_project/shared_variables.json`
- the startup area id is `title_screen`
- the first playable showcase area id is `village_square`
- the connected interior example area id is `village_house`
- the main runtime log is `logs/error.log`

## Implemented

- project scaffold with `pyproject.toml`
- runnable `pygame-ce` game and editor launchers
- project manifest support via external `project.json` files
- project-relative search paths for areas, entity templates, named commands, assets, and shared variables
- project-authored `global_entities`
- JSON area loading
- layered tilemaps with separate walkability cell flags
- reusable entity templates with per-instance parameters
- template entity saves that keep generated runtime data out of authored room JSON
- standalone resizable editor with tileset browser, map canvas, and inspector panels
- paint/select editor workflow
- recursive PNG tileset discovery across active project asset paths
- configurable bitmap-font system with JSON font definitions
- command runner foundation
- command-driven grid movement, interaction, and pushing
- fixed-timestep simulation for movement and command playback
- simple visual animation playback and movement-timed walk animation
- reusable project-level named command libraries loaded from `named_command_paths`
- startup validation for areas, entity templates, and named command libraries
- startup-built in-memory named-command database reused by runtime `run_named_command` lookups
- explicit variable primitives such as `set_world_var`, `set_entity_var`, `increment_world_var`, `increment_entity_var`, `check_world_var`, and `check_entity_var`
- runtime entity references through `self`, `actor`, `caller`, plus `$self_id`, `$actor_id`, and `$caller_id`
- generic `set_entity_field` command for safe runtime entity-field mutation, including nested visual paths such as `visuals.main.tint`
- per-action input routing through project/area `input_targets` plus runtime `set_input_target`, `route_inputs_to_entity`, `push_input_routes`, and `pop_input_routes`
- strict primitive entity-target commands across variables, input routing, camera follow/query, movement, and visual/animation control now require explicit ids or resolved `$..._id` tokens; raw symbolic `self` / `actor` / `caller` ids are rejected at startup validation and runtime
- controller-driven dialogue/menu flow with entity-owned state and stack snapshots on the controller entity
- generic JSON/text helpers such as `set_var_from_json_file`, `set_var_from_wrapped_lines`, `set_var_from_text_window`, `append_world_var`, `append_entity_var`, `pop_world_var`, and `pop_entity_var` for entity-authored dialogue logic
- reusable dialogue/menu data stored as ordinary JSON under the sample project's `dialogues/` folder
- transient and persistent room reset commands
- persistent save-slot state layered over authored room data
- generic `change_area`, `new_game`, `save_game`, `load_game`, and `quit_game` primitives
- authored area `entry_points` plus transfer-aware area changes and fresh-session starts
- traveler persistence for cross-area entities, including non-duplication on room re-entry
- explicit camera runtime state with follow entity/input-target modes, offsets, bounds, deadzones, and save/load restore
- explicit camera runtime tokens such as `$camera.x`, `$camera.follow_entity_id`, `$camera.bounds`, and `$camera.has_bounds`
- project-scoped JSON save slots rooted in each project's `saves/` folder
- persistent spawned-entity and persistent destruction support in save data

## Current Sample Project

The sample project currently includes:

- a title-screen startup area with a screen-space backdrop and an auto-opened controller-driven title menu
- a tilemap-based `village_square` outdoor area with a save point, a note sign, and a door into a house
- a connected tilemap-based `village_house` interior area with a persistent lever/gate puzzle
- one pushable block in the house that resets when you leave and re-enter
- global `dialogue_controller` and `pause_controller` entities authored in `project.json`
- ordinary JSON dialogue/menu data for title actions, save prompts, showcase notes, lever narration, and the in-level `Escape` menu

Expected behavior:

- move with arrows or `WASD`
- interact and advance dialogue with `Space` or `Enter`
- from the title screen, choose `New Game`, `Load Game`, or `Exit`
- in `village_square`, face the save point and press `Space` to open an authored save prompt
- face the house door and press `Space` to enter `village_house`
- in `village_house`, face the lever and press `Space` to toggle the gate open or closed
- leave and return to confirm the lever/gate state persisted
- push the house block, leave the house, and return to confirm the block reset to its authored position
- press `Escape` in a playable area to open the controller-driven pause menu with `Continue`, `Load`, and `Exit`

## Important Notes

- Movement is command-driven. Input requests events; it does not mutate positions directly.
- Interaction is also command-driven. The player triggers a top-level interact command, which resolves a target and runs that target's command chain.
- Entities now define persistent visuals through a `visuals` array. Legacy `sprite` blocks are rejected at load time.
- `space: "world"` entities use grid coordinates. `space: "screen"` entities use screen pixel coordinates and must not author `x` / `y`.
- `scope: "global"` entities are authored in `project.json` and installed into each runtime world as global entities.
- Dialogue is no longer a special engine-owned runtime session. Old commands such as `run_dialogue`, `start_dialogue_session`, `dialogue_advance`, and the old text-session commands now fail fast on purpose.
- The supported dialogue flow is: send an event to the controller entity, let controller-owned commands load ordinary JSON dialogue data, mutate controller variables, and redraw the UI.
- Nested dialogue/menu restore is split cleanly: the engine-owned input-route stack restores who receives input, and the controller-owned `dialogue_state_stack` restores which dialogue/menu state comes back on screen.
- Modal controllers should borrow and restore routes through `push_input_routes` / `pop_input_routes` instead of returning input through `actor`.
- The transient input-route stack is runtime-only and is intentionally not written into save files.
- Authored areas must not declare `player_id`; initial control and camera behavior now come from explicit `input_targets`, transition payloads, and area `camera` defaults.
- Save data stores the current area, the current logical input-target routing, the current camera state, traveler session state, persistent diffs for visited areas, and the full current diff of the active area at save time.

## Suggested Next Steps

- expand dialogue authoring with stronger editor-facing tooling
- add inventory and usable-item commands
- improve the editor's parameter editing and room-creation workflows
- revisit movement/render feel and finish the pixel-perfect quality pass
