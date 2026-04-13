# Editor Gaps And Future Work

The editor has moved well beyond the earliest phase, but it is not fully caught up with the runtime.

## Main Known Gaps

The most important current gaps are:

- richer screen-space placement and direct-manipulation polish
- runtime handoff or launch integration
- broader structured editing coverage for newer engine-owned entity fields and workflow values
- richer structured dialogue and menu editing
- more contextual reference pickers inside editing panels

## What Is Already Partly Solved

Several areas that used to be major gaps are now at least partly addressed:

- project manifest editing
- shared variable and UI-preset editing
- item editing
- global entity editing
- reference-aware rename or move for file-backed content
- safer layer management

That means the editor should be described as a strong project and area authoring tool, not as a phase-1 prototype.

## Likely Next High-Value Improvements

Based on the current roadmap and future-features notes, the next valuable steps are:

- broader structured coverage for engine-owned fields
- clearer reference pickers and broken-reference surfacing
- better screen-space manipulation and placement polish
- runtime launch or handoff from the editor
- richer content editing for dialogue and commands

Recent correctness-focused progress already moved `scope`, `color`, `input_map`,
`inventory`, `entity_commands`, and common template defaults into the structured
entity-instance and template editing surfaces, so there are no remaining
runtime-known authored entity fields that require whole-file raw JSON editing.
The remaining command-related gap is richer command-builder assistance on top
of the focused entity-command JSON surface.

## Longer-Term Future Features

Ideas that are clearly interesting but should still be treated as future work include:

- guided command-chain editing for templates and items
- richer asset previews
- template drag-and-drop placement workflows
- "find references" style project refactor support beyond the existing rename or move flows

## Scope Reminder

Even as the editor grows, some things are intentionally out of scope for now:

- full gameplay simulation inside the editor
- reproducing runtime `World` or command-runner behavior
- becoming a second engine
- visually exposing every arbitrary JSON shape the runtime can express

## Deep References

- [tools/area_editor/ROADMAP.md](https://github.com/alext512/dungeon-engine/blob/main/tools/area_editor/ROADMAP.md)
- [tools/area_editor/FUTURE_FEATURES.md](https://github.com/alext512/dungeon-engine/blob/main/tools/area_editor/FUTURE_FEATURES.md)
- [tools/area_editor/SCOPE.md](https://github.com/alext512/dungeon-engine/blob/main/tools/area_editor/SCOPE.md)
