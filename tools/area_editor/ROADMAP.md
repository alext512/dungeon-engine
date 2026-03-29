# Roadmap

This roadmap is for the future external area editor only.

Phase 0 and Phase 1 are complete. Later phases remain planned work.

## Phase 0: Documentation And Boundary Lock (Completed)

Goal:

- define scope
- define data boundary
- document the separation from the runtime

Exit criteria:

- this folder exists
- future agents can understand the intended direction from docs alone

## Phase 1: Read-Only Project Browser (Completed)

Goal:

- open a project
- discover area files
- inspect an area in read-only form

Deliverables:

- manifest loading
- area discovery
- tileset discovery
- basic area rendering or structured inspection

Implemented in the current tool:

- PySide6 app shell with docked panels
- read-only browsing for areas, entity templates, dialogues, commands, and assets
- area loading into a zoomable, pannable tile canvas
- layer/entity visibility toggles plus grid toggle
- entity markers and template sprite previews
- focused automated tests for manifest loading, asset resolution, and area documents

## Phase 2: Tabbed Document Area (Completed)

Goal:

- open multiple documents simultaneously in tabs
- view any content type (areas, templates, dialogues, commands, assets)

Implemented:

- central QTabWidget replacing single-canvas layout
- double-click in side panels opens document in a tab (or focuses existing)
- right-click context menu with "Open" on all side panels
- closable, reorderable, middle-click-closable tabs
- area tabs render in the existing tile canvas with full zoom/pan
- entity templates, dialogues, and commands open in a read-only JSON viewer
- image assets open in a zoomable preview with checkerboard transparency
- layer panel contextually binds to whichever area tab is active
- welcome page shown when no tabs are open
- tab deduplication (re-opening same content focuses existing tab)

## Phase 3: Tile And Cell Editing

Goal:

- edit room layout safely

Deliverables:

- layer selection
- tile painting
- erase/replace actions
- walkability or cell-flag editing
- save with preservation guarantees

## Phase 4: Entity Placement And Movement

Goal:

- manage room entities without hand-editing placement JSON

Deliverables:

- place entity from template
- move entity
- delete entity
- reorder stack or layer-related fields
- id generation assistance

## Phase 5: Inspector And Entity References

Goal:

- make common per-instance edits comfortable

Deliverables:

- basic inspector
- selected parameter editing
- entity-reference picker widgets
- broken-reference warnings

## Phase 6: Raw JSON Escape Hatches

Goal:

- avoid blocking advanced authored data

Deliverables:

- controlled raw JSON view or editor for advanced fields
- preservation tests for unknown data

## Phase 7: Validation And Runtime Handoff

Goal:

- shorten the edit-test loop without coupling to the runtime

Deliverables:

- lightweight validation
- optional external runtime launch for the current project/area
- clearer save/test workflow

## Phase 8: Quality Pass

Possible later improvements:

- undo/redo
- better large-map ergonomics
- better tileset browsing
- stronger entity-ref filtering
- project-specific field hints
