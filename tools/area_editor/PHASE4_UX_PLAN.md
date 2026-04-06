# Phase 4 UX/UI Plan

This document defines the concrete UX/UI plan for the first editor catch-up
slice.

It is intentionally focused on:

- the current editor shell
- the next high-value workflows
- the minimum new UI surface needed to support them well

It is not a long-term full UI spec for every future editor feature.

## UX Goal

The first catch-up slice should make this workflow feel natural:

1. open a project
2. open an area
3. paint tiles / edit cell flags / place entities as before
4. select an entity and configure its important exposed fields
5. browse item definitions and adjust item metadata
6. open shared project config such as `shared_variables.json`
7. inspect and edit `global_entities`
8. save and test

The user should feel like they are still using the same editor, just with the
missing modern authoring surfaces now present and discoverable.

## Primary UX Principles

1. **Do not disrupt the existing area workflow.**
   Tile painting, layer selection, and entity selection should still feel like
   the editor's center of gravity.

2. **Prefer discoverable panels over hidden power features.**
   If items and shared variables matter to current projects, they should not be
   effectively hidden behind manual filesystem browsing.

3. **Structured where practical, raw JSON where safer.**
   The first slice should expose the common, high-value fields directly and
   leave complicated or unusual data to guarded JSON editors.

4. **Keep forms calm.**
   Avoid a giant wall of fields. Group them into sections that match how users
   think about the entity or file.

5. **Respect the curated workflow.**
   The UX should make it easy to use the provided library of templates and
   content, not try to become a generic editor for every possible JSON pattern.

## Main Window Layout

The existing main window layout should stay recognizable:

- **Left dock area**:
  content/navigation panels
- **Center**:
  tabbed document area
- **Right dock area**:
  layer panel, render controls, tileset browser
- **Lower-left dock**:
  selected entity inspector

The first slice should extend this layout rather than replace it.

## Left Dock Plan

The left dock should continue to be the main content browser region.

### Existing tabs to keep

- Areas
- Entity Templates
- Dialogues
- Commands
- Assets

### New tab to add

- **Items**

The Items tab should behave like the other content tabs:

- tree view grouped by folders under `item_paths`
- single-click selects
- double-click opens in a central tab
- context menu includes at least `Open`

### Project-level entry points

The first slice also needs discoverable access to:

- `shared_variables.json`
- `project.json`

These do **not** need their own full dock tabs yet.

Preferred first version:

- expose them from the **File** menu and/or a small **Project** menu
- optionally add a lightweight project-content panel later if needed

Reason:

- they are singleton project files, not large content trees
- forcing them into their own always-visible dock tabs may add clutter early

## Central Tab Area

The central tabbed document area remains the main editing surface.

### New tab types needed

- item JSON/editor tab
- shared variables tab
- project manifest tab

### Tab behavior

Use the same interaction model as existing tabs:

- re-open focuses existing tab
- dirty marker in tab title
- close asks to save if dirty

### First-slice editing style

For the first catch-up slice:

- **areas** keep their existing specialized canvas/editor
- **items**, **shared variables**, and **project manifest** may start as
  guarded JSON tabs unless a simple structured editor is clearly worthwhile

This avoids building too many new editor surfaces at once.

## Entity Inspector UX

The selected-entity dock remains the main structured editing surface for placed
entities.

This is the most important UX area in the first slice.

## Entity Inspector Structure

The Fields tab should be reorganized into clearly separated sections.

Recommended order:

1. Identity
2. Position
3. Physics / Interaction
4. Visibility
5. Parameters
6. Variables
7. Extra / passthrough summary

The existing raw JSON tab stays as the escape hatch.

## Entity Inspector Sections

### 1. Identity

Fields:

- `id`
- `template` (read-only label, optional `Open Template` button later)
- `kind`
- `tags`

UX notes:

- `tags` can be a simple comma-separated field in the first version
- avoid fancy chip editors unless they are cheap to implement

### 2. Position

Keep and extend the existing position widgets:

- `space`
- `x`, `y`
- `pixel_x`, `pixel_y`
- `facing`

UX notes:

- continue honoring the existing world vs screen-space distinction
- keep screen-space behavior consistent with the current editor rules

### 3. Physics / Interaction

Fields:

- `solid`
- `pushable`
- `weight`
- `push_strength`
- `collision_push_strength`
- `interactable`
- `interaction_priority`

UX notes:

- booleans should be checkboxes
- numeric values should be spinboxes
- labels should stay plain-language where possible

### 4. Visibility

Fields:

- `present`
- `visible`
- `entity_commands_enabled`

These should remain simple booleans.

### 5. Parameters

This remains one of the highest-value sections.

Behavior:

