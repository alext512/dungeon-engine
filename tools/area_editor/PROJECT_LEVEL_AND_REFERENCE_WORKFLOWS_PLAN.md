# Project-Level And Reference Workflows Plan

This document defines the next editor workstream after the entity identity and
persistence catch-up slice.

The goal is to finish the highest-value project-level authoring workflows and
then use those as the foundation for safer reference handling and
rename/move-with-updates support.

## Goal

After these phases, the editor should support:

1. practical structured editing for singleton project documents
2. targeted reference pickers for common workflows
3. safe rename/move workflows with previewed reference updates

This should reduce both:

- hand-editing of fragile project config
- manual string-typing for references
- filesystem-only rename/move workflows

## Scope

This plan covers:

1. structured `project.json` editing
2. structured `shared_variables.json` editing
3. targeted reference pickers
4. rename/move with previewed reference updates

This plan does **not** cover:

- a full visual editor for arbitrary UI preset schemas
- generic import/copy systems
- full command-chain builder UI
- runtime in-process simulation

## Guiding UX Principles

### 1. Singleton Project Files Should Open In Central Tabs

`project.json` and `shared_variables.json` are singleton documents, not
browsable collections.

They should continue to open via project-level actions:

- `Project > Open Project Manifest`
- `Project > Open Shared Variables`

and edit in central tabs like other documents.

### 2. Keep Side Panels Focused On Collections

The left browser dock is still best for:

- areas
- templates
- items
- dialogues
- commands
- assets

Singleton project docs should not be forced into the tree just to be editable.

### 3. Prefer Small Structured Surfaces Plus Raw JSON

The next project-level editors should expose only the high-value fields that
are commonly authored and engine-read.

Everything else still keeps a raw JSON escape hatch.

### 4. Reference Pickers Should Be Narrow And Intentional First

Do not try to auto-detect every possible string reference in the project.

Start with:

- explicit engine fields
- a few well-known high-value template parameters

## Phase A: Structured `project.json` Tab

### Why Start Here

This is the smallest project-level surface with immediate payoff.

The editor already opens `project.json` in a central tab. The main missing
piece is replacing raw JSON-only editing for the practical fields.

### Recommended V1 Fields

- `startup_area`
- `debug_inspection_enabled`
- `save_dir`
- `shared_variables_path`

Optional but lower priority in the same surface:

- content-path lists if they stay simple and readable

### Strong Recommendation

`startup_area` should use an area picker instead of free text.

That gives immediate value and creates the first reusable picker pattern.

### Tab Shape

- `Project Settings` structured tab
- `Raw JSON` tab

### Validation

- `startup_area` must resolve to a discovered area id
- `shared_variables_path` should stay inside the project root
- `save_dir` should be non-empty if present

## Phase B: Structured `shared_variables.json` Tab

### Why Next

This is the other singleton project document the editor already opens.

It strongly affects both runtime feel and editor behavior through display size.

### Recommended V1 Fields

- `display.internal_width`
- `display.internal_height`
- `movement.ticks_per_tile`

These are the highest-value fields because they directly affect:

- screen-pane sizing in the editor
- movement feel in the runtime
- project startup defaults

### About UI Presets

Do **not** make broad "UI preset editing" a headline feature yet.

For now:

- keep `dialogue_ui`
- keep `inventory_ui`

as raw/focused JSON only unless a specific painful workflow emerges that
deserves a structured control.

### Tab Shape

- `Shared Variables` structured tab
- `Raw JSON` tab

### Validation

- display dimensions must be positive integers
- movement ticks should be a positive integer

## Phase C: Targeted Reference Pickers

### Why After Project Tabs

Once the editor has a structured project tab and shared-vars tab, the picker
pattern will already exist and can be reused more safely.

### C1. Area Picker

This is the first and most valuable picker.

Use cases:

- `startup_area`
- area-targeting parameters such as door/gate transitions
- `change_area`-like focused editor fields later

### C2. Asset Picker

Use for the most obvious asset-path fields:

- item `icon.path`
- item `portrait.path`
- later maybe focused entity/template visual path fields

### C3. Entity Picker

Start narrowly:

- current-area entity ids only
- for known fields/parameters where the editor already understands the schema

Examples:

- gate/lever wiring in curated templates
- current-area camera/input target choices

### C4. Item And Dialogue Pickers

Useful, but lower priority than area and asset pickers.

Recommended first use:

- specific curated parameter fields
- not broad heuristic replacement of all string editing

### Reference Picker Non-Goal

Do not attempt a universal generic picker for every string in every JSON object
yet.

## Phase D: Rename/Move With Reference Updates

This is important and should be treated as a serious planned workstream, not a
miscellaneous polish task.

### Why It Matters

Without this, the editor still depends on fragile filesystem/manual workflows
for one of the most common maintenance tasks.

### D1. Rename/Move Areas

Changing an area file path changes its area id.

References that need updating include:

- `project.json.startup_area`
- area-targeting parameters
- project commands and area/entity commands that reference area ids
- cross-area persistence-oriented commands/queries
- save data keys that use area ids

### D2. Rename/Move Templates

Changing a template file path changes its template id.

References that need updating include:

- area entity instances using `template`
- `global_entities` using `template`
- `spawn_entity` commands referencing templates

### D3. Rename Area Entity Ids

Area entity ids are now project-wide identities and should be treated more
carefully than before.

References that need updating include:

- same-area input targets
- same-area camera follow
- known template parameters that point at entity ids
- command chains referencing that entity id
- cross-area commands targeting that entity id

### Required Workflow Shape

Use a previewed update flow, not blind automatic replacement:

1. choose rename/move target
2. compute the new id/path-derived id
3. scan the project for candidate references
4. show a preview list
5. apply accepted updates
6. write changed files

### Reusable Machinery Needed

This phase will likely want:

- project-wide content scanner
- targeted reference-match representation
- preview/apply UI

That same machinery can later support:

- find all references
- broken-reference warnings
- duplicate/clone helpers

## Recommended Implementation Order

### Step 1

Structured `project.json` tab:

- `startup_area` picker
- `debug_inspection_enabled`
- `save_dir`
- `shared_variables_path`

### Step 2

Structured `shared_variables.json` tab:

- `display.internal_width`
- `display.internal_height`
- `movement.ticks_per_tile`

### Step 3

Area picker and asset picker as reusable components

### Step 4

Narrow entity/item/dialogue pickers for curated high-value fields

### Step 5

Rename/move with reference updates:

- areas first
- templates second
- entity-id rename third

This order is recommended because:

- project tabs are smaller and unblock immediate workflows
- picker components become reusable infrastructure
- rename/move is important, but it benefits from having picker/scanner
  groundwork and a stronger project-content model first

## Testing Expectations

### Project Tab Tests

- `startup_area` saves correctly through the structured tab
- invalid `startup_area` is rejected clearly
- shared variables fields save back correctly
- raw tab and structured tab stay in sync

### Picker Tests

- area picker returns stable discovered ids
- asset picker writes project-relative paths
- picker-backed save flows update the underlying JSON correctly

### Rename/Move Tests

- rename/move preview lists expected reference hits
- accepted updates rewrite only chosen references
- unchanged references stay unchanged
- affected sample projects still load after updates

## Exit Criteria

This workstream is successful when:

- `project.json` no longer needs casual raw editing for the core startup fields
- `shared_variables.json` no longer needs casual raw editing for display and
  movement basics
- common high-value references stop depending on fragile string typing
- rename/move of key content types becomes a safe editor workflow instead of a
  filesystem-only risk
