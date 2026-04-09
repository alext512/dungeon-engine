# Roadmap

This roadmap is for the external editor.

Phases 0-3 are complete, and meaningful parts of later phases have also landed
out of order. Treat this document as a status-aware roadmap: some later slices
below are already partially or substantially implemented, while the remaining
notes describe the gaps still worth closing.

The guiding goal is to let a non-coder build a full game through the supported
template-driven workflow while keeping raw JSON escape hatches for advanced
users. The editor does not need to visually expose every arbitrary JSON shape
the runtime can express.

## Phase 0: Documentation And Boundary Lock (Completed)

Goal:

- define scope
- define data boundary
- document the separation from the runtime

## Phase 1: Read-Only Project Browser (Completed)

Goal:

- open a project
- discover area files
- inspect an area in read-only form

Implemented:

- manifest loading
- area discovery
- tileset discovery
- basic area rendering and structured inspection

## Phase 2: Tabbed Document Area (Completed)

Goal:

- open multiple documents simultaneously in tabs
- view any content type the editor currently supports

Implemented:

- central tabbed document area
- tab deduplication and close controls
- area tabs, JSON viewer tabs, and image preview tabs

## Phase 3: Tile And Cell Editing (Completed, In Active Use)

Goal:

- edit room layout safely

Implemented:

- preservation-safe saving for edited area tabs
- canvas-based `cell_flags` editing with dirty tracking
- tileset browser panel with visual tile grid and dropdown
- active layer selection in layer panel
- tile paint mode with left-click paint, right-click erase, and Alt+click eyedrop
- ghost tile preview during paint mode
- mutually exclusive edit modes
- per-area tileset browser population on tab switch

Current reality note:

- the editor is usable for area-centric work
- the runtime has moved ahead in other authoring surfaces
- the next practical work is a catch-up slice for item definitions,
  `shared_variables.json` / UI preset editing, `global_entities`, and better
  configuration of placed entities

## Phase 4: Placed Entity Catch-Up

Goal:

- make placed-entity configuration comfortable for the supported workflow
- expose the highest-value fields authors actually need when using the provided
  template library

Current status:

- substantially implemented through structured entity-instance editing,
  template-parameter editing, variable editing, render-property editing, and
  guarded raw JSON fallback tabs
- the main remaining gaps are broader structured coverage for newer
  engine-owned fields plus better direct manipulation workflows such as drag to
  move and richer screen-space editing polish

Deliverables:

### 4a. Expand the existing fields inspector

Add structured widgets for the most commonly authored entity fields:

- `kind`
- `tags`
- `facing`
- `solid`
- `pushable`
- `weight`
- `push_strength`
- `collision_push_strength`
- `interactable`
- `interaction_priority`
- `present`
- `visible`
- `entity_commands_enabled`
- existing render-order fields

Keep the current raw JSON tab as the escape hatch for anything deeper.

### 4b. Better template-parameter editing

- show template parameters with labeled fields
- make these the main way non-coders configure provided templates
- leave unusual parameter structures to raw JSON

### 4c. Simple variables editor

- key-value editing for practical exposed variables
- add/remove rows
- basic type handling for string, number, boolean, and simple JSON values

### 4d. Basic asset/sprite selection where relevant

- asset picker for practical sprite/path choices
- simple preview where that can be done safely
- do not try to become a full arbitrary visual-stack editor yet

Exit criteria:

- a non-coder can configure the common placed-entity cases without touching raw JSON
- template parameters are much easier to edit
- common exposed variables are editable
- save/load round-trip remains safe

## Phase 5: Reference Pickers And Content Browsing

Goal:

- replace high-friction free-text references with contextual pickers
- make browsing of supported content types much easier

Current status:

- partially implemented through file-backed browsers for areas, templates,
  items, dialogues, commands, assets, and folders
- reference-aware rename/move operations already exist for file-backed content
- the biggest remaining gaps are richer in-form contextual pickers and clearer
  broken-reference surfacing inside editing panels

Deliverables:

### 5a. Entity reference picker

- pick an entity id from the current area
- show id plus helpful context such as template or position
- highlight broken references

### 5b. Template picker

- browse the provided template library
- show template ids and sprite thumbnails where available

