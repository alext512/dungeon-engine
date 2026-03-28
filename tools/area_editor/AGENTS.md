# Agent Onboarding

This folder is the starting point for any future work on the new external area editor.

Read this file first.

## Current Status

This workspace is intentionally documentation-only.

Do not add editor code unless the user explicitly asks for implementation work.

The goal of the current scaffold is to preserve decisions, boundaries, and planned workflows before any new editor code exists.

## What This Folder Is

`tools/area_editor/` is the planned home for a future external authoring tool for:

- painting tilemaps
- editing walkability or other cell flags
- placing, moving, and deleting entity instances
- editing a small set of high-value instance fields and parameters
- especially helping with parameters that reference other entities in the same room

It is not part of the runtime package.

## Hard Rules

Follow these rules unless the user explicitly changes them:

1. Do not import `dungeon_engine`.
2. Do not move code back under `dungeon_engine/`.
3. Treat JSON files as the contract between the runtime and the tool.
4. Preserve unknown JSON fields when editing files owned by the tool.
5. Do not simulate gameplay, command execution, persistence, or runtime state inside the tool unless the user later asks for that on purpose.
6. Keep tool-only state outside game/runtime data.
7. Prefer a focused convenience tool over a giant all-in-one editor.
8. If a feature would require copying large parts of the runtime, stop and reconsider the design.

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

Then refresh yourself on the runtime's JSON contract:

1. [../../AUTHORING_GUIDE.md](../../AUTHORING_GUIDE.md)
2. [../../ENGINE_JSON_INTERFACE.md](../../ENGINE_JSON_INTERFACE.md)
3. [../../AGENTS.md](../../AGENTS.md)

The archived built-in editor is available only as historical reference:

- [../../archived_editor/README.md](../../archived_editor/README.md)

Do not treat the archived editor as the implementation baseline unless the user explicitly asks for that.

## Intended Relationship To The Runtime

The future editor should:

- read project manifests and authored JSON files from disk
- scan project assets and templates from disk
- help the user edit those files faster and more safely

The future editor should not:

- import runtime classes or systems
- depend on runtime-only object models
- assume any privileged in-process connection to the game

If the tool launches the game later, it should do so as an external process.

## Practical Guidance For Future Agents

If you are asked to extend this tool later:

- start with the smallest workflow that removes painful manual JSON editing
- keep the first versions narrow and boring
- add strong save/load preservation before fancy UI behavior
- prefer explicit boundary docs over clever shortcuts
- document every important decision in `DECISIONS.md`
- put unresolved tradeoffs in `OPEN_QUESTIONS.md`

If a future request conflicts with these docs, update the docs in the same change so the next agent inherits the new truth.
