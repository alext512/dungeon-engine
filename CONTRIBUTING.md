# Contributing

Read these files in this order:

1. `STATUS.md`
2. `functionality.md`
3. `architecture.md`
4. `roadmap.md`

## Project direction

- This is a new Python project.
- The old Godot project is inspiration and reference material, not the runtime we are extending.
- The project should stay close to the command-driven spirit of the original game.

## Working rules

- Prefer reusable commands over bespoke per-object scripts.
- Keep the game runnable after each phase.
- Treat the editor as an early requirement, not a late bonus.
- Use data files for content.
- Keep room/entity/command data portable so a future runtime can reuse the same content pipeline.
- Update the docs when implementation changes the plan.

## Replatforming stance

- Continue development in Python for now.
- Do not start a runtime migration until the command model, data schemas, and editor workflow are more stable.
- If wider platform support becomes a real priority later, treat MonoGame as the first replatforming candidate.
- If a replatform happens, port the runtime first and keep the Python editor as an external authoring tool until replacing it is clearly worth the cost.

## Practical rule of thumb

If a feature would be triggered by the player, an NPC, a usable item, or a cutscene, try to express it through the same command system.
