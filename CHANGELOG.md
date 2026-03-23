# Changelog

Reverse-chronological log of functionality changes. Each entry describes what was added or changed, not how.

---

## Named Command Startup Database

- Build a full in-memory named-command database per project at startup instead of rediscovering command files during gameplay
- Reuse that startup-built database for runtime `run_named_command` lookups so frequent movement/interaction command chains no longer rescan `command_paths`
- Keep startup validation aligned with the same database-building path so malformed files, duplicate ids, and literal missing references are still caught before launch

## Dialogue UI Sample Refactor

- Replaced the test project's old `run_dialogue` + `dialogue_controller` sample flow with a focused `dialogue_ui` entity that owns page advancement, menu selection, and dialogue teardown
- Migrated the sample sign and blue-guide NPC onto the new text-session-driven dialogue flow
- Added a second sample NPC that demonstrates more than three choices, visible menu scrolling, and marquee-style long option text

## Active Entity Input Maps

- Added text-session primitives for UI entities: `prepare_text_session`, `read_text_session`, `advance_text_session`, and `reset_text_session`
- Added engine-managed page and marquee text processing so UI entities can own dialogue/choice flow while still using shared text-layout services
- Added generic `set_entity_field` support for safe runtime entity-field mutation, including focused input maps and the common visibility/solidity/color-style fields
- Collapsed the older field-specific setter commands onto the generic field-mutation path while keeping their command names available
- Added entity-owned `input_map` support so the focused entity can decide which named events handle logical inputs
- Updated input dispatch to resolve the active entity's mapping first, while keeping project-level `input_events` as fallback defaults
- Authored the sample player and dialogue controller with explicit input maps to make control ownership visible in project content
- Added `push_active_entity` / `pop_active_entity` commands plus a runtime active-entity stack for temporary UI/controller focus handoff

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

- Changed play-mode persistence so live persistent changes stay in memory instead of auto-writing `saves/slot_1.json`
- Added explicit play-mode save/load controls: `F5` writes the current persistent state to disk and `F9` reloads the current save slot
- Updated the play HUD to show live-state/save-file status and manual save feedback

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
- Simple player sprite animation while moving
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
