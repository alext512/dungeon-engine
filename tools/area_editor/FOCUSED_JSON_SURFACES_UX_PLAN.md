# Focused JSON Surfaces UX Plan

This document turns the general `FOCUSED_JSON_SURFACES_PLAN.md` direction into
a concrete editor UX plan.

The purpose is to define:

- where these surfaces live in the editor
- how users move between structured fields, focused JSON blocks, and full raw JSON
- which content types get which editing surfaces first
- what validation and save behavior should feel like

This is a near-term implementation UX plan, not a final long-term UI spec.

## UX Goal

Give authors a comfortable middle path between:

- highly structured field editing
- and opening the entire file as raw JSON

The editor should let a user say:

- "I only want to change a few common properties"
- "I need to tweak this one nested engine-owned block"
- "I want the whole file because I know what I am doing"

without making them feel trapped in any one mode.

## User Model

The intended author ladder is:

1. **Basic author**
   Uses structured fields only.
2. **Intermediate author**
   Uses structured fields plus focused JSON blocks like `visuals`, `icon`, or `portrait`.
3. **Advanced author**
   Opens full raw JSON when needed.

All three should be supported in one coherent UI.

## Core UX Principles

### 1. Full Raw JSON Is Always Visible And Legitimate

Every supported content type should keep an obvious full raw JSON path.

It should feel like:

- a normal advanced tool

not:

- a hidden emergency escape hatch

### 2. Focused JSON Blocks Should Be Small And Named By Engine Schema

The editor should not guess intent from arbitrary template parameter names.

Good focused blocks:

- `visuals`
- `variables`
- `icon`
- `portrait`

Bad focused blocks:

- inferred "sprite settings" based on seeing `$sprite_path`
- guessed "gift settings" from `item_id`

### 3. Structured Fields Stay For The Simple, Frequent Things

Use structured fields when the data is:

- common
- simple
- stable
- low-ambiguity

Use focused JSON when the data is:

- nested
- meaningful
- still small enough to understand in isolation

### 4. The Editor Should Reveal The Layering Clearly

Where possible, the UI should make it clear whether the user is editing:

- top-level structured fields
- a focused nested block
- or the full file/entity JSON

This matters especially for entity instances, where template inheritance exists.

## High-Level Editing Model

For the relevant content types, the editor should converge on this pattern:

### Structured Tab

Used for:

- common properties
- exposed parameters
- a few focused JSON sections

### Raw JSON Tab

Used for:

- exact whole-file or whole-entity editing

This means the structured tab is the default working surface, while the raw tab
remains always available.

## Entity Instance UX

This is the first and most important content type for the focused-JSON model.

### Current baseline

The instance editor already has:

- structured common fields
- parameters
- `variables` JSON block
- full raw entity-instance JSON tab

### Next focused JSON addition

Add a dedicated `Visuals` JSON section to the structured entity-instance editor.

### Entity Instance Editor Layout

Recommended section order:

1. Identity
2. Position
3. Physics / Interaction
4. Visibility
5. Parameters
6. Variables
7. Visuals
8. Extra

### Variables section

Keep the current plain JSON object block.

Behavior:

- accepts only a JSON object
- invalid JSON gives a precise local validation error

### Visuals section

Add a second plain JSON block directly below `Variables`.

Behavior:

- accepts only a JSON array
- content represents the instance-level `visuals` override
- invalid JSON gives a precise local validation error
- wrong top-level type gives a precise local validation error

### Visuals help text

The section should include a short small note, something like:

- "Override this entity instance's visuals. This is an instance-level `visuals` array."

Optional second sentence:

- "Use the raw JSON tab if you need the full entity document."

### What users should be able to do here

- change a visual `path`
- change `frame_width` / `frame_height`
- change `frames`
- change `animation_fps`
- change `visible`
- change offsets

without opening the full entity JSON document

### Raw JSON tab for entity instances

Keep exactly as today:

- full entity JSON
- whole-document editing
- advanced fallback

## Entity Template UX

Templates need a similar pattern, but the first pass should stay lighter than
the instance editor.

