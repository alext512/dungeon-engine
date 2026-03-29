# Area Editor — Phase 1: Read-Only Project Browser (PySide6)

## Context

The puzzle dungeon engine is data-driven — gameplay is authored via JSON files (areas, entity templates, project commands). Hand-editing these JSONs is painful for tile painting, entity placement, and cross-entity references. The area editor is an external convenience tool that reads/writes the same JSON files without importing the runtime.

Phase 0 (docs/planning) is complete. This plan covers **Phase 1: read-only project browser** — opening a project, viewing areas, and rendering tile grids with entity markers. No editing yet.

**UI framework decision: PySide6** (cross-platform, native docking/panels, QGraphicsView for tile canvas).

---

## File Structure

```
tools/area_editor/                # Portable root (can be copied standalone)
    requirements.txt              # PySide6>=6.6
    Run_Editor.cmd                # Windows launcher
    (existing .md docs)
    area_editor/                  # Python package (python -m area_editor)
        __main__.py               # Entry point
        app/
            __init__.py
            app.py                # QApplication setup, file dialogs
            main_window.py        # QMainWindow with docks, menu, status bar
        project_io/
            __init__.py
            manifest.py           # Load project.json, discover areas/templates
            asset_resolver.py     # Resolve authored asset paths to filesystem
        documents/
            __init__.py
            area_document.py      # AreaDocument, TileLayerDocument, EntityDocument
        catalogs/
            __init__.py
            tileset_catalog.py    # Load tileset PNGs, GID→frame lookup
        widgets/
            __init__.py
            area_list_panel.py    # QDockWidget: area list
            layer_list_panel.py   # QDockWidget: layer visibility toggles
            tile_canvas.py        # QGraphicsView: tile rendering + zoom/pan
    tests/                        # Automated tests (no Qt required for most)
        __init__.py
        test_manifest.py          # Area discovery, area_id derivation, path resolution
        test_asset_resolver.py    # Asset path resolution against test_project
        test_area_document.py     # Document loading, unknown-field preservation, round-trip
```

The Python package is `area_editor/` (inside `tools/area_editor/`). All internal imports use `from area_editor.xxx import yyy`. The working directory when running is `tools/area_editor/`.

---

## Portability

The editor folder must be **fully self-contained and portable** — copyable to another location and usable standalone. This means:
- `tools/area_editor/requirements.txt` with `PySide6>=6.6`
- `tools/area_editor/Run_Editor.cmd` — Windows launcher script (finds/uses a local or system Python)
- No imports from `dungeon_engine` or any sibling package
- No relative imports above `tools/area_editor/`

---

## Implementation Steps

### Step 1: Entry point and app skeleton
- `__main__.py`: parse `--project <path>` arg, create QApplication, show MainWindow
- `app/app.py`: QApplication setup, helper for project.json file dialog
- `app/main_window.py`: empty QMainWindow with menu bar (File > Open Project, Quit) and status bar
- **Verify**: `python -m area_editor` opens an empty window

### Step 2: Manifest loading and area discovery
- `project_io/manifest.py`: `ProjectManifest` dataclass, `load_manifest()`, `discover_areas()`
- Replicate runtime's path resolution logic from `dungeon_engine/project.py` lines 393-441 (`_resolve_paths` pattern: if key missing/empty, fall back to conventional dir)
- Replicate `area_id()` from lines 263-277 (relative path, strip .json, normalize slashes)
- **Verify**: discovers 3 areas from test_project (village_square, village_house, title_screen)

### Step 3: Document model with unknown-field preservation
- `documents/area_document.py`: dataclasses for `TilesetRef`, `TileLayerDocument`, `EntityDocument`, `AreaDocument`
- Each class: `from_dict()` pops known keys, remainder -> `_extra: dict`; `to_dict()` merges back
- `load_area_document(path) -> AreaDocument`
- Known area fields: name, tile_size, tilesets, tile_layers, cell_flags, entry_points, entities, camera, input_targets, variables, enter_commands
- Known entity fields (for Phase 1): id, x, y, pixel_x, pixel_y, space, layer, template, parameters — everything else -> `_extra`
- Entities may use grid coords (x/y) or pixel coords (pixel_x/pixel_y) depending on `space` ("world" vs "screen")
- **Verify**: loads village_square.json with correct dimensions, layer count, entity count

### Step 4: Asset resolver and tileset catalog
- `project_io/asset_resolver.py`: replicate runtime's `resolve_asset()` from lines 217-235 (rooted_candidate = asset_dir.parent / rel_path, then direct_candidate = asset_dir / rel_path)
- `catalogs/tileset_catalog.py`: load tileset PNGs as QPixmap, cache frames
- GID resolution: find tileset with largest firstgid <= gid, local_index = gid - firstgid
- Frame extraction: columns = png_width // tile_width, col = local_index % columns, row = local_index // columns, copy source rect
- **Verify**: resolves showcase_tiles.png, extracts GID 1 -> first tile frame

