# Area And Screen-Space Workflows Plan

This document defines the next concrete editor implementation slice after the
focused JSON surfaces work.

The goal is to unlock full-slice authoring through the editor without adding
generic import systems or a dedicated title-screen subsystem.

## Scope

This slice covers three things:

1. new area creation
2. directional area growth/shrink tools
3. screen-space entity creation and placement

This slice explicitly does **not** cover:

- project import or content-pack import
- generic asset-import workflows
- dedicated main-menu support
- dedicated title-screen support
- broad new-project scaffolding
- tile-size migration for existing areas

The expected title-screen workflow remains:

- start from a project that already contains suitable templates/content
- create or open the startup/title area
- place and arrange screen-space entities visually
- configure those entities through the existing editor surfaces

## Product Goal

After this slice, a user should be able to:

- create a new area from inside the editor
- expand an area in controlled directions without hand-editing JSON
- place screen-space entities visually in the screen pane
- build a simple title/start screen from reusable screen-space templates

This should be enough to make a real playable slice feel practical, even before
new-project creation and import workflows exist.

## UX Principles

1. prefer explicit directional operations over abstract resize math
2. keep area creation simple and opinionated
3. reuse the current paint/select/editor mental model where possible
4. treat screen-space entities as normal entities with different placement rules
5. do not special-case title screens in the editor UI

## Workstream 1: New Area Creation

## UX

Add a `New Area...` action.

Preferred menu placement:

- `File > New Area...`

The action should be enabled only when a project is open.

Opening the action should show a small modal dialog with:

- `area_id`
- `display_name`
- `width`
- `height`
- `tile_size`
- `include_default_ground_layer`

Recommended defaults:

- `area_id`: empty
- `display_name`: empty
- `width`: `20`
- `height`: `15`
- `tile_size`: current project/common default or `16`
- `include_default_ground_layer`: checked

Validation:

- `area_id` must be non-empty
- `area_id` must resolve inside one configured `area_paths` root
- target file must not already exist
- width and height must be `>= 1`
- tile size must be `>= 1`

On success, the editor should:

1. create the area JSON file
2. refresh the Areas panel
3. open the new area immediately
4. highlight it in the Areas panel

## File Shape

The generated area should be conservative and predictable.

Recommended baseline:

```json
{
  "name": "My Area",
  "tile_size": 16,
  "tilesets": [],
  "tile_layers": [
    {
      "name": "ground",
      "render_order": 0,
      "y_sort": false,
      "stack_order": 0,
      "grid": [[0]]
    }
  ],
  "entities": [],
  "variables": {}
}
```

The `grid` should be created to the requested width and height.

If `include_default_ground_layer` is unchecked:

- `tile_layers` should start as an empty list

## Implementation Notes

- add a helper that builds a valid `AreaDocument`
- reuse existing area-save path instead of writing ad hoc JSON strings
- prefer creating the document in memory and then calling `save_area_document`

## Tests

Add tests for:

- successful creation of a new area file
- duplicate area id rejection
- new area appears in the Areas panel
- created area opens immediately
- created area has expected width/height/tile size/layer defaults

## Workstream 2: Directional Area Growth/Shrink

## UX

Do **not** start with one generic resize dialog.

Instead, add explicit directional actions:

- `Area > Add Rows Above...`
- `Area > Add Rows Below...`
- `Area > Add Columns Left...`
- `Area > Add Columns Right...`
- `Area > Remove Top Rows...`
- `Area > Remove Bottom Rows...`
- `Area > Remove Left Columns...`
- `Area > Remove Right Columns...`

All actions should be enabled only when an area tab is active.

Each action should open a very small dialog with:

- count to add/remove
- confirmation text when the action can discard tiles or move entities

Recommended first-pass behavior:

- preserve the top-left origin semantics of the existing area model
- add/remove only in the explicitly chosen direction

## Semantics

### Add Rows Above

- prepend empty rows to every tile layer grid
- shift every world-space entity `grid_y += count`
- keep screen-space entities unchanged

### Add Rows Below

- append empty rows to every tile layer grid
- keep all entities unchanged

### Add Columns Left

- prepend empty cells to each row in every tile layer
- shift every world-space entity `grid_x += count`
- keep screen-space entities unchanged

### Add Columns Right

- append empty cells to each row in every tile layer
- keep all entities unchanged

### Remove Top Rows

- remove rows from the top of every tile layer
- shift every surviving world-space entity `grid_y -= count`
- warn and block if any world-space entity would become out of bounds

### Remove Bottom Rows

- remove rows from the bottom of every tile layer
- warn and block if any world-space entity would become out of bounds

### Remove Left Columns

