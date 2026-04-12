# Python Dungeon Engine Architecture

## Purpose

This project is a new Python game project. It is not a refactor of the old Godot game.

The spirit should still come from the old Godot project:

- gameplay is driven by reusable commands
- objects do not hard-code bespoke one-off behavior
- the same command ideas should be usable by the player, interactable objects, and dialogue choices
- testing content creation should be possible early through a lightweight authoring workflow

This is not meant to be a totally generic engine. It is a focused, data-driven puzzle/RPG framework.

## Scope

The core engine is centered on:

- grid movement
- interactable objects
- dialogue
- world creation
- data-driven authoring support

This document is about architectural direction, not a promise of specific future engine features.

## Tech Stack

- Python 3.11+
- `pygame-ce` as the runtime library for windowing, rendering, input, timing, fonts, and audio
- JSON for content data such as areas, entities, items, and authored room state
- Python standard library for most support code, including `dataclasses`, `pathlib`, `json`, and `typing`

`pygame-ce` is a good fit here because we want a Python-first project with direct control over rendering, data loading, UI flow, and command execution without fighting a heavier engine framework.

## Design Principles

### 1. Commands are the main gameplay language

Almost everything should be expressed as commands or command chains.

That includes:

- player movement attempts
- object interactions
- tile triggers
- dialogue branching

Systems still exist, but systems provide primitives. Commands orchestrate those primitives into gameplay.

### 2. Input does not directly perform gameplay

Input should request top-level commands.

Example:

- pressing Up does not directly move an entity
- it queues a `run_entity_command` request for the currently routed `move_up` target's configured entity command
- that entity command can call sub-commands or services to set facing, check collision, push a block, animate movement, and fire enter/leave triggers

Control routing is layered:

- the project can also define default `input_targets`
- an area may override `input_targets`
- actions omitted by both stay unrouted until runtime commands assign them
- the routed entity for each logical action may define its own `input_map`
- runtime commands may reroute one action or many through `set_input_target` / `route_inputs_to_entity`
- modal controllers may snapshot and restore borrowed routes through `push_input_routes` / `pop_input_routes`
- the project may enable or disable debug inspection controls such as zoom/pause/step through `project.json`

This keeps player input and controller-driven behavior aligned around the same action model.

### 3. Grid-first, not grid-only forever

The first implementation is grid-based. The data model and command API should not assume that grid movement is the only future mode.

The same top-level action can later be executed by:

- a grid movement executor
- a free movement executor
- a turn scheduler that decides when actions are allowed

### 4. Authoring tools stay outside the runtime

The project needs a practical authoring workflow, but the runtime should not be coupled to a built-in editor.

The intended pattern is:

- the runtime consumes JSON files
- external authoring tools or focused helpers read and write those same JSON files
- gameplay/runtime code does not import tool UI code
- tool-specific state should stay outside runtime data structures

### 5. Data should describe content, not replace code entirely

The project is command-driven and data-driven, but not every hard problem should be forced into raw data.

The intended split is:

- data defines content, command chains, entities, items, dialogue, and room setup
- code defines the runtime, command execution, rendering, collision, UI, and persistence

Project content may live inside this repo for version control, for example under `projects/my_game/`, but that does not make it engine data. The real boundary is:

- engine code lives under `dungeon_engine/`
- project content lives in a project folder selected through `project.json`

That means a repo-local project is just a convenient versioned project, not a special built-in one.

## High-Level Runtime Model

### Areas

An area is a playable map with:

- tile layers
- cell-flag data
- placed entities
- local variables
- transitions to other areas

Areas are loaded from JSON and can be created or modified in authoring tools.

### Entities

Entities are runtime objects such as:

- player
- NPC
- lever
- gate
- button
- chest
- pickup
- door
- projectile
- invisible trigger

Entities should be defined from templates plus local overrides.

### Components and State

Use a lightweight entity/component style world model. It does not need to be a strict ECS for its own sake, but it should keep data separate from gameplay execution.

Typical state buckets:

- position and facing
- visual and animation state
- collision and pushability
- authored tags used for grouping, selection, and reset targeting
- interaction command chains
- trigger command chains
- stats and custom variables
- visibility, presence, and entity-command enabled state

### Systems

Systems should provide reusable services such as:

- rendering
- camera
- tile map lookup
- collision and spatial lookup
- movement execution
- animation playback
- dialogue UI
- save/load

