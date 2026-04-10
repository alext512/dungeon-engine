# Dungeon Engine

<div class="hero">
This project is a command-driven 2D top-down puzzle and RPG engine written in Python with <code>pygame-ce</code>. Most game behavior lives in JSON files instead of one-off Python gameplay scripts, and the repo also ships with a separate external area editor for authoring common content safely.
</div>

## What This Docs Site Covers

This site is meant to help three kinds of users:

- content authors who want to build rooms, entities, dialogue, items, and puzzle logic
- engine contributors who need a map of the runtime, content contract, and module boundaries
- coding agents that need to understand what is canonical, what is planning material, and how to validate changes safely

It is also the permanent home for the public long-form manuals. Root-level compatibility pointers still exist in the repo, but the docs site is now the main place to browse and maintain them.

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
- If you want exact command and token surfaces, go to `JSON Reference` and the long-form manuals there.
- If you want to understand the engine's design intent, read `Project Direction`.
- If you are changing Python code or maintaining docs, use `Development`.

## Long-Form Manuals

The deepest permanent manuals now live inside `docs/` as part of the site:

- [Authoring Guide](manuals/authoring-guide.md)
- [Engine JSON Interface](manuals/engine-json-interface.md)
- [Project Spirit](project/project-spirit.md)
- [Architecture Direction](project/architecture-direction.md)
- [Editor Manual](editor/editor-manual.md)

Repo-level files such as `README.md`, `AGENTS.md`, and `CONTRIBUTING.md` still live at the repo root because they also serve repository and hosting conventions.

## Current Limits Worth Knowing Up Front

- The editor is strong but not fully caught up with every newer runtime surface.
- Runtime handoff from the editor, richer screen-space direct manipulation, and some structured editing coverage are still missing.
- The JSON contract is rich enough that advanced workflows still sometimes fall back to raw JSON editing.

## A Good First Goal

Open the repo-local example project, trace one area, one entity template, and one command flow, then open the same project in the editor. That gives you the shortest path to understanding how the runtime, project content, and tooling fit together.
