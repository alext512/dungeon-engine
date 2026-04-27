# Changelog

Reverse-chronological log of functionality changes. Each entry describes what was added or changed, not how.

---

## Direct Input Routes

- Replaced authored input routing with `input_routes`, where each logical
  action maps directly to an `entity_id` and `command_id`
- Removed the authored `set_input_target` and `route_inputs_to_entity`
  command surface in favor of `set_input_route`
- Updated runtime persistence, sample content, editor command helpers, docs,
  and focused tests for direct entity-command routing

---

## Camera Command Cleanup

- Replaced the focused authored camera follow command with explicit
  `set_camera_follow_entity`, `set_camera_follow_input_target`, and
  `clear_camera_follow`
- Added `clear_camera_bounds` and `clear_camera_deadzone` so the focused camera
  commands can clear their own state instead of relying on `set_camera_policy`
- Renamed the umbrella patch command from `set_camera_state` to
  `set_camera_policy`, keeping the same atomic `follow` / `bounds` /
  `deadzone` patch semantics with `null` sections clearing those parts of the
  policy
- Updated the editor, docs, focused tests, and helper UIs to use the new camera
  command surface

---

## Grid Step Command Rename

- Renamed the built-in authored command `move_in_direction` to
  `step_in_direction` so the JSON contract reads more clearly as one
  discrete grid/tile step
- Updated the live runtime registration, active docs, sample project command
  content, and focused movement tests to use `step_in_direction`

---

## Runtime Context Ref Cleanup

- Stopped auto-injecting engine-owned `instigator` / `caller` refs into
  `entity_refs`; authored `entity_refs` now only represent refs explicitly
  passed by JSON
- Added/standardized direct `instigator_id` runtime context across movement,
  occupancy, interaction, dialogue, inventory item use, and area-transition
  flows
- Updated sample content, docs, and focused tests to use direct
  `$instigator_id` where engine-owned acting-entity context is intended, while
  keeping explicit `entity_refs` examples for author-passed cross-entity refs

---

## Inline Dialogue Definitions

- Added `dialogue_definition` as a first-class inline source for
  `open_dialogue_session`, alongside file-backed `dialogue_path`
- Added deferred command-audit handling for inline dialogue definitions so
  segment and option commands stay raw until the dialogue runtime executes them
- Added `dialogue_definition` as a typed template parameter spec for embedded
  entity-owned dialogue data

---

## Facing-Aware Default Visual State

- Added optional visual `default_animation_by_facing` mappings so entities can
  explicitly pick different default clips for `up`, `down`, `left`, and
  `right` facings
- Updated entity construction and transfer-reset logic to restore visuals from
  the entity's current facing-aware default state instead of always falling
  back to one hardcoded default clip
- Updated the sample project player template to use facing-aware idle defaults

---

## Area Transition Traveler Fixes

- Added an optional `allowed_instigator_kinds` guard to `change_area` so
  occupancy-triggered active scene transitions can be limited to selected
  entity kinds, and standard grid movement treats those trigger cells as closed
  to rejected entity kinds
- Updated the sample area-transition template to be player-gated, transfer the
  entering entity, and keep the camera following that transferred entity
- Fixed returning travelers so they replace their authored origin placeholder
  instead of colliding with a duplicate entity id

---

## External Editor Dependency And Preview Catch-Up

- Added the editor's `json5` dependency to its own requirements file and
  launcher dependency check so a fresh or existing editor venv can recover
  before startup
- Added a visible canvas-tools strip for `Paint`, `Entity Select`,
  `Tile Select`, and `Cell Flags`
- Added an Area Tools `Cell Flags` brush panel so authors can choose which
  blocked or custom cell-flag operation canvas clicks paint
- Added an Area Tools `Entities` list for selecting active-area entity
  instances, including hard-to-click screen-space entities
- Updated external editor template previews, brush previews, and canvas sprites
  to honor visual `default_animation` frames and clip-level `flip_x`
- Flattened the external editor template surface so `Raw JSON` sits beside
  `Visuals` and `Persistence` instead of behind a second top-level tab
- Ensured new editor-created area JSON data files get the standard file-level
  notes header, while existing files are left alone
- Added editor tests covering default-animation preview selection and
  clip-only visual previews

## Named Visual Animation Clips

- Added named per-visual animation clips with `default_animation`,
  `animations`, clip-level `flip_x`, and clip-local `preserve_phase`
- Changed entity `play_animation` to call named clips with `animation`,
  optional `frame_count`, optional `duration_ticks`, and optional `wait`
  instead of accepting raw `frame_sequence` command payloads
- Added exact simulation-tick animation timing so selected sprite frames are
  distributed across `duration_ticks`
