# Changelog

Reverse-chronological log of functionality changes. Each entry describes what was added or changed, not how.

---

## Primitive Command Cleanup

- Removed the broad variable primitives (`set_var`, `increment_var`, `set_var_length`, `append_to_var`, `pop_var`, `set_var_from_collection_item`, `check_var`) in favor of explicit world/entity forms
- Tightened strict entity-target mutation and input-routing primitives so they now require explicit ids or resolved `$..._id` tokens instead of raw symbolic `self` / `actor` / `caller` ids
- Tightened `set_camera_follow_entity` the same way, so camera follow targeting now matches the strict primitive model
- Removed the broad `set_var_from_camera` helper in favor of explicit `set_world_var_from_camera` and `set_entity_var_from_camera`
- Added startup validation and runtime fail-fast errors for the removed broad forms and for raw symbolic ids on strict primitives
- Updated the sample content, tests, and active docs to describe the stricter primitive-command model

## Entity-Owned Dialogue State

- Removed manifest-level `dialogue_paths` and the old dialogue-definition lookup layer; reusable dialogue/menu content is now just ordinary project-relative JSON loaded by commands
- Removed the engine-owned dialogue session handle and text-session manager from the active runtime model
- Made legacy dialogue/session commands such as `start_dialogue_session`, `dialogue_advance`, `dialogue_confirm_choice`, `prepare_text_session`, and `close_dialogue` fail fast during validation and at runtime
- Added generic controller-friendly helpers such as `set_var_from_json_file`, `set_var_from_wrapped_lines`, `set_var_from_text_window`, `append_to_var`, `pop_var`, `run_commands_for_collection`, and `wait_seconds`
- Migrated the sample `dialogue_controller` to own its dialogue/menu state, nested `dialogue_state_stack`, and UI redraw flow through named commands instead of engine-owned session state
- Updated the sample project, tests, and active docs to describe controller-owned dialogue/menu flow plus ordinary JSON dialogue data

## Transfer-Aware Area Flow + Explicit Camera State

- Added authored area `entry_points` and transfer-aware `change_area` / `new_game` payloads so projects can move one or more live entities into named destinations instead of relying on player-specific area assumptions
- Added traveler persistence so transferred entities keep one live session identity, suppress their authored origin placeholder while away, and restore correctly across save/load and room re-entry
- Removed the runtime `input_targets` fallback to `player_id`; omitted actions now stay unrouted unless project defaults, area overrides, or runtime commands assign them
- Removed authored area `player_id` from the active schema and made old uses fail fast during validation
- Added explicit camera runtime state with authored area defaults, follow offsets, bounds rectangles, deadzones, query support through `set_var_from_camera`, and save/load restore of the current camera
- Removed the legacy player-specific camera follow command so authored camera control now uses explicit entity or input-target references
- Fixed routed controller input during active dialogue/menu sessions so opted-in input events execute alongside the active handle instead of deadlocking behind it
- Replaced leftover sample-project `if_var` usage with `check_var` and made `if_var` fail fast during startup validation
- Updated the sample project doors, startup flow, and showcase areas to use entry markers, actor transfer, and explicit camera follow requests

## Input Route Stack + Modal Controller Cleanup

- Added engine-managed `push_input_routes` and `pop_input_routes` so modal controllers can borrow and restore exact per-action input routing without a single active-entity concept
- Changed project-level `input_targets` handling to stay partial, so omitted actions stay unrouted unless project defaults, area overrides, or runtime commands assign them
- Added a project-level `pause_controller` sample entity and moved `Escape` handling off the player template
- Reworked the sample title menu, pause menu, and save prompt so post-close actions run from `dialogue_on_end` after input routes are restored
- Kept current logical input targets in save/load, while intentionally leaving the transient route stack out of save data

## Strict Visuals + Global Dialogue Controller Refactor

- Replaced legacy single-`sprite` entity authoring with the strict `visuals` array model in runtime validation and sample content
- Added explicit entity `space` (`world` or `screen`) and `scope` (`area` or `global`) to the active data model
- Added `project.json`-level `global_entities` and moved the sample dialogue controller to that project-owned global entity layer
- Removed authored `run_dialogue` usage from the sample project and made the command name fail fast so old content does not silently keep working
- Standardized controller-driven dialogue flow around `start_dialogue_session` plus `dialogue_advance`, `dialogue_move_selection`, `dialogue_confirm_choice`, and `dialogue_cancel`
- Added caller-facing runtime references `self`, `actor`, and `caller`, plus `$self_id`, `$actor_id`, and `$caller_id`
- Reworked the sample title screen, pause menu, save prompt, signs, and lever puzzle to route through the shared `dialogue_controller`
- Kept area-level `enter_commands` as the way authored areas trigger startup behavior such as the title menu

## Title Screen, Save Slots, and Connected Showcase Areas

