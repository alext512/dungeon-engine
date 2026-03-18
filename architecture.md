# Python Puzzle Engine Architecture

## Purpose

This project is a new Python game project. It is not a refactor of the old Godot game.

The spirit should still come from the old Godot project:

- gameplay is driven by reusable commands
- objects do not hard-code bespoke one-off behavior
- the same command ideas should be usable by the player, interactable objects, usable items, dialogue choices, and cinematics
- testing content creation should be possible early through an in-app editor

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

- pressing Up does not directly move the player
- it queues a `player_step` command with `direction=up`
- that command can call sub-commands or services to set facing, check collision, push a block, animate movement, and fire enter/leave triggers

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
- jump into play-test mode quickly

### 5. Data should describe content, not replace code entirely

The project is command-driven and data-driven, but not every hard problem should be forced into raw data.

The intended split is:

- data defines content, command chains, entities, items, dialogue, and room setup
- code defines the runtime, command execution, rendering, collision, UI, persistence, and editor behavior

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
- interaction command chains
- trigger command chains
- inventory or item container state
- stats and custom variables
- visibility and enabled state

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
- level/world: change area, warp, set spawn, persist state
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

1. receive `player_step(direction)`
2. update facing
3. check target tile
4. if blocked by pushable object, try push chain
5. if passable, animate and move
6. fire leave and enter triggers
7. finish

## World Data

The source of truth for content should be JSON files.

Expected content groups:

- `data/areas/`
- `data/entities/`
- `data/items/`
- `data/dialogue/` if dialogue is split out

The editor should read and write these files.

The first versions can keep the schemas simple. They do not need to predict every future feature perfectly.

## Suggested Project Structure

```text
puzzle_dungeon/
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
- `data/`: JSON content

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
- switch into play-test mode and back

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

- text reveal
- advance and skip behavior
- choices
- branching results
- input lock while active

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
