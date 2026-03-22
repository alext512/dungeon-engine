# Python Dungeon Engine Architecture

## Purpose

This project is a new Python game project. It is not a refactor of the old Godot game.

The spirit should still come from the old Godot project:

- gameplay is driven by reusable commands
- objects do not hard-code bespoke one-off behavior
- the same command ideas should be usable by the player, interactable objects, usable items, dialogue choices, and cinematics
- testing content creation should be possible early through an editor

This is not meant to be a totally generic engine. It is a focused, data-driven puzzle/RPG framework with room to grow.

## Core Direction

The first-class functionality is:

- grid movement
- interactable objects
- dialogue
- world creation
- inventory and requirement checks
- usable items
- early cinematics
- early level editor

The architecture should also leave room for later features without forcing a rewrite:

- turn-based mode
- free movement mode
- NPC AI
- richer combat and stats
- better editor tooling

## Tech Stack

- Python 3.11+
- `pygame-ce` as the runtime library for windowing, rendering, input, timing, fonts, and audio
- JSON for content data such as areas, entities, items, and editor-saved room state
- Python standard library for most support code, including `dataclasses`, `pathlib`, `json`, and `typing`

`pygame-ce` is a good fit here because we want a Python-first project with direct control over rendering, data loading, UI flow, command execution, and editor behavior without fighting a heavier engine framework.

## Design Principles

### 1. Commands are the main gameplay language

Almost everything should be expressed as commands or command chains.

That includes:

- player movement attempts
- object interactions
- tile triggers
- dialogue branching
- inventory checks
- using items
- cinematics

Systems still exist, but systems provide primitives. Commands orchestrate those primitives into gameplay.

### 2. Input does not directly perform gameplay

Input should request top-level commands.

Example:

- pressing Up does not directly move an entity
- it queues a `run_event` request for the active entity's configured `move_up` event
- that event can call sub-commands or services to set facing, check collision, push a block, animate movement, and fire enter/leave triggers

Control routing is layered:

- the project defines default input event names
- the project can also define a default active entity id
- an area may override the active entity id
- runtime commands may still switch the active entity or remap input event names temporarily
- the project may enable or disable debug inspection controls such as zoom/pause/step through `project.json`

This keeps player input, AI behavior, and cinematics aligned around the same action model.

### 3. Grid-first, not grid-only forever

The first implementation is grid-based. The data model and command API should not assume that grid movement is the only future mode.

The same top-level action can later be executed by:

- a grid movement executor
- a free movement executor
- a turn scheduler that decides when actions are allowed

### 4. The editor is part of the product

The level editor is not a late convenience feature. It is part of the intended workflow and should arrive early.

The early editor only needs to be strong enough to:

- create and edit rooms
- paint tiles
- set walkability
- place entities
- edit a few important properties
- save and load data
- save and launch the room in the standalone game quickly

### 5. Data should describe content, not replace code entirely

The project is command-driven and data-driven, but not every hard problem should be forced into raw data.

The intended split is:

- data defines content, command chains, entities, items, dialogue, and room setup
- code defines the runtime, command execution, rendering, collision, UI, persistence, and editor behavior

Project content may live inside this repo for version control, for example under `projects/test_project/`, but that does not make it engine data. The real boundary is:

- engine code lives under `dungeon_engine/`
- project content lives in a project folder selected through `project.json`

That means a repo-local project is just a convenient versioned project, not a special built-in one.

## High-Level Runtime Model

### Areas

An area is a playable map with:

- tile layers
- walkability data
- placed entities
- local variables
- transitions to other areas

Areas are loaded from JSON and can be created or modified in the editor.

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
- sprite and animation state
- collision and pushability
- authored tags used for grouping, selection, and reset targeting
- interaction command chains
- trigger command chains
- inventory or item container state
- stats and custom variables
- visibility, presence, and event enabled state

### Systems

Systems should provide reusable services such as:

- rendering
- camera
- tile map lookup
- collision and spatial lookup
- movement execution
- animation playback
- dialogue UI
- inventory handling
- save/load
- editor tools

Systems should not become giant one-off gameplay scripts. If a behavior is content-specific, it should usually be represented as commands.

The camera should be command-addressable too:

- it can follow the active entity by default
- commands can retarget it to a specific entity
- commands can clear follow mode for manual framing
- commands can move or teleport it independently for cutscenes and inspection

## Command Architecture

### Command runner

The project needs a central command runner that can:

- execute a command immediately
- execute a chain of commands
- branch on success, failure, or choice
- wait for async commands to finish
- pass context between related commands

### Command context

Every command should have access to a runtime context such as:

- world
- current area
- initiator entity
- target entity
- direction
- selected choice
- item being used
- active input target
- temporary local variables

This matters because the same command type may be used by:

- the player
- an NPC
- a door
- a dialogue branch
- a cutscene
- a usable item

### Command types

Expected early command categories:

