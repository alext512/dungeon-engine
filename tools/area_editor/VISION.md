# Vision

## Problem

The runtime is data-driven, but many authoring tasks are awkward to do by hand in
JSON, especially for non-coders.

The painful cases are practical, not philosophical:

- painting tilemaps
- managing layers visually
- placing and repositioning entities
- assigning ids cleanly
- editing parameters that should point at other entity instances
- configuring exposed visuals, physics, and interaction properties
- managing items, dialogue/menu data, and selected project settings

The user does not need a second engine.

The user needs an authoring environment that makes the supported workflow practical:

- build rooms from tiles and placed entities
- use a provided library of templates, items, and other reusable content
- configure exposed fields, variables, references, and assets
- fall back to raw JSON when they intentionally go beyond the supported workflow

## Desired Outcome

The editor should make game content authoring fast, safe, and accessible to
non-coders.

Success looks like:

- a non-coder can build a complete game through the supported template-driven workflow
- routine authoring is quicker than hand-editing JSON
- raw JSON is always available as an escape hatch for advanced fields
- the tool is easier to maintain than the old built-in editor
- runtime refactors do not automatically break the tool
- new runtime features do not force constant tool rewrites unless the shared file contract changes

## Product Philosophy

The editor should be:

- external
- JSON-first
- convenience-oriented
- intentionally limited
- replaceable if a better tool emerges later

It should not try to become:

- a full game simulation environment
- a custom command-runtime previewer
- a second copy of the engine's world model
- a visual editor for every arbitrary JSON structure the runtime can express
- a giant all-purpose content suite on day one

## Design Principles

1. File contract first.
   The shared truth between runtime and tooling is authored JSON on disk.

2. Convenience over generic completeness.
   Solve the painful 80 percent first, especially around curated templates and exposed fields.

3. Unknown fields survive.
   The tool should not damage data it does not actively understand.

4. Reference-driven workflows deserve special care.
   The tool should make cross-entity and cross-content references much easier than raw string editing.

5. Escape hatches matter.
   Raw JSON access is acceptable for advanced or rare cases.

6. Runtime independence is a feature.
   The editor is healthier if it can survive runtime refactors.

## Long-Term Hope

If this tool succeeds, the project gains:

- a practical authoring environment accessible to non-coders for the supported workflow
- faster content iteration across all supported content types
- less risk from runtime/editor coupling
- a clearer separation between play code and authoring code
- a stronger foundation for future tooling
