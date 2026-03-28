# Vision

## Problem

The runtime is data-driven, but some high-friction authoring tasks are still awkward to do by hand in JSON.

The painful cases are mostly practical, not philosophical:

- painting tilemaps
- managing layers visually
- placing and repositioning entities
- assigning ids cleanly
- editing parameters that should point at other entity instances

The user does not need a second engine.

The user needs a convenience tool that removes repetitive manual editing while staying out of the runtime's way.

## Desired Outcome

The future area editor should make common room-authoring tasks fast, safe, and boring.

Success looks like:

- authoring a room is quicker than hand-editing JSON
- the tool is easier to maintain than the old built-in editor
- runtime refactors do not automatically break the tool
- new runtime features do not force constant tool rewrites unless the file contract changes

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
- a giant all-purpose content suite on day one

## Design Principles

1. File contract first.
   The shared truth between runtime and tooling is authored JSON on disk.

2. Convenience over completeness.
   Solve the painful 80 percent first.

3. Unknown fields survive.
   The tool should not damage data it does not actively understand.

4. Entity references deserve special care.
   The tool should make cross-entity references much easier than raw string editing.

5. Escape hatches matter.
   Raw JSON access is acceptable for advanced or rare cases.

6. Runtime independence is a feature.
   The editor is healthier if it can survive runtime refactors.

## Long-Term Hope

If this tool succeeds, the project gains:

- faster content iteration
- less risk from runtime/editor coupling
- a clearer separation between play code and authoring code
- a better foundation for future tooling beyond rooms alone
