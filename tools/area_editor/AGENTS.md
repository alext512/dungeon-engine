# Agent Onboarding

This folder is the starting point for work on the external area editor.

Read this file first.

## Current Status

The core area-editing foundation is complete, and substantial catch-up work
from later roadmap phases is already in place.

Use `ROADMAP.md` as a historical plan plus a status tracker for what remains,
not as a signal that everything after Phase 3 is untouched.

The editor currently supports strong area-centric and project-aware authoring:

- tile painting
- cell-flag editing
- entity placement and nudging
- structured entity/template/item/project editing plus guarded raw JSON fallbacks
- guarded raw JSON editing

The main remaining editor work is to keep catching the tool up to the newer
runtime-facing authoring surface:

- better placed-entity configuration through exposed fields and parameters
- richer screen-space placement/manipulation workflows
- richer command-builder help for workflow-heavy authored blocks such as
  `entity_commands`
- stronger contextual reference pickers
- runtime launch/handoff integration

The overarching goal is to let a non-coder build a full game through the
supported template-driven workflow while keeping raw JSON escape hatches for
advanced users.

## What This Folder Is

`tools/area_editor/` is the home of the external authoring tool. Its scope covers:

- area editing: tile painting, cell flags, entity placement
- entity instance/template editing: exposed engine-known fields, color, parameters, variables, input routing, entity commands, inventory, persistence, visuals
- content editing: supported items, dialogues/menus, and new areas
- project configuration: selected settings such as global entities, input routing, shared variables, and UI presets
- reference pickers: entity, template, area, item, dialogue, and asset references
- runtime integration: external launch for quick testing later

It is not part of the runtime package.

The editor/runtime entity-field ownership map lives in
`area_editor/entity_field_coverage.py`. If the runtime adds or removes authored
entity fields in `dungeon_engine/world/loader_entities.py`, update that map and
its regression tests in `tests/test_entity_field_coverage.py`.

## Hard Rules

Follow these rules unless the user explicitly changes them:

1. Do not import `dungeon_engine`.
2. Do not move code back under `dungeon_engine/`.
3. Treat JSON files as the contract between the runtime and the tool.
4. Preserve unknown JSON fields when editing files owned by the tool.
5. Do not simulate gameplay, command execution, persistence, or runtime state inside the tool unless the user later asks for that on purpose.
6. Keep tool-only state outside game/runtime data.
7. Prefer a focused convenience tool over a giant all-in-one editor.
8. Build around the curated template-driven workflow first; do not assume the editor must visually expose every arbitrary JSON possibility.
9. If a feature would require copying large parts of the runtime, stop and reconsider the design.

## JSON Authoring Notes

When creating authored JSON data files (`.json` or `.json5`), start them with
the standard file-level notes header:

```json5
/*
  NOTES

  Add file-level notes here.
*/
```

The engine/editor JSON loader accepts file-level comments for both `.json` and
`.json5` authored data. Treat that notes area like source-code comments: add
brief explanations for intent, non-obvious choices, and authoring context when
that would help the next human or agent.

Do not force comments back into existing files. If a user deletes the notes
header or removes comments, preserve that choice unless they explicitly ask you
to add comments again.

## Read Order

Read these files in this order:

1. `README.md`
2. `VISION.md`
3. `SCOPE.md`
4. `DATA_BOUNDARY.md`
5. `ARCHITECTURE.md`
6. `UX_NOTES.md`
7. `ROADMAP.md`
8. `DECISIONS.md`
9. `OPEN_QUESTIONS.md`

Then refresh yourself on the runtime JSON contract:

1. [../../docs/authoring/manuals/authoring-guide.md](../../docs/authoring/manuals/authoring-guide.md)
2. [../../docs/authoring/manuals/engine-json-interface.md](../../docs/authoring/manuals/engine-json-interface.md)
3. [../../AGENTS.md](../../AGENTS.md)

The archived built-in editor is available only as historical reference:

- [../../archived_editor/README.md](../../archived_editor/README.md)

Do not treat the archived editor as the implementation baseline unless the user explicitly asks for that.

## Intended Relationship To The Runtime

The editor should:

- read project manifests and authored JSON files from disk
- scan project assets and templates from disk
- help the user edit those files faster and more safely

The editor should not:

- import runtime classes or systems
- depend on runtime-only object models
- assume any privileged in-process connection to the game

If the tool launches the game later, it should do so as an external process.

## Practical Guidance For Future Agents

If you are asked to extend this tool later:

- build on the existing foundation instead of treating this folder as docs-only
- start with the smallest workflow that removes painful manual JSON editing
- optimize first for curated templates plus exposed fields and references
- keep the first versions narrow and boring
- add strong save/load preservation before fancy UI behavior
- prefer explicit boundary docs over clever shortcuts
- document every important decision in `DECISIONS.md`
- put unresolved tradeoffs in `OPEN_QUESTIONS.md`

If a future request conflicts with these docs, update the docs in the same change so the next agent inherits the new truth.
