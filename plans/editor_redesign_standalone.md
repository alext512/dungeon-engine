# Standalone Tiled-Like Editor + Game/Editor Separation

> **Status: Implemented**

## Context

The current editor is tightly coupled with the game runtime (F1 toggles between play and edit). The editor UI was built using the game's 320x240 internal renderer, resulting in cramped space and hidden tools. This plan separates the game and editor into standalone applications, and redesigns the editor with a Tiled-like layout at native resolution.

## Goals

1. **Separate game and editor** into independent applications with their own entry points
2. **Tiled-like editor layout** with persistent panels (tileset grid, entity list, properties)
3. **Two clear modes**: Paint (tiles + area flags) and Select (entities + properties)
4. **Editor renders at native resolution** — no 320x240 internal surface, everything at comfortable zoom

## Two Separate Applications

### Game (`run_game.py`)
- Opens with a level selection screen (lists JSON files from `data/areas/`)
- Player selects a level, game runs it using existing play mode code
- No editor code involved

### Editor (`run_editor.py`)
- Opens with a level selection screen, or accepts a file path argument
- Full Tiled-like editor window (~1400x800)
- Pure editing — no play mode
- Future: "Test" button could launch the game process with the current file

## Editor Layout

```
+--[~1400x800]---------------------------------------------------------+
| [Save][Reload]  Mode: [Paint | Select]  Layer: [< ground >]          |
+-----------+--------------------------------------+-------------------+
| LEFT      |                                      | RIGHT PANEL       |
| PANEL     |         MAP VIEW                     |                   |
| (~260px)  |       (2x zoom, pannable)            | Paint: layer mgmt |
|           |                                      | Select: entities  |
| Tileset:  |    Grid overlay + tiles +            |   + properties    |
| [< name >]|    entities at native res            |                   |
| [tile grid|                                      |                   |
|  scrollable]                                     |                   |
|           |                                      |                   |
| --------- |                                      |                   |
| Area Tiles|                                      |                   |
| [Walk]    |                                      |                   |
| [Block]   |                                      |                   |
+-----------+--------------------------------------+-------------------+
| Status: Tile floor:3 | Hover (5,3) | Dirty: yes                      |
+-----------------------------------------------------------------------+
```

## Two Editor Modes

### Paint Mode
- **Left panel active**: full tileset grid (click frame to select brush) + area tile palette
- Click/drag on map to paint selected tile GID or area flag (walkable/blocked)
- Right-click/drag to erase
- **Right panel**: current brush preview, layer list with add/rename/delete, draw-above-entities toggle

### Select Mode
- Click on map to select a cell (highlighted)
- **Right panel active**: entity stack at selected cell
  - Each entity row: `index. entity_id (kind) [^][v][Del][Move]`
  - Add entity: template selector `[<] block [>] [Add]`
  - Properties editor for the selected entity in the list
- **Move workflow**: click [Move] on entity, then click destination cell on map. Entity moves preserving all properties. Escape cancels.

## Left Panel

1. **Tileset selector**: `[<] dungeon_walls [>]` — arrows cycle through available tileset PNGs
2. **Tileset grid**: Full tileset image at 2x zoom (32px per frame for 16px tiles). Scrollable. Click frame to select as painting brush. Selected frame highlighted.
3. **Separator**
4. **Area Tiles palette**: Color-coded clickable rows
   - `[green] Walkable` — selects walkable brush
   - `[red] Blocked` — selects blocked brush
   - Extensible for future area types

## Right Panel

**Paint Mode content:**
- Current brush preview (tile or area type)
- Layer list: clickable rows, active layer highlighted
  - [Add Layer] button
  - Per-layer: [Rename] [Delete] [Above entities toggle]

**Select Mode content:**
- "Cell (x, y)" header
- Entity stack list (sorted by layer + stack_order)
  - `1. block_1 (block) [^][v][X][Move]`
  - Player entity has no [X] button