- flow: sequence, branch, filter, wait, repeat-if-needed
- movement: step entity, push entity, move entity along a path, face direction
- interaction: trigger entity, trigger tile, enable, disable
- visibility/map: show, hide, remove from map, restore to map
- dialogue: show text, choices, branch on choice
- variables: set, increment, compare, copy
- inventory: add item, remove item, check item, consume item, use item
- stats: modify stat, check stat
- level/world: change area, warp, set spawn, persist state, reset transient state, reset persistent state
- camera: follow, move, shake, lock
- audio: play sound, play music, stop audio

### Command composition

Commands should support composition patterns inspired by the old Godot project:

- execute these children in order
- if condition is true, run one branch, otherwise another
- choose next branch from a dialogue selection
- disable a command after it has run once

Movement should follow the same spirit.

Example movement chain:

1. receive `run_event(entity_id=active_entity, event_id=configured_move_right_event)`
2. start any project-authored walk animation
3. call `move_entity_one_tile(direction=right)`
4. if blocked by pushable object, try push chain
5. if passable, animate and move
6. run any `on_complete` cleanup such as restoring the idle frame
7. finish

## World Data

The source of truth for content should be JSON files.

Expected content groups:

- `areas/`
- `entities/`
- `items/`
- `dialogue/` if dialogue is split out

The editor should read and write these files.

The first versions can keep the schemas simple. They do not need to predict every future feature perfectly.

## Suggested Project Structure

```text
projects/
    test_project/                # Versioned sample project content (optional location)
        project.json
        areas/
        entities/
        assets/
        commands/

dungeon_engine/
    main.py
    config.py

    engine/
    world/
    systems/
    commands/
    ui/
    editor/
    data/
```

Suggested responsibilities:

- `engine/`: game loop, renderer, camera, asset loading, save/load
- `world/`: area model, entity storage, data loading, persistence helpers
- `systems/`: movement, collision, dialogue, inventory, animation
- `commands/`: command runner, registry, command implementations
- `ui/`: dialogue boxes, choices, inventory UI, debug overlays
- `editor/`: editor state, tools, inspector, save/load helpers
- `data/`: engine-owned internal support data only, if still needed

Important boundary:

- `dungeon_engine/` is the engine/editor package
- `projects/<name>/` is one possible place to keep project content under version control
- the engine must not assume any specific project exists there

## Editor Architecture

The editor should operate on the same data model as play mode, not a separate hidden format.

Early editor scope:

- create a room
- resize a room
- paint tiles
- toggle walkability
- place and remove entities
- select an entity
- edit a small set of important properties
- save and load
- save and launch the same room in the game quickly

The first editor version does not need a full visual command-chain authoring UI. A simple property inspector plus raw JSON editing for advanced fields is acceptable early on.

## Inventory and Requirements

Inventory is not just a bag of items. It is part of the interaction system.

Important use cases:

- a key allows a door interaction
- an item can be consumed to trigger commands
- an NPC can require an item before continuing a dialogue branch
- a puzzle can check for item combinations

This suggests early support for:

- item definitions
- inventory storage
- requirement-check commands
- success and failure branches
- usable-item commands

## Dialogue and Cinematics

Dialogue and cinematics should share the command system rather than becoming separate script formats.

Dialogue needs:

- text wrapping and pagination
- advance behavior
- branching results
- temporary input ownership while active

Current practical split:

- the engine owns text measurement, wrapping, and page advancement
- projects own panel images, portraits, choice layout, and dialogue-specific input flow

So the intended dialogue pattern is:

1. show panel image through screen-space commands
2. optionally show portrait image
3. call `run_dialogue` for the text only
4. if choices are needed, render them as normal screen text
5. hand input to a controller entity whose events update the choice texts and branch

This keeps dialogue aligned with the general command architecture instead of
turning it into a separate hardcoded menu system.

Cinematics need:

- sequence commands
- wait commands
- movement commands
- camera commands
- dialogue commands
- input lock while active

Because both are command-driven, a cinematic can simply become a command chain that temporarily owns input flow.

## Persistence

Persistence should support:

- player progress
- current area
- inventory
- persistent area state
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
          "solid": false
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

Keeping those names separate will make both the editor UX and the save model easier
to understand.

### Current Caveats To Keep In Mind

The current implementation should eventually align with this model. Two discovered issues
are especially relevant:

- template-based entities must serialize all intended authored per-instance overrides, not only a narrow subset such as template parameters
- commands that move structured data such as dicts or lists into runtime variables should copy that data rather than aliasing the original command payload

Those are implementation problems, not arguments against the layered persistence model itself.

## Deferred Expansion Hooks

The architecture should deliberately leave extension points for later work:

### Turn-based mode

Later, a turn manager can decide when commands are allowed to start. Because actions are already commands, the turn layer can sit above them rather than replacing them.

### Free movement

Later, movement commands can target a different movement executor while keeping the same higher-level action API.

### NPC AI

Later, AI can issue the same commands the player does instead of needing a separate bespoke behavior pathway.

## What Success Looks Like Early

The architecture is on the right track if we can quickly build a small room where:

- the player walks on a grid
- a lever opens a gate
- a box can be pushed
- an NPC talks
- a key unlocks a door
- a usable item triggers an effect
- a short cutscene runs as a command sequence
- the room can be created and tested from the editor

If the architecture makes that awkward, it should be changed.