### Goal

Give template authors a simpler path for the most important reusable fields
without attempting a complete generic template editor.

### Recommended first template editor surface

The first structured template editor should have:

1. Summary / identity fields if useful
2. Focused `visuals` JSON block
3. Optional `variables` JSON block later if it proves useful
4. Full raw JSON tab always available

### Template visuals block

This is where template authors define the reusable default visual data.

The UX should mirror the instance `Visuals` block closely so the concept feels
consistent:

- same monospace styling
- same validation rules
- similar label and help text

### What should stay out of scope for now

- full structured `entity_commands` editing
- full generic nested template editing
- inferred semantic help from parameter names

## Item UX

Items are the second major content type that benefits from the focused-JSON
model.

### Goal

Let users comfortably edit routine item metadata and the nested image objects
without needing to manage the entire item file.

### Recommended item editor shape

The first item editor should use:

#### Structured fields

- `name`
- `description`
- `max_stack`
- `consume_quantity_on_use`

#### Focused JSON sections

- `icon`
- `portrait`

#### Full raw JSON tab

- complete item JSON

### Item layout

Recommended order:

1. Basic
2. Inventory Behavior
3. Icon
4. Portrait
5. Raw JSON tab

### Icon section

Plain JSON object block.

Validation:

- must be a JSON object when non-empty

Expected use:

- `path`
- `frame_width`
- `frame_height`
- `frame`

### Portrait section

Plain JSON object block.

Validation:

- must be a JSON object when non-empty

Expected use:

- `path`
- `frame_width`
- `frame_height`
- `frame`

### Item raw JSON tab

Always available.

This remains necessary for:

- `use_commands`
- advanced fields
- unusual item definitions

### Explicit non-goal for first item surface

Do not try to build a visual command editor for `use_commands` yet.

## Common Focused JSON Widget Behavior

All focused JSON blocks should share the same behavior.

### Appearance

- monospace text area
- no line wrapping
- moderate fixed height
- optional placeholder example

### Validation timing

First pass recommendation:

- validate on Apply / Save
- show exact parse/type errors in a clear message

Optional later enhancement:

- light live invalid-state highlighting

### Empty-state rules

Use simple consistent rules:

- empty `variables` block -> no explicit override written
- empty `visuals` block -> no explicit override written
- empty `icon` / `portrait` block -> field omitted unless explicitly needed

### Error wording

Keep messages concrete, for example:

- "`visuals` must be valid JSON."
- "`visuals` must be a JSON array."
- "`icon` must be a JSON object."

Avoid vague wording like:

- "Invalid field state"

## Navigation / Discoverability

The structured editor should remain the default landing tab for content types
that have one.

The raw JSON tab should still be:

- adjacent
- obvious
- one click away

This avoids the feeling that raw JSON is hidden while still encouraging the
safer intermediate path first.

## Save / Dirty UX

Focused JSON blocks should participate in the same dirty model as the
structured editor around them.

Desired behavior:

- editing a focused block marks the current content as dirty
- save saves the whole underlying content object/file
- revert restores the focused block to the last saved state

This should feel exactly like other editor changes, not like a special mode.

## Scope Boundaries

### In scope for this UX layer

- entity-instance `visuals` block
- future template `visuals` block
- future item `icon` / `portrait` blocks
- keeping raw JSON visible everywhere

### Out of scope for now

- full visual stack editor
- image preview widgets inside every focused JSON block
- semantic guessing from variable names
- template parameter help metadata system
- visual merge-by-id engine redesign

## Suggested Implementation Order

1. add entity-instance `visuals` focused JSON block
2. validate that the pattern feels good in real use
3. add a small template editor surface with `visuals` block + raw JSON
4. add a modest item editor with structured basics + `icon` / `portrait` blocks

## Success Criteria

This UX direction is successful if:

- a user can change common visual-related data without opening the full file
- raw JSON remains easy to access when needed
- the editor feels more capable without becoming overwhelming
- intermediate users gain real leverage without us needing a giant generic editor
