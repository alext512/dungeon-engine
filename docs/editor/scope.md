# Scope

## Intended Scope

The editor's goal is to let a non-coder build a full game through the supported
template-driven workflow while keeping raw JSON escape hatches for advanced users.

That means a content creator should be able to:

- create and edit areas
- paint tiles and edit cell flags
- place entities from a provided template library
- configure exposed entity fields, parameters, variables, references, and assets
- create or edit supported item records
- create or edit supported dialogue and menu data
- configure selected project-level settings such as startup area, shared variables,
  UI presets, input routing, and global entities
- launch the runtime directly from the editor for quick testing

The room-editing workflows are already implemented. The remaining scope is the
editor catch-up work needed to support the newer runtime-facing authoring surface.

## Out Of Scope

Do not treat these as required:

- gameplay simulation or command execution preview
- in-tool save/load persistence playback
- dialogue or inventory runtime emulation
- animation preview systems that depend on runtime behavior
- full visual command-chain editing
- arbitrary visual authoring of every possible JSON structure the runtime can express
- generic free-form entity-system authoring that ignores the curated template library
- combat, AI, or interaction debugging
- importing or reproducing runtime `World`, `Entity`, or command-runner behavior

## Editing Philosophy

The tool should own only the fields it can edit confidently.

For everything else:

- preserve the original structure
- avoid destructive rewrites
- offer raw JSON escape hatches

## Data Ownership Expectations

The tool may reasonably own structured editing for:

- area tilesets, tile layers, cell flags, entry points, and camera defaults
- entity placement plus exposed engine-known fields, variables, visuals, and references
- supported item definitions or item archetype records
- dialogue/menu file structure
- selected project manifest settings
- shared variables and UI presets
- input routing configuration

The tool should be cautious around:

- large free-form command payloads
- nested data blobs it does not understand
- fields that are clearly runtime-derived
- advanced template internals that are not part of the supported workflow
- content outside the currently edited document unless explicitly requested
