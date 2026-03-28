> **Status: Completed**
>
> **Historical note:** this plan describes the intermediate browser-window editor that landed before the later standalone-editor redesign. References here to `browser_window.py`, `F1`, and in-game editor flow are historical, not the current architecture.

# Editor Overhaul: GID-Based Tilemap + Full Tileset View + Entity Inspector

## Context

The current editor uses named string-based tile definitions (`"floor"`, `"wall"`) which requires pre-defining every tile before using it. This is non-standard and clunky. The industry-standard approach (used by Tiled, Godot, RPG Maker, etc.) is **GID-based**: tile grids store integers, each integer maps to a specific frame in a specific tileset. This eliminates named definitions entirely for normal tiles — you just click a frame in the tileset and paint.

The user also wants: full tileset image view in the browser window, entity property editing, and a cleaner layout.

## Part 1: Migrate to GID-Based Tilemap

### New Data Model

**Tileset dataclass** (new, in `world/area.py`):
```python
@dataclass
class Tileset:
    firstgid: int          # First GID assigned to this tileset (1-based, 0 = empty)
    path: str              # Relative path to PNG (e.g., "assets/tiles/basic_tiles.png")
    tile_width: int        # Width of each tile frame in pixels
    tile_height: int       # Height of each tile frame in pixels
    # columns and tile_count computed on load from image dimensions
    columns: int = 0
    tile_count: int = 0
```

**Area changes:**
- Remove `tile_definitions: dict[str, dict]`
- Add `tilesets: list[Tileset]`
- `TileLayer.grid` changes from `list[list[str | None]]` to `list[list[int]]` (0 = empty)
- Add method `resolve_gid(gid: int) -> tuple[str, int, int, int] | None` — returns `(tileset_path, tile_width, tile_height, local_frame_index)` by finding which tileset's GID range contains the given GID

**New area JSON format:**
```json
{
  "name": "Test Room",
  "tile_size": 16,
  "tilesets": [
    {
      "firstgid": 1,
      "path": "assets/tiles/basic_tiles.png",
      "tile_width": 16,
      "tile_height": 16
    }
  ],
  "tile_layers": [
    {
      "name": "ground",
      "grid": [[1, 1, 1, 0], [1, 2, 2, 0]]
    }
  ]
}
```
GID 0 = empty. GID 1 = first frame of first tileset. If tileset has 100 frames, GIDs 1–100 are its range. Second tileset starts at firstgid 101.

### Files Changed for Migration

**`world/area.py`**
- Add `Tileset` dataclass
- Remove `tile_definitions` field from `Area`
- Add `tilesets: list[Tileset]` field
- Change `TileLayer.grid` type to `list[list[int]]`
- Remove `tile_definition()` method
- Add `resolve_gid(gid) -> tuple | None` method
- Add `gid_for_tileset_frame(tileset_index, local_frame) -> int` helper

**`world/loader.py`**
- Parse `tilesets` array instead of `tile_definitions`
- Load each tileset's image to compute `columns` and `tile_count` from image dimensions (via `AssetManager`)
- Parse grids as `list[list[int]]` (already integers in JSON, simpler than strings)
- Remove string-based tile_definition lookup code

**`world/serializer.py`**
- Serialize `tilesets` array instead of `tile_definitions`
- Grids are already integers, serialize directly

**`engine/renderer.py`** — `_draw_tile_layers`:
- Replace `area.tile_definition(tile_id)` with `area.resolve_gid(gid)`
- Call `asset_manager.get_frame(path, tw, th, local_frame)` with resolved values
- Same for `_draw_editor_preview`, `_draw_tile_icon`, `_draw_palette_item`

**`engine/asset_manager.py`**
- Add `get_frame_count(path, fw, fh) -> int` — compute columns * rows from cached image
- Add `get_image_size(path) -> tuple[int, int]` — return cached image dimensions

