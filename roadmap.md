# Python Puzzle Engine Roadmap

## How to use this roadmap

This roadmap is a guide, not a contract.

If implementation exposes a better approach, change the plan and update the docs. The point is to preserve the spirit of the project:

- Python project
- command-driven gameplay
- early editor
- steady playable progress

## Ground Rules

1. The game should stay runnable after every phase.
2. The command model is central, not decorative.
3. The editor arrives early enough to support testing and content creation.
4. Favor vertical slices over huge architecture dumps.
5. If a phase reveals a bad assumption, refactor early instead of protecting the document.

## Phase 1: Core Shell and Grid Room

### Goal

Boot the Python project, load a room from JSON, and move the player on a grid through commands.

### Deliverables

- project scaffold
- window, renderer, camera
- area JSON loader
- tile layers and walkability
- lightweight world/entity model
- command runner skeleton
- input mapped to top-level commands
- player step command
- grid collision
- placeholder test room

### Exit criteria

- the app launches
- a test room renders
- arrow input or equivalent triggers movement commands
- the player moves one tile at a time
- walls block movement
- camera follows the player

## Phase 2: Interaction Core

### Goal

Make the room interactive through command chains.

### Deliverables

- interactable entities
- trigger tiles or area effects
- command composition basics: sequence, filter, enable/disable, remove/restore, variable set/check
- pushable objects
- lever, gate, button, door examples
- movement-trigger integration for enter/leave logic

### Exit criteria

- player can press interact on an object
- a lever can open a gate
- a button or trigger tile can run commands
- a pushable block puzzle works
- one-time interactions can disable themselves

## Phase 3: Early Editor and World Creation

### Goal

Create and test rooms from inside the app instead of relying on manual JSON editing.

### Deliverables

- editor mode
- tile painting
- walkability editing
- entity placement and removal
- entity selection
- basic property inspection and editing
- save/load room data
- quick play-test toggle

### Exit criteria

- create a new room in the editor
- place player spawn and puzzle objects
- save and reload the room
- switch into play mode and test it immediately

## Phase 4: Dialogue

### Goal

Support NPC conversations and branching results with the same command system.

### Deliverables

- dialogue textbox UI
- character-by-character text reveal
- advance and skip behavior
- branching choices
- command branching from selected choices
- input lock during dialogue

### Exit criteria

- an NPC can show dialogue
- dialogue choices can branch to different outcomes
- player movement is blocked while dialogue is active

## Phase 5: Inventory, Requirements, and Usable Items

### Goal

Make items part of the command-driven interaction model.

### Deliverables

- item definitions
- inventory storage
- add/remove/check item commands
- requirement checks with success and failure branches
- usable-item commands
- sample content: key, locked door, consumable or activatable item

### Exit criteria

- player can pick up an item
- a key can unlock or allow interaction with a door
- missing-item cases can branch to a different response
- a usable item can trigger commands

## Phase 6: Cinematics, Area Changes, and Persistence

### Goal

Support short scripted sequences and a multi-room world that remembers state.

### Deliverables

- wait commands
- scripted movement commands for entities
- camera control commands
- cinematic mode with input lock
- area transitions
- save/load of inventory and room state

### Exit criteria

- entering a trigger can start a short cutscene
- a cutscene can move entities, show dialogue, and wait
- moving to another area works
- revisiting an area restores its changed state

## Phase 7: Content Pipeline and Quality Pass

### Goal

Make content production smoother and improve debuggability.

### Deliverables

- better editor property editing
- basic validation for room/entity/item data
- command debugging helpers
- audio commands
- cleaner sample content and test areas

### Exit criteria

- authoring a new small puzzle room is reasonably fast
- broken content is easier to diagnose
- sound and music can be triggered through commands

## Phase 8: Deferred Expansion

These are planned, but they are not required before the core project is useful.

### Candidate features

- turn-based mode
- free movement mode
- NPC AI
- richer stats/combat
- stronger editor tooling for command authoring

### Important rule

Do not block early phases waiting for these. Instead, preserve clean extension points so they can be added later.

## Recommended First Vertical Slice

The first true milestone should be a single room that proves the spirit of the whole project:

- grid movement
- one pushable object
- one lever and one gate
- one NPC with dialogue
- one key and one locked door
- one usable item
- one short cutscene
- room creation or editing through the early editor

If that slice works well, the architecture is healthy.