### 5c. Area picker

- browse `area_paths`
- support area ids and entry-point follow-up selection

### 5d. Item picker

- browse `item_paths`
- show item id, name, and icon where available

### 5e. Asset and dialogue pickers

- file pickers scoped to project content roots
- previews where practical

### 5f. Conservative reference heuristics

Start with:

- hardcoded known engine fields
- common parameter-name patterns

Do not over-assume that every matching string is a reference.

Exit criteria:

- lever-to-gate and similar wiring no longer require raw id typing in common cases
- broken references are surfaced clearly

## Phase 6: Supported Content Editing

Goal:

- support the high-value content types needed by the curated workflow

Current status:

- partially implemented through structured item, template, project-manifest,
  shared-variables, global-entity, and entity-instance editing surfaces
- guarded JSON tabs cover dialogue/menu and command payload editing today
- the remaining gaps are richer structured dialogue/menu editing and continued
  workflow polish around newer authoring surfaces

Deliverables:

### 6a. Item-definition support

- items browser panel
- open item files in tabs
- structured editing for supported item fields such as:
  - `name`
  - `description`
  - `icon`
  - `portrait`
  - `max_stack`
  - `consume_quantity_on_use`
- raw JSON escape hatch for advanced item behavior

### 6b. Dialogue/menu data support

- easier browsing of dialogue/menu files
- structured editing for the most common dialogue data where practical
- raw JSON remains available for advanced or unusual dialogue structures

### 6c. New area creation

- create a new area file with basic geometry and default layers
- open it immediately for editing

### 6d. Template-library support

- improve browsing and usability of the provided template library
- keep generic free-form template authoring out of the first catch-up slice

Exit criteria:

- non-coders can handle routine item and dialogue work without hand-writing JSON everywhere
- creating a new area is comfortable

## Phase 7: Project-Level Editing

Goal:

- support the selected project-level configuration that currently still needs
  hand-editing

Current status:

- substantially implemented through structured project-manifest,
  shared-variables, and global-entity editors plus guarded raw JSON fallbacks
- the main remaining gaps are deeper coverage for some newer runtime-owned
  fields and smoother project-wide workflow integration

Deliverables:

### 7a. Project manifest editing

Structured editing for practical `project.json` fields such as:

- `startup_area`
- content-path lists
- `shared_variables_path`
- `save_dir`
- `debug_inspection_enabled`

### 7b. Global entities

- inspect and edit `global_entities`
- use the same general editing model as placed entities where practical

### 7c. Input targets

- edit project-level and area-level input routing

### 7d. Shared variables and UI presets

- open and edit `shared_variables.json`
- provide structured support for the current important engine-read keys, especially:
  - `display.internal_width`
  - `display.internal_height`
  - `movement.ticks_per_tile`
  - `dialogue_ui`
  - `inventory_ui`

### 7e. Entry points and camera defaults

- better structured editing for area `entry_points`
- better structured editing for area `camera`

Exit criteria:

- the common project-level settings can be handled without casual raw JSON editing

## Phase 8: Runtime Integration And Content Management

Goal:

- shorten the edit-test loop
- reduce filesystem-only workflows

Current status:

- partially implemented through reference-aware rename/move workflows, guarded
  delete flows with usage previews, folder operations, and area duplication
- the largest remaining gap in this phase is runtime launch/handoff integration

Deliverables:

### 8a. External runtime launch

- launch the runtime as an external process
- support project-wide and area-focused launch
- consider auto-save before launch

### 8b. Rename and move with reference updating

- rename or move areas, templates, items, and commands
- use preview plus targeted replacement
- do not assume blind text replacement is always safe

### 8c. Duplicate and delete helpers

- duplicate supported content
- delete with reference warnings where practical

### 8d. Optional project creation helper

- bootstrap a new project folder with the expected structure

Exit criteria:

- the edit-test loop is much shorter
- common rename/move workflows are safer than manual filesystem edits

## Phase 9: Quality Pass

Goal:

- polish the editing experience for sustained content production

Possible later improvements:

- undo/redo
- multi-entity selection
- drag-to-move entities
- better search and filtering
- better tileset ergonomics
- validation panel
- stronger large-map ergonomics
