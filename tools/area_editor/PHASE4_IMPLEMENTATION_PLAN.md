# Phase 4 Implementation Plan

This document turns the editor catch-up direction into a concrete first
implementation slice.

It is intentionally narrower than the long-term roadmap. The goal is to unlock
the highest-value authoring workflows without turning the editor into a second
runtime or a generic visual editor for every possible JSON shape.

## Goal

Make the editor good enough for the current supported workflow:

- build areas visually
- place entities from a provided template library
- configure the most important exposed entity fields and parameters
- browse and edit item definitions
- browse and edit `shared_variables.json`
- inspect and edit `global_entities`
- keep raw JSON available for advanced or unusual cases

This phase should make it noticeably easier to build a small real game slice
without needing to hand-edit JSON for routine work.

## Product Boundary

This plan assumes the intended editor workflow is:

- authors work mostly with a curated library of existing templates and items
- the editor exposes selected fields, variables, references, and asset choices
- the editor does not need to visually support every arbitrary JSON structure
- raw JSON remains the escape hatch for advanced/custom authoring

That means the first implementation should optimize for:

- practical leverage
- preservation-safe editing
- controlled exposure of important fields

Not for:

- perfect generic completeness
- full command authoring UI
- runtime simulation
- free-form entity system design

## First-Slice Scope

The first slice includes four concrete workstreams:

1. manifest/content-browser catch-up
2. placed-entity inspector catch-up
3. project-level JSON catch-up
4. focused tests and preservation checks

## Workstream 1: Manifest And Browser Catch-Up

### Why

The editor currently knows about:

- areas
- entity templates
- dialogues
- commands
- assets

But the runtime/project contract now also relies heavily on:

- `item_paths`
- `shared_variables.json`
- `global_entities`

So the browser surface is behind the runtime.

### Deliverables

#### 1a. Manifest support

Extend `area_editor/project_io/project_manifest.py` to expose:

- `item_paths`
- `shared_variables_path`
- raw access to `global_entities`

The editor still must not import `dungeon_engine`; it should replicate only the
needed manifest/path behavior locally.

#### 1b. New browser surfaces

Add new content entry points in the main window:

- **Items panel**
  - browses all files under `item_paths`
  - opens item JSON in tabs
- **Shared Variables entry**
  - opens the configured `shared_variables.json` in a tab
  - if no file exists, the entry is absent or disabled
- **Project/Globals entry**
  - at minimum, exposes a path into `project.json` editing
  - later can become its own focused panel

#### 1c. New document content types

Extend the central tab model to support:

- item definition tabs
- shared variables tab
- project manifest tab

These can initially reuse the existing guarded JSON viewer until a more
structured editor is added.

### UX

- Items should live beside existing left-dock content panels.
- Shared variables and project manifest should be openable from a predictable
  place, not hidden behind filesystem browsing only.
- The first version does not need creation wizards yet; opening and editing
  existing files is enough.

## Workstream 2: Placed Entity Inspector Catch-Up

### Why

The current structured entity editor is still biased toward early area editing:

- id
- position
- template
- parameters

But real current projects now frequently need structured access to things like:

- `kind`
- `tags`
- `facing`
- `solid`
- `pushable`
- `interactable`
- visibility/presence toggles
- practical exposed variables

### Principle

This workstream should expose the **highest-value common fields** only.

Do not try to fully model:

- all possible nested visuals
- all command payloads
- all template inheritance behavior
- every engine-owned field just because it exists

### Deliverables

#### 2a. Structured top-level fields

Extend the existing Fields tab with simple widgets for:

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

Keep the current position and render-order fields.

#### 2b. Better parameter editing

Continue treating template parameters as first-class.

Improve them by:

- keeping labels derived from parameter names
- preserving nontrivial values safely
- preparing for future reference pickers, but not blocking on them

#### 2c. Simple variables table

Add a practical `variables` editor:

- list rows of key/value pairs
- add/remove rows
- parse simple values as:
  - string
  - number
  - boolean
  - JSON for complex values

This should be presented as a convenience layer over the real JSON, not a
perfect semantic variable system.

#### 2d. Asset choice where it matters

Where the selected instance or its parameters expose simple asset-driven choices,
support:

- picking an asset path from project assets
- lightweight preview if available

This should be narrow and practical, not a full arbitrary visuals editor yet.

### UX

The Fields tab should remain calm and scannable.

Recommended grouping:

- Identity
- Position
- Physics / Interaction
- Visibility
- Parameters
- Variables
- Extra / passthrough preview