- Updated the sample project player to use one `body` visual with explicit
  `walk_*` and `idle_*` clips, including left/right clips instead of a shared
  `side` visual
- Migrated sample project levers, gates, falling objects, and hole-fill
  animations to named clips
- Updated authoring/reference docs and tests for the named-clip animation API

## Arithmetic Value Sources

- Replaced the older `$sum` / `$product` value-source names with clearer
  `$add` / `$multiply` names, without keeping legacy aliases
- Added `$subtract` and `$divide` value sources for explicit authored numeric
  math such as gameplay-tick animation timing
- Changed unknown single-key `$...` value-source objects to fail immediately
  instead of passing through as ordinary dictionaries
- Updated authoring/reference docs and runtime tests for the new arithmetic
  value-source surface

## Command Runner Settling And Tick Phases

- Added guarded eager command settling so ready command chains continue in the
  same simulation tick until they reach a real wait
- Added project-level `command_runtime` safety/diagnostic settings for settle
  pass limits, immediate-command limits, usage-peak logging, and warning ratio
- Reworked the play-mode simulation tick into explicit settle, simulation,
  input, presentation, and scene-boundary phases
- Changed scene-changing commands such as `change_area`, `new_game`, and
  `load_game` to cancel old-scene command work instead of letting later
  commands in the old scene continue
- Added focused tests for zero-dt settling, spawned-flow eagerness, safety-fuse
  overflow, and scene-boundary cancellation
- Updated authoring and reference docs to explain eager command timing,
  `wait=true` / `wait=false`, `spawn_flow`, scene boundaries, and
  `command_runtime`

## Command Authoring Shorthand And Sequence Naming

- Renamed the command-list orchestration command from `run_commands` to
  `run_sequence` without keeping a legacy alias
- Added entity-command array shorthand so common named commands can omit the
  wrapper object and `enabled: true`
- Kept the long entity-command object form for disabled commands and future
  named-command metadata
- Updated command docs and validation around `commands: [...]` as the default
  sequential body shape

## Render Defaults Cleanup

- Updated area/entity serialization so default entity render fields are omitted
  from authored JSON instead of repeated on every instance
- Updated sample project templates and area content to rely on render defaults
  where appropriate
- Updated docs to clarify the render-order defaults and when explicit
  `render_order`, `y_sort`, `sort_y_offset`, and `stack_order` are useful

## Area Start UI + Template Parameter Cleanup

- Added a tabbed right-side area workspace in the external editor so `Layers`
  stays focused and area-enter behavior now has its own `Area Start` surface
- Added `Area Start` helper insertions for common `enter_commands` such as
  routing inputs, running one entity command, opening dialogue, setting camera
  follow, and starting music
- Fixed the `set_camera_follow` helper to author the real structured `follow`
  payload instead of an invalid shorthand field
- Moved static configuration on `new_project` transition, button, lever, gate,
  counter-target, and hole templates from runtime `variables` into real
  template `parameters` with authored defaults
- Updated the starter transition instances to override destination data through
  instance `parameters`, which now surfaces those fields properly in the entity
  instance editor
- Taught the editor to show template-authored default parameter values as
  placeholders, while avoiding misleading project-command pickers for
  entity-command id parameters

## Command Authoring Validation

- Added startup validation for known command-bearing JSON surfaces such as
  project commands, entity commands, area `enter_commands`, item
  `use_commands`, and dialogue inline command lists
- Strict primitive commands now fail fast on unknown top-level authored keys,
  which helps catch likely JSON typos before launch
- Mixed flow/helper commands such as `run_sequence`, `run_parallel`,
  `spawn_flow`, `run_entity_command`, `run_project_command`, and `if` remain
  intentionally permissive for caller-supplied runtime params
- Encoded runner-level authored fields such as `value_mode: "raw"` into the
  command registration metadata so validation matches the active runtime
  contract
- Moved the `$json_file` cache from process-global state onto the live runtime
  command context, so repeated reads stay cached during one active runtime but
  rebuild cleanly after area changes, `new_game`, and `load_game`

## Editor Workflow Catch-Up

- Added destination-marker-based area transitions through
  `destination_entity_id` on `change_area` / `new_game`, so transferred entities
  can now land on authored marker entities instead of only named `entry_points`
- Added `new_project` sample transition templates and marker entities
  (`area_transition` and `area_transition_target`) to demonstrate the newer flow
- Added a deprecation-planning note for eventually phasing out `entry_points` as
  the preferred authoring model while keeping compatibility for existing content
- Expanded the external editor beyond the earlier area-only slice with
  structured project-level tabs for `project.json`, `shared_variables.json`,
  items, and `global_entities`, while keeping guarded raw JSON fallbacks
