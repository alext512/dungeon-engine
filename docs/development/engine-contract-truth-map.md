# Engine Contract Truth Map

This page maps the active engine contract: the places where authored project
JSON, runtime behavior, validation, editor behavior, tests, and docs must agree.

Use this when changing project manifests, authored JSON shapes, command
behavior, value sources, runtime-owned fields, validation rules, editor
round-tripping, or repo-local sample content.

## Direction

The project direction is:

- no transitional adapter layers
- no retired entry points
- no hidden alternate import surfaces
- no weaker design just because a refactor is larger
- no casual authored JSON breakage

If the contract needs to change, change it deliberately across runtime,
validation, editor behavior, docs, tests, and sample content in the same work.

## Public Contract Sources

| Contract surface | Runtime owner | Validation owner | Editor owner | Canonical docs |
|---|---|---|---|---|
| Project manifest loading | `dungeon_engine/project_context.py` | `dungeon_engine/project_context.py`, `dungeon_engine/startup_validation.py` | `tools/area_editor/area_editor/project_io/project_manifest.py` | `docs/authoring/manuals/engine-json-interface.md`, `docs/authoring/reference/project-manifest.md` |
| Content roots and path-derived IDs | `dungeon_engine/project_context.py`, `dungeon_engine/world/loader.py`, `dungeon_engine/world/loader_entities.py`, `dungeon_engine/items.py`, `dungeon_engine/commands/library.py` | `dungeon_engine/world/loader.py`, `dungeon_engine/world/loader_entities.py`, `dungeon_engine/items.py`, `dungeon_engine/commands/library.py` | `tools/area_editor/area_editor/project_io/project_manifest.py` | `docs/authoring/manuals/engine-json-interface.md` |
| Area file shape | `dungeon_engine/world/loader.py`, `dungeon_engine/world/area.py` | `dungeon_engine/world/loader.py` | `tools/area_editor/area_editor/documents/area_document.py`, area editor widgets | `docs/authoring/manuals/engine-json-interface.md`, `docs/authoring/manuals/authoring-guide.md` |
| Area serialization | `dungeon_engine/world/serializer.py` | runtime/editor round-trip tests | editor document saving code | `docs/authoring/manuals/engine-json-interface.md` |
| Entity template and instance shape | `dungeon_engine/world/loader_entities.py`, `dungeon_engine/world/entity.py` | `dungeon_engine/world/loader_entities.py` | entity template and instance editor widgets | `docs/authoring/manuals/engine-json-interface.md`, `docs/authoring/manuals/authoring-guide.md` |
| Item definition shape | `dungeon_engine/items.py`, `dungeon_engine/inventory.py` | `dungeon_engine/items.py` | item/global-entity editor surfaces | `docs/authoring/manuals/engine-json-interface.md` |
| Project command files | `dungeon_engine/commands/library.py` | `dungeon_engine/commands/library.py`, `dungeon_engine/startup_validation.py` | command file browser/editor surfaces | `docs/authoring/manuals/engine-json-interface.md` |
| Builtin command names and invocation shapes | `dungeon_engine/commands/builtin.py`, `dungeon_engine/commands/builtin_domains/`, `dungeon_engine/commands/registry.py` | `dungeon_engine/commands/registry.py`, `dungeon_engine/startup_validation.py` | command/reference authoring UI where present | `docs/authoring/manuals/engine-json-interface.md`, `docs/authoring/reference/builtin-commands.md` |
| Runtime tokens | `dungeon_engine/commands/runner_resolution.py` | command startup validation and command runtime tests | JSON editing guardrails where present | `docs/authoring/manuals/engine-json-interface.md`, `docs/authoring/reference/runtime-tokens.md` |
| Structured value sources | `dungeon_engine/commands/runner_resolution.py`, `dungeon_engine/commands/runner_value_utils.py`, `dungeon_engine/commands/runner_query_values.py` | startup validation and focused value-source tests | JSON editing guardrails where present | `docs/authoring/manuals/engine-json-interface.md` |
| Command/runtime service boundary | `dungeon_engine/commands/context_services.py`, `dungeon_engine/commands/context_types.py`, `dungeon_engine/commands/runner.py`, `dungeon_engine/commands/registry.py`, `dungeon_engine/engine/game.py` | command injection and runtime tests | not editor-owned | `docs/development/runtime-architecture.md` |
| Startup validation pipeline | `dungeon_engine/startup_validation.py`, `run_game.py` | runtime tests, repo-local project validation, and headless startup smoke | editor author feedback where present | `docs/authoring/startup-checks.md`, `docs/development/verification-and-validation.md` |
| Runtime-owned dialogue and inventory sessions | `dungeon_engine/engine/dialogue_runtime.py`, `dungeon_engine/engine/inventory_runtime.py`, command domains | runtime tests | editor docs and structured field support where present | `docs/authoring/manuals/authoring-guide.md`, `docs/authoring/manuals/engine-json-interface.md` |
| Persistence and save-data behavior | `dungeon_engine/world/persistence.py`, `dungeon_engine/world/persistence_data.py`, `dungeon_engine/world/persistence_snapshots.py`, `dungeon_engine/world/persistence_travelers.py` | persistence and startup tests | editor field support where present | `docs/project/architecture-direction.md`, `docs/authoring/manuals/engine-json-interface.md` |
| External editor project interpretation | runtime/editor contract is shared by file format, not imports | parity tests | `tools/area_editor/area_editor/project_io/project_manifest.py` | `docs/development/editor-data-boundary.md`, `docs/development/editor-architecture.md` |

