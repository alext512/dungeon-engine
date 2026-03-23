# Project Status

## Current State

This folder contains the active Python project built with `pygame-ce`.

Run it with:

- `Run_Game.cmd` for play mode
- `Run_Editor.cmd` for the standalone editor
- or `.venv/Scripts/python run_game.py`
- or `.venv/Scripts/python run_editor.py`

The project now uses standalone game/editor applications plus `project.json` manifests for asset, area, entity, and font search paths.
The launchers remember the last selected project and the last area opened in game/editor mode.
The repo now includes a versioned sample project at `projects/test_project/`, but the engine remains independent from any specific project folder.

## Fast Catch-Up

If you only need the current reality quickly:

- engine code is under `dungeon_engine/`
- sample content is under `projects/test_project/`
- gameplay behavior is mostly authored in JSON commands and entity events
- the current sample room is `projects/test_project/areas/test_room.json`
- shared project values are in `projects/test_project/variables.json`
- player movement is authored in `projects/test_project/entities/player.json`
- dialogue text lives in `projects/test_project/dialogues/`
- reusable command libraries live in `projects/test_project/commands/`
- `run_dialogue` is still available as a text-only helper, but the sample project now drives dialogue through a focused `dialogue_ui` entity plus text-session commands
- dialogue panels, portraits, and choice lists are command-authored screen elements
- sample dialogue choices, long-choice marquee behavior, and choice scrolling now live in `projects/test_project/entities/dialogue_ui.json`
- the main runtime log is `logs/error.log`

## Implemented

- project scaffold with `pyproject.toml`
- runnable `pygame-ce` game and editor launchers
- project manifest support via external `project.json` files
- project-relative search paths for areas, entities, and assets
- JSON area loading
- camera and basic sprite/tile rendering
- generated test asset sheets for tiles and sprites
- layered tilemaps with separate walkability cell flags
- reusable entity templates with per-instance parameters
- template entity saves that keep generated command data in the template instead of writing resolved `interact_commands` into room JSON
- pixel-art rendering mode with snapped camera/draw positions
- standalone resizable editor with tileset browser, map canvas, and inspector panels
- paint/select editor workflow
- recursive PNG tileset discovery across active project asset paths
- automatic room tileset registration when painting from a newly selected tileset
- configurable bitmap-font system with JSON font definitions
- generic screen-space element layer for images, text, and simple frame animation
- first blocking screen-space dialogue-style interaction via a sign entity
- reusable text-only `run_dialogue` command with automatic text wrapping and pagination by pixel width + max lines
- project-level dialogue assets loaded from `dialogues/` via dialogue ids
- command-authored dialogue layouts that use screen-space images for panels and portraits
- command-authored dialogue choices rendered as normal screen text and driven through a reusable dialogue UI entity
- command runner foundation
- command-driven grid movement
- fixed-timestep simulation for movement/command playback
- wall collision
- pushable block behavior
- event-driven push delegation for pushable objects
- held movement that starts the next step as soon as the previous move fully finishes
- facing-based interaction input
- interactable entity command chains
- first lever/gate example
- simple player sprite animation while moving
- UI/editor text rendered through the custom `pixelbet` bitmap font atlas
- persistent rotating error log in `logs/error.log`
- reusable project-level named command libraries loaded from `command_paths`
- startup validation for named command libraries (duplicate ids, malformed files, and literal missing references)
- startup-built in-memory named-command database reused by runtime `run_named_command` lookups
- variable system with `set_var`, `increment_var`, and `check_var` commands (entity and world scopes)
- `check_var` supports conditional branching with `then`/`else` command lists
- world-level variables storage (serialized in area JSON)
- `lever_toggle` entity template demonstrating toggle behavior via variables
- persistent save-slot state layered over authored room data
- in-memory live persistent state that tracks gameplay changes without auto-writing a save file
- stable `area_id` support for room-level persistence
- persistent command updates for entity fields and variables
- generic `set_entity_field` command for runtime-safe entity field mutation
- text-session primitives for UI-driven paged and marquee text flow
- transient and persistent room reset commands
- authored entity tags for grouping and reset targeting

