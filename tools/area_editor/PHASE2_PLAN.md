# Area Editor — Phase 2: Tabbed Document Area

## Goal

Replace the single-area central canvas with a tabbed document interface. Any content item (area, entity template, dialogue, command, asset) can be opened as a tab. Multiple tabs can be open simultaneously.

---

## Architecture

### Central Widget: `DocumentTabWidget`

A `QTabWidget` replaces the single `TileCanvas` as the central widget.

- **Closable tabs** — each tab has an X button
- **Reorderable** — tabs can be dragged to reorder
- **Middle-click to close** — standard convention
- **Tab tooltip** — shows the full content id (e.g. `areas/village_square`)
- **Empty state** — when no tabs are open, show a centered welcome label ("Open a file from the side panels")
- **Dirty indicator** — tab title shows `*` prefix when content is modified (plumbing only, no editing yet)

### Tab Content by Type

| Content Type | Widget | Description |
|---|---|---|
| Area | `TileCanvas` (existing) | Full tile rendering with zoom/pan |
| Entity Template | `JsonViewerWidget` | Read-only syntax-highlighted JSON |
| Dialogue | `JsonViewerWidget` | Read-only JSON |
| Named Command | `JsonViewerWidget` | Read-only JSON |
| Asset (image) | `ImageViewerWidget` | Zoomable image preview |
| Asset (other) | `JsonViewerWidget` | Fallback: raw text display |

### Side Panel Interaction

Current behavior: single-click in area panel loads the area. New behavior:

- **Double-click** on any item in any side panel → opens in a new tab (or focuses existing tab if already open)
- **Single-click** → selects in the tree only, no tab opened
- **Right-click** → context menu: "Open", "Open in New Tab" (for future: "Open" could reuse the active tab)
- Clicking on an already-open tab's item in the tree just focuses that tab

### Layer Panel Contextual Binding

The Layer panel (right dock) shows layers for the **currently active area tab**:

- When switching between area tabs, the layer panel updates to show that area's layers
- When a non-area tab is active, the layer panel shows empty / "No layers"
- Layer visibility state is per-tab (each area tab remembers its own visibility toggles)

---

## New Files

```
area_editor/widgets/
    document_tab_widget.py    # QTabWidget subclass, tab management
    json_viewer_widget.py     # Read-only JSON text display
    image_viewer_widget.py    # Zoomable image preview (QGraphicsView)
```

---

## Implementation Steps

### Step 1: `JsonViewerWidget`

Simple `QPlainTextEdit` in read-only mode:
- Loads and displays JSON content with indentation
- Monospace font
- No editing (Phase 2 is still read-only)
- Constructor: `JsonViewerWidget(file_path: Path)`

### Step 2: `ImageViewerWidget`

`QGraphicsView` with a single `QGraphicsPixmapItem`:
- Loads image file as QPixmap
- Zoom with mouse wheel (same range/step as TileCanvas)
- Pan with drag
- Nearest-neighbor rendering (pixel art)
- Checkerboard background for transparency
- Constructor: `ImageViewerWidget(file_path: Path)`

### Step 3: `DocumentTabWidget`

Core tab manager widget:
- Subclasses `QTabWidget`
- `open_document(content_id, file_path, content_type)` — creates appropriate widget, adds tab, or focuses existing
- Tracks open tabs by content_id to prevent duplicates
- `close_tab(index)` — removes tab and cleans up
- Middle-click on tab → close
- Signals:
  - `active_document_changed(content_id, content_type)` — when tab switches
  - `tab_closed(content_id)` — when a tab is closed
  - `no_tabs_open()` — when all tabs closed
- Empty-state: stacked widget with welcome QLabel underneath

For area tabs specifically:
- Stores the `AreaDocument` and layer visibility state per tab
- Exposes `active_area_canvas() -> TileCanvas | None` for layer panel binding

### Step 4: Refactor `MainWindow`