## Active Ownership Rules

- Runtime project loading is owned by `dungeon_engine/project_context.py`.
- Editor project loading is owned by `tools/area_editor/area_editor/project_io/project_manifest.py`.
- Those two modules stay separate and are aligned through contract tests, not shared imports.
- Builtin command authoring metadata is owned by `dungeon_engine/commands/registry.py` registrations, including strict/mixed validation mode, accepted authored fields, and deferred nested command payload shapes.
- Project command file metadata is owned by `dungeon_engine/commands/library.py`, including `params`, `deferred_param_shapes`, and strict top-level field validation.
- `docs/authoring/manuals/engine-json-interface.md` is the main public JSON contract reference.
- `docs/authoring/manuals/authoring-guide.md` explains how to use that contract in real projects.
- `docs/development/runtime-architecture.md` explains the runtime module map and command service boundary.
- `docs/development/verification-and-validation.md` owns maintainer verification expectations.

## Drift-Prone Surfaces

These are the surfaces most likely to fall out of sync:

| Surface | Current risk | Next worthwhile action |
|---|---|---|
| Builtin command inventory | Command behavior still lives in domain modules, while authoring metadata is exposed through registry contract snapshots. | Use the registry contract snapshots for validation tests, docs checks, or editor assistance where that removes hand-maintained drift. |
| Runtime tokens and value sources | Tokens/value-source behavior is split across resolver modules and docs. | Audit docs against resolver behavior and add focused tests where the docs rely on subtle runtime behavior. |
| Engine-known entity fields | Loader, serializer, editor widgets, and docs all need to agree on authored versus runtime-owned fields. Shared editor surfaces such as the render-properties dock can drift if they only update their owned subset but forget to preserve the rest of the authored object. | Inventory fields, label ownership, and tighten round-trip expectations, including proving focused editor surfaces do not strip raw-only engine-owned fields. |
| Project manifest parity | Runtime and editor intentionally interpret the same manifest without importing each other. | Keep parity tests focused on every manifest key with behavior beyond simple path storage, including runtime-control fields such as `save_dir`, `input_targets`, `debug_inspection_enabled`, `global_entities`, and `command_runtime`. |
| Command service injection | Production runtime wiring and test-friendly partial contexts can blur together. | Keep production assembly strict, and keep command-visible runtime payload types in `context_types.py`. |
| Startup validation coverage | Unit tests can pass while actual repo-local projects still contain broken references. | Keep `tools/validate_projects.py` aligned with startup validation, covered by `tests/test_project_validation_tool.py`, and run it for contract-sensitive changes. |
| Sample content coverage | Example content may not exercise every important authored surface. | Keep `docs/development/sample-content-coverage.md` aligned with what canonical sample projects prove. |
| Authoring docs language | Time-relative terms can hide whether a feature is active, advanced, or slated for removal. | Reword active docs to use current architectural categories, or remove the feature if it is truly retired. |