- remove columns from the left of every tile layer
- shift every surviving world-space entity `grid_x -= count`
- warn and block if any world-space entity would become out of bounds

### Remove Right Columns

- remove columns from the right of every tile layer
- warn and block if any world-space entity would become out of bounds

## Failure Policy

For V1, removal should be conservative:

- if the operation would push any world-space entity out of bounds, block it
- do not silently delete or clamp entities

This is safer and easier to reason about than destructive truncation.

Tiles may be discarded by removal actions because that is the point of the
operation, but the dialog should make that clear.

## Implementation Notes

- add pure document-level helpers for each directional operation
- update all tile layers consistently
- world-space entities use `grid_x` / `grid_y`
- screen-space entities are unaffected by grid growth/shrink
- after mutation:
  - refresh canvas
  - keep active tab dirty
  - refresh status text if needed
  - refresh selection if selected entity moved

## Tests

Add tests for:

- add rows above shifts world-space entities down
- add columns left shifts world-space entities right
- add rows below / add columns right leave entities unchanged
- screen-space entities remain unchanged in all operations
- removal operations block when they would push entities out of bounds
- layer grids resize correctly

## Workstream 3: Screen-Space Entity Creation And Placement

## Goal

Make it practical to build title/start screens and other UI-like scenes using
ordinary screen-space entity templates.

The editor should not gain a special title-screen mode.

## Current Foundation

The editor already supports:

- rendering the screen pane
- selecting existing screen-space entities
- nudging screen-space entities by pixels

The missing part is comfortable creation/placement.

## UX

The workflow should mirror the existing entity-brush idea as much as possible.

### Template Selection

When the user clicks a template in the Templates panel:

- if the template is world-space, current world placement behavior stays the same
- if the template is screen-space, the editor should still enter entity-placement mode

Current limitation to remove:

- screen-space templates should no longer be treated as unsupported for creation

### Placement

When a screen-space template brush is active:

- clicking in the screen pane places a new screen-space entity
- placement should set:
  - `space: "screen"` effectively through template or instance semantics
  - `pixel_x`
  - `pixel_y`
- world-grid cells should not be involved

### Positioning Rule

Use the clicked screen-pane pixel as the initial placement origin.

For V1, do not try to center based on sprite bounds or image dimensions.

That means:

- placement is simple
- later nudging refines the exact composition

### Selection And Movement

Once placed, screen-space entities should continue to support:

- selection in the screen pane
- pixel nudging

If feasible in this slice, add drag-move in the screen pane.

If drag-move is not trivial, it is acceptable to defer it and rely on:

- click-to-place
- select
- keyboard/menu nudging

### Editor Feedback

When a screen-space brush is active:

- the status bar should clearly show the selected template
- the screen pane hover/click region should feel active
- unsupported suffixes for screen templates should be removed once placement is supported

## Data Semantics

Placement of a screen-space entity should:

- create a new entity instance with generated id
- preserve the selected template id
- write `pixel_x` / `pixel_y`
- not write `grid_x` / `grid_y`

Any template parameters still behave normally.

## Generated Ids

Use the same general unique-id generation strategy as existing entity placement.

If the template basename is `title_logo`, examples may become:

- `title_logo_1`
- `title_logo_2`

Consistency matters more than exact naming.

## Implementation Notes

- extend current entity-brush support checks so screen-space templates can be placed
- add a dedicated canvas signal or adapt the existing placement signal to carry
  screen-space coordinates when placement happens in the screen pane
- keep world placement and screen placement paths separate enough to stay clear
- reuse existing `place_entity`-style helpers where practical, but do not force
  screen placement through grid-cell semantics

## Tests

Add tests for:

- selecting a screen-space template enables placement rather than reporting unsupported
- clicking in the screen pane creates a new entity with the chosen template
- created entity gets pixel coordinates
- created entity does not get world-grid coordinates
- created screen-space entity becomes selectable afterward

## Suggested Implementation Order

1. `New Area...`
2. directional grid-growth helpers and UI
3. screen-space entity placement

Why this order:

- new-area creation is the smallest and safest standalone feature
- directional area growth/shrink is well-bounded document work
- screen-space placement is the most interaction-heavy and benefits from the
  earlier area workflow improvements already being stable

## Non-Goals For This Slice

- no project import/content-pack import
- no dedicated title-menu editor
- no area-template system
- no asset-picking helpers unless they become trivially reusable during the work
- no broad new-project wizard
- no tile-size migration for existing areas

## Exit Criteria

This slice is complete when:

- a user can create a new area from the editor
- a user can grow/shrink area bounds from explicit directional actions
- a user can place new screen-space entities visually from templates
- the full editor suite stays green
- sample title/start-screen style content becomes practical without raw JSON for
  the basic placement workflow
