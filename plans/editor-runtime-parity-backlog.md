# Editor Runtime Parity Backlog

This backlog tracks concrete places where the external editor and runtime need
to stay aligned. It is scoped to active project/file contracts, not archived
editor code.

## Current Strong Points

- Runtime and editor manifest loaders both resolve manifest roots, shared
  variables, display dimensions, startup area, save directory, input targets,
  debug-inspection flag, global entities, and command-runtime settings.
- Runtime/editor parity tests compare area, entity template, command, item, and
  global entity discovery, and now also compare the normalized runtime-control
  manifest fields the editor can rely on.
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
- Hardened editor manifest normalization so runtime-control fields such as
  `save_dir`, `input_targets`, `debug_inspection_enabled`, `global_entities`,
  and `command_runtime` match the runtime loader instead of living only in raw
  JSON.
- Added focused editor coverage proving the project-settings surface can edit
  its owned fields without dropping runtime-control manifest data that still
  lives in raw JSON.
- Added focused entity-instance and template regression coverage proving the
  structured editors can apply owned fields without dropping raw-only
  engine-owned fields such as `entity_commands`, `inventory`, `input_map`,
  `scope`, and `color`.
- Promoted `scope` into the structured entity-instance and template editor
  surfaces so one high-impact engine-owned field no longer depends on raw JSON
  editing alone.
- Added focused shared-variable editor coverage proving display/movement edits
  do not drop other engine-used sections such as `dialogue_ui`,
  `inventory_ui`, or custom project data.
- Added focused item-editor coverage proving common item-field edits preserve
  raw-only item behavior such as `use_commands`, while also keeping extra art
  object keys intact.
- Added focused global-entities editor coverage proving edits to the
  `global_entities` array preserve the rest of `project.json`.
- Added focused area-start integration coverage proving `enter_commands` edits
  preserve other area JSON surfaces such as `camera`, `input_targets`, and
  unrelated root data.
- Added shared render-properties integration coverage proving layer render edits
  preserve unrelated layer metadata and entity render edits preserve
  non-render authored entity fields while saving through the normal editor flow.

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