## Current Test Room

The starter room currently includes:

- player
- one pushable block
- one toggle lever (can be toggled on and off via variables)
- one readable sign that opens a simple dialogue panel
- one NPC with portrait-backed dialogue and a choice-based follow-up conversation
- one bard NPC with a portrait-backed dialogue menu that demonstrates more than three choices plus scrolling and marquee choice text
- the sign now reads its text from a dialogue asset instead of embedding the text inline
- one gate
- a wall tile with a painting overlay tile on top of it

Expected behavior:

- move with arrows or `WASD`
- interact with `Space`
- face the lever and press `Space` to toggle the gate open/closed
- face the sign and press `Space` to open a simple dialogue panel, then press `Space` again to close it
- face the NPC and press `Space` to open a portrait-backed dialogue, then use `Up` / `Down` and `Space` to choose a reply
- face the bard and press `Space` to open a longer portrait-backed menu; more-choice indicators appear when the list scrolls past the first three rows
- dialogue choice navigation now moves once per keypress; it does not keep scrolling while a direction is held
- highlighted long choice text now scrolls sideways and freezes at the end until you move the selection away
- long sign dialogue now auto-splits into multiple pages when it exceeds the configured dialogue line count
- live lever/gate state persists for the current play session in memory
- if `saves/slot_1.json` exists when play starts, its overrides are loaded on top of the room JSON
- press `F5` in play mode to write the current persistent state to `saves/slot_1.json`
- press `F9` in play mode to reload persistent overrides from `saves/slot_1.json`
- if the active project's `project.json` enables `debug_inspection_enabled`, `F6` pauses/resumes simulation, `F7` advances one simulation tick, and `[` / `]` zoom the output window out or in
- the player uses a tiny 2-frame walk animation while moving
- player walking now carries a simple alternating walk phase across successful moves
- the room uses layered tiles instead of a single character grid

## Editor Controls

- `Ctrl+S`: save
- `Tab`: toggle `Paint` / `Select` mode
- `[` / `]`: cycle the currently browsed tileset
- `Escape`: cancel move/text edit, deselect, or confirm quit when dirty
- `Delete`: remove the selected entity in `Select` mode
- Arrow keys: pan the camera
- Middle click + drag on the map: pan the camera
- Mouse wheel over the left panel: scroll the tileset view
- Mouse wheel over the map: pan vertically
- Left click in `Paint` mode on the map: paint the selected tile or apply the selected walkability brush
- Right click in `Paint` mode on the map: erase tile data or apply the inverse walkability brush
- Drag with left/right mouse in `Paint` mode: paint continuously
- Left panel top arrows: cycle available tilesets
- Left panel tileset grid: pick a tile frame to paint with
- Left panel `Walkable` / `Blocked`: switch to walkability painting
- Toolbar buttons: `Save`, `Reload`, `Paint`, `Select`
- Right panel in `Paint` mode: select layers, rename the selected layer, toggle above/below-entity draw order, add/remove layers
- Left click in `Select` mode on the map: select a cell
- Right panel in `Select` mode: select, reorder, move, remove, or add entities on the selected cell
- Right panel property rows in `Select` mode: click booleans to toggle, facing to cycle, and parameter rows to start text editing
- `Enter` while editing a layer name or parameter: confirm
- `Escape` while editing a layer name or parameter: cancel

## Editor UX Notes

- The editor is now a standalone native-resolution app, not an in-game overlay.
- The left panel shows the full currently selected tileset and walkability brushes.
- The center pane is a pannable map view with tile preview, walkability overlay, and selection feedback.
- The right panel changes by mode: paint/layer tools in `Paint`, entity stack and property inspection in `Select`.
- Tile selection is thumbnail-based rather than label-based.
- Middle-mouse dragging pans a free editor camera, so panning remains useful even when the room is smaller than the viewport.
- Visual tile layers remain separate from walkability flags, and entities stay independent from both.
- The editor no longer assumes only `ground / structure / overlay`; layers are a general ordered list and can now be added, renamed, or removed.
- Stacked entities are shown in the right panel with persistent `stack_order` so their order can be saved, reloaded, and rearranged.
- Hovering a tile previews the currently selected tile before you click.
- If you click without a visible change, the status line explains why, for example when a cell already has the selected tile.
- The editor can browse PNG assets recursively from the active project's asset paths, but it does not yet have a built-in "import external PNG into project" workflow.

