# Area Editor — Phase 3: Tile Painting UX/UI Plan

## Context

The editor has read-only browsing (Phase 1), tabbed documents (Phase 2),
and cell-flag editing (partial Phase 3). The next major UX feature is
**tile painting** — letting the user select a tile from a tileset and
paint it onto the canvas.

Cell-flag editing already established the editing pattern: toggle an edit
mode, left/right click to paint, mutations go through `operations/`
functions, canvas rebuilds the affected group. Tile painting follows the
same pattern but needs a **tile picker** UI.

---

## How Tilesets Work (Quick Reference)

- Each area has a `tilesets` array: `[{ firstgid, path, tile_width, tile_height }]`
- Tile layers have a `grid: int[][]` where each value is a GID (0 = empty)
- GID -> tileset: find tileset with largest `firstgid <= gid`, `local_index = gid - firstgid`
- Local index -> pixel position in the PNG sheet: `col = index % columns`, `row = index // columns`
- Test project: `showcase_tiles.png` is 112x16 -> 7 tiles at 16x16

---

## Core Workflow

1. User opens an area (already works)
2. User selects a **layer** to paint on (layer panel, left click on row)
3. User selects a **tile** from the **tileset browser** (new panel)
4. User enables **paint mode** (Edit > Paint Tiles, or `P` key)
5. User **paints** by clicking/dragging on the canvas
6. User can **erase** (right-click) or **eyedrop** (Alt+click to pick a tile)

---

## Interaction Modes

The canvas already has a cell-flag edit mode. Tile painting is another
mode in the same family. Only one edit mode can be active at a time.

| Mode | Left-click | Right-click | Middle-drag |
|---|---|---|---|
| **Navigate** (default) | — | — | Pan |
| **Paint Tiles** | Place selected GID | Erase (GID->0) | Pan |
| **Edit Cell Flags** | Paint blocked | Clear blocked | Pan |

---

## New UI Elements

### 1. Tileset Browser Panel

New `QDockWidget`, docked on the right side below the Layer panel.

```
+-- Tileset Browser -----------------+
| [Tileset: v showcase_tiles       ] |
| +--+--+--+--+--+--+--+            |
| |01|02|03|04|05|06|07|            |
| +--+--+--+--+--+--+--+            |
| (scrollable grid of tile frames)   |
|                                    |
| Selected: GID 3                    |
+------------------------------------+
```

**Components:**
- **Dropdown** (`QComboBox`) lists all tilesets in the current area by
  filename (e.g. "showcase_tiles")
- **Tile grid** (`QGraphicsView` or custom `QWidget` with `paintEvent`)
  showing all frames from the selected tileset
  - Each cell rendered at a fixed display size (32x32 pixels) regardless
    of actual tile_size, using nearest-neighbour scaling
  - GID 0 (eraser) shown as the first cell with a crosshatch pattern
  - Grid reflows on panel resize (responsive columns)
- **Click** a tile -> selects it as the active brush GID
- **Selected tile** gets a highlight border (2px cyan)
- **Status label** at bottom shows "GID: 3" or "Eraser" for GID 0

**Signals:**
- `tile_selected(int)` — emits the selected GID

**Per-area state:** each area tab should remember its selected tileset
and selected GID. Switching tabs restores the selection.

### 2. Active Layer Selection in Layer Panel

The Layer panel currently only has visibility checkboxes. It needs to
also show which layer is the **active paint target**.

**Changes to `LayerListPanel`:**
- **Click** on a layer row (not the checkbox) sets it as the active
  paint target
- Active layer is highlighted (bold text or background colour)
- The virtual "Entities" row cannot be selected as a paint target
- New signal: `active_layer_changed(int)` emitting the layer index
- Default active layer: index 0 (first layer, typically "ground")

This is distinct from visibility: you might want to see all layers but
only paint on one.

### 3. Paint Mode Toggle

**Where:** Edit menu (alongside existing "Edit Cell Flags")

- `Edit > Paint &Tiles` (checkable, shortcut: `P`)
- Mutually exclusive with `Edit > Edit Cell Flags` — enabling one
  disables the other
- When paint mode is active:
  - Cursor changes to crosshair
  - Canvas drag mode switches to NoDrag for left/right click
  - Middle-mouse still pans (same as cell-flag mode)
  - Tileset browser panel auto-shows if hidden

### 4. Canvas Painting Behaviour

When paint mode is active:

| Input | Action |
|---|---|
| Left-click | Set `grid[row][col]` = selected GID on active layer |
| Left-drag | Continuous painting (each cell painted once per stroke) |
| Right-click | Erase: set GID to 0 on active layer |
| Right-drag | Continuous erasing |
| Alt + left-click | **Eyedropper**: pick the GID at that cell on the active layer, select it in tileset browser |
| Middle-drag | Pan (unchanged) |
| Mouse wheel | Zoom (unchanged) |

