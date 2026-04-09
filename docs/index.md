# Dungeon Engine

<div class="hero">
This project is a command-driven 2D top-down puzzle and RPG engine written in Python with <code>pygame-ce</code>. Most game behavior lives in JSON files instead of one-off Python gameplay scripts, and the repo also ships with a separate external area editor for authoring common content safely.
</div>

## What This Docs Site Covers

This site is meant to help three kinds of users:

- content authors who want to build rooms, entities, dialogue, items, and puzzle logic
- engine contributors who need a map of the runtime, content contract, and module boundaries
- coding agents that need to understand what is canonical, what is planning material, and how to validate changes safely

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

- If you want to get the engine running quickly, start with [Getting Started](getting-started/index.md).
- If you want to make content, go to [Authoring Workflow](guides/authoring-workflow.md) and [Project Manifest](reference/project-manifest.md).
- If you want to understand how gameplay logic works, read [Command System](guides/command-system.md) and [Built-in Commands](reference/builtin-commands.md).
- If you are validating content or changing command surfaces, read [Validation and Startup Checks](guides/validation-and-startup-checks.md).
- If you want to use or extend the editor, read [Editor Overview](editor/index.md) and [Editor Workflow](editor/workflow.md).
- If you are modifying the codebase or using coding agents, read [For Coding Agents](architecture/for-coding-agents.md) and [Docs Maintenance](contributing/docs-maintenance.md).

## Canonical Long-Form Sources In The Repo

This docs site is the guided front door. The deep canonical sources still live in the repo and are worth keeping nearby:

- [README.md](https://github.com/alext512/dungeon-engine/blob/main/README.md)
- [AUTHORING_GUIDE.md](https://github.com/alext512/dungeon-engine/blob/main/AUTHORING_GUIDE.md)
- [ENGINE_JSON_INTERFACE.md](https://github.com/alext512/dungeon-engine/blob/main/ENGINE_JSON_INTERFACE.md)
- [PROJECT_SPIRIT.md](https://github.com/alext512/dungeon-engine/blob/main/PROJECT_SPIRIT.md)
- [architecture.md](https://github.com/alext512/dungeon-engine/blob/main/architecture.md)
- [tools/area_editor/README.md](https://github.com/alext512/dungeon-engine/blob/main/tools/area_editor/README.md)

## Current Limits Worth Knowing Up Front

- The editor is strong but not fully caught up with every newer runtime surface.
- Runtime handoff from the editor, richer screen-space direct manipulation, and some structured editing coverage are still missing.
- The JSON contract is rich enough that advanced workflows still sometimes fall back to raw JSON editing.

## A Good First Goal

Open the repo-local example project, trace one area, one entity template, and one command flow, then open the same project in the editor. That gives you the shortest path to understanding how the runtime, project content, and tooling fit together.
