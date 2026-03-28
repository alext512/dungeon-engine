# Roadmap

This roadmap is for the future external area editor only.

It does not imply that implementation should start immediately.

## Phase 0: Documentation And Boundary Lock

Goal:

- define scope
- define data boundary
- document the separation from the runtime

Exit criteria:

- this folder exists
- future agents can understand the intended direction from docs alone

## Phase 1: Read-Only Project Browser

Goal:

- open a project
- discover area files
- inspect an area in read-only form

Deliverables:

- manifest loading
- area discovery
- tileset discovery
- basic area rendering or structured inspection

## Phase 2: Tile And Cell Editing

Goal:

- edit room layout safely

Deliverables:

- layer selection
- tile painting
- erase/replace actions
- walkability or cell-flag editing
- save with preservation guarantees

## Phase 3: Entity Placement And Movement

Goal:

- manage room entities without hand-editing placement JSON

Deliverables:

- place entity from template
- move entity
- delete entity
- reorder stack or layer-related fields
- id generation assistance

## Phase 4: Inspector And Entity References

Goal:

- make common per-instance edits comfortable

Deliverables:

- basic inspector
- selected parameter editing
- entity-reference picker widgets
- broken-reference warnings

## Phase 5: Raw JSON Escape Hatches

Goal:

- avoid blocking advanced authored data

Deliverables:

- controlled raw JSON view or editor for advanced fields
- preservation tests for unknown data

## Phase 6: Validation And Runtime Handoff

Goal:

- shorten the edit-test loop without coupling to the runtime

Deliverables:

- lightweight validation
- optional external runtime launch for the current project/area
- clearer save/test workflow

## Phase 7: Quality Pass

Possible later improvements:

- undo/redo
- better large-map ergonomics
- better tileset browsing
- stronger entity-ref filtering
- project-specific field hints
