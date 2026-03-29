# Open Questions

These questions are intentionally unresolved.

Do not treat them as blockers unless the user says they are.

## Save Preservation Strategy

- How strict should unknown-field preservation be?
- Is formatting preservation important, or just semantic preservation?
- Should the tool rewrite whole files or patch only owned sections later?

## Entity-Reference Hints

- How should the tool know that a parameter is an entity reference?
- Hardcoded known parameter names?
- Project-level config?
- Sidecar metadata?
- Conservative heuristics only?

## Raw JSON Editing

- Should raw JSON be area-wide, entity-wide, or field-level?
- Should advanced raw editing ship early, or only after structured editing exists?

## Tool-Owned Metadata

- Will the editor eventually need a sidecar file for UI hints?
- If yes, where should it live?
- Should sidecars be project-scoped, room-scoped, or fully local to the tool user?

## Launch Workflow

- this is about launching the runtime from the editor, not opening a project in the editor itself
- Should the tool eventually launch the game directly?
- Should it launch a selected area only?
- Should save-before-launch be mandatory?

## Undo/Redo

- Is undo/redo required for the first implementation, or can it wait?
- If added later, should it operate on document operations only or on raw JSON edits too?

## Scope Expansion

- Should the tool ever grow beyond areas into broader project tooling?
- If yes, should that happen inside this folder or under sibling tools?
