# Tile Selection And Stamp Plan

## Goal

Add a practical first-pass tile selection workflow to the external editor without overloading the existing paint and entity-selection behavior.

V1 should make it easy to:

- select a rectangular region on the active tile layer
- clear/delete the selected tiles
- copy and cut the selected tiles
- paste them back onto the active tile layer

This plan also outlines the follow-up for larger tileset-region selection as a paint stamp, but that is intentionally phase 2.

## Main Decision

Tile selection should be its **own tool/mode**, not part of the existing entity `Select` mode.

Reason:

- current `Select` mode is entity-oriented
- tile selection and entity selection would otherwise compete for the same mouse gestures
- tile editing becomes easier to reason about if each tool has one clear meaning

So the editor tool model becomes:

- `Paint`
- `Select` (entities)
- `Tile Select`
- `Edit Cell Flags`

## V1 Scope

### Included

- rectangular selection on the **active tile layer only**
- visible selection marquee on the canvas
- `Delete` / `Clear Selection`
- `Copy`
- `Cut`
- `Paste` at a chosen anchor cell

### Not Included

- multi-layer tile selection
- entity + tile mixed selection
- transform operations like flip / rotate
- non-rectangular selection
- true drag-move of a selected block as a separate mode
- tileset-region stamping

## Interaction Model

### Tile Select mode

When `Tile Select` is active:

- left-drag creates or updates a rectangular tile selection
- clicking without drag selects a 1x1 cell
- clicking outside the map clears the selection
- entities are ignored in this mode

### Clipboard actions

- `Copy`: copies selected tile data from the active layer
- `Cut`: copies then clears the selected cells
- `Delete`: clears selected cells to GID `0`
- `Paste`: places the copied block with its top-left corner anchored at the clicked cell

### Paste preview

V1 can start without a rich ghost preview if needed, but ideally:

- after `Copy` or `Cut`, clipboard data stays available
- when `Tile Select` is active and a clipboard exists, paste can be triggered explicitly
- the first version can use the current hovered cell as the paste anchor

## Data Model

Tile selection state should live on the canvas/editor side, not in the area document.

Suggested canvas state:

- selected rectangle:
  - `start_col`
  - `start_row`
  - `end_col`
  - `end_row`
- normalized selection bounds helper
- optional clipboard payload:
  - width
  - height
  - 2D GID grid

Clipboard should be editor-local for V1, not system clipboard text.

## Rendering

Canvas should render:

- a selection outline over the selected rectangle
- optional subtle fill tint for selected cells

This should be a separate overlay item/group, similar to:

- grid overlay
- cell-flag overlay
- entity selection highlight

## Commands / Actions / Shortcuts

### New actions

- `Tile Select`
- `Copy Tiles`
- `Cut Tiles`
- `Paste Tiles`
- `Delete Selected Tiles`
- `Clear Tile Selection`

### Suggested shortcuts

- `T` or another dedicated shortcut for `Tile Select`
- `Ctrl+C` copy
- `Ctrl+X` cut
- `Ctrl+V` paste
- `Delete` clear selected tiles when tile selection exists
- `Escape` clear tile selection

Important:

- this must coexist cleanly with current entity selection delete/escape behavior
- action routing should prefer the active tool/mode

## Implementation Order

### Phase 1: Selection state + drawing

- add `Tile Select` mode to main window and canvas
- track drag rectangle on tile cells
- render visible selection bounds
- clear selection on tool changes when appropriate

### Phase 2: Clear/delete

- add `Delete Selected Tiles`
- set selected cells to `0` on the active layer
- mark tab dirty
- rebuild scene

### Phase 3: Copy / cut / paste

- add editor-local tile clipboard payload
- implement copy from active layer
- implement cut as copy + clear
- implement paste at hovered/clicked anchor cell
- clip pasted content to area bounds

### Phase 4: UX polish

- status-bar hints
- action enable/disable state
- optional paste preview
- clearer border/fill styling

### Phase 5: Tileset-region selection (follow-up)

- rectangular selection inside tileset browser
- promote selected region to a paint stamp
- stamp paints the multi-cell pattern onto the active layer

This should come **after** map-side selection is stable.

## Testing Plan

Add editor tests for:

- entering tile-select mode and creating a rectangle
- deleting selected tiles on the active layer only
- copy/cut/paste preserving the selected block shape
- paste clipping at area edges
- switching between entity select and tile select cleanly
- `Escape` clearing tile selection
- `Delete` affecting tile selection vs entity selection appropriately

## Risks / Nuances

### 1. Tool conflict

Biggest risk is conflict between:

- entity `Select`
- tile `Paint`
- tile `Tile Select`

This is why `Tile Select` should be explicit rather than overloaded into current select mode.

### 2. Active-layer ambiguity

V1 should stay strict:

- selection acts only on the active tile layer

No hidden multi-layer behavior.

### 3. Clipboard expectations

Users may expect system clipboard integration, but editor-local clipboard is fine for V1 and much simpler.

## Recommendation

Implement in this order:

1. tile-select mode
2. visible rectangle selection
3. delete/clear
4. copy/cut/paste
5. tileset multi-tile stamp later

That gives a coherent first editing workflow without dragging us into a much bigger generalized map editor feature set.