Systems should not become giant one-off gameplay scripts. If a behavior is content-specific, it should usually be represented as commands.

The camera should be command-addressable too:

- authored areas can provide initial camera defaults through structured `follow`, `bounds`, and `deadzone` sections
- commands can retarget it to a specific entity or to the current recipient of one routed input action
- follow state should include offsets, so content can frame a target intentionally
- commands can apply or clear bounds and deadzone policies
- commands can clear follow mode for manual framing
- commands can move or teleport it independently for cutscenes and inspection
- save/load and transfer flow should preserve explicit camera state rather than inferring it from a privileged player entity

## Command Architecture

### Command runner

The project needs a central command runner that can:

- execute a command immediately
- execute a chain of commands
- branch on success, failure, or choice
- wait for async commands to finish
- pass context between related commands

Project command libraries should be indexed at project startup so runtime
`run_project_command` calls only use in-memory definitions instead of rediscovering
files from disk during active play.

### Command context

Commands need access to live runtime state, but primitive command APIs should stay narrow and explicit. The engine may keep a broad internal runtime root, while primitive commands receive only the dependencies they actually need.

The current implementation exposes that access through a `CommandContext` plus a `CommandServices` bundle. Commands that need runtime systems can request `services` and read grouped surfaces like:

- `services.world` (world + area)
- `services.ui` (camera, screen manager, dialogue/inventory runtimes)
- `services.audio`
- `services.persistence`
- `services.runtime` (scene-change requests, debug toggles)

The bundle is assembled in `engine/game.py` and mirrors the real play-mode wiring, so commands can remain narrow without importing concrete runtime classes. Protocols in `commands/context_types.py` describe the stable shape of those services for typing and future refactors.

`CommandContext` is now a thin facade over that bundle rather than a second copy of the same runtime references. Registry injection still lets commands ask for explicit parameters like `world`, `area`, `camera`, `dialogue_runtime`, or `request_area_change`, but those values are resolved from `CommandServices` instead of being duplicated as separate stored fields.

### Command types

Expected early command categories:

- flow: sequence, branch, filter, wait, repeat-if-needed
- movement: claim grid position, move entity in world or screen space, push entity, move entity along a path
- interaction: trigger entity, trigger tile, enable, disable
- visibility/map: show, hide, remove from map, restore to map
- dialogue: show text, choices, branch on choice
- variables: set, increment, compare, copy
- level/world: change area, warp, set spawn, persist state, reset transient state, reset persistent state
- camera: follow, move, lock
- audio: play sound, play music, stop audio

### Command composition

Commands should support composition patterns inspired by the old Godot project:

- execute these children in order
- if condition is true, run one branch, otherwise another
- choose next branch from a dialogue selection
- disable a command after it has run once

Movement should follow the same spirit.

Example movement chain:

1. receive `run_entity_command(entity_id=input_target_for_move_right, command_id=configured_move_right_command)`
2. start any project-authored walk animation
3. query the target tile and its blockers
4. if blocked by a pushable object, try the push chain
5. if passable, claim the target tile and start the pixel tween
6. run any authored cleanup command such as restoring the idle frame
7. finish

## World Data

The source of truth for content should be JSON files.

Expected content groups:

- `areas/`
- `entity_templates/`
- `items/`
- optional ordinary project JSON data such as `dialogues/`

Authoring tools should read and write these files.

The first versions can keep the schemas simple. They do not need to predict every future feature perfectly.

## Suggested Project Structure

```text
projects/
    my_game/                     # Versioned project content (optional location)
        project.json
        shared_variables.json
        areas/
        entity_templates/
        items/
        assets/
        commands/

dungeon_engine/
    config.py

    engine/
    world/
    systems/
    commands/

tools/
    area_editor/
```

Suggested responsibilities:

- `engine/`: game loop, renderer, camera, asset loading, audio, dialogue/inventory session runtimes, screen-space UI
- `world/`: area model, entity storage, data loading, persistence helpers
- `systems/`: movement, collision, interaction, animation
- `commands/`: command runner, registry, command implementations, project command library
- `tools/`: external authoring tools that operate on the same JSON data

Important boundary:

- `dungeon_engine/` is the runtime package
- `projects/<name>/` is one possible place to keep project content under version control
- the engine must not assume any specific project exists there

## Authoring Tooling

Authoring tools should operate on the same file format as play mode, not a separate hidden format.

