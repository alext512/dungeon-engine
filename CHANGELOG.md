# Changelog

Reverse-chronological log of functionality changes. Each entry describes what was added or changed, not how.

---

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
- Browser window now shows full tileset PNG with clickable frame selection
- Tilesets auto-added to area when a frame is selected from a new tileset
- Tileset cycling with `[`/`]` keyboard shortcuts
- Entity stack management in the browser window

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
- Separate browser window for layers, palettes, entity stack management
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