Avoid giant flat forms that expose everything equally.

### Raw JSON rule

The existing raw JSON tab remains the escape hatch.

The structured editor must:

- update the JSON model
- preserve unknown fields
- avoid pretending it owns data it does not understand

## Workstream 3: Project-Level Catch-Up

### Why

The runtime now depends more on project-level authored data than the editor
currently exposes conveniently.

The first important targets are:

- `shared_variables.json`
- `global_entities`

### Deliverables

#### 3a. Shared variables editing

The first version can be hybrid:

- guarded JSON editor as the baseline
- optional small structured helpers for especially important known keys later

Initial known high-value keys:

- `display.internal_width`
- `display.internal_height`
- `movement.ticks_per_tile`
- `dialogue_ui`
- `inventory_ui`

But the first slice does not need a full preset designer yet.

#### 3b. Global entities editing

Add a way to inspect and edit `global_entities` from `project.json`.

The first version can be modest:

- list existing global entities
- select one
- reuse the same general editing model as placed entities where possible
- fall back to raw JSON when needed

This is important because newer UI/menu/controller flows increasingly rely on
global or quasi-global authored entities.

### UX

Do not hide these behind raw file browsing alone.

There should be a discoverable path such as:

- a project-level tab
- or explicit open actions in the main window

## Architecture Changes

### New/expanded editor layers

#### `project_io/`

Extend manifest discovery to understand:

- `item_paths`
- `shared_variables_path`
- enough `project.json` structure to surface `global_entities`

#### `documents/`

If needed, add tool-owned document models for:

- item definitions
- shared variables
- project manifest/global entities

Only add typed document models where they materially help safe structured
editing. Otherwise guarded JSON tabs are acceptable in the first slice.

#### `widgets/`

Likely additions or extensions:

- items browser panel
- project/shared-variables entry point
- expanded entity fields editor widgets
- variables table widget or embedded form section

#### `catalogs/`

Potential new lightweight item catalog later, but do not add one unless it
materially helps the first slice.

### Boundary rules

Still required:

- no `dungeon_engine` imports
- preserve unknown fields
- treat authored JSON as the contract

## UI / UX Details

### Left dock

After this slice, the left side should conceptually expose:

- Areas
- Entity Templates
- Items
- Dialogues
- Commands
- Assets

Project-level files such as `shared_variables.json` and `project.json` can live:

- in a small project section
- or in the File menu / project actions

The exact placement matters less than discoverability.

### Entity editing flow

Expected flow:

1. open area
2. select entity
3. adjust exposed fields/parameters/variables in the Fields tab
4. save area
5. optionally test

This should stay the fastest supported loop.

### Advanced editing flow

Expected flow:

1. open the same entity or file
2. switch to JSON tab
3. make advanced/manual edits
4. save

The structured editor should not block this.

## Testing Plan

This phase should add focused editor tests for:

### Manifest / discovery

- `item_paths` discovery
- shared variables path discovery
- project/global data discovery where applicable

### Main-window integration

- items panel population
- opening item files in tabs
- opening shared variables / project-level docs

### Entity fields editor

- loading new top-level fields
- applying structured changes
- preserving unknown fields
- round-tripping variables edits safely

### Project/global editing

- loading and saving global entities without destructive rewrites
- shared variables round-trip behavior

Run the full editor suite from `tools/area_editor/` after implementation.

## Explicit Non-Goals For This Slice

Do not include these in the first catch-up implementation:

- dialogue visual editor with full segment UI
- generic template authoring system
- command visual editor
- runtime embedding or simulation
- full arbitrary visuals-stack editor
- perfect inheritance/override visualization
- undo/redo
- rename/move reference-updating tools

## Recommended Implementation Order

1. extend manifest/project discovery
2. add items/shared-variables/project document opening
3. add item browser panel
4. expand entity fields editor with top-level fields
5. add simple variables editor
6. add global entities editing path
7. add focused tests
8. polish UX labels and save behavior

## Exit Criteria

This first slice is successful if:

- item definitions are discoverable and editable from the editor
- `shared_variables.json` is discoverable and editable from the editor
- `global_entities` are no longer effectively hidden
- placed entities can be configured through a richer structured inspector
- common current workflows need much less hand-authored JSON
- unknown data still round-trips safely

## Follow-Up After This Phase

Once this slice lands, the next likely implementation plan should cover:

- reference pickers
- better project-level helpers
- runtime launch integration

Those should be separate steps, not silently folded into this one.
