# RPG Engine — Implementation Roadmap

> **Important note for implementors (human or AI agent):** This roadmap and `ARCHITECTURE.md` are guides, not rigid contracts. If you encounter issues during implementation — a design choice that doesn't work in practice, a better pattern that emerges, or a technical constraint that forces a different approach — you have flexibility to deviate. Just document what changed and why. The architecture is a starting point, not a straitjacket. Use good judgment.

> **Relationship to ARCHITECTURE.md:** This file describes *when* and *how* to build things. `ARCHITECTURE.md` describes *what* the systems are and how they work. If you find a contradiction between the two, flag it, resolve it pragmatically, and update whichever file is wrong.

---

## Guiding Principles

1. **Editor-first development.** The level editor (or at minimum, a way to create and test areas) must be available early. Without it, testing is painful and progress stalls. Every phase should end with the ability to create test content using the editor.

2. **Always runnable.** After every phase (and ideally every sub-step), the game should launch and be testable. No "dark periods" where nothing works.

3. **Additive changes.** Each phase adds new components and command types. Existing code should rarely need modification. If a phase requires rewriting a prior system, that's a design smell — reconsider.

4. **Test with real content.** Don't just write systems — create test areas that exercise them. The test area should grow with each phase.


---

## Phase 1a: Core Engine + Grid Movement

**Goal:** A window opens. Tiles render. A player character moves on a grid. Camera follows.

### Steps (in order):

1. **Project scaffold**
   - Create directory structure: `puzzle_dungeon/engine/`, `ecs/`, `systems/`, `map/`, `commands/`, `ui/`, `data/levels/`, `data/entities/`, `data/sprites/`
   - `config.py` — constants: `TILE_SIZE = 16`, `INTERNAL_WIDTH = 320`, `INTERNAL_HEIGHT = 240`, `SCALE = 3`, `FPS = 60`
   - `main.py` — pygame init, create window, start game

2. **ECS core**
   - `ecs/world.py` — entity registry, component storage, `query()` method
   - `ecs/component.py` — dataclasses: `Position`, `Sprite`, `GridMovement`, `Collision`, `Tags`

3. **Asset manager**
   - `engine/asset_manager.py` — load PNG sprite sheets, slice into frames by grid, cache
   - Create placeholder sprites: colored rectangles (16x16) for player, wall, floor, lever, gate. These can be actual tiny PNGs or generated at runtime.

4. **Tile map + spatial grid**
   - `map/tile_map.py` — tile layers, walkability grid, `is_walkable(gx, gy)`
   - `map/spatial_grid.py` — 2D array of entity sets per tile

5. **Level loader**
   - `map/level_loader.py` — parse area JSON, create TileMap, load entity templates, spawn entities into World
   - `data/entities/player.json` — player template (Position, Sprite, GridMovement, Collision, Tags)
   - `data/levels/test_area.json` — small test area (10x10, some walls, player spawn)

6. **Renderer**
   - `engine/renderer.py` — internal surface rendering, tile layer drawing, entity drawing sorted by layer+y, integer scaling to display

7. **Camera**
   - `engine/camera.py` — follow player entity, clamp to map bounds

8. **Input handler**
   - `engine/input_handler.py` — keyboard events -> action names (`"move_up"`, `"move_down"`, `"move_left"`, `"move_right"`, `"action"`, `"cancel"`)

9. **Movement system**
   - `systems/movement_system.py` — `request_move(entity, direction)` for grid movement with interpolation, `update(dt)` for animation
   - Only grid mode, but use the abstract `request_move` interface so free movement slots in later

10. **Collision system**
    - `systems/collision_system.py` — `check_tile(gx, gy)` returns `"free"` / `"blocked"` / `"pushable"` / `"out_of_bounds"`

11. **Animation system**
    - `systems/animation_system.py` — advance frames based on `AnimationState`, update `Sprite.frame`
    - Add `AnimationState` component

