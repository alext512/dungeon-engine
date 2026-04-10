# Architecture

This document describes the current editor architecture plus the intended shape
of later slices.

Status: active architecture note for the current standalone editor.

The editor has moved well beyond the earliest phase-1 slice. Editing, saving,
focused validation, project-level surfaces, and reference-aware file workflows
are implemented. The main remaining planned areas are runtime handoff/launch
integration, broader structured coverage for newer engine-owned fields, richer
direct-manipulation workflows, and continued internal decomposition as the tool
grows.

## High-Level Shape

The tool is a normal standalone application with a small number of clearly
separated concerns.

Current slices:

- app shell
- project scanner
- area document loading/saving with unknown-field preservation
- tileset, asset, and template catalog support
- focused editing operations for tiles, cell flags, entities, areas, and
  tilesets
- world-space entity placement plus basic screen-space placement, selection,
  and nudging support
- structured editors for project manifest, shared variables, items, templates,
  global entities, and entity instances
- reference-aware file/folder reorganization for file-backed content
- UI layer
- tests

Planned later slices:

- broader structured coverage for newer engine-owned fields and workflows
- richer direct-manipulation workflows, especially for screen-space content
- runtime handoff / launch integration
- tool-owned settings

## Dependency Direction

Keep the dependency direction simple:

- UI depends on editing operations and document services
- editing operations depend on area documents
- area documents depend on file I/O and preservation logic
- file I/O depends only on the filesystem and JSON handling

Nothing in the tool should depend on `dungeon_engine`.

## Proposed Future Internal Modules

Current modules already include:

- `app/`
  - startup, configuration, session lifecycle
- `project_io/`
  - manifest loading, path resolution, area discovery, template discovery
- `documents/`
  - area document model, layer document model, entity instance document model
- `catalogs/`
  - tileset image indexing, entity/template summaries
- `operations/`
  - current: cell-flag, tile, tileset, entity, and area editing helpers
  - later: continue extracting editor-window logic into narrower
    operations/services
- `widgets/`
  - tile canvas, layer panel, area list, template list, generic file-tree
    panels, tabbed document area, JSON viewer, image viewer, tileset browser,
    project-level editors, entity/template/item editing surfaces, and
    supporting docks
- `tests/`
  - manifest loading, asset resolution, area-document round-tripping,
    canvas behavior, focused operations, browser/workspace behavior, and
    editor panels

Planned later modules/slices:

- `widgets/`
  - continue decomposing the largest widgets and docks as the editor surface
    expands
- `settings/`
  - tool-owned preferences and UI state

## Recommended Data Flow

The current tool should continue to follow this flow:

1. Load project manifest and discover content roots.
2. Load one area file into a tool-owned document model.
3. Run editing operations against that document model.
4. Save back to JSON while preserving unknown fields as much as possible.
5. Optionally launch the runtime externally for verification.

## Document Model Guidance

The tool should not use runtime objects as its internal editing model.

Prefer tool-owned document shapes that represent authored data, for example:

- area dimensions
- tilesets used by an area
- tile layers
- cell flags
- entity instances
- per-instance parameters
- unknown passthrough fields

Tool-owned document models should be optimized for safe editing and
round-tripping, not gameplay execution.

## Unknown Field Strategy

The architecture should include a preservation story from the start.

That likely means each tool-owned document keeps:

- fields the tool understands well
- passthrough buckets for unknown fields or subtrees

Without this, the tool will become dangerous as soon as runtime content evolves.

## Validation Strategy

Validation should happen in layers:

1. Basic file and schema sanity checks owned by the tool.
2. Editing-time checks for things like duplicate ids or missing entity references.
3. Optional external runtime verification when the user wants a stronger check.

The tool does not need perfect runtime parity to be useful.

## Launch Integration

If the tool later offers a "test in game" action, it should:

- save the current area first
- run the game as a subprocess
- pass project and area identifiers as CLI args

It should not embed or import the runtime loop.

## Recommended Ongoing Implementation Order

Earlier implementation phases covered:

1. project scan and area list
2. load area and render read-only grid
3. tabbed document area and non-area viewers
4. tile painting and tile selection/stamping
5. world/screen entity placement, selection, and nudging
6. structured editors plus guarded JSON editing for focused content surfaces
7. preservation-focused saving and reference-aware file operations

The next recommended order is:

8. continue splitting large editor modules into clearer services/helpers
9. broaden structured editing for newer engine-owned entity/workflow fields
10. improve direct-manipulation workflows such as drag editing and richer screen-space placement polish
11. add runtime launch/handoff integration