Early authoring scope:

- create a room
- resize a room
- paint tiles
- toggle blocked flags
- place and remove entities
- select an entity
- edit a small set of important properties
- save and load
- launch the same room in the game quickly

The first tool does not need a full visual command-chain authoring UI. A focused convenience tool plus raw JSON editing for advanced fields is acceptable early on.

## Dialogue

Dialogue needs:

- text wrapping and pagination
- advance behavior
- branching results
- temporary input ownership while active

### Engine-owned dialogue sessions (recommended default)

The engine now provides a built-in dialogue session runtime through
`open_dialogue_session` and `close_dialogue_session`. This path handles input
lock, text pagination, choice selection, nested session suspension/resume, and
cleanup automatically. Projects supply dialogue data as ordinary JSON files and
configure the visual layout through UI presets. Caller hooks allow project
commands to run at session boundaries.

This is the recommended default for most dialogue and menu needs.

### Controller-owned dialogue (advanced/custom)

For flows that need full custom control, projects can still build dialogue
manually using the same primitives the engine-owned path is built on:

1. push the currently borrowed input routes
2. reroute those actions to a UI entity
3. show panel image through screen-space commands
4. optionally show portrait image
5. load ordinary JSON dialogue/menu data into UI-entity variables
6. derive wrapped lines and the currently visible text through generic helper commands
7. render the returned text through normal screen-text commands
8. let the UI entity decide whether input advances text, changes selection, opens another dialogue, or closes the dialogue
9. if nested dialogue is needed, store the previous state in an entity-owned stack before replacing it
10. pop the borrowed routes to restore the exact previous input ownership

Both paths stay aligned with the general command architecture instead of turning
dialogue into a separate hardcoded menu system.

## Persistence

Persistence should support:

- player progress
- current area
- persistent area state
- transferred cross-area traveler state
- current camera state when exact session restore matters
- entity visibility/enabled changes
- puzzle state changes

Keep the first persistence model simple and explicit. The goal is reliable restore behavior, not clever serialization.

### Persistent State Model

The project should treat persistence as a layered system, not as a second full copy
of every room or entity definition.

Use these layers:

- authored content: the original area JSON plus entity templates
- transient runtime state: changes that only matter until the area is reloaded or the game closes
- persistent runtime state: changes that should survive area transitions and save/load
- save slots: serialized snapshots of the persistent runtime state

The intended load flow for an area should be:

1. load the authored area JSON
2. instantiate entities from templates plus per-instance authored overrides
3. apply persistent overrides for that area and entity ids
4. begin play with transient state starting fresh

This keeps the original room files as the source of truth for designed starting state
while allowing playthrough-specific changes to be layered on top.

### What Belongs Where

Authored room data should describe how a room starts before the player changes it:

- placed entities
- template parameters
- authored per-instance overrides
- default local variables

Persistent state should describe what changed during this playthrough:

- opened or closed gates
- consumed chests or pickups
- puzzle progress that should survive leaving the area
- entity visibility, enabled state, and relevant variables
- global progress flags such as bosses defeated or quests advanced

Transient state should describe short-lived runtime details that do not need to survive
an area change:

- in-progress movement or animation state
- temporary combat or interaction state
- one-room-only changes that should reset when the room reloads

### Prefer Overrides Over Full Entity Copies

For persistence, prefer storing per-area and per-entity override data keyed by stable ids
instead of writing full duplicate JSON copies of every entity.

Example shape:

```json
{
  "globals": {
    "boss_dead": true
  },
  "areas": {
    "test_room": {
      "entities": {
        "gate_1": {
          "visible": false,
          "variables": {
            "blocks_movement": false
          }
        },
        "lever_1": {
          "variables": {
            "toggled": true
          }
        }
      }
    }
  }
}
```

This keeps save data compact and readable, avoids duplication, and makes it clear
which changes came from the player's playthrough instead of the original room design.

### Reset Behavior

Two reset concepts are useful and should stay separate:

- reset transient state: restore an entity to its authored state plus any persistent overrides that still apply
- reset persistent state: clear the saved overrides for an entity or a specific field so future loads fall back to authored room data

This distinction matters for puzzle design. Some effects should reset when the room reloads,
while others should remain solved across area transitions.

Persistent reset should support room-level filtering without hardcoding every entity id.
Authored entity tags are a good fit for this.

