# Contributing

Read these files in this order:

1. `functionality.md`
2. `architecture.md`
3. `roadmap.md`

## Project direction

- This is a new Python project.
- The old Godot project is inspiration and reference material, not the runtime we are extending.
- The project should stay close to the command-driven spirit of the original game.

## Working rules

- Prefer reusable commands over bespoke per-object scripts.
- Keep the game runnable after each phase.
- Treat the editor as an early requirement, not a late bonus.
- Use data files for content.
- Update the docs when implementation changes the plan.

## Practical rule of thumb

If a feature would be triggered by the player, an NPC, a usable item, or a cutscene, try to express it through the same command system.