**Ghost preview:**
- When hovering, a semi-transparent preview of the selected tile is
  shown at the hovered cell position
- Ghost sits at z=2999 (just below grid overlay)
- Ghost follows the mouse in real-time
- Ghost is hidden when cursor leaves the canvas or when not in paint mode

**After painting:**
- The affected layer's `QGraphicsItemGroup` is rebuilt (or individual
  tile items are added/removed)
- The tab is marked dirty (`*` prefix in tab title)
- Ctrl+S saves (already wired via `save_area_document`)

### 5. Status Bar Updates

When paint mode is active:

```
village_square | Cell: (3, 5) | Layer: ground | GID: 3 | 200%
```

New segments: active layer name + selected tile GID.

---

## Layout

```
+------------------------------------------------------------+
| File  Edit  View                                           |
+--------+--------------------------------------+------------+
| [Areas]|                                      | [Layers]   |
| [Templ]|         Canvas                       |  * ground  | <- bold = active
| [Dialg]|         (tile painting here)         |  * struct  |
| [Comds]|                                      |  * overlay |
| [Asset]|                                      |  * Entities|
|        |                                      +------------+
|        |                                      | [Tileset]  |
|        |                                      |  Browser   |
|        |                                      |  (grid of  |
|        |                                      |   tiles)   |
+--------+--------------------------------------+------------+
| village_square | Cell: (3,5) | Layer: ground | GID: 3|200%|
+------------------------------------------------------------+
```

---

## Files to Create / Modify

| File | Action | What |
|---|---|---|
| `widgets/tileset_browser_panel.py` | **CREATE** | QDockWidget with tileset dropdown + tile grid |
| `operations/tiles.py` | **CREATE** | `paint_tile(area, layer_idx, col, row, gid) -> bool` |
| `widgets/tile_canvas.py` | **MODIFY** | Add paint mode, ghost preview, paint/erase/eyedrop handlers |
| `widgets/layer_list_panel.py` | **MODIFY** | Add active-layer click selection + signal |
| `app/main_window.py` | **MODIFY** | Wire tileset browser, paint mode toggle, active layer, status bar segments |

---

## Implementation Steps

### Step 1: `operations/tiles.py`
Simple paint operation following `cell_flags.py` pattern:
```python
def paint_tile(area, layer_index, col, row, gid) -> bool:
    """Set one cell's GID. Returns True if document changed."""
def eyedrop_tile(area, layer_index, col, row) -> int:
    """Read the GID at one cell."""
```

### Step 2: `TilesetBrowserPanel`
- Build the tile grid widget that renders tileset frames
- Dropdown to switch between tilesets
- Click-to-select with highlight
- `tile_selected(int)` signal

### Step 3: Active layer in `LayerListPanel`
- Add click-to-select (separate from checkbox)
- `active_layer_changed(int)` signal
- Visual highlight on active row

### Step 4: Paint mode in `TileCanvas`
- `set_tile_paint_mode(enabled, active_layer, selected_gid, catalog)`
- Ghost preview item
- Paint/erase/eyedrop handlers in `_handle_edit_pointer_event`
- `tile_painted` signal for dirty tracking
- Rebuild affected layer group on paint

### Step 5: Wire in `MainWindow`
- Add `Edit > Paint Tiles` action (mutually exclusive with cell flags)
- Create and dock `TilesetBrowserPanel`
- Connect signals: tileset browser -> canvas selected GID,
  layer panel -> canvas active layer, canvas paint -> dirty tracking
- Update status bar with layer name and GID

---

## What This Does NOT Cover

- Multi-tile stamp selection (rectangular brush)
- Flood fill tool
- Tile rotation or flipping
- Adding/removing tile layers
- Adding/removing tilesets from an area
- Undo/redo

---

## Verification

1. Open village_square area
2. Tileset browser shows 7 tiles from showcase_tiles.png + eraser cell
3. Click a tile in the browser -> it gets highlighted
4. Click a layer in the layer panel -> it becomes the active target
5. Enable paint mode (`Edit > Paint Tiles` or `P`)
6. Cursor changes to crosshair
7. Hover over canvas -> ghost tile preview follows mouse
8. Left-click a cell -> tile appears on the active layer
9. Right-click -> cell is erased (GID 0)
10. Alt+click -> eyedroppers the GID and selects it in the browser
11. Tab title shows `*` dirty indicator
12. Ctrl+S saves, `*` disappears
13. Switch to another area tab -> tileset browser updates
14. Enabling paint mode disables cell-flag mode and vice versa
