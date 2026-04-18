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
The repo-local `new_project` version of this smoke is covered by
`tests/test_startup_smoke.py` when that fixture is present.

## Repo-Local Project Validation

If you changed command ids, command references, authoring conventions, or repo-local project content, validate each repo-local project manifest directly.

```text
.venv/Scripts/python tools/validate_projects.py
.venv/Scripts/python tools/validate_projects.py --headless-smoke
```

The validation command itself is covered by `tests/test_project_validation_tool.py`
so changes to its input handling, default project discovery, headless-smoke
flow, or exit-code behavior stay visible in the runtime suite. The optional
`--headless-smoke` mode runs the same `run_game.py --project ... --headless
--max-frames 2` startup path the runtime uses, but loops over each selected
project automatically.

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

Check repo-local Markdown links:

```text
.venv/Scripts/python tools/check_markdown_links.py
```

The Markdown link checker is covered by `tests/test_markdown_link_checker.py`
so stale local doc paths and pointer targets stay visible in the runtime suite.

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
- [Sample Content Coverage](sample-content-coverage.md) for what `projects/new_project` proves today
- [For Coding Agents](for-coding-agents.md) for repo-specific agent workflow
- [Docs Maintenance](docs-maintenance.md) for the docs truth model