- Add entity: `[<] template_id [>] [Add]`
- Separator
- Properties for selected entity:
  - `Template: block` (read-only)
  - `Kind: block` (read-only)
  - `Facing: right` (click to cycle through up/right/down/left)
  - `Solid: true` (click to toggle)
  - `Pushable: false` (click to toggle)
  - `Enabled: true` (click to toggle)
  - `Visible: true` (click to toggle)
  - Template parameters: `target: gate_1` (click to text-edit, Enter to confirm, Escape to cancel)

## Architecture

### New Files
| File | Purpose |
|------|---------|
| `run_game.py` | Game entry point with level selection |
| `run_editor.py` | Editor entry point |
| `dungeon_engine/editor/editor_app.py` | Main editor application (~800-1000 lines) |

### Modified Files
| File | Changes |
|------|---------|
| `dungeon_engine/editor/level_editor.py` | Simplify: remove `handle_events()`/`update()`, keep all data methods (tile painting, entity ops, save/load) |
| `dungeon_engine/engine/game.py` | Remove all editor code, accept area_path, add level selection |
| `dungeon_engine/engine/renderer.py` | Revert to play-mode only, remove editor_ui parameter |
| `dungeon_engine/config.py` | Add `EDITOR_WIDTH`, `EDITOR_HEIGHT` constants |

### Deleted Files
| File | Reason |
|------|--------|
| `dungeon_engine/editor/editor_ui.py` | Replaced by `editor_app.py` |
| `dungeon_engine/editor/browser_window.py` | No longer needed |

### EditorApp Class

The `EditorApp` class in `editor_app.py` owns the entire editor:
- Creates its own pygame window at ~1400x800
- Has its own main loop (separate from game)
- Renders map tiles/entities directly at zoom level (no internal 320x240 surface)
- Uses `pygame.font.SysFont` for native-resolution UI text
- Reuses `AssetManager` for image loading
- Reuses `Camera` for map panning
- Delegates data operations to `LevelEditor` (tile painting, entity management, save/load)

### Map Rendering

The editor renders the map directly at native resolution with configurable zoom (default 2x):
1. Calculate visible tile range from camera position
2. For each tile in each layer: get frame from AssetManager, scale to zoom, blit to map viewport
3. For each entity: get sprite (or draw colored rect), scale, blit
4. Draw overlays: grid lines, walkability colors, selection/hover highlights

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+S | Save |
| Tab | Toggle Paint / Select mode |
| `[` / `]` | Cycle tilesets |
| Scroll wheel | Scroll tileset panel (if hovering left panel) |
| Arrow keys | Pan map |
| MMB drag | Pan map |
| Escape | Cancel move-pending / deselect |
| Delete | Remove selected entity (Select mode) |

## Implementation Phases

### Phase 1: Entry points + game separation
Create `run_game.py` and `run_editor.py`. Strip editor code from `game.py`. Restore `renderer.py` to play-only. Add editor constants to `config.py`.

### Phase 2: EditorApp skeleton + map renderer
Create `editor_app.py` with window, layout, main loop. Implement map rendering (tiles + entities at zoom). Add grid overlay and camera panning.

### Phase 3: Left panel — tileset browser + area tiles
Tileset selector with cycling. Full tileset grid (scaled, scrollable, clickable). Area tiles palette.

### Phase 4: Toolbar + mode switching
Save, Reload buttons. Paint/Select mode toggle. Layer selector in toolbar.

### Phase 5: Paint mode — map interaction
Click/drag to paint tiles or area flags. Right-click to erase. Walkability overlay.

### Phase 6: Right panel — Paint mode (layer management)
Layer list with add/rename/delete. Draw-above-entities toggle.

### Phase 7: Select mode — entity management
Entity stack display. Add/reorder/delete entities. Move workflow.

### Phase 8: Property editor
Entity property display and editing. Boolean toggle, facing cycle, text-edit for parameters.

### Phase 9: Status bar + cleanup
Status bar. Delete old editor files.

## Verification

- `python run_editor.py` opens editor, shows level selection or default level
- Left panel shows full tileset, click to select tile brush
- Paint mode: click/drag map to paint tiles, select area tile to paint walkable/blocked
- Tab to Select mode: click cell, right panel shows entity stack
- Add/remove/reorder entities, edit properties
- [Move] entity to new cell
- Ctrl+S saves to JSON
- `python run_game.py` opens game independently, plays selected level

