# Scope

## Intended Core Scope

The first useful version of the future tool should focus on room editing only.

That means:

- open a project
- browse authored areas
- open one area
- view and edit tile layers
- paint tiles
- edit walkability and related cell flags
- place, move, reorder, and delete entity instances
- edit a small set of high-value instance fields
- edit selected per-instance parameters
- provide better UI for parameters that reference other entity ids
- save safely back to JSON

## Strong Candidates For Early Support

These are especially aligned with the user's stated needs:

- tileset browsing
- visual layer selection
- cell selection and coordinate feedback
- entity list per cell
- entity id generation help
- parameter fields with room-local entity pickers
- raw JSON view for advanced fields
- save plus quick launch of the runtime as an external process

## Out Of Scope For Early Versions

Do not treat these as required for version one:

- gameplay simulation
- command execution preview
- in-tool save/load persistence playback
- dialogue runtime emulation
- animation preview systems that depend on runtime behavior
- full visual command-chain editing
- project-wide refactors across every content type
- combat, AI, or interaction debugging
- importing or reproducing runtime `World`, `Entity`, or command-runner behavior

## Editing Philosophy

The tool should own only the fields it can edit confidently.

For everything else:

- preserve the original structure
- avoid destructive rewrites
- offer raw JSON escape hatches if needed later

## Data Ownership Expectations

The future tool may reasonably own:

- room tilesets
- tile layers
- cell flags
- entity placement
- entity ordering fields
- selected instance parameters

The future tool should be cautious around:

- large free-form command payloads
- nested data blobs it does not understand
- fields that are clearly runtime-derived
- any content outside the currently edited room unless explicitly requested

## Future Expansion

Possible later additions, but not assumed now:

- stronger validation
- reusable room templates
- map-wide search tools
- project-wide entity reference repair tools
- richer side-panel inspectors
- optional sidecar metadata for smarter field widgets
