# Getting Started

Use this section when you are new to the engine and want a reliable path into the project.

## First Principles

The fastest way to orient yourself is:

1. Learn the mental model.
2. Run the example project.
3. Inspect one area and one entity template.
4. Read the command-system docs.
5. Open the same project in the editor.

## Suggested Reading Order

- [Install and Run](install-and-run.md)
- [Project Layout](project-layout.md)
- [Engine Concepts](../guides/engine-concepts.md)
- [Authoring Workflow](../guides/authoring-workflow.md)
- [Command System](../guides/command-system.md)

Then use the long-form manuals when you need more depth:

- [README.md](https://github.com/alext512/dungeon-engine/blob/main/README.md) for the overview and quick commands
- [Authoring Guide](../manuals/authoring-guide.md) for full author-facing workflow details
- [Engine JSON Interface](../manuals/engine-json-interface.md) for the exact JSON contract

## Pick Your Track

### I want to play or smoke-test the engine

- Install the runtime dependencies.
- Run `run_game.py` against the repo-local example project.
- Use the headless command for quick validation.

### I want to author a game

- Start with `project.json`, one area, one player template, and one set of input routes.
- Use the editor for map-centric tasks and structured project editing.
- Drop to raw JSON for advanced command chains until the editor catches up.

### I want to modify engine code

- Read [Runtime Architecture](../architecture/runtime-architecture.md).
- Read [For Coding Agents](../architecture/for-coding-agents.md).
- Run the runtime and editor tests that match the surfaces you touch.

## Repo-Local Example Project

The repo currently includes `projects/new_project/`, which is useful because it shows:

- a real `project.json`
- multiple authored areas
- reusable entity templates
- dialogue JSON
- assets, fonts, and UI art

Good first files to inspect:

- `projects/new_project/project.json`
- `projects/new_project/areas/start.json`
- `projects/new_project/entity_templates/player.json`
- `projects/new_project/dialogues/system/title_menu.json`

## What To Expect

This engine already has meaningful runtime and authoring functionality, but it is still actively evolving. Expect a real usable system, not a frozen platform. The safest habit is to treat the JSON contract as the source of truth and the docs site as the guided map into that contract.
