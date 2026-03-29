# Architecture

This document describes the current editor architecture plus the intended shape of later slices.

Phase 1 is implemented. Editing, saving, validation, and runtime handoff remain planned work.

## High-Level Shape

The tool is a normal standalone application with a small number of clearly separated concerns.

Current slices:

- app shell
- project scanner
- area document loading/saving
- tileset and asset catalog
- UI layer
- tests

Planned later slices:

- entity reference helpers
- editing operations
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
  - current: cell-flag editing helpers, tile painting helpers
  - planned: place entity, move entity, reorder entity, rename id
- `widgets/`
  - tile canvas, layer panel, area list, template list, generic file-tree panels,
    tabbed document area, JSON viewer, image viewer, tileset browser
- `tests/`
  - manifest loading, asset resolution, and area-document round-tripping

Planned later modules/slices:

- `operations/`
  - expand beyond cell flags into tile and entity editing operations
- `widgets/`
  - tileset browser, entity inspector, entity-ref picker, raw JSON pane
- `settings/`
  - tool-owned preferences and UI state

## Recommended Data Flow

The future tool should ideally follow this flow:

1. Load project manifest and discover content roots.
2. Load one area file into a tool-owned document model.
3. Run editing operations against that document model.
4. Save back to JSON while preserving unknown fields as much as possible.
5. Optionally launch the runtime externally for verification.

## Document Model Guidance

The future tool should not use runtime objects as its internal editing model.

Prefer tool-owned document shapes that represent authored data, for example:

- area dimensions
- tilesets used by an area
- tile layers
- cell flags
- entity instances
- per-instance parameters
- unknown passthrough fields

Tool-owned document models should be optimized for safe editing and round-tripping, not gameplay execution.

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

## Recommended First Implementation Order

The implementation order so far has covered:

1. project scan and area list
2. load area and render read-only grid

The next recommended order is:

3. tabbed document area (done — multiple documents open in tabs, JSON/image viewers for non-area content)
4. tile painting
5. entity placement and movement
6. entity inspector with entity-ref fields
7. preservation-focused saving
8. launch runtime externally
