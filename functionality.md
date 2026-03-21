# Functionality Guide

This file is the plain-language feature list for the project. It is meant to be easy to inspect and easy to change.

## P0: Core starting functionality

- The project is a new Python game project, not a continuation of the Godot runtime.
- Gameplay is command-driven in the spirit of the old Godot project.
- Player movement is initiated through commands, not direct movement code.
- The world is tile-based and grid-first.
- The player can move, collide with walls, and push movable objects.
- The player can interact with nearby objects and trigger command chains.
- Rooms can contain levers, gates, doors, switches, buttons, triggers, pickups, NPCs, and similar entities.
- Dialogue supports text reveal, advancing, and branching choices.
- Rooms can be created and edited early through a standalone editor that shares the same data model as play mode.
- Inventory exists early and supports item checks as interaction requirements.
- Usable items can trigger command chains.
- Cinematics exist early as sequenced command chains with temporary input lock.

## P1: Important near-term functionality

- Multiple connected areas.
- Persistent area state across revisits.
- Save/load support.
- Entity visibility and enabled-state changes.
- Variable checks and branching logic.
- Basic stats and stat-changing commands.
- Audio commands.
- Better editor inspection and property editing.

## P2: Deferred but intentionally supported

- Turn-based mode.
- Free movement mode.
- NPC AI.
- Richer combat systems.
- More advanced editor tooling for authoring command chains visually.

## Non-negotiable behavioral rules

- Commands are the main way content expresses gameplay behavior.
- Systems provide reusable services, but content-specific logic should usually live in command data.
- The editor uses the same underlying room and entity data as play mode.
- The game should remain playable after each implementation phase.
- If the architecture fights the intended functionality, the architecture should change.