- show parameter fields derived from the selected template
- use plain text fields in the first slice
- keep this compatible with later reference-picker upgrades

UX notes:

- parameter labels should use the actual parameter names
- missing template should show a clear warning
- do not over-interpret parameter meanings in this slice

### 6. Variables

Add a simple variables table:

- key column
- value column
- add row
- remove row

Value handling:

- parse string / number / boolean / simple JSON
- preserve unknown or more complex values safely

UX notes:

- this is meant for practical exposed variables, not deep schema editing
- if something looks unusual, the raw JSON tab remains the better tool

### 7. Extra / passthrough summary

Optional first-slice behavior:

- show a read-only preview of extra unknown fields
- make it obvious that more data exists even if not surfaced structurally

This is helpful for trust, but not mandatory for the first implementation.

## Raw JSON Tab UX

The raw JSON tab should remain available and clearly framed as:

- advanced editing
- escape hatch
- exact file/entity representation

It should not feel hidden or discouraged.

But the structured fields tab should be the default landing place for routine
workflow.

## Items UX

The first slice needs item support, but it does not need a huge dedicated item
designer yet.

### Items panel

Location:

- left dock as a new peer tab beside Areas/Templates/Dialogues/Commands/Assets

Behavior:

- browse all item files under `item_paths`
- folder tree layout consistent with other file panels
- later can add icons/previews if useful

### Item editing

First version recommendation:

- open items in guarded JSON tabs
- if one tiny structured helper is added later, it should focus on:
  - `name`
  - `description`
  - `icon`
  - `portrait`
  - `max_stack`
  - `consume_quantity_on_use`

But the first implementation does **not** require a full structured item form.

Reason:

- the most urgent gap is discoverability and access
- a safe JSON tab is already valuable

## Shared Variables UX

`shared_variables.json` is a project-level singleton file.

### Access path

Preferred first version:

- open through menu action such as:
  - `File -> Open Shared Variables`
  - or `Project -> Shared Variables`

### Editing style

First version:

- guarded JSON editor tab

Later structured helpers can be added for:

- display size
- dialogue UI presets
- inventory UI presets

But the first slice does not need a full preset designer.

## Project Manifest / Global Entities UX

`project.json` is also a singleton, but `global_entities` specifically deserves
attention.

### Access path

Preferred first version:

- menu action to open `project.json`
- plus a specific action or focused UI path for `global_entities`

### First version recommendation

Do **not** try to build a giant project-settings editor immediately.

Instead:

1. make `project.json` easy to open in a guarded editor
2. add a focused `global_entities` editing path if practical

Good first UX for `global_entities`:

- simple list of global entities
- select one
- reuse entity-style editing model where possible

If this reuse is too large for the first slice, then:

- allow `project.json` editing first
- defer the dedicated globals UI to the next iteration

## Reference Picker UX

Reference pickers are important, but they do **not** need to land in the first
implementation slice.

Still, the UX should be prepared for them.

That means:

- parameter fields should stay easy to replace later
- labels should be clear
- field layout should leave space for future picker buttons or dropdowns

## Menu / Action Plan

The first slice should add a few explicit open actions:

- Open Project
- Save
- Open Shared Variables
- Open Project Manifest

Optional if easy:

- Open Global Entities

These actions make project-level data discoverable without needing a new large
navigation subsystem yet.

## Save Feedback

The existing calm save behavior should continue.

Desired behavior:

- success message stays lightweight
- save failures are concrete and local
- dirty tabs remain obvious

## Error Messaging

Keep concrete wording.

Good examples:

- missing item file
- duplicate entity id
- failed to parse JSON field value
- template not found for selected entity

Avoid vague “invalid state” type messaging.

## First-Slice Non-Goals

Do **not** include these in the first UX implementation:

- full structured dialogue editor
- full structured project manifest editor
- generic template creation wizard
- full arbitrary visual-stack editor
- rich inheritance/override badge system
- runtime launch button
- validation dashboard
- command visual editor

## UX Success Criteria

The first slice is a UX success if:

- items are easy to find and open
- shared variables are easy to find and open
- project/global editing is no longer hidden
- selected entities expose enough important fields to avoid frequent raw JSON edits
- the editor still feels coherent rather than overloaded

## Recommended Implementation Sequence

1. add items browser tab
2. add shared variables / project open actions
3. extend entity fields tab with the new grouped sections
4. add variables table
5. wire save/dirty behavior through the new tabs
6. add focused tests

## Future UX Follow-Up

After this slice, the next UX-focused plan should probably cover:

- reference pickers
- dedicated `global_entities` editor surface
- structured item editor
- structured shared UI preset editor

Those are good next steps, but they should not block this first catch-up slice.