### Step 5: Tile canvas (core rendering)
- `widgets/tile_canvas.py`: QGraphicsView + QGraphicsScene
- Scene sized to (width * tile_size, height * tile_size)
- One QGraphicsItemGroup per tile layer (bottom-up draw order)
- **Z-order must follow the runtime render model**: tile layers and entity markers need unified `render_order` support, with y-sorted layers/cells and entity markers able to interleave in the same band.
- For each cell: resolve GID -> tileset frame -> QGraphicsPixmapItem at (col * tile_size, row * tile_size)
- Entity markers: colored semi-transparent rectangles with tooltips showing id + template
- Entity marker placement: use (x * tile_size, y * tile_size) for world-space entities, (pixel_x, pixel_y) for screen-space entities
- Grid overlay: thin lines at tile boundaries (toggleable)
- Zoom: mouse wheel, anchor under mouse, 0.25x-10x range, nearest-neighbor (no smooth transform — pixel art)
- Pan: ScrollHandDrag mode (middle mouse or hold-drag)
- Mouse move -> emit cell coordinates for status bar
- **Verify**: village_square renders with all 3 tile layers composited, and the canvas can preview the runtime ordering model (`render_order`, `y_sort`, `stack_order`) instead of the retired below/above split

### Step 6: Area list panel
- `widgets/area_list_panel.py`: QDockWidget with QListWidget
- Populated from `discover_areas()`, emits `area_selected(area_id, file_path)` signal
- **Verify**: shows 3 areas, clicking one triggers loading

### Step 7: Layer list panel
- `widgets/layer_list_panel.py`: QDockWidget with checkable list items
- One row per tile layer + virtual "Entities" row
- Checkbox toggles -> show/hide the corresponding QGraphicsItemGroup
- **Verify**: unchecking a layer hides those tiles on canvas

### Step 8: Main window wiring
- Wire: menu Open Project -> file dialog -> load manifest -> populate area list
- Wire: area list selection -> load area document + tileset catalog -> render canvas + populate layer list
- Status bar: area name, cell coordinates (from canvas hover signal), zoom level (from canvas zoom signal)
- `--project` CLI arg: auto-load on startup
- **Verify**: full flow from open project -> browse areas -> view tiles

### Step 9: Automated tests
- `tests/test_manifest.py`: test against `projects/test_project/` — area discovery finds 3 areas, area_id derivation matches expected ids, path fallback logic works when keys are missing
- `tests/test_asset_resolver.py`: test against `projects/test_project/` — resolves known tileset paths, returns None for missing paths
- `tests/test_area_document.py`: load village_square.json — correct dimensions, layer count, entity count, `render_order` / `y_sort` fields preserved, unknown fields round-trip through `from_dict()`/`to_dict()`
- Run with: `python -m pytest tests/` from `tools/area_editor/`
- These tests are pure Python (no Qt dependency) and use the real test_project fixtures via relative path

### Step 10: Edge cases and polish
- Missing tileset PNG -> magenta placeholder tile + console warning
- GID out of range -> magenta placeholder
- Area with no tile layers or empty grids -> blank canvas, no errors
- title_screen: no tilesets but has screen-space entities -> entity markers render at pixel positions
- Ctrl+0 to reset zoom
- Grid overlay toggle in View menu

---

## Key Design Decisions

1. **Dataclass documents with `_extra` passthrough** — every document level preserves unknown fields for safe round-tripping (Phase 2 saving)
2. **Independent path resolution** — replicates runtime's algorithms from `dungeon_engine/project.py` without importing it (JSON-only contract)
3. **QGraphicsItemGroup per layer** — O(1) visibility toggling, clean compositing
4. **Z-order matches the unified runtime render model** — tile layers and entity markers share `render_order`, with y-sorted content interleaving inside a band
5. **No entity sprite rendering in Phase 1** — just colored markers with tooltips; sprite visuals are Phase 3+
6. **Automated tests against real fixtures** — area discovery, asset resolution, and document round-trip tested against test_project to catch drift from runtime conventions
7. **Pixel-perfect rendering** — SmoothPixmapTransform disabled for crisp pixel art at all zoom levels

---

## Critical Reference Files

| File | Why |
|------|-----|
| `dungeon_engine/project.py` lines 217-235, 263-277, 393-441 | Path resolution and area ID algorithms to replicate |
| `projects/test_project/project.json` | Test fixture for manifest loading |
| `projects/test_project/areas/village_square.json` | Primary test area (3 layers, entities, tilesets) |
| `ENGINE_JSON_INTERFACE.md` | Canonical JSON field reference |
| `tools/area_editor/ARCHITECTURE.md` | Module structure and constraints |
| `tools/area_editor/DATA_BOUNDARY.md` | Import boundary rules |

---

## How to Run

```
cd tools/area_editor
pip install -r requirements.txt
python -m area_editor
python -m area_editor --project ../../projects/test_project/project.json
```

Or double-click `tools/area_editor/Run_Editor.cmd`.

---

## Verification Checklist

1. From `tools/area_editor/`: `python -m area_editor --project ../../projects/test_project/project.json` opens without errors
2. Area list shows: title_screen, village_house, village_square
3. Clicking village_square renders the tile grid with all 3 layers
4. Layer checkboxes toggle visibility
5. Entity markers appear at correct grid positions with tooltips
6. Mouse wheel zooms (pixel-art crisp), drag pans
7. Status bar shows cell coordinates on hover
8. title_screen loads without errors — screen-space entity markers render at pixel positions
9. `python -m pytest tests/` passes — area discovery, asset resolution, document round-trip all verified automatically

---

## Doc Updates After Implementation

- `DECISIONS.md` — record PySide6 choice and rationale
- `OPEN_QUESTIONS.md` — mark UI framework as resolved
- `ROADMAP.md` — mark Phase 1 as complete