12. **Game loop**
    - `engine/game.py` — state machine, main loop: input -> update systems -> render
    - Wire everything together: World, TileMap, SpatialGrid, all systems, renderer, camera

### Verification:
- `python main.py` launches a window
- Colored-rectangle tiles render on screen
- Player moves with arrow keys, one tile at a time, with smooth interpolation
- Player cannot walk through walls
- Camera follows the player
- FPS is stable at 60

---

## Phase 1b: Command System + Interactions

**Goal:** Player can interact with objects. Levers open doors. Pushable blocks work.

### Steps:

1. **Command core**
   - `commands/command.py` — `Command` dataclass, `CommandRunner` class (execute, finish, update, async command tracking)
   - `commands/registry.py` — `@register_command` decorator, `COMMAND_REGISTRY` dict

2. **Basic command types**
   - `commands/animation.py` — `play_animation` (async when `wait: true`)
   - `commands/visibility.py` — `set_visibility`, `toggle_visibility`
   - `commands/variables.py` — `set_variable`, `check_variable`, `increment_variable`
   - `commands/flow.py` — `filter` (conditional), `sequence` (run commands in order)
   - `commands/map_ops.py` — `remove_from_map`, `restore_on_map`
   - `commands/enable.py` — `set_enabled`

3. **Interaction components**
   - Add to `ecs/component.py`: `Interactable`, `AreaEffect`, `Variables`, `Movable`

4. **Interaction system**
   - `systems/interaction_system.py` — handle action button (check facing tile for Interactable entities, run command chain), handle area effects (on_enter, on_leave when entity arrives at new tile)

5. **Push mechanic**
   - Extend movement system: when moving into a tile with a `Movable` entity, try to push it in the same direction. If the tile behind it is free, push succeeds.

6. **Entity templates + test content**
   - `data/entities/lever.json`, `data/entities/iron_gate.json`
   - Update `test_area.json`: add a lever that opens a gate, a pushable block

7. **Wire CommandRunner into game loop**
   - CommandRunner gets references to all systems
   - CommandRunner.update(dt) called each frame

### Verification:
- Player presses action key facing a lever -> lever animates -> gate disappears
- Player pushes a block -> block moves one tile
- Lever can only be activated once (set_enabled disables it after use)
- Area effects trigger when stepping on specific tiles

---

## Phase 1c: Basic Level Editor

**Goal:** Create and edit areas visually. Save/load JSON. Play-test from editor.

This is critical for all future development — without an editor, testing new features requires hand-editing JSON.

### Steps:

1. **Editor state in game loop**
   - Add `"editor"` state to `engine/game.py` state machine
   - Hotkey to toggle between `"play"` and `"editor"` (e.g., F1)

2. **UI manager foundation**
   - `ui/ui_manager.py` — manage UI panels, handle mouse input routing

3. **Editor core**
   - `map/level_editor.py` — editor modes: `tile`, `walkability`, `entity`, `select`
   - Mouse-based interaction: left click to paint/place, right click to erase/remove
   - Camera panning in editor (middle mouse drag or arrow keys)
   - Grid overlay rendering

4. **Tile mode**
   - `ui/editor_ui.py` — tile palette panel (shows available tiles from tileset)
   - Click tile in palette to select, click on grid to paint
   - Support for multiple tile layers

5. **Walkability mode**
   - Visual overlay: red tint on non-walkable tiles, green on walkable
   - Click to toggle walkability per tile

6. **Entity mode**
   - Entity template palette (list of available templates from `data/entities/`)
   - Click to place entity on grid, right click to remove
   - Entities show their sprite on the grid

7. **Select mode**
   - Click entity to select it
   - Show its properties (entity ID, template, position, overrides) in a panel
   - Basic property editing (at minimum: entity ID, position)
   - Command chain editing can be deferred — for now, edit JSON manually for complex commands

8. **Save/Load**
   - Save current area state to JSON file
   - Load area from JSON file
   - "New area" with configurable width/height