A useful conceptual model is:

- entities may declare optional authored tags
- a reset command may accept `include_tags` and `exclude_tags`
- if no filters are supplied, the whole room is reset
- matching should only consider authored tags, not ad-hoc runtime mutation

This allows content such as:

- reset only puzzle objects
- reset everything except story-critical entities
- reset only entities that were meant to respawn

Reset timing should also be explicit:

- immediate: clear the selected persistent overrides and rebuild the room now
- on_reentry: clear the selected persistent overrides, but only rebuild when the room is next loaded

`on_reentry` is useful when an in-place rebuild would create awkward runtime edge cases,
while `immediate` is useful for visible room-reset mechanics such as time loops or magical resets.

### Naming Guidance

Avoid using the word "parameter" for every kind of changeable value. In this project,
it is useful to distinguish between:

- template parameters: authored inputs used to specialize a template instance
- variables/state: mutable runtime values used by gameplay and persistence
- persistent overrides: saved differences layered over authored data

Keeping those names separate will make both the authoring UX and the save model easier
to understand.

### Current Caveats To Keep In Mind

The current implementation should eventually align with this model. Two discovered issues
are especially relevant:

- template-based entities must serialize all intended authored per-instance overrides, not only a narrow subset such as template parameters
- commands that move structured data such as dicts or lists into runtime variables should copy that data rather than aliasing the original command payload

Those are implementation problems, not arguments against the layered persistence model itself.

## Engine-Owned Runtime Sessions

Some recurring gameplay patterns (dialogue, inventory browsing) involve enough
boilerplate that projects should not need to rebuild them from scratch every time.
The engine addresses this through **engine-owned runtime sessions**: modal
runtimes that the engine manages end-to-end while still allowing project
customization through presets, hooks, and caller-supplied data.

Current engine-owned sessions:

- **Dialogue sessions** (`open_dialogue_session` / `close_dialogue_session`):
  text pagination, choice selection, nested session suspension/resume, preset-driven layout
- **Inventory sessions** (`open_inventory_session` / `close_inventory_session`):
  item list browsing, detail panel, action popup, preset-driven layout

Each session takes exclusive input control for its duration, runs caller hooks at
key boundaries, and restores the previous input state on close. Projects that
need fully custom flows can still use the lower-level primitives directly.

## Physics Contract

The engine exposes a standard set of entity fields and built-in commands for
grid-based movement and interaction so projects do not need to rebuild common
physics from scratch:

- **Entity fields**: `facing`, `solid`, `pushable`, `weight`, `push_strength`
- **Cell flags**: `blocked`
- **Built-in commands**: `move_in_direction`, `push_facing`, `interact_facing`

This contract is opt-in. Projects can use these helpers for standard grid physics
or build entirely custom movement through lower-level commands.

## Occupancy Hooks

Entities can declare command hooks that fire when other entities enter or leave
their grid cell, or when movement into their cell is blocked:

- `on_occupant_enter`: runs when another entity arrives on this cell
- `on_occupant_leave`: runs when another entity leaves this cell
- `on_blocked`: runs when another entity tries to enter this cell but is blocked

These are ordinary `entity_commands` entries, so they compose with the rest of the
command system. They replace the need for separate controller entities to watch
for spatial triggers in many common puzzle scenarios.

## Items and Inventory

Items are a first-class content type:

- **Item definitions** are authored JSON files discovered through `item_paths` in
  `project.json`, with path-derived IDs matching the pattern used by areas and
  entity templates
- **Inventories** are entity-owned, stack-based, with configurable capacity
- **Built-in commands** handle add, remove, use, and quantity queries
- **Value sources** allow conditions to check inventory contents

The inventory data model lives in `dungeon_engine/inventory.py` and
`dungeon_engine/items.py`. The engine-owned inventory UI session lives in
`dungeon_engine/engine/inventory_runtime.py`.

## Travelers

Entities that need to move between areas (such as a player or a follower) use the
**traveler** system. When an area transition occurs, designated entities are
detached from the current area, carried across the transition, and placed in the
destination area. Traveler state is included in save data so cross-area entity
transfer survives save/load cycles.

## Success Check

The architecture is on the right track if we can quickly build a small room where:

- the player walks on a grid
- a lever opens a gate
- a box can be pushed
- an NPC talks
- the room can be authored and tested through the chosen workflow

If the architecture makes that awkward, it should be changed.
