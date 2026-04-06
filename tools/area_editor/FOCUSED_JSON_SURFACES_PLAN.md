"""Planning note for the next editor UX layer.

This is intentionally narrower than the broad roadmap. It captures the
agreed middle-ground approach:

- structured fields for common/simple authoring
- focused JSON sections for complex nested data
- full raw JSON always available as the final escape hatch
"""

# Focused JSON Surfaces Plan

## Goal

Give intermediate users a safer editing surface than full-file JSON without
forcing the editor to grow a giant custom widget for every nested engine
schema.

The intended ladder is:

1. structured fields for common/high-value properties
2. focused JSON sections for complex nested parts
3. full raw JSON tab always available

This preserves flexibility while making typical workflows much less
intimidating.

## Core Principles

### 1. Full Raw JSON Must Always Remain Available

Every content type should keep a full guarded JSON editing path.

Structured or semi-structured editor surfaces are convenience layers, not the
only authoring path.

### 2. The Editor Should Not Guess JSON Meaning

The editor should not infer semantic meaning from arbitrary variable names.

Bad:
- assuming `item_id` always means “item to give”
- assuming `sprite_path` is an engine-reserved concept

Good:
- editing known engine schema directly
- reading explicit author-provided metadata later if such metadata is added

### 3. Focused JSON Sections Are A Deliberate Middle Layer

Some nested data is too complex for a first-pass structured editor but still
important enough to deserve its own smaller editing surface.

Examples:
- entity `visuals`
- entity/item `variables`
- item `icon`
- item `portrait`

## What Counts As Structured vs Focused JSON

### Good Structured Fields

These are simple, common, and low-risk:

- entity id
- template id
- grid position
- facing
- tags
- `solid`
- `interactable`
- `interaction_priority`
- basic item metadata like `name`, `description`, `max_stack`

### Good Focused JSON Sections

These are complex enough that raw JSON is still appropriate, but small enough
to deserve a dedicated subsection:

- entity `visuals`
- entity `variables`
- template `visuals`
- item `icon`
- item `portrait`
- later maybe item `use_commands`

### Still Best Left To Full Raw JSON For Now

- large command graphs
- generic deep template authoring
- advanced menu/dialogue logic
- arbitrary nested custom project extensions

## Recommended Near-Term Editor Surfaces

### A. Entity Instances

Current status:
- structured common fields already exist
- parameters already exist
- variables JSON block already exists

Next recommended addition:
- add a focused `visuals` JSON section beside `variables`

Why:
- instance-level visual overrides are useful
- this avoids requiring a full visual editor immediately
- users can override paths, frames, offsets, visibility, and animation speed

Important note:
- full raw entity-instance JSON remains available

### B. Entity Templates

Recommended first step:
- add a template-focused editor surface later with:
  - small structured summary where useful
  - focused `visuals` JSON section
  - maybe `variables` later if useful

Do not try to build a complete template editor in one pass.

### C. Items

Recommended first pass:
- modest structured item form for:
  - `name`
  - `description`
  - `max_stack`
  - `consume_quantity_on_use`

Plus focused JSON sections for:
- `icon`
- `portrait`

Later possibility:
- focused `use_commands` JSON section

Raw full item JSON remains available at all times.

## Visual Override Semantics To Keep In Mind

Current engine behavior:
- template + instance merge recursively for dicts
- list values, such as `visuals`, are replaced wholesale

So today, overriding template visuals at the instance level usually means
providing a replacement `visuals` array.

This is acceptable for now, especially if surfaced through a dedicated
`visuals` JSON subsection.

Possible future engine improvement:
- merge entity `visuals` by visual `id`

That is worth discussing later, but it is not required before the editor can
offer a useful `visuals` JSON section.

## Things To Discuss Later

### 1. Friendly Parameter Labels / Help Text

If needed, this should come from explicit JSON metadata, not editor guessing.

Possible future shape:

```json
{
  "editor_parameters": {
    "item_id": {
      "label": "Item To Give",
      "description": "Item definition id granted to the interacting entity."
    }
  }
}
```

This is deferred for now.

### 2. Smarter Visual Override UX

Possible future direction:
- allow users to “override just the path” in a friendly UI
- editor writes the necessary `visuals` override JSON under the hood

This is deferred for now.

### 3. Visual Merge By `id`

If the engine later merges `visuals` entries by `id`, instance/template visual
override workflows become much nicer.

This should be discussed intentionally rather than slipped in casually.

## Suggested Implementation Order

1. add entity-instance `visuals` JSON section
2. design a small template editor surface with raw JSON fallback
3. add a modest structured item editor plus `icon` / `portrait` JSON sections
4. revisit parameter metadata and visual-merge behavior only after real use

## Success Criteria

This direction is working if:

- intermediate users can edit common visual data without opening the entire file
- advanced users never lose access to full raw JSON
- the editor remains curated and manageable instead of becoming a giant generic schema editor
- new editor surfaces reduce friction without requiring engine-specific guessing
