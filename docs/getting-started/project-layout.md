# Project Layout

Understanding the repo layout makes the rest of the engine easier to follow.

## Repo Layout

At a high level:

```text
python_puzzle_engine/
    dungeon_engine/          # Runtime package
    tools/area_editor/       # External authoring tool
    tests/                   # Runtime tests
    projects/                # Repo-local example projects
    docs/                    # This documentation site
    run_game.py              # Main game entry point
    README.md                # Repo front page
```

Important separation:

- `dungeon_engine/` is the engine runtime
- `tools/area_editor/` is a separate authoring application
- `projects/<name>/` is content, not engine code

## Project Content Layout

A typical project looks like this:

```text
my_project/
    project.json
    shared_variables.json
    items/
    areas/
    entity_templates/
    commands/
    dialogues/
    assets/
```

The stable contract is the file format, not the fact that a project happens to live under `projects/`.

`dialogues/` is conventional rather than manifest-indexed, but it is still an important convention today: dialogue/menu JSON often lives there, editor pickers expect it, and startup dialogue auditing currently scans that tree specifically.

## Path-Derived IDs

Areas, templates, commands, and items derive identity from their path under configured content roots.

Examples:

- `areas/start.json` becomes `areas/start`
- `areas/levels/first_area.json` becomes `areas/levels/first_area`
- `entity_templates/player.json` becomes `entity_templates/player`

This matters because references across the runtime use those path-derived ids.

## Minimal `project.json`

The repo-local example project starts like this:

```json
{
  "entity_template_paths": ["entity_templates/"],
  "asset_paths": ["assets/"],
  "area_paths": ["areas/"],
  "command_paths": ["commands/"],
  "shared_variables_path": "shared_variables.json",
  "global_entities": [],
  "startup_area": "areas/title_screen",
  "input_targets": {},
  "debug_inspection_enabled": true
}
```

## Where Different Kinds Of Logic Live

- engine behavior lives in Python under `dungeon_engine/`
- game-specific behavior mostly lives in JSON commands and content files
- common room editing lives in the external editor
- advanced edge cases can still use raw JSON surfaces

## Good Habits

- Keep engine code and project content mentally separate.
- Treat `project.json` as the project root contract.
- Prefer reading one real example file from `projects/new_project/` whenever a concept feels abstract.
- Use [Project Manifest](../reference/project-manifest.md) and [Content Types](../reference/content-types.md) once you are ready for the exact surfaces.
