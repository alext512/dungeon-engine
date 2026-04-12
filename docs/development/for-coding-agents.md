# For Coding Agents

This page is the shortest reliable onboarding path for agents working on the repo.

## Read In This Order

- [AGENTS.md](https://github.com/alext512/dungeon-engine/blob/main/AGENTS.md)
- [Project Spirit](../project/project-spirit.md)
- [README.md](https://github.com/alext512/dungeon-engine/blob/main/README.md)
- [Authoring Guide](../authoring/manuals/authoring-guide.md)
- [Engine JSON Interface](../authoring/manuals/engine-json-interface.md)
- [Architecture Direction](../project/architecture-direction.md)
- [CONTRIBUTING.md](https://github.com/alext512/dungeon-engine/blob/main/CONTRIBUTING.md)
- [CHANGELOG.md](https://github.com/alext512/dungeon-engine/blob/main/CHANGELOG.md)

If the change touches the editor, also read:

- [Editor Manual](../authoring/editor/editor-manual.md)
- [Editor Architecture](editor-architecture.md)
- [Editor Data Boundary](editor-data-boundary.md)

If you want the fast mental model first, read:

- [Engine In 10 Minutes](engine-in-10-minutes.md)
- [Engine Contract Truth Map](engine-contract-truth-map.md)

## What Is Canonical

For current behavior, trust these first:

- implementation
- [Engine JSON Interface](../authoring/manuals/engine-json-interface.md) for the exact JSON contract
- [Engine Contract Truth Map](engine-contract-truth-map.md) for contract ownership and cross-file update expectations
- [Authoring Guide](../authoring/manuals/authoring-guide.md) for current author-facing workflows
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

Use [Startup Checks](../authoring/startup-checks.md) when you need the exact current startup pipeline and the command-bearing surfaces the runtime audits before launch.
Use [Verification and Validation](verification-and-validation.md) when you need the full maintainer workflow: tests, smoke commands, repo-local project validation, and docs builds.

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
- Use [Sample Content Coverage](sample-content-coverage.md) before changing
  `projects/new_project/`, then update that page if the sample starts proving a
  new contract.
- Respect the runtime/editor boundary.
- Preserve user changes you did not make.
- Avoid treating old plans as implemented behavior.
- When behavior changes, think in terms of code plus docs plus project validation, not code alone.
