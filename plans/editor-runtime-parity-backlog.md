# Editor Runtime Parity Backlog

This backlog tracks concrete places where the external editor and runtime need
to stay aligned. It is scoped to active project/file contracts, not archived
editor code.

## Current Strong Points

- Runtime and editor manifest loaders both resolve manifest roots, shared
  variables, display dimensions, and startup area.
- Runtime/editor parity tests compare area, entity template, command, item, and
  global entity discovery.
- Area documents preserve unknown fields while exposing key authored surfaces
  such as tile layers, cell flags, entity instances, render properties, and
  enter commands.
- Editor manifest loading stays separate from runtime loading and is aligned by
  tests rather than imports.

## Completed In This Pass

- Added editor-side project command discovery through
  `area_editor.project_io.project_manifest.discover_commands(...)`.
- Expanded runtime/editor parity coverage so command ids are compared alongside
  area, template, and item ids.
- Added editor manifest coverage for command discovery from `command_paths`.

## Next High-Value Gaps

- Audit engine-known entity fields against the structured entity instance and
  template editors.
- Add parity or round-trip tests for any field that the runtime treats as
  engine-owned and the editor edits through a focused widget.
- Improve command/reference pickers for authored fields that currently depend on
  raw JSON editing.
- Add runtime handoff from the editor by saving first and launching
  `run_game.py` externally with project and area ids.

## Validation Expectations

- Run runtime tests when parity tests change.
- Run editor tests from `tools/area_editor/` when editor project I/O or widgets
  change.
- Run `tools/validate_projects.py` after project-content or command-reference
  changes.
