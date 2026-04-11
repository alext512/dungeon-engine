# Identity And Persistence Catch-Up Plan

This document defines the next focused editor catch-up slice after the runtime
entity identity and persistence refactor.

The runtime now enforces project-wide unique entity ids and supports authored
entity/template persistence policies. The editor needs a practical authoring
surface for both.

## Goal

Bring the editor in line with the new engine rules without widening scope into
full project-level content editing yet.

After this slice:

- the editor should help prevent invalid duplicate entity ids across the whole
  project
- newly placed entities should get safe ids that already respect project-wide
  uniqueness
- entity instances and entity templates should expose the new `persistence`
  authoring surface without forcing raw JSON for the common case

## Scope

This slice covers:

1. project-wide entity id validation for area entities
2. project-wide safe id generation for newly placed area entities
3. structured/focused persistence editing for entity instances
4. structured/focused persistence editing for entity templates

This slice does **not** cover:

- automatic reference rewriting when an entity id changes
- first-class editing of `global_entities`
- project-wide rename/move helpers
- persistence editing for `global_entities`
- new command-chain builder workflows
- asset picker polish

## Current Gaps

The editor currently:

- validates entity ids only inside the active area
- generates new ids only against the active area's entities
- does not expose `persistence` in any structured editor surface

That is now behind the runtime contract.

## Runtime Reality The Editor Must Match

### 1. Entity Ids Are Project-Wide Unique

Area entities must not collide with:

- other area entities in any area
- project `global_entities`

The editor must treat this as a hard rule, not a suggestion.

### 2. `persistence` Is Authored On Entities And Templates

The runtime accepts:

```json
"persistence": {
  "entity_state": true,
  "variables": {
    "shake_timer": false,
    "times_pushed": true
  }
}
```

The runtime deep-merges template data with instance data. That means an entity
instance can author a partial `persistence` block that augments or overrides a
template's defaults.

## Product Principles

### 1. Fail Early On Invalid Duplicate Ids

The editor should surface duplicate ids before the user gets all the way to
runtime validation.

### 2. Prefer Simple Controls First

For persistence, the common high-value control is:

- whether the entity's general state is persistent

Variable-specific persistence overrides are still important, but they fit best
as a focused JSON subsection rather than a big custom variable-policy table in
the first pass.

### 3. Keep Raw JSON Available

Raw JSON remains the fallback for anything more advanced than the supported
surface.

## Workstream 1: Project-Wide Entity Id Index

Add one editor-side project entity index helper.

Recommended responsibility:

- scan all discovered areas
- collect area entity ids with their owning area id and file path
- collect project `global_entities` ids from the manifest
- allow open in-memory area docs to override the on-disk area view when needed

Recommended output shape:

- `entity_id -> one or more ownership records`

Ownership record needs enough detail for clear errors, for example:

- kind: `area_entity` or `global_entity`
- area_id when applicable
- file path when applicable

### Why On-Demand Is Fine First

For this first pass, correctness matters more than caching cleverness.

A simple on-demand rebuild is acceptable if it keeps implementation safer and
lets validation reflect unsaved open tabs correctly.

If needed later, this can be cached and incrementally updated.

## Workstream 2: Project-Wide Id Validation UX

### A. Area Entity Apply/Save Validation

When the user applies changes to a selected entity instance:

- reject blank ids
- reject ids that collide with any other area entity anywhere in the project
- reject ids that collide with any `global_entity`

Error messages should name the conflicting location clearly, for example:

- `Entity id 'player_main' is already used by area 'areas/village_square'.`
- `Entity id 'dialogue_controller' is already used by a project global entity.`

### B. New Entity Placement

When placing a new world-space or screen-space entity:

- generate the id against the full project entity index
- not just the current area

### C. Rename Behavior

For this slice, renaming an entity id is allowed if the new id is unique.

The editor should **not** attempt automatic reference updates yet.

Recommended first-pass behavior:

- allow the rename
- validate uniqueness strictly
- do not add a rename-preview system yet

Optional nice note later:

- warn that changing ids may require reference updates elsewhere

That warning is useful, but it is not required to ship the first catch-up pass.

## Workstream 3: Entity Instance Persistence Surface

Extend the existing entity instance structured editor with a `Persistence`
section.

### Recommended V1 Surface

Structured field:

- `entity_state` checkbox

Focused JSON block:

- `variables`

Recommended authored result:

- if checkbox is off and the variables JSON block is empty, omit
  `persistence` from authored JSON
- if checkbox is on, write:

```json
"persistence": {
  "entity_state": true
}
```

- if variable overrides are present, write:

```json
"persistence": {
  "entity_state": false,
  "variables": {
    "times_pushed": true
  }
}
```

### Validation

- persistence block must be a JSON object if present
- `variables` subsection must be a JSON object
- variable names must be non-blank strings
- variable values must be booleans

### Merge Note

Because template + instance data deep-merge at runtime, the instance editor can
author only the instance-side `persistence` block. It does **not** need to
compute the fully resolved final runtime policy in this first pass.

A small helper note in the UI would be good:

- template defaults may also contribute to the final effective persistence

That note is helpful but optional for the first implementation pass.

## Workstream 4: Entity Template Persistence Surface

Extend the current template editor beyond `visuals` only.

### Recommended V1 Template Editor Shape

Keep the current focused template surface modest:

- summary fields already shown
- `visuals` JSON block
- `persistence.entity_state` checkbox
- `persistence.variables` JSON block
- raw JSON remains available as a sibling section tab

This keeps the editor aligned with the "focused surface + raw JSON fallback"
direction rather than turning template editing into a giant bespoke form.

### Validation

Same rules as the instance editor:

- variable overrides must be a JSON object
- keys must be non-blank
- values must be booleans

## Workstream 5: Tests

Add focused editor coverage around:

### Entity Instance Tests

- building an entity from fields with persistence omitted
- writing `entity_state: true`
- writing variable override JSON
- rejecting invalid persistence variable JSON

### Main Window / Integration Tests

- duplicate id rejection against another area
- duplicate id rejection against a project global entity
- new placed entity id generation avoiding ids used in other areas

### Template Editor Tests

- editing and saving template persistence through the focused editor
- invalid persistence JSON warning path

## Proposed Implementation Order

1. add project entity index helper
2. update area-entity id generation to use the project index
3. upgrade area-entity apply validation to use project-wide uniqueness
4. add entity-instance persistence surface
5. extend template editor with persistence
6. add/update tests

## Non-Goals And Intentional Deferrals

- no automatic id-reference rewrite flow yet
- no global-entities structured persistence editor yet
- no per-variable custom widget table for persistence overrides
- no inline project-wide validation panel yet

## Exit Criteria

This slice is done when:

- the editor no longer generates area-local ids that are invalid project-wide
- entity-instance edits cannot save/apply duplicate ids that violate the engine
  rule
- entity instances can author the new persistence policy without raw JSON in
  the common case
- entity templates can author the new persistence policy without dropping raw
  JSON access
