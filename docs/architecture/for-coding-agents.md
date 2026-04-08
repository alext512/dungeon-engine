# For Coding Agents

This page is the shortest reliable onboarding path for agents working on the repo.

## Read In This Order

- `AGENTS.md`
- `PROJECT_SPIRIT.md`
- `README.md`
- `AUTHORING_GUIDE.md`
- `ENGINE_JSON_INTERFACE.md`
- `architecture.md`
- `CONTRIBUTING.md`
- `CHANGELOG.md`

If the change touches the editor, also read:

- `tools/area_editor/README.md`
- `tools/area_editor/ARCHITECTURE.md`
- `tools/area_editor/DATA_BOUNDARY.md`

## What Is Canonical

For current behavior, trust these first:

- implementation
- `ENGINE_JSON_INTERFACE.md` for the exact JSON contract
- `AUTHORING_GUIDE.md` for current author-facing workflows
- `README.md` for the project summary and current capabilities

Treat these as planning or historical material unless they explicitly say otherwise:

- `plans/`
- `roadmap.md`
- `archive/`
- `archived_editor/`

## High-Risk Change Types

Take extra care when changing:

- command names or invocation shape
- command-library loading or validation
- project manifest rules
- path-derived id behavior
- entity/template expansion rules
- project content under `projects/`
- editor workflows that claim support for structured surfaces

## Validation Checklist

If you touch command surfaces, authoring conventions, or repo-local example project content:

1. Run the relevant automated tests.
2. Validate each repo-local `project.json`.
3. Prefer startup-style validation instead of only low-level engine tests.
4. Re-run project-command validation if command ids or references changed.
5. Do a brief manual smoke start if feasible.

If you touch `tools/area_editor/`, also run its own test suite from inside that folder.

## Documentation Rules

- Do not let plans silently become truth.
- Update canonical contract docs when implementation changes.
- Update author-facing docs when workflows change.
- Keep the changelog historical, not aspirational.
- If docs disagree and the correct behavior is unclear, stop and resolve the ambiguity instead of guessing.

## Common File Map

- runtime entry point: `run_game.py`
- runtime package: `dungeon_engine/`
- editor app: `tools/area_editor/`
- runtime tests: `tests/`
- repo-local example projects: `projects/`
- active docs site: `docs/`

## Good Agent Habits In This Repo

- Prefer reading a real example file from `projects/new_project/` before abstracting.
- Respect the runtime/editor boundary.
- Preserve user changes you did not make.
- Avoid treating old plans as implemented behavior.
- When behavior changes, think in terms of code plus docs plus project validation, not code alone.
