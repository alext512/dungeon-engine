# Dungeon Engine

<div class="hero">
This project is a command-driven 2D top-down puzzle and RPG engine written in Python with <code>pygame-ce</code>. Most game behavior lives in JSON files instead of one-off Python gameplay scripts, and the repo also ships with a separate external area editor for authoring common content safely.
</div>

## What This Docs Site Covers

This site is centered on people building games through JSON and the editor.

It also includes smaller sections for project direction and engine/developer workflow, but the main path through the site is `Game Authoring`.

The docs site is also the permanent home for the public long-form manuals. Root-level compatibility pointers still exist in the repo, but the site is now the main place to browse and maintain them.

## What You Can Build Today

Runtime features already in active use include:

- manifest-driven projects through `project.json`
- tile-based areas with independent tile layers and walkability flags
- path-derived ids for areas, templates, commands, and items
- reusable entity templates with per-instance parameters
- command-driven interaction, movement, animation, area changes, and persistence
- engine-owned dialogue and inventory sessions
- screen-space UI commands for panels, text, images, and animations
- save/load plus layered persistent state

The external editor already supports:

- tile painting, tile selection, and stamp painting
- cell-flag editing
- entity placement, selection, deletion, and nudging
- render-property editing
- project manifest, shared variable, item, and global-entity editing
- guarded JSON editing and reference-aware file moves or renames

## What Makes This Engine Different

- The stable contract is JSON content, not hidden engine-side behaviors.
- Gameplay flows go through the command runner instead of custom per-object scripts.
- Runtime code and authoring tools are intentionally separate.
- Repo-local example projects are useful learning material, but the engine is not hardcoded to one bundled game.

## Recommended Reading Paths

- If you want to build a game through JSON and the editor, start in the `Game Authoring` section.
- If you are a complete beginner, go straight to [Absolute Beginner Quickstart](authoring/absolute-beginner-quickstart.md).
- If you want exact command and token surfaces, stay in `Game Authoring` and use the `JSON and Command Reference` subsection there.
- If you want to understand the engine's design intent, read `Project Direction`.
- If you are changing Python code or maintaining docs, use `Development`.

## Long-Form Manuals

The deepest permanent manuals now live inside `docs/` as part of the site:

- [Authoring Guide](authoring/manuals/authoring-guide.md)
- [Engine JSON Interface](authoring/manuals/engine-json-interface.md)
- [Project Spirit](project/project-spirit.md)
- [Architecture Direction](project/architecture-direction.md)
- [Editor Manual](authoring/editor/editor-manual.md)

Repo-level files such as `README.md`, `AGENTS.md`, and `CONTRIBUTING.md` still live at the repo root because they also serve repository and hosting conventions.

## Current Limits Worth Knowing Up Front

- The editor is strong but not fully caught up with every newer runtime surface.
- Runtime handoff from the editor, richer screen-space direct manipulation, and some structured editing coverage are still missing.
- The JSON contract is rich enough that advanced workflows still sometimes fall back to raw JSON editing.

## A Good First Goal

Open the repo-local example project, trace one area, one entity template, and one command flow, then open the same project in the editor. That gives you the shortest path to understanding how the runtime, project content, and tooling fit together.