- Added project-wide id validation and safer id generation so editor-authored
  entity ids match the runtime's stricter uniqueness rules
- Added reference-aware `Rename/Move...` workflows for areas, templates, items,
  dialogues, commands, assets, and global-entity ids
- Added delete workflows with usage previews for the same file-backed content
  plus global entities, while intentionally leaving broken references unchanged
  after confirmed deletion
- Added visible folder management in the browser tabs, including `New Folder...`,
  `Rename/Move Folder...`, and deletion of completely empty folders
- Reworked the left browser into a custom two-row workspace tab surface and
  improved tab overflow behavior for the editor's focused tab widgets
- Removed the fake `Entities` row from the Layers panel, moved entity visibility
  to `View > Show Entities`, and added real tile-layer add/rename/delete/reorder
  workflows
- Added a dedicated `Tile Select` tool for active-layer rectangle selection plus
  clear/delete, `Ctrl+C`, `Ctrl+X`, and `Ctrl+V`
- Added multi-tile tileset selection so dragged rectangles in the tileset
  browser now paint as stamp brushes on the active layer
- Added `Duplicate Area...` with `Full Copy` and `Layout Copy` modes so authors
  can clone a room either with remapped entity instances or as a stripped
  tilemap/layering shell
- Tightened startup validation so statically resolvable broken `dialogue_path`
  and asset-path references now fail before launch instead of slipping into play
  until first use
- Removed the top-level area `name` field from the active contract; area identity
  is now file/id-only, `$area.name` is gone, and the runtime/editor now reject
  authored area files that still try to declare a separate display-name field

## Inventory UI V1

- Added the first engine-owned inventory session runtime with modal browsing,
  snapped list scrolling, a bottom detail panel, and a small `Use / Cancel`
  popup
- Added `open_inventory_session` and `close_inventory_session` builtins
- Added inventory-key routing (`I`) plus modal input blocking so open dialogue
  and inventory sessions prevent world input from leaking through
- Added optional item `portrait` support alongside existing `icon` support
- Expanded `projects/physics_contract_demo` with inventory UI presets, an
  inventory shortcut, a pause menu path to inventory, and item metadata for the
  new browser
- Added focused tests for inventory UI empty state, direct item use,
  non-usable-item feedback, item portraits, and the new inventory input path

## Inventory V1

- Added `item_paths` plus path-derived reusable item ids such as `items/light_orb`
- Added item-definition loading, validation, and startup validation for `items/*.json`
- Added entity-owned inventory state with stack-based persistence and serialization
- Added inventory builtins: `add_inventory_item`, `remove_inventory_item`,
  `use_inventory_item`, and `set_inventory_max_stacks`
- Added inventory value sources: `$inventory_item_count` and `$inventory_has_item`
- Added focused runtime tests for item ids, inventory parsing, add/remove modes,
  item use, and inventory value-source behavior
- Expanded `projects/physics_contract_demo` to show the new contract through an
  auto-pickup item, an NPC gift, a key-locked door, and direct consumable item use

## Unified Render Ordering

- Replaced the old tile-layer `draw_above_entities` split with a unified runtime render model shared by tile layers and entities
- Added authored `render_order`, `y_sort`, `sort_y_offset`, and `stack_order` support for tile layers
- Added authored `render_order`, `y_sort`, and `sort_y_offset` support for entities
- Changed world rendering so non-y-sorted tile layers, y-sorted tile cells, and world entities can interleave in one sort space
- Updated persistence, serialization, mutation commands, tests, and active docs to write and describe the new layering model

## Camera API Cleanup

- Replaced the old split camera-follow commands with structured `set_camera_follow` and `set_camera_state`
- Added `push_camera_state` / `pop_camera_state` so cutscenes and temporary camera overrides can restore the previous camera policy cleanly
- Renamed authored camera bounds to `set_camera_bounds` and made camera coordinate spaces explicit with `world_pixel`, `world_grid`, `viewport_pixel`, and `viewport_grid`
- Updated `change_area`, `new_game`, and area `camera` defaults to use structured `camera_follow` / `follow` payloads instead of split camera-follow fields
- Updated camera runtime tokens to expose structured `$camera.follow` state instead of separate top-level follow fields
- Removed the old camera follow / clear / bounds-clear surface without compatibility aliases
- Updated the sample project, active tests, and docs to match the cleaned camera contract

## Current-Area Naming + Cross-Area State APIs

- Renamed the authored `world`-variable family to `current_area` so the JSON surface now matches the real runtime meaning of those values
- Renamed the runtime token family from `$world...` to `$current_area...`
- Added first-pass cross-area persistent state commands `set_area_var`, `set_area_entity_var`, and `set_area_entity_field`
- Added `$area_entity_ref` for explicit area-id/entity-id reads against area-owned authored state plus that area's persistent overrides
- Kept first-pass cross-area reads intentionally simple by excluding globals and travelers from `$area_entity_ref`
- Updated active tests and docs to describe the current-area naming and the new cross-area state surface

