# Engine Concepts

This engine gets much easier once you understand a few core ideas.

## The Engine Code Is Not The Game

The Python code provides systems such as:

- rendering
- input polling
- movement and collision
- command execution
- dialogue and inventory sessions
- save/load

Your project files provide:

- areas
- entity templates
- items
- dialogue data
- reusable command chains
- shared variables and UI presets

That separation is the heart of the project.

## The Command Runner Is The Gameplay Backbone

Most gameplay changes should happen through commands, not direct one-off Python mutations.

That means:

- inputs normally route to named entity commands
- interactions are resolved through command chains
- puzzle state changes are authored in JSON
- flows can compose other flows through built-ins such as `run_sequence`, `run_parallel`, and `run_project_command`

Command chains are eager: when a chain is ready, it keeps running in the same
simulation tick until it reaches a real wait. Rendering sees the settled result
of command, input, and simulation work rather than the intermediate steps.

Scene-changing commands such as `change_area`, `new_game`, and `load_game` are
boundaries. They stop old-scene command work instead of letting later commands
in the old scene continue after the request.

## Projects Are Manifest-Driven

The runtime does not depend on one bundled game. It loads a `project.json` manifest that tells it where to find content.

Typical content roots include:

- `area_paths`
- `entity_template_paths`
- `command_paths`
- `item_paths`
- `asset_paths`

See [Project Manifest](reference/project-manifest.md) for the exact fields.

## Areas And Entities

An area file defines:

- tile size
- tilesets
- tile layers
- placed entities
- local variables
- input routing
- startup behavior such as `enter_commands`

Entities usually come from templates and can then be specialized per instance with:

- authored field overrides
- parameters
- variables
- render settings

## Path-Derived Identity

Files are not just storage. Their path under the configured root becomes their id.

Examples:

- `areas/start.json` -> `areas/start`
- `entity_templates/player.json` -> `entity_templates/player`
- `dialogues/system/title_menu.json` -> `dialogues/system/title_menu`

This is one of the reasons move or rename operations are important authoring events.

## Engine-Owned Sessions

Some recurring gameplay patterns are important enough that the engine owns them directly.

Current engine-owned sessions:

- dialogue sessions opened with `open_dialogue_session`
- inventory sessions opened with `open_inventory_session`

These handle modal input ownership, session lifecycle, and UI flow while still allowing project-specific presets and hooks.

## Persistence Is Layered

Think of persistence as layers:

- authored content is the designed starting state
- transient runtime state is short-lived session state
- persistent runtime state is the changed playthrough state
- save slots serialize the persistent layer

This is why commands can choose whether a mutation is persistent or transient.

## The Editor Is Separate On Purpose

The external editor is not a mini runtime and should not import `dungeon_engine`.

Its job is to:

- operate on the same JSON contract
- provide safe editing for common cases
- preserve unknown fields where possible
- leave advanced escape hatches available

That boundary matters for both architecture and long-term tool safety.

## Render Ordering Has A Specific Model

World rendering uses a unified ordering model across layers and entities:

- `render_order` is the coarse band
- `y_sort` controls vertical interleaving inside that band
- `sort_y_offset` adjusts the sort pivot
- `stack_order` breaks ties

This matters when you want a tile layer, prop, actor, or screen-space element to appear in the right visual order.

## When In Doubt

If something feels unclear, ask:

1. Is this engine behavior or project content?
2. Is this authored state or runtime state?
3. Is this a reusable command flow or a one-off data field?
4. Is the editor supposed to own this safely, or is raw JSON still the better surface?

Those four questions solve a lot of confusion.