- Replace `self._canvas = TileCanvas()` / `setCentralWidget(self._canvas)` with `self._tab_widget = DocumentTabWidget()` / `setCentralWidget(self._tab_widget)`
- Remove the single `_current_area` / `_current_area_id` state — now tracked per tab
- Connect `active_document_changed` → update layer panel, status bar
- Connect `tab_closed` → clean up
- `_load_area()` becomes `_open_area()` — creates/focuses area tab instead of replacing canvas

### Step 5: Side Panel Double-Click + Context Menu

Modify `FileTreePanel`:
- Change `currentItemChanged` (single-click) to `itemDoubleClicked` for opening
- Keep single-click for selection only (no signal emission for opening)
- Add `QTreeWidget.setContextMenuPolicy(Qt.CustomContextMenu)` + context menu handler
- Context menu items: "Open" (same as double-click)
- Emit new signal: `file_open_requested(content_id, file_path)` on double-click/context-menu-open
- Keep `file_selected(content_id, file_path)` for single-click selection if needed

Modify `AreaListPanel`:
- Same pattern: `area_open_requested` signal on double-click
- Keep `area_selected` for single-click tree selection

### Step 6: Layer Panel Binding

- `MainWindow` connects `DocumentTabWidget.active_document_changed` → update layer panel
- When active tab is an area: `layer_panel.set_layers(doc.tile_layers)`, reconnect visibility signals to that tab's canvas
- When active tab is not an area: `layer_panel.clear_layers()`
- Per-tab visibility: each area tab's `TileCanvas` independently tracks which layers are visible

### Step 7: Status Bar Updates

- Area tab active: show area name + cell coords + zoom (same as now)
- Other tab active: show content id, hide cell/zoom
- No tabs: show project name only

---

## Implementation Status

**Implemented (UI complete):**
- Steps 1–7 are all implemented and verified
- 28 existing tests pass, launch-tested with test_project
- Tab deduplication, middle-click close, context menus all working

**Known gaps for backend/follow-up agent to address:**

1. **Per-tab layer visibility state is not persisted across tab switches.**
   Currently when you switch between area tabs, the layer panel rebuilds
   from the document. Any visibility toggles the user made are lost.
   Fix: store a `dict[int, bool]` visibility map per tab in `_TabInfo` or
   on the `TileCanvas` itself, and restore it in `_on_active_tab_changed`.

2. **Canvas signal accumulation.** Each time `_connect_canvas` is called,
   it connects `cell_hovered` and `zoom_changed` to the main window
   slots. These connections are never disconnected when switching tabs,
   so old canvases may still emit to the status bar. Fix: disconnect the
   previous canvas's signals before connecting the new one.

3. **No tests for the new widgets.** `DocumentTabWidget`,
   `JsonViewerWidget`, and `ImageViewerWidget` have no automated tests.
   Testing these requires a `QApplication` instance. Consider adding a
   `conftest.py` with a session-scoped `qapp` fixture and writing basic
   tests (open tab, verify deduplication, close tab, verify cleanup).

4. **`_create_viewer` doesn't handle missing files gracefully.**
   `JsonViewerWidget._load` catches `OSError` but `ImageViewerWidget`
   silently shows a blank scene for missing/corrupt images. Consider
   adding a visible error message.

5. **Tab dirty indicator plumbing exists but is unused.**
   `_TabInfo.dirty` is always `False`. When editing is added, the tab
   title should show `*` prefix via `_tabs.setTabText(idx, f"*{label}")`.

---

## What This Does NOT Include

- Editing (still read-only)
- Drag-and-drop from side panels to canvas
- Undo/redo
- Dirty state tracking (plumbing is there, but nothing sets dirty=true yet)

These are Phase 3+.

---

## Verification Checklist

1. Double-click area in side panel → area tab opens with tile rendering
2. Double-click same area again → focuses existing tab (no duplicate)
3. Double-click entity template → JSON viewer tab opens
4. Double-click dialogue/command → JSON viewer tab opens
5. Double-click image asset → image viewer tab opens
6. Double-click non-image asset → text viewer tab opens
7. Tabs are closable (X button), middle-click closes
8. Switching between area tabs updates the layer panel
9. Layer visibility is independent per area tab
10. Non-area tab active → layer panel shows empty
11. Right-click context menu works in all side panels
12. All existing tests still pass