## Primitive Command Cleanup

- Reworked command scheduling so top-level flows now run independently by default instead of through one privileged main lane plus detached/background exceptions
- Added explicit composition commands `run_parallel` and `spawn_flow`, while `run_sequence` now names the ordered composition path directly
- Removed most historical removed-command / removed-field startup blacklists so validation now focuses on current structural invariants instead of memorializing obsolete authoring forms
- Removed generic command-level `on_start` / `on_end` wrapper syntax from the active runtime model in favor of explicit `run_sequence`, `run_parallel`, and `spawn_flow` composition
- Reworked the sample `walk_one_tile` command to use explicit sequencing instead of hidden lifecycle wrappers
- Tightened validation/runtime so old wrapper syntax now fails fast while dialogue hook payload data such as `segment_hooks[].on_end` continues to work as ordinary controller-owned data
- Changed primitive command execution so strict primitive families now receive only the engine services named in their Python signatures instead of the full runtime service bag
- Added generic tile-query value sources `"$entities_at"` and `"$entity_at"` that return plain entity refs for explicit spatial authoring
- Removed `run_facing_event` from the active runtime surface and migrated the sample push path to explicit query/result-driven `run_event`
- Added generic `"$entity_ref"` and `"$sum"` value sources so authored logic can read runtime tile/facing state and compute explicit target coordinates
- Removed `interact_facing` from the active runtime surface and migrated the sample player interaction path to explicit coordinate math plus `"$entity_at"` and `run_event`
- Removed the play-mode `Escape -> quit` fallback so `Escape` is now only the routed logical `menu` action
- Added explicit debug runtime commands for simulation pause, single-step, and zoom, and routed the sample project's debug keys through a normal global `debug_controller`
- Removed `set_var_from_json_file`, `set_var_from_wrapped_lines`, and `set_var_from_text_window` in favor of explicit variable commands with structured value sources such as `{"$json_file": ...}`, `{"$wrapped_lines": {...}}`, and `{"$text_window": {...}}`
- Removed the project-level `input_events` fallback mapping and `set_input_event_name`, so routed entities now fully own input meaning through explicit `input_map` entries
- Removed the broad variable primitives (`set_var`, `increment_var`, `set_var_length`, `append_to_var`, `pop_var`, `set_var_from_collection_item`, `check_var`) in favor of explicit world/entity forms
- Tightened strict entity-target mutation and input-routing primitives so they now require explicit ids or resolved `$..._id` tokens instead of raw symbolic `self` / `actor` / `caller` ids
- Tightened `set_camera_follow_entity` the same way, so camera follow targeting now matches the strict primitive model
- Tightened strict visual/animation primitives such as `set_facing`, `play_animation`, `wait_for_animation`, `stop_animation`, `set_visual_frame`, and `set_visual_flip_x` so they now follow the same explicit-id rule
- Tightened strict movement primitives such as `move_entity_one_tile`, `move_entity`, `teleport_entity`, and `wait_for_move` so they now follow the same explicit-id rule
- Removed the broad `set_var_from_camera` helper and the transitional `set_world_var_from_camera` / `set_entity_var_from_camera` replacements in favor of runtime tokens like `$camera.x`
- Added startup validation and runtime fail-fast errors for the removed broad forms and for raw symbolic ids on strict primitives
- Updated the sample content, tests, and active docs to describe the stricter primitive-command model

## Entity-Owned Dialogue State

- Removed manifest-level `dialogue_paths` and the old dialogue-definition lookup layer; reusable dialogue/menu content is now just ordinary project-relative JSON loaded by commands
- Removed the engine-owned dialogue session handle and text-session manager from the active runtime model
- Made legacy dialogue/session commands such as `start_dialogue_session`, `dialogue_advance`, `dialogue_confirm_choice`, `prepare_text_session`, and `close_dialogue` fail fast during validation and at runtime
- Added generic controller-friendly helpers such as `set_var_from_json_file`, `set_var_from_wrapped_lines`, `set_var_from_text_window`, `append_to_var`, `pop_var`, `run_commands_for_collection`, and `wait_seconds`
- Migrated the sample `dialogue_controller` to own its dialogue/menu state, nested `dialogue_state_stack`, and UI redraw flow through project commands instead of engine-owned session state
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

## Project Command Startup Database

- Build a full in-memory project command database per project at startup instead of rediscovering command files during gameplay
- Reuse that startup-built database for runtime `run_command` lookups so frequent movement/interaction command chains no longer rescan `command_paths`
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