**`data/areas/test_room.json`** — rewrite to new format (it's small, only 3 tile types used)

### Migration Notes
- The old `tile_definitions` dict with "floor"?frame 0, "wall"?frame 1, "painting"?frame 2 maps directly to GIDs 1, 2, 3 with a single tileset at firstgid=1
- The grids just change from `"floor"` ? `1`, `"wall"` ? `2`, `null` ? `0`

---

## Part 2: Full Tileset View in Browser Window

### Editor State Changes (`level_editor.py`)

- Add `list_tileset_paths() -> list[str]` — scans `config.TILES_DIR` for PNGs
- New fields: `available_tileset_paths: list[str]` (all discoverable tilesets), `selected_tileset_index: int` (which tileset to show in browser), `selected_gid: int` (current brush)
- `select_tileset_frame(tileset_index, local_frame) -> None` — computes the GID via `area.gid_for_tileset_frame()`, adding the tileset to the area if it's not already present. Sets the GID as the current brush.
- Remove `tile_ids`, `selected_tile_index` fields (replaced by GID-based selection)
- Keep `current_tile_id` as a computed property for HUD display: returns a readable label like `"basic_tiles:0"` from the selected GID

### Browser Window Changes (`browser_window.py`)

**Tile mode — tileset view replaces icon palette:**

- **Tileset selector**: Row at top of palette area showing current tileset name with prev/next buttons. Cycles through `editor.available_tileset_paths`.
- **Full tileset image**: Load the full PNG via `asset_manager.get_image()`, scale by 2x (16px ? 32px display), blit into the palette area. Clip to palette bounds, scroll vertically for large tilesets.
- **Grid overlay**: Semi-transparent grid lines at `tile_width * scale` intervals.
- **Selection highlight**: Colored border on the frame matching the current brush GID (reverse-compute: if brush GID falls in this tileset's range, highlight `local_frame = gid - firstgid`).
- **Click ? select**: `_tileset_frame_at(mouse_pos) -> int | None` converts pixel position to local frame index. On click, calls `editor.select_tileset_frame(tileset_index, local_frame)`.
- **Scroll**: Mousewheel scrolls vertically. New state: `tileset_scroll_y: int = 0`.

**Entity and walkability modes** — unchanged from current behavior.

### Adding New Tilesets to an Area

When the user browses to a tileset that isn't in the area's `tilesets` list and clicks a frame:
- `select_tileset_frame` auto-adds the tileset to `area.tilesets` with a computed `firstgid` = max existing GID + 1 (rounded up to avoid collisions)
- This is transparent to the user — they just click and paint

---

## Part 3: Entity Property Inspector

### Editor State (`level_editor.py`)

- `selected_entity_properties() -> list[tuple[str, str, str]]` — returns `(field_name, label, value_str)` for the selected entity: template_id (read-only), template parameters (editable key-value pairs), facing, solid, pushable, enabled, visible
- `set_entity_property(entity_id, field_name, value_str)` — parses and applies, marks dirty

### Browser Window (`browser_window.py`)

- Split entity panel: **entity stack list** (top) + **property inspector** (bottom)
- Property rows: label on left, clickable value on right
- Click activates text input (reuses existing `active_text_field` pattern from layer name editing)
- Enter commits, Escape cancels
- New state: `active_property_field: str | None`, `property_value_buffer: str`

---

## Part 4: Layout Reorganization

Make `_layout` mode-aware:

```
Top:          [Play] [Save] [Reload]           (40px)
Mode tabs:    [Tiles] [Flags] [Entities]       (40px)
Layers:       Layer list + controls             (170px)

Tile mode:    Tileset selector (24px) + full tileset image (remaining)
Walk mode:    Walk/Block cards (unchanged)
Entity mode:  Template palette (~200px) + entity stack (~120px) + inspector (remaining)

Status bar:   One line                          (20px)
```

---

## Part 5: Polish

- `[` / `]` keyboard shortcuts to cycle tilesets
- Error handling for missing tileset PNGs
- Reset scroll when switching tilesets
- Verify save/load round-trips
- Verify existing shortcuts still work (F1–F4, Q/E, Ctrl+S, mouse painting)

---

## Files Changed (all paths relative to `dungeon_engine/`)

| File | Scope |
|------|-------|
| `world/area.py` | Add `Tileset`, remove `tile_definitions`, GID grid, `resolve_gid()` |
| `world/loader.py` | Parse new tileset/GID format |
| `world/serializer.py` | Serialize new format |
| `engine/renderer.py` | Use `resolve_gid()` in all tile rendering paths |
| `engine/asset_manager.py` | Add `get_frame_count()`, `get_image_size()` |
| `config.py` | Add `TILES_DIR` constant |
| `editor/level_editor.py` | GID-based selection, tileset state, entity property methods |
| `editor/browser_window.py` | Tileset image view, entity inspector, revised layout |
| `data/areas/test_room.json` | Rewrite to GID format |

No changes needed to: `engine/game.py`, `engine/camera.py`, `world/entity.py`, `world/world.py`

## Implementation Order

1. **Data model first** (area.py, loader.py, serializer.py, test_room.json) — get the GID system working, game loads and renders correctly
2. **Renderer update** (renderer.py) — tiles render from GIDs
3. **Editor tile painting** (level_editor.py) — painting works with GIDs
4. **Tileset view** (browser_window.py) — full tileset image in browser
5. **Entity inspector** (level_editor.py, browser_window.py) — property editing
6. **Layout + polish** (browser_window.py) — final layout, keyboard shortcuts, error handling

## Verification

1. Run game ? map renders correctly with GID-based tiles
2. Enter editor (F1) ? tile mode (F2) ? browser shows full tileset PNG
3. Click any frame ? paints on map ? Ctrl+S saves ? JSON has GIDs
4. Entity mode (F4) ? select placed entity ? properties appear ? edit target_gate ? save ? persists
5. Play mode (F1) ? lever/gate interaction still works