## Change Checklist

When changing the contract, update every applicable row:

| If changing... | Check these files |
|---|---|
| Project manifest keys or defaults | `dungeon_engine/project_context.py`, `tools/area_editor/area_editor/project_io/project_manifest.py`, `tests/test_project_layout_parity.py`, `docs/authoring/manuals/engine-json-interface.md`, `docs/authoring/reference/project-manifest.md` |
| Area JSON fields | `dungeon_engine/world/loader.py`, `dungeon_engine/world/serializer.py`, area editor document/widgets, `tests/test_project_content_contract.py`, `docs/authoring/manuals/engine-json-interface.md` |
| Entity/template JSON fields | `dungeon_engine/world/loader_entities.py`, `dungeon_engine/world/serializer.py`, entity editor widgets, `tests/test_project_content_contract.py`, `docs/authoring/manuals/engine-json-interface.md` |
| Item/inventory fields | `dungeon_engine/items.py`, `dungeon_engine/inventory.py`, item editor surfaces, inventory runtime tests, `docs/authoring/manuals/engine-json-interface.md` |
| Builtin command shape | `dungeon_engine/commands/builtin.py`, `dungeon_engine/commands/builtin_domains/`, `dungeon_engine/commands/registry.py`, `dungeon_engine/commands/audit.py`, startup validation tests, `docs/authoring/manuals/engine-json-interface.md` |
| Runtime tokens or value sources | `dungeon_engine/commands/runner_resolution.py`, `dungeon_engine/commands/runner_value_utils.py`, `dungeon_engine/commands/runner_query_values.py`, focused value-source tests, `docs/authoring/manuals/engine-json-interface.md` |
| Command runtime services | `dungeon_engine/commands/context_services.py`, `dungeon_engine/commands/context_types.py`, `dungeon_engine/commands/registry.py`, `dungeon_engine/commands/runner.py`, `dungeon_engine/engine/game.py`, runtime architecture docs |
| Startup checks | `dungeon_engine/startup_validation.py`, `run_game.py`, `tests/test_command_authoring_and_runtime_cache.py`, `docs/authoring/startup-checks.md`, `docs/development/verification-and-validation.md` |
| Editor project interpretation | `tools/area_editor/area_editor/project_io/project_manifest.py`, editor tests, `tests/test_project_layout_parity.py`, editor architecture/data-boundary docs |

## Required Validation Habits

For contract-sensitive changes, use the maintainer workflow:

```text
.venv/Scripts/python -m unittest discover -s tests -v
```

If the editor changed:

```text
cd tools/area_editor
..\..\.venv\Scripts\python -m unittest discover -s tests -v
```

For repo-local projects:

```text
.venv/Scripts/python tools/validate_projects.py
.venv/Scripts/python tools/validate_projects.py --headless-smoke
```

When feasible, also smoke the startup path:

```text
.venv/Scripts/python run_game.py --project projects/new_project --headless --max-frames 2
```

## Immediate Refactor Targets

Based on the current map, the next high-value implementation targets are:

1. use command contract snapshots where they improve docs checks, validation coverage, or editor command assistance
2. keep tightening command-visible service contracts where callbacks still use broad types
3. audit engine-known entity fields across loader, serializer, editor widgets, and docs
4. expand repo-local project validation coverage where it catches real content-facing regressions
5. reword or remove active docs that describe current behavior as time-relative or retired
