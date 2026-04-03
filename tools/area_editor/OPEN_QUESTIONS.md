# Open Questions

Questions are listed with their current status.

## Save Preservation Strategy

**Resolved:** Semantic preservation through `_extra` dicts. The tool pops known
keys, stores the rest in `_extra`, and merges them back on save. Formatting
preservation is not a goal; semantic round-trip is sufficient.

## Entity-Reference Hints

**Current direction:**
- Start with hardcoded engine fields such as `template`, `entity_id`, `item_id`,
  `area_id`, `dialogue_path`, and visual asset `path`
- Add common parameter-name pattern matching such as `*_entity`, `*_target`,
  `*_item`, `*_dialogue`, and `*_path`
- If heuristics are insufficient later, consider template-level hints or a small
  project-scoped sidecar config

## Raw JSON Editing

**Resolved:** Raw JSON is an intentional escape hatch. The existing entity raw-JSON
tab should remain, and similar escape hatches are acceptable for other content
types when structured editing does not cover a case safely.

## Tool-Owned Metadata

**Deferred:** No sidecar files for now. If needed later, they should be
project-scoped and stored alongside `project.json`. The near-term plan should
prefer hardcoded engine fields plus conservative heuristics.

## Launch Workflow

**Current direction:**
- If runtime launch is added, it should launch the runtime as an external process
- Support both project-wide launch and area-focused launch
- Auto-save before launch is desirable, but still a design choice rather than an implemented fact

## Undo/Redo

**Current direction:**
- Undo/redo is deferred to a later quality pass
- It should cover structured edits, tile painting, entity placement, and field changes first
- Raw JSON edits do not need undo/redo coverage in the first version

## Scope Expansion

**Current direction:** The tool should grow beyond room-only editing into selected
project-level workflows, still within this folder. The near-term growth is around
item definitions, dialogue/menu data, shared variables and UI presets,
`global_entities`, and better reference-driven configuration on top of the curated
template library. Raw JSON remains the escape hatch for advanced or fully custom
authoring.
