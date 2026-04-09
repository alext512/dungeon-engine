# Validation and Startup Checks

This engine does more than just load `project.json` and hope for the best.

## What Startup Validation Currently Checks

`run_game.py` calls the startup validator before play begins.

The current order is:

1. entity template validation
2. item-definition validation
3. area validation
4. project-command validation
5. strict command-authoring audit
6. static reference validation

That means many authored mistakes fail before the main loop starts.

## What The Command-Authoring Audit Scans

The strict command-authoring pass currently audits known command-bearing JSON surfaces such as:

- project command files under `command_paths`
- item `use_commands`
- template `entity_commands`
- area `enter_commands`
- inline area-entity `entity_commands`
- `project.json` `global_entities[*].entity_commands`
- dialogue JSON under the conventional `dialogues/` tree
- nested deferred command payloads such as `segment_hooks`, inline option commands, and `option_commands_by_id`

One practical benefit is that likely top-level typos on strict primitive commands, such as `persitent` instead of `persistent`, fail before launch.

## What Static Reference Validation Catches

The static-reference pass currently checks statically resolvable dialogue and asset references across:

- `project.json`
- `shared_variables.json`
- JSON files under configured template, area, command, item, and asset roots
- dialogue JSON under the conventional `project_root/dialogues/` tree
- loaded areas and loaded global entities after template expansion

This catches issues such as:

- missing literal `dialogue_path` values
- missing literal asset paths
- missing literal asset/dialogue references that only become visible after template parameters are applied

## What It Intentionally Does Not Treat As Broken Up Front

Dynamic runtime references are not rejected just because they are dynamic.

Examples:

- token-based values such as `$sprite_path`
- other runtime-filled references that cannot be resolved safely at startup

So the startup validator is strong, but it is not a substitute for real gameplay coverage.

## Important Convention: `dialogues/`

Dialogue and menu JSON is ordinary project-relative JSON and can be loaded through `$json_file`.

However, the current extra startup dialogue scanning is still convention-based: it walks the conventional `dialogues/` folder specifically. Keeping dialogue/menu data there gives you the most tooling and validation coverage today.

## Recommended Validation Habit

When you change command surfaces, authoring conventions, or repo-local example project content:

1. run the relevant automated tests
2. validate each repo-local `project.json`
3. prefer startup-style validation, not only low-level tests
4. re-run project-command validation if ids or references changed
5. do a brief smoke start when feasible

## Useful Commands

Runtime tests:

```text
.venv/Scripts/python -m unittest discover -s tests -v
```

Quick headless smoke:

```text
.venv/Scripts/python run_game.py --project projects/new_project --headless --max-frames 2
```

Repo-local project validation snippet:

```text
@'
from pathlib import Path
from dungeon_engine.project_context import load_project
from dungeon_engine.commands.library import validate_project_commands

project_manifests = sorted(Path("projects").glob("*/project.json"))
if not project_manifests:
    print("No repo-local project manifests found under projects/.")
else:
    for project_json in project_manifests:
        project = load_project(project_json)
        validate_project_commands(project)
        print(f"{project.project_root.name}: project command validation OK")
'@ | .venv/Scripts/python -
```

## For Agents And Contributors

If docs and implementation disagree about validation behavior, trust the implementation first and record the ambiguity explicitly instead of silently "fixing" the docs to match an older plan.