9. **Play-test toggle**
   - Press F1 to switch from editor to play mode
   - Play mode loads the current editor state as a playable area
   - Press F1 again to return to editor

10. **Resize area**
    - Ability to change area dimensions (expand/shrink)

### Verification:
- Press F1 to enter editor
- Paint tiles on the grid using tile palette
- Toggle walkability on tiles
- Place entities (lever, gate, player spawn) from palette
- Save area to JSON, close game, reopen, load area — everything preserved
- Press F1 to play-test, interact with placed objects, press F1 to return to editor
- Create a new area from scratch, save it, load it

---

## Phase 2: Dialogue System

**Goal:** NPCs can talk. Dialogue appears with character-by-character reveal. Choices branch the conversation.

### Steps:

1. **Dialogue system**
   - `systems/dialogue_system.py` — state machine: IDLE -> REVEALING -> WAITING -> CHOICES
   - Character-by-character text reveal with configurable speed
   - Text queue (multiple lines)
   - Action button advances: during reveal -> show full text; when waiting -> next line or finish

2. **UI: Textbox**
   - `ui/textbox.py` — renders dialogue box at bottom of screen
   - Text wrapping, pagination indicators

3. **UI: Choices panel**
   - `ui/choices_panel.py` — vertical list of choices with arrow key navigation and selection indicator

4. **Dialogue commands**
   - `commands/dialogue.py`:
     - `dialogue` — queue text lines, async (finishes when player dismisses last line)
     - `choices_dialogue` — show text + choices, async (finishes with selected index as argument, used with `select_next: true`)

5. **Input blocking during dialogue**
   - Player movement is blocked while dialogue is active
   - Only action/cancel/arrows work

