# Verification and Validation

Use this page when you are changing Python code, editor behavior, docs infrastructure, or repo-local example content and need the maintainer workflow rather than the normal author workflow.

If you are authoring a game through JSON and the editor, the user-facing page is [Startup Checks](../authoring/startup-checks.md).

## Runtime Tests

```text
.venv/Scripts/python -m unittest discover -s tests -v
```

## Editor Tests

From `tools/area_editor/`:

```text
..\..\.venv\Scripts\python -m unittest discover -s tests -v
```

## Quick Startup Smoke

This is a fast way to confirm that a project loads through the normal startup path:

```text
.venv/Scripts/python run_game.py --project projects/new_project --headless --max-frames 2
```

Headless mode still exercises startup validation, project loading, command-library loading, and early runtime wiring.

## Repo-Local Project Validation

If you changed command ids, command references, authoring conventions, or repo-local project content, validate each repo-local project manifest directly.

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

## Docs Site Commands

Install docs-only dependencies:

```text
pip install -r requirements-docs.txt
```

Preview locally:

```text
mkdocs serve
```

Build static output:

```text
mkdocs build --strict
```

## Recommended Maintainer Habit

When you change command surfaces, authoring conventions, repo-local example projects, or editor workflows:

1. run the relevant automated tests
2. validate each affected repo-local `project.json`
3. prefer startup-style validation, not only low-level tests
4. re-run project-command validation if ids or references changed
5. do a brief smoke start when feasible
6. update the canonical docs that describe the changed behavior

## Related Pages

- [Startup Checks](../authoring/startup-checks.md) for what authors can expect before play begins
- [For Coding Agents](for-coding-agents.md) for repo-specific agent workflow
- [Docs Maintenance](docs-maintenance.md) for the docs truth model
