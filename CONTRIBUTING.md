# Contributing

Read these files in this order:

1. `PROJECT_SPIRIT.md`
2. `README.md`
3. `AUTHORING_GUIDE.md`
4. `ENGINE_JSON_INTERFACE.md`
5. `architecture.md`
6. `roadmap.md`

## Project direction

- This is a new Python project.
- The old Godot project is inspiration and reference material, not the runtime we are extending.
- The project should stay close to the command-driven spirit of the original game.

## Working rules

- Prefer reusable commands over bespoke per-object scripts.
- Keep the game runnable after each phase.
- Use data files for content.
- Keep authoring tooling external to the runtime unless there is a strong reason to merge it back in.
- Keep the boundary clear: engine code belongs under `dungeon_engine/`, while project content belongs in a project folder selected through `project.json`, even if that project is versioned inside this repo under `projects/`.
- Keep room/entity/command data portable so future runtimes and external tooling can reuse the same content pipeline.
- Update the docs when implementation changes the plan.
- Review and update affected docs after each implementation step rather than
  batching doc fixes at the end of a larger refactor.
- Use `plans/documentation_inventory_and_truth_map.md` to decide which docs are
  canonical, summary-level, planning-only, or historical before editing them.
- Add or update focused regression tests when engine behavior changes. The runtime suite runs with `.venv/Scripts/python -m unittest discover -s tests -v`. If you touch `tools/area_editor/`, run `..\..\.venv/Scripts/python -m unittest discover -s tests -v` from inside `tools/area_editor/`.

## Replatforming stance

- Continue development in Python for now.
- Do not start a runtime migration until the command model, data schemas, and authoring workflow are more stable.
- If wider platform support becomes a real priority later, treat MonoGame as the first replatforming candidate.
- If a replatform happens, port the runtime first and keep authoring tools external and data-driven until replacing them is clearly worth the cost.

## Practical rule of thumb

If a feature would be triggered by the player, an NPC, or a controller flow, try to express it through the same command system.