6. **NPC template + test content**
   - `data/entities/npc_basic.json` — basic NPC template with Interactable
   - Update test area: add NPC with dialogue, add NPC with choices that give an item (even if inventory isn't built yet, use `set_variable` as placeholder)

7. **Editor: dialogue preview**
   - When selecting an entity in editor, show its dialogue text if it has dialogue commands

### Verification:
- Interact with NPC -> dialogue box appears at bottom
- Text reveals character by character
- Press action -> text appears fully / advances to next line
- Choices NPC shows options, arrow keys navigate, action confirms
- Different choice leads to different follow-up dialogue
- Player cannot move during dialogue

---

## Phase 3: Area Transitions + Persistence

**Goal:** Multiple areas connected by transitions. State persists across area changes.

### Steps:

1. **Area manager**
   - `map/area_manager.py` — tracks current area, handles loading/unloading
   - `change_area(area_id, spawn_position)` — save current area state, load new area, place player

2. **Transition entities**
   - Area JSON has `transitions` array — each with position, target_area, target_position
   - When player steps on a transition tile (area effect on_enter), execute `change_area` command

3. **Persistence system**
   - When leaving area: snapshot entities with `Persist` component (Variables, visibility, position, collision state, removed-from-map status)
   - Store in `area_states[area_id]` dict in memory
   - When re-entering area: load base JSON, apply saved state on top

4. **Save/load to disk**
   - `engine/save_manager.py` — serialize game state to JSON file: current area, player state, global variables, all area states
   - Load from save file on game start (if exists)

5. **Level commands**
   - `commands/level.py` — `change_area`, `warp`

6. **Test content**
   - Create a second test area (`test_area_2.json`)
   - Connect the two areas with transitions
   - Place a lever in area 1 that persists — pull it, go to area 2, come back, lever is still pulled

7. **Editor: transition editing**
   - New editor mode or property: configure transitions on tiles
   - Specify target area (by filename) and target spawn position

### Verification:
- Walk to edge of area 1 -> area 2 loads, player appears at target position
- Walk back to area 1 -> area 1 loads with persisted state (pulled levers, removed gates)
- Save game, close, reopen, load save -> correct area with correct state
- Editor: create transition, save, play-test, transition works

---

## Phase 4: Inventory + Items + Stats

**Goal:** Player has inventory. Items can be picked up, used, and checked. Characters have HP and stats.

### Steps:

1. **Components**
   - Add `Inventory` and `Stats` to `ecs/component.py`

2. **Inventory system**
   - `systems/inventory_system.py` — add_item, remove_item, has_item, get_all_items

3. **Stats system**
   - `systems/stats_system.py` — deal_damage (with defense calc), heal, modify_stat, get_stat, is_dead

4. **Inventory commands**
   - `commands/inventory.py` — `add_item`, `remove_item`, `check_item` (with on_success/on_fail branching)

5. **Stats commands**
   - `commands/stats.py` — `damage`, `heal`, `modify_stat`, `check_stat`

6. **Item definitions**
   - `data/items/items.json` — define items with name, description, sprite, tags, use_commands
   - Usable items (e.g., health potion) have command chains that execute on use

7. **UI: Inventory**
   - `ui/inventory_ui.py` — inventory screen (toggle with a key, e.g., I)
   - Show items, select to use

8. **UI: HUD**
   - `ui/hud.py` — HP bar overlay during gameplay

9. **Test content**
   - Item pickup on ground (entity with AreaEffect.on_enter that adds item + removes itself)
   - NPC that gives item through dialogue choice
   - Door that checks for key item
   - Trapped lever that deals damage

10. **Player template update**
    - Add `Inventory` and `Stats` components to player template

### Verification:
- Pick up item from ground -> appears in inventory
- Open inventory screen -> see items
- Use health potion -> HP restored, potion consumed
- Talk to NPC, choose option -> receive item
- Interact with locked door without key -> "need a key" dialogue
- Interact with locked door with key -> door opens, key consumed
- Trapped lever -> player takes damage, HP bar updates

---

## Phase 5: Turn-Based Grid Mode

**Goal:** Areas can be configured as turn-based. Nothing moves until the player acts.

### Steps:

1. **Turn system**
   - `systems/turn_system.py` — state machine: WAITING_FOR_PLAYER -> ANIMATING_PLAYER -> PROCESSING_NPCS -> ANIMATING_NPC
   - Activated when area has `"turn_based": true`

2. **TurnActor component**
   - Added to entities that participate in turns (NPCs, enemies)

3. **Integration with movement system**
   - In turn-based mode, movement_system only processes moves when the turn system allows it
   - Player input only accepted in WAITING_FOR_PLAYER state

4. **Integration with AI system** (if AI exists yet — may need a basic idle AI first)
   - Each NPC gets one action per turn
   - Actions process sequentially with animation between each

5. **Test content**
   - Create `test_area_turnbased.json` with `"turn_based": true`
   - Place an NPC with simple patrol AI (or at minimum, one that moves toward the player)

### Verification:
- Enter turn-based area -> nothing moves
- Player moves one tile -> NPC takes one action -> game waits for player again
- Visual feedback: player move animates, then NPC move animates
- Leaving to a non-turn-based area -> normal real-time behavior resumes

---

## Phase 6: NPC AI

**Goal:** NPCs have modular behavior patterns.

### Steps:

1. **AI system**
   - `systems/ai_system.py` — behavior handler registry
   - Built-in handlers: `idle`, `patrol`, `chase`, `flee`

2. **AIBehavior component**
   - behavior_type, patrol_points, chase_target, chase_range, state

3. **Patrol behavior**
   - Move between defined waypoints in sequence
   - Return to start when reaching end

4. **Chase behavior**
   - Move toward target (usually player) when within range
   - Simple pathfinding: move in the direction that reduces Manhattan distance (avoid obstacles with simple redirect)

5. **Flee behavior**
   - Move away from target when within range

6. **Integration with turn system**
   - In turn-based mode: AI gets one move per turn
   - In real-time mode: AI moves at configured speed

7. **Test content**
   - Patrolling guard NPC
   - Enemy that chases player when nearby
   - Fleeing NPC

### Verification:
- Guard patrols between waypoints
- Enemy notices player within range, chases
- Enemy stops chasing when player is out of range
- All behaviors work in both real-time and turn-based modes

---

## Phase 7: Cinematics

**Goal:** Scripted sequences play out automatically.

### Steps:

1. **Cinematic system**
   - `systems/cinematic_system.py` — disable player input, execute command sequence, re-enable input when done

2. **Camera commands**
   - `commands/camera_cmd.py` — `move_camera` (pan to target, async), `shake_camera`, `reset_camera`

3. **Wait commands**
   - `commands/wait.py` — `wait_seconds`, `wait_frames`

4. **Scripted movement**
   - `commands/movement.py` — `move_entity` (move NPC/entity in direction, async)

5. **Cinematic triggers**
   - Area effects that trigger cinematics (e.g., entering a room starts a cutscene)
   - Variable-gated so they only play once

6. **Test content**
   - Room with a trigger zone: entering starts a cinematic where the camera pans to an NPC, NPC speaks, walks toward player, camera returns

### Verification:
- Step on trigger -> player input disabled
- Camera pans to NPC, NPC talks, NPC walks, camera returns
- Player input re-enabled
- Re-entering the room doesn't re-trigger the cinematic

---

## Phase 8: Free Movement Mode (Deferred)

**Goal:** Areas can use free (non-grid) movement.

### Steps:

1. **FreeMovement component**
2. **Extend movement system** — velocity-based movement with friction
3. **AABB collision** — pixel-based collision with entity collision boxes
4. **Spatial grid updates** — update tile occupancy as entities cross tile boundaries
5. **Editor: collider editing** — define collision shapes for free-movement entities
6. **Area-level toggle** — `"movement_mode": "free"` in area JSON

### Verification:
- Enter free-movement area -> smooth movement in any direction
- Collision with walls and objects works
- Area effects still trigger when crossing tile boundaries
- Can transition between grid and free-movement areas

---

## Phase 9: Audio + Polish

**Goal:** Sound effects and music.

### Steps:

1. **Sound commands** — `commands/sound.py`: `play_sound`, `play_music`, `stop_music`
2. **Asset manager extension** — load .wav/.ogg files
3. **Wire into existing content** — add sounds to lever pulls, door opens, dialogue blips, footsteps
4. **Music per area** — `on_load` command in area JSON plays area music

---

## Summary: What Each Phase Delivers

| Phase | Delivers | Editor Capability |
|-------|----------|-------------------|
| 1a | Moving player on a grid with tiles | — |
| 1b | Interactable objects, command system | — |
| 1c | Level editor | Tile painting, walkability, entity placement, save/load |
| 2 | Dialogue with choices | Dialogue preview on entities |
| 3 | Multiple connected areas, persistence, saving | Transition editing |
| 4 | Inventory, items, HP/stats | Item definitions |
| 5 | Turn-based mode | — (area property toggle) |
| 6 | NPC AI behaviors | AI behavior configuration |
| 7 | Cinematics | Cinematic sequence building |
| 8 | Free movement mode | Collider editing |
| 9 | Audio | — |

---

## Working Conventions for AI Agents

- **Read ARCHITECTURE.md first** for system designs and data formats.
- **Check existing code** before creating new files — avoid duplicating what's already built.
- **Use the editor to test.** After implementing a feature, create or update a test area that exercises it.
- **Keep components as data-only dataclasses.** No game logic in components.
- **Keep commands as registered functions.** New commands = new function + `@register_command` decorator. No changes to CommandRunner.
- **JSON is the source of truth for game content.** Don't hard-code levels, entities, or items in Python.
- **If the architecture doesn't work,** adapt it. Document what changed and why in a comment or commit message. Don't blindly follow a design that's fighting you.