## Important Notes

- Movement is command-driven. Input requests commands rather than mutating position directly.
- Player-style stepping now follows a more old-project-like flow: face, probe ahead, delegate push behavior to the object in front when appropriate, then re-probe before walking.
- Interaction is now also command-driven. The player triggers a top-level interact command, which resolves a target and runs that target's command chain.
- Levels now define tiles through tile-definition data rather than hardcoded wall logic.
- Visual tile layers and walkability are now separate concepts.
- Reusable object definitions live in the active project's `entities/` folders.
- For template entities, room JSON should normally store authored inputs such as `template`, `parameters`, and simple explicit overrides. Generated command chains are rebuilt from the template at load time instead of being written back during a normal save.
- Fonts now live in the active project's `assets/fonts/` folder as named JSON definitions plus atlas PNGs.
- The current UI font is `pixelbet`, which auto-measures per-glyph widths from the atlas so narrow letters do not consume the same width as wide ones.
- Future systems like dialogue can choose fonts by `font_id` through the shared text renderer instead of using hardcoded font objects.
- Screen-space content can now be created through commands instead of being baked directly into the renderer, which is the intended foundation for dialogue panels, portraits, title cards, and later menu-like overlays.
- Dialogue can now be authored as a single long text block and automatically paginated using measured font widths plus the project's configured `dialogue.max_lines`.
- `run_dialogue` is intentionally text-only; panel images, portraits, and choice lists are authored separately through normal commands.
- The sample NPC dialogue flow is handled in project JSON through a hidden `dialogue_ui` entity plus text-session commands, not through a baked engine choice-menu primitive.
- Active input now resolves from the focused entity's `input_map` first, with project-level `input_events` only serving as fallback defaults.
- Runtime focus handoff now supports `push_active_entity` / `pop_active_entity`, so temporary UI/controller entities can take input and return it to the previous active entity.
- The current assets are intentionally simple generated test art, not final art.
- Pixel-perfect behavior is currently handled as a renderer/camera policy, not a level-data rule.
- The game and editor are separate applications now, but they still share the same area/entity JSON model.
- Play mode layers any existing save-slot state on top of the authored room clone without modifying authored room data.
- The live persistent layer is kept in memory during play; it is only written to disk when you press `F5`.
- Runtime interaction now resolves the topmost enabled entity on a tile based on the current stack order, not just insertion order.
- Named-command library errors such as malformed files, duplicate command ids, or missing literal `run_named_command` targets are now validated at project startup; launch is blocked, the full report is written to `logs/error.log`, and runtime command failures still show a short in-game hint to check the log.
- Named commands are now indexed and loaded into memory at startup, so runtime command execution does not rescan project command folders while the game is already running.
- `project.json` controls where the active project looks for areas, entities, assets, and fonts.
- `project.json` can also define `dialogue_paths`, so reusable dialogue content can live separately from entity/event files.
- `projects/test_project/` is now the repo-local versioned sample project; it is not bundled engine data, and other projects can still live anywhere else as long as they provide a `project.json`.
- Uncaught runtime errors and Tk/file-picker callback failures are logged to `logs/error.log`.
- Entity parameter editing is still minimal. Template placement works, but rich per-instance parameter editing will need a follow-up pass.
- The current movement/render feel still needs a dedicated revisit: inspect pixel-perfect output on real hardware again, tighten any remaining pacing/camera issues, and keep the debug inspection tools around until that pass is complete.

## Suggested Next Steps

- add an editor-side tileset import flow for external PNGs
- expand dialogue choices into richer branching tools and editor-friendly authoring
- add inventory and usable-item commands
- improve the editor with parameter editing and room creation
- revisit movement/render feel and finish the pixel-perfect quality pass