- Added generic `change_area`, `new_game`, `save_game`, `load_game`, and `quit_game` primitives so project JSON can drive area travel, fresh-session resets, save/load, and quitting without hardcoded project logic
- Moved save/load to project-scoped JSON slots rooted in each project's `saves/` folder and removed the old `F5` / `F9` debug-only save flow
- Updated save data to record the current area, current logical input-target routing, persistent per-area diffs, and an exact diff for the currently loaded area
- Added one-time restore of the saved current area so temporary room changes come back on load but still disappear after the player leaves that room again
- Added support for persistent spawned entities and persistent deletion in area-diff save data
- Reworked the sample project to start in a title-screen area with authored `New Game`, `Load`, and `Exit` menu options
- Added a connected tilemap showcase slice with `village_square` and `village_house`, including a save point, a persistent lever/gate puzzle, and a non-persistent push block example

## Named Command Startup Database

- Build a full in-memory named-command database per project at startup instead of rediscovering command files during gameplay
- Reuse that startup-built database for runtime `run_named_command` lookups so frequent movement/interaction command chains no longer rescan `named_command_paths`
- Keep startup validation aligned with the same database-building path so malformed files, duplicate ids, and literal missing references are still caught before launch

## Dialogue UI Sample Refactor

- Replaced the test project's old `run_dialogue` + `dialogue_controller` sample flow with a focused `dialogue_ui` entity that owns page advancement, menu selection, and dialogue teardown
- Migrated the sample sign and blue-guide NPC onto the new text-session-driven dialogue flow
- Added a second sample NPC that demonstrates more than three choices, visible menu scrolling, and marquee-style long option text

## Input Routing Maps

- Added text-session primitives for UI entities: `prepare_text_session`, `read_text_session`, `advance_text_session`, and `reset_text_session`
- Added engine-managed page and marquee text processing so UI entities can own dialogue/choice flow while still using shared text-layout services
- Added generic `set_entity_field` support for safe runtime entity-field mutation, including focused input maps and the common visibility/solidity/color-style fields
- Collapsed the older field-specific setter commands onto the generic field-mutation path while keeping their command names available
- Added entity-owned `input_map` support so routed entities can decide which named events handle logical inputs
- Updated input dispatch to resolve each logical action through routed `input_targets`, while keeping project-level `input_events` as fallback defaults
- Authored the sample player and dialogue controller with explicit input maps to make control ownership visible in project content
- Added per-action input routing through project/area `input_targets` plus runtime `route_inputs_to_entity` / `set_input_target`

## Standalone Editor + Project Manifests

- Split the old combined workflow into standalone `run_game.py` and `run_editor.py` entry points plus `Run_Game.cmd` and `Run_Editor.cmd`
- Replaced the browser-window editor UI with the native-resolution standalone `editor_app.py` editor
- Added `project.json`-driven project contexts so areas, entities, and assets can be resolved from configurable search paths
- Updated asset loading and tileset discovery to work across the active project's asset roots

## Template Entity Save Hygiene

- Rebuild template instances in the editor after parameter edits so generated fields stay in sync with the current parameter values
- Stop serializing generated data such as resolved `interact_commands` back into room JSON for normal template entities
- Cleaned the starter room's stale lever override so the second lever again resolves its target gate from template parameters

## Manual Save Flow

- Changed play-mode persistence so live persistent changes stay in memory instead of auto-writing save data during gameplay
- This older milestone has since been superseded by the project-scoped menu/save-point save flow described above

## Persistence Foundation

- Added stable `area_id` support and a save-slot JSON format for persistent room overrides
- Added persistent runtime tracking for entity fields and variables without overwriting authored room data
- Added transient and persistent room reset commands
- Added authored entity tags for future reset filtering and grouping
- Updated the toggle lever example so its gate/lever state persists across play re-entry

## Variables & Requirements

- Added `set_var`, `increment_var`, and `check_var` commands for entity and world scopes
- Added world-level variables storage (serialized in area JSON)
- `check_var` supports branching with `then`/`else` command lists
- Added `lever_toggle` entity template demonstrating toggle behavior via variables

## Editor Overhaul: GID-Based Tilemap

- Migrated from named string-based tile definitions to industry-standard GID-based tilemaps
- Editor tileset browsing now shows full clickable tileset frames
- Tilesets auto-added to area when a frame is selected from a new tileset
- Tileset cycling with `[`/`]` keyboard shortcuts
- Entity stack management in the editor UI

## Interaction Core (partial)

- Facing-based interaction input
- Interactable entity command chains (`interact_commands`)
- Lever/gate example using `set_visible`, `set_solid`, `set_enabled`, `set_color` commands
- Pushable block behavior via collision system
- Simple player visual animation while moving
- Held movement that chains steps seamlessly

## Early Editor

- Editor mode with document/playtest separation (F1 toggle)
- Tile painting, walkability editing, entity placement/removal
- Earlier browser-window-based editor for layers, palettes, and entity stack management
- Middle-mouse drag panning with free editor camera
- Hover preview of selected tile/entity before placement
- Save (Ctrl+S) and reload (R) support
- Configurable tile layers (add, rename, remove)
- Count badges for stacked entities

## Core Shell and Grid Room

- Project scaffold with `pyproject.toml` and `pygame-ce`
- JSON area loading with layered tilemaps and separate walkability flags
- Camera and pixel-art rendering with snapped positions
- Command runner foundation with command-driven grid movement
- Wall collision
- Reusable entity templates with per-instance `$variable` parameter substitution
- Configurable bitmap font system (`pixelbet`) with per-glyph width measurement
- Persistent rotating error log in `logs/error.log`
