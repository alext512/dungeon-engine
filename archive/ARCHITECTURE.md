# RPG Engine Architecture

## 1. Overview

A modular, data-driven top-down RPG engine built in Python. Inspired by the existing Godot-based dungeon puzzle game (`dungeon-puzzle-2/`), this engine expands the concept into a full RPG framework with:

- **Dual movement modes:** Grid-based (Pokemon-style) and free movement (deferred)
- **Turn-based option:** Mystery Dungeon-style where nothing moves until the player acts
- **Modular interactables:** Levers, doors, switches, movable objects — all defined as composable command chains in JSON
- **Dialogue system:** Character-by-character text reveal with branching choices that trigger game events
- **Inventory & items:** Pickups, item requirements, usable items — all wired into the command system
- **Character stats:** HP, attack, defense, custom stats for both player and NPCs
- **NPC AI:** Modular behavior patterns (patrol, chase, flee) that work in both real-time and turn-based modes
- **Cinematic events:** Scripted sequences using the same command system
- **Persistent multi-area world:** Areas retain state (pulled levers, defeated enemies) across visits
- **In-game level editor:** Tile painting, entity placement, command chain configuration, JSON export

**Core principle:** All game logic lives in composable JSON command chains. The engine code provides systems (movement, collision, rendering, etc.) and command types (dialogue, damage, toggle_visibility, etc.). New gameplay behaviors are created by combining existing commands in JSON — no Python code changes needed.


---

## 2. Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.11+ | Best language for AI-agent-generated code; clean, readable, well-known |
| Framework | Pygame-ce | Community Edition of Pygame — actively maintained, same API. Used as a thin layer for rendering, input, audio. `pip install pygame-ce`, `import pygame` |
| Data format | JSON | All levels, entities, items, dialogues are JSON files. Human-readable, agent-editable |
| Assets | PNG sprite sheets | Pixel art focused. Integer scaling for crisp rendering |

**Why Pygame-ce over alternatives:**
- We're building a custom ECS and command system. Pygame stays out of our way — it just provides a window, surface blitting, input events, image loading, and sound playback.
- Arcade's built-in sprite/tilemap systems would conflict with our custom ECS (dual state management).
- AI agents produce Pygame code with high reliability due to massive training data.
- Pygame-ce is the actively maintained fork with performance improvements over original Pygame.

---

## 3. Project Structure

```
puzzle_dungeon/
    main.py                         # Entry point, argument parsing
    config.py                       # Global constants, paths, default settings

    engine/
        __init__.py
        game.py                     # Main game loop, state machine (play / editor / menu / cinematic)
        camera.py                   # Camera: smooth follow, bounds clamping, shake
        renderer.py                 # Pixel-art renderer: internal surface + integer scaling
        input_handler.py            # Input abstraction: keyboard mapping, action names
        asset_manager.py            # Load/cache sprites, slice sprite sheets, font loading
        save_manager.py             # Global save/load, per-area state persistence

    ecs/
        __init__.py
        world.py                    # Entity registry, component storage, queries, global variables
        component.py                # All component dataclasses

    commands/
        __init__.py
        command.py                  # Command dataclass + CommandRunner (dispatcher + async management)
        registry.py                 # Decorator-based command type registry
        dialogue.py                 # dialogue, choices_dialogue
        movement.py                 # move_entity (scripted movement for cinematics)
        animation.py                # play_animation, stop_animation
        inventory.py                # add_item, remove_item, check_item
        variables.py                # set_variable, check_variable, increment_variable
        visibility.py               # toggle_visibility, set_visibility
        flow.py                     # filter, sequence, repeat
        map_ops.py                  # remove_from_map, restore_on_map
        enable.py                   # set_enabled, toggle_enabled
        stats.py                    # damage, heal, modify_stat, check_stat
        camera_cmd.py               # move_camera, shake_camera, reset_camera
        wait.py                     # wait_frames, wait_seconds
        level.py                    # change_area, warp
        sound.py                    # play_sound, play_music, stop_music

    systems/
        __init__.py
        movement_system.py          # Grid movement (+ future free movement slot)
        collision_system.py         # Tile-based collision (+ future AABB slot)
        interaction_system.py       # Player interaction dispatch, area effect triggers
        dialogue_system.py          # Text display state machine, choice handling
        inventory_system.py         # Add/remove/check items
        stats_system.py             # HP, damage calc, stat queries
        animation_system.py         # Sprite animation: frame advancing, state transitions
        ai_system.py                # NPC behavior dispatch: idle, patrol, chase, flee
        cinematic_system.py         # Scripted sequence playback, input blocking
        turn_system.py              # Turn-based scheduler: player acts -> NPCs act -> repeat

    map/
        __init__.py
        tile_map.py                 # Tile grid data: multiple layers, tileset references
        spatial_grid.py             # 2D array of entity sets per tile (collision + lookup)
        level_loader.py             # JSON -> World: parse area, spawn entities from templates
        level_editor.py             # In-game editor: tile painting, entity placement, property editing
        area_manager.py             # Multi-area world: load/unload, transitions, state persistence

    ui/
        __init__.py
        ui_manager.py               # UI layer stack, input routing to active UI
        textbox.py                  # Dialogue box: character reveal, pagination, indicators
        choices_panel.py            # Choice list: arrow navigation, selection
        inventory_ui.py             # Inventory grid/list display
        hud.py                      # HP bars, stat display, minimap
        editor_ui.py                # Editor panels: tile palette, entity palette, property inspector

    data/
        levels/                     # Area JSON files (one per area)
            test_area.json
        entities/                   # Entity template JSON files
            player.json
            lever.json
            iron_gate.json
            npc_guard.json
        items/                      # Item definition files
            items.json
        sprites/                    # PNG sprite sheets and individual sprites
        sounds/                     # Sound effects and music files
```

---

## 4. Core Architecture

### 4.1 Entity-Component System (ECS)

**Entities** are string IDs (e.g., `"player"`, `"lever_1"`, `"gate_1"`) stored in a central `World`. Each entity has a dictionary of **components** — plain Python dataclasses that hold data only. **Systems** are classes that process entities with specific component combinations.

```python
# ecs/world.py

class World:
    def create_entity(self, entity_id: str = None) -> str:
        """Create entity with given or auto-generated ID."""

    def destroy_entity(self, entity_id: str):
        """Remove entity and all its components."""

    def add_component(self, entity_id: str, component) -> None:
        """Attach a component instance to an entity."""

    def get_component(self, entity_id: str, component_type) -> component:
        """Get a specific component from an entity. Returns None if not found."""

    def has_component(self, entity_id: str, component_type) -> bool:
        """Check if entity has a component type."""

    def remove_component(self, entity_id: str, component_type) -> None:
        """Detach a component from an entity."""

    def query(self, *component_types) -> list[tuple]:
        """Return all (entity_id, comp1, comp2, ...) tuples for entities
        that have ALL the specified component types."""

    def get_entity_ids_with(self, *component_types) -> list[str]:
        """Return entity IDs that have all specified components."""

    # Global variables (shared across the current area, persisted in save)
    variables: dict  # {"gate_opened": True, "lever_count": 3}
```

**Why not a traditional ECS with systems as functions?** We use class-based systems because they hold references to other systems and the world. The query-based approach keeps things decoupled without the overhead of a full archetype-based ECS (overkill for this scale).

### 4.2 Components

All components are dataclasses in `ecs/component.py`. They hold data only — no methods with game logic.

#### Phase 1 Components

```python
@dataclass
class Position:
    """World position. Grid coords are authoritative in grid mode;
    pixel coords are for rendering interpolation."""
    x: float = 0.0           # Pixel position (for rendering)
    y: float = 0.0
    grid_x: int = 0          # Tile position (authoritative in grid mode)
    grid_y: int = 0
    layer: int = 0           # Render sorting layer (0 = ground, 1 = objects, 2 = overhead)

@dataclass
class Sprite:
    """Visual representation."""
    sheet_id: str = ""        # Key into AssetManager's loaded sprite sheets
    frame: int = 0            # Current frame index in the sheet
    offset_x: float = 0.0    # Render offset from Position
    offset_y: float = 0.0
    visible: bool = True
    flip_h: bool = False      # Horizontal flip
    flip_v: bool = False      # Vertical flip

@dataclass
class AnimationState:
    """Sprite animation controller."""
    animations: dict = field(default_factory=dict)
    # Format: {"idle_down": {"frames": [0,1,2,3], "speed": 0.15, "loop": True},
    #          "walk_up": {"frames": [4,5,6,7], "speed": 0.1, "loop": True}}
    current_anim: str = ""
    current_frame_index: int = 0   # Index into the current animation's frames list
    frame_timer: float = 0.0
    playing: bool = False

@dataclass
class Collision:
    """Marks entity as a collidable body."""
    solid: bool = True         # Blocks movement if True
    width: int = 1             # Collision size in tiles (grid mode)
    height: int = 1

@dataclass
class Movable:
    """Entity can be pushed by other entities."""
    pushable: bool = True
    push_speed: float = 4.0    # Tiles per second when being pushed

@dataclass
class GridMovement:
    """Grid-based movement state."""
    moving: bool = False
    start_x: float = 0.0      # Pixel start position (for interpolation)
    start_y: float = 0.0
    end_x: float = 0.0        # Pixel end position
    end_y: float = 0.0
    progress: float = 0.0     # 0.0 to 1.0 interpolation progress
    speed: float = 5.0        # Tiles per second
    facing: str = "down"      # "up", "down", "left", "right"
    move_queued: bool = False  # Input buffering: next move is queued
    queued_direction: str = "" # Direction of queued move

@dataclass
class Interactable:
    """Commands executed when player presses action button facing this entity."""
    command_chain: list = field(default_factory=list)  # List of command dicts

@dataclass
class AreaEffect:
    """Commands triggered by entity presence on tile."""
    on_enter: list = field(default_factory=list)   # When entity steps onto this tile
    on_leave: list = field(default_factory=list)   # When entity leaves this tile
    on_stay: list = field(default_factory=list)    # Each tick while entity is on this tile
    trigger_tags: list = field(default_factory=lambda: ["player"])
    # Only entities with these tags trigger the effects

@dataclass
class Variables:
    """Entity-local key-value store. Commands can read/write these."""
    data: dict = field(default_factory=dict)
    # Examples: {"activated": False, "combination": [0, 0, 0], "hit_count": 0}

@dataclass
class Tags:
    """Freeform tags for identification and filtering."""
    values: set = field(default_factory=set)
    # Examples: {"player"}, {"npc", "guard"}, {"lever", "interactable"}, {"door", "locked"}

@dataclass
class Persist:
    """Marks entity for state persistence when leaving/re-entering an area."""
    enabled: bool = True
    # Which component fields to persist (empty = persist all persistable components)
    fields: list = field(default_factory=list)
```

#### Later Phase Components

```python
@dataclass
class FreeMovement:
    """Velocity-based movement for free movement mode."""
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    max_speed: float = 120.0
    acceleration: float = 600.0
    friction: float = 500.0
    facing: str = "down"

@dataclass
class Inventory:
    """Item container."""
    items: list = field(default_factory=list)  # List of item_id strings
    max_size: int = -1  # -1 = unlimited

@dataclass
class Stats:
    """Character stats."""
    hp: int = 10
    max_hp: int = 10
    attack: int = 1
    defense: int = 0
    speed: int = 1
    custom: dict = field(default_factory=dict)  # Extensible: {"mana": 5, "luck": 3}

@dataclass
class Actions:
    """Actions the character can perform. Each action is a command chain."""
    available: dict = field(default_factory=dict)
    # Format: {"fireball": {"name": "Fireball", "cost": {"mana": 3}, "commands": [...]},
    #          "heal": {"name": "Heal", "cost": {"mana": 2}, "commands": [...]}}

@dataclass
class AIBehavior:
    """NPC behavior configuration."""
    behavior_type: str = "idle"     # "idle", "patrol", "chase", "flee", "scripted"
    state: str = "idle"             # Current state within the behavior
    patrol_points: list = field(default_factory=list)  # [(gx, gy), ...]
    patrol_index: int = 0
    chase_target: str = ""          # Entity ID to chase
    chase_range: int = 5            # Tiles
    flee_range: int = 8             # Tiles to flee before stopping
    params: dict = field(default_factory=dict)  # Behavior-specific extra params

@dataclass
class TurnActor:
    """Participates in the turn-based system."""
    has_acted: bool = False
    speed_points: int = 0           # For initiative/speed-based turn order
    actions_per_turn: int = 1
```

### 4.3 Command System

The command system is the engine's backbone. All game logic — interactions, events, cinematics, item effects — is expressed as **command chains**: trees of commands that execute sequentially, with branching.

#### Command Structure

```python
# commands/command.py

@dataclass
class Command:
    type: str                    # Registry key, e.g. "dialogue", "set_variable", "filter"
    params: dict                 # Type-specific parameters
    next: list = None            # Child commands to execute after this finishes
    select_next: bool = False    # If True, finish(argument) picks a specific child by index
```

In JSON:
```json
{
    "type": "dialogue",
    "params": {"texts": ["Hello!", "Welcome to the dungeon."]},
    "next": [
        {"type": "add_item", "params": {"entity": "trigger", "item": "key_gold"}}
    ]
}
```

#### CommandRunner

```python
class CommandRunner:
    """Dispatches commands to registered handlers. Manages async command lifecycle."""

    def __init__(self, world: World, systems: dict):
        self.world = world
        self.systems = systems          # Reference to all game systems
        self._registry: dict = {}       # type_name -> handler_function
        self._active: list = []         # Currently running async commands

    def register(self, type_name: str, handler: Callable):
        """Register a command type handler."""

    def execute(self, command_data: dict | Command, context: dict):
        """Execute a command. Context flows through the chain.

        Context dict contains:
            'source_entity': str    - Entity that owns this command chain
            'trigger_entity': str   - Entity that triggered execution (e.g. player)
            'world': World          - Reference to the world
            'runner': CommandRunner  - Self-reference for sub-execution
        """

    def finish(self, command: Command, argument: int = None):
        """Called by async commands when they complete.
        Chains to next commands. If select_next and argument given,
        executes only the child at that index (for dialogue choices)."""

    def update(self, dt: float):
        """Tick active async commands (e.g., movement interpolation)."""

    def is_busy(self) -> bool:
        """True if any async commands are still running."""
```

#### Command Type Registry

```python
# commands/registry.py

COMMAND_REGISTRY: dict[str, Callable] = {}

def register_command(name: str):
    """Decorator to register a command handler function."""
    def decorator(func):
        COMMAND_REGISTRY[name] = func
        return func
    return decorator
```

#### Entity Reference Resolution

Commands reference entities by string. Special keywords:
- `"self"` — the entity that owns the command chain
- `"trigger"` — the entity that triggered the interaction (usually player)
- `"player"` — always resolves to the player entity
- Any other string — looked up by entity ID in the World

```python
def resolve_entity(ref: str, context: dict, world: World) -> str:
    """Resolve an entity reference string to an entity ID."""
    if ref == "self":
        return context["source_entity"]
    elif ref == "trigger":
        return context["trigger_entity"]
    elif ref == "player":
        return world.get_entity_ids_with(Tags)[0]  # Find entity tagged "player"
    else:
        return ref  # Direct entity ID
```

#### Built-in Command Types

**Dialogue commands** (`commands/dialogue.py`):

| Command | Params | Behavior |
|---------|--------|----------|
| `dialogue` | `texts: list[str]`, `instant: bool = false` | Queue text lines in the dialogue box. Async — finishes when player dismisses last line. |
| `choices_dialogue` | `text: str`, `choices: list[str]` | Show text with choices. Async — finishes with `argument = selected_index`. Must have `select_next: true` to branch. |

**Animation commands** (`commands/animation.py`):

| Command | Params | Behavior |
|---------|--------|----------|
| `play_animation` | `entity: str`, `animation: str`, `wait: bool = false` | Play named animation on entity. If `wait`, async — finishes when animation completes. |
| `stop_animation` | `entity: str` | Stop current animation. |

**Variable commands** (`commands/variables.py`):

| Command | Params | Behavior |
|---------|--------|----------|
| `set_variable` | `scope: "entity"\|"world"`, `entity: str`, `variable: str`, `value: any` | Set a variable. Entity scope writes to `Variables.data`, world scope writes to `World.variables`. |
| `increment_variable` | `scope`, `entity`, `variable`, `amount: int` | Add amount to a numeric variable. |
| `check_variable` | `scope`, `entity`, `variable`, `operator: str`, `value: any`, `on_true: list`, `on_false: list` | Check variable against value (operators: `==`, `!=`, `>`, `<`, `>=`, `<=`). Execute `on_true` or `on_false` commands. |

**Visibility commands** (`commands/visibility.py`):

| Command | Params | Behavior |
|---------|--------|----------|
| `set_visibility` | `entity: str`, `visible: bool` | Set entity visibility. |
| `toggle_visibility` | `entity: str` | Flip visibility. |

**Flow control commands** (`commands/flow.py`):

| Command | Params | Behavior |
|---------|--------|----------|
| `filter` | `condition: dict`, `on_true: list`, `on_false: list` | Evaluate condition, branch accordingly. Condition format: `{"scope": "world", "variable": "gate_opened", "operator": "==", "value": true}` |
| `sequence` | `commands: list` | Execute a list of commands sequentially (each waits for previous). |

**Map operation commands** (`commands/map_ops.py`):

| Command | Params | Behavior |
|---------|--------|----------|
| `remove_from_map` | `entity: str` | Remove entity from spatial grid (makes it non-collidable, non-interactable). Does NOT destroy it. |
| `restore_on_map` | `entity: str` | Re-add entity to spatial grid at its Position. |

**Enable commands** (`commands/enable.py`):

| Command | Params | Behavior |
|---------|--------|----------|
| `set_enabled` | `entity: str`, `enabled: bool` | Enable/disable an entity's interactable and area effects. Disabled entities don't respond to interactions. |

**Inventory commands** (`commands/inventory.py`):

| Command | Params | Behavior |
|---------|--------|----------|
| `add_item` | `entity: str`, `item: str`, `count: int = 1` | Add item(s) to entity's inventory. |
| `remove_item` | `entity: str`, `item: str`, `count: int = 1` | Remove item(s). |
| `check_item` | `entity: str`, `item: str`, `count: int = 1`, `on_success: list`, `on_fail: list` | Check if entity has item(s), branch accordingly. |

**Stats commands** (`commands/stats.py`):

| Command | Params | Behavior |
|---------|--------|----------|
| `damage` | `entity: str`, `amount: int`, `source: str = null` | Deal damage (reduced by defense). |
| `heal` | `entity: str`, `amount: int` | Restore HP (capped at max_hp). |
| `modify_stat` | `entity: str`, `stat: str`, `amount: int` | Add/subtract from a stat. |
| `check_stat` | `entity: str`, `stat: str`, `operator: str`, `value: int`, `on_true: list`, `on_false: list` | Branch based on stat value. |

**Camera commands** (`commands/camera_cmd.py`):

| Command | Params | Behavior |
|---------|--------|----------|
| `move_camera` | `target: str \| [x,y]`, `speed: float`, `wait: bool = true` | Smoothly move camera to entity or position. |
| `shake_camera` | `intensity: float`, `duration: float` | Screen shake effect. |
| `reset_camera` | | Return camera to following the player. |

**Wait commands** (`commands/wait.py`):

| Command | Params | Behavior |
|---------|--------|----------|
| `wait_seconds` | `seconds: float` | Pause command chain for duration. Async. |
| `wait_frames` | `frames: int` | Pause for N frames. Async. |

**Level commands** (`commands/level.py`):

| Command | Params | Behavior |
|---------|--------|----------|
| `change_area` | `area_id: str`, `spawn_point: str \| [gx, gy]` | Transition to another area. Saves current area state, loads target. |
| `warp` | `entity: str`, `position: [gx, gy]` | Teleport entity to grid position within current area. |

**Movement commands** (`commands/movement.py`):

| Command | Params | Behavior |
|---------|--------|----------|
| `move_entity` | `entity: str`, `direction: str`, `tiles: int = 1`, `wait: bool = true` | Move entity in direction. For cinematics/scripted sequences. |

**Sound commands** (`commands/sound.py`):

| Command | Params | Behavior |
|---------|--------|----------|
| `play_sound` | `sound_id: str`, `volume: float = 1.0` | Play sound effect. |
| `play_music` | `music_id: str`, `volume: float = 1.0`, `loop: bool = true` | Start background music. |
| `stop_music` | `fade_seconds: float = 0` | Stop music with optional fade. |

### 4.4 Movement System

Designed with an abstract interface from day one. Grid movement is implemented first; free movement slots in later without changing any code above the movement system.

```python
# systems/movement_system.py

class MovementSystem:
    def __init__(self, world: World, spatial_grid: SpatialGrid, collision_system: CollisionSystem):
        self.world = world
        self.spatial_grid = spatial_grid
        self.collision = collision_system
        self.tile_size = 16  # From config

    def request_move(self, entity_id: str, direction: str) -> bool:
        """Try to move entity one tile in direction. Returns True if movement started.
        Direction: "up", "down", "left", "right"
        """
        # 1. Calculate target tile
        # 2. Update facing direction regardless of success
        # 3. Check collision at target tile
        # 4. If pushable object at target, try to push it first
        # 5. If clear, start interpolated movement
        # 6. Update spatial grid immediately (claim new tile)
        # 7. Return True

    def update(self, dt: float):
        """Interpolate all moving entities. Trigger area effects on arrival."""
        for entity_id, gm, pos in self.world.query(GridMovement, Position):
            if gm.moving:
                gm.progress += gm.speed * dt
                if gm.progress >= 1.0:
                    # Snap to final position
                    gm.moving = False
                    pos.x, pos.y = gm.end_x, gm.end_y
                    # Trigger on_enter area effects at new tile
                    # Trigger on_leave area effects at old tile
                else:
                    # Linear interpolation
                    t = gm.progress
                    pos.x = gm.start_x + (gm.end_x - gm.start_x) * t
                    pos.y = gm.start_y + (gm.end_y - gm.start_y) * t

    def is_entity_moving(self, entity_id: str) -> bool:
        """Check if entity is currently in motion."""
```

**Direction vectors:**
```python
DIRECTION_VECTORS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}
```

### 4.5 Spatial Grid

Equivalent to the Godot project's `array_of_items[y][x]`. Tracks which entities occupy which tiles. Used for collision detection, area effect triggers, and entity lookups.

```python
# map/spatial_grid.py

class SpatialGrid:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        # grid[y][x] = set of entity_ids
        self.grid: list[list[set]] = [[set() for _ in range(width)] for _ in range(height)]

    def add_entity(self, entity_id: str, gx: int, gy: int): ...
    def remove_entity(self, entity_id: str, gx: int, gy: int): ...
    def move_entity(self, entity_id: str, old_gx: int, old_gy: int, new_gx: int, new_gy: int): ...
    def get_entities_at(self, gx: int, gy: int) -> set[str]: ...
    def get_entities_in_rect(self, x1: int, y1: int, x2: int, y2: int) -> set[str]: ...
    def is_in_bounds(self, gx: int, gy: int) -> bool: ...
    def clear(self): ...
```

**Multiple entities per tile:** A tile can hold a floor decoration, a pressure plate, an item pickup, and an NPC simultaneously. The set-based storage handles this naturally.

### 4.6 Collision System

```python
# systems/collision_system.py

class CollisionSystem:
    def __init__(self, world: World, spatial_grid: SpatialGrid, tile_map: TileMap):
        self.world = world
        self.spatial_grid = spatial_grid
        self.tile_map = tile_map

    def check_tile(self, gx: int, gy: int, ignore_entity: str = None) -> str:
        """Check what's at a tile.
        Returns: 'free', 'blocked', 'pushable', 'out_of_bounds'
        """
        if not self.spatial_grid.is_in_bounds(gx, gy):
            return "out_of_bounds"
        if not self.tile_map.is_walkable(gx, gy):
            return "blocked"  # Tile itself is not walkable

        for eid in self.spatial_grid.get_entities_at(gx, gy):
            if eid == ignore_entity:
                continue
            collision = self.world.get_component(eid, Collision)
            if collision and collision.solid:
                movable = self.world.get_component(eid, Movable)
                if movable and movable.pushable:
                    return "pushable"
                return "blocked"
        return "free"

    def get_solid_entity_at(self, gx: int, gy: int, ignore: str = None) -> str | None:
        """Get the solid entity at a tile, if any."""
```

### 4.7 Rendering System

Pixel-art focused renderer. Draws to a small internal surface, then scales up with nearest-neighbor filtering for crisp pixels.

```python
# engine/renderer.py

class Renderer:
    def __init__(self, internal_width: int = 256, internal_height: int = 224, scale: int = 3):
        self.internal_surface = pygame.Surface((internal_width, internal_height))
        self.scale = scale
        self.display = pygame.display.set_mode(
            (internal_width * scale, internal_height * scale)
        )

    def render_world(self, world: World, camera: Camera, tile_map: TileMap):
        """Render the game world."""
        self.internal_surface.fill((0, 0, 0))

        # 1. Render tile layers (bottom to top)
        self._render_tiles(tile_map, camera)

        # 2. Collect visible entities, sort by layer then y-position
        renderables = []
        for eid, sprite, pos in world.query(Sprite, Position):
            if sprite.visible:
                renderables.append((pos.layer, pos.y, eid, sprite, pos))
        renderables.sort(key=lambda r: (r[0], r[1]))

        # 3. Render entities
        for _, _, eid, sprite, pos in renderables:
            screen_x = pos.x - camera.x + sprite.offset_x
            screen_y = pos.y - camera.y + sprite.offset_y
            frame_surface = self.asset_manager.get_frame(sprite.sheet_id, sprite.frame)
            if sprite.flip_h or sprite.flip_v:
                frame_surface = pygame.transform.flip(frame_surface, sprite.flip_h, sprite.flip_v)
            self.internal_surface.blit(frame_surface, (int(screen_x), int(screen_y)))

        # 4. Scale up to display
        scaled = pygame.transform.scale(
            self.internal_surface,
            (self.internal_surface.get_width() * self.scale,
             self.internal_surface.get_height() * self.scale)
        )
        self.display.blit(scaled, (0, 0))

    def render_ui(self, ui_manager: UIManager):
        """Render UI on top (at display resolution, not internal)."""
        ui_manager.draw(self.display)
```

### 4.8 Interaction System

Handles player interactions (action button) and area effects (step on tile).

```python
# systems/interaction_system.py

class InteractionSystem:
    def try_interact(self, entity_id: str, facing: str):
        """Called when entity presses action button.
        Checks tile in facing direction for interactable entities."""
        pos = self.world.get_component(entity_id, Position)
        dx, dy = DIRECTION_VECTORS[facing]
        target_gx = pos.grid_x + dx
        target_gy = pos.grid_y + dy

        for target_eid in self.spatial_grid.get_entities_at(target_gx, target_gy):
            interactable = self.world.get_component(target_eid, Interactable)
            if interactable and interactable.command_chain:
                # Check if entity is enabled
                enabled = self.world.get_component(target_eid, CommandEnabled)
                if enabled and target_eid in enabled.disabled_commands:
                    continue
                context = {
                    "source_entity": target_eid,
                    "trigger_entity": entity_id,
                }
                for cmd_data in interactable.command_chain:
                    self.command_runner.execute(cmd_data, context)
                return True
        return False

    def check_area_effects(self, entity_id: str, gx: int, gy: int, effect_type: str):
        """Check for area effects at a tile. effect_type: 'on_enter', 'on_leave', 'on_stay'"""
        entity_tags = self.world.get_component(entity_id, Tags)
        for target_eid in self.spatial_grid.get_entities_at(gx, gy):
            area_effect = self.world.get_component(target_eid, AreaEffect)
            if area_effect:
                # Check if this entity's tags match the trigger_tags
                commands = getattr(area_effect, effect_type, [])
                if commands:
                    context = {
                        "source_entity": target_eid,
                        "trigger_entity": entity_id,
                    }
                    for cmd_data in commands:
                        self.command_runner.execute(cmd_data, context)
```

### 4.9 Tile Map

```python
# map/tile_map.py

class TileMap:
    def __init__(self, width: int, height: int, tile_size: int):
        self.width = width
        self.height = height
        self.tile_size = tile_size
        self.layers: list[list[list[int]]] = []        # [layer][y][x] = tile_id
        self.walkability: list[list[bool]] = []         # [y][x] = walkable
        self.tileset_id: str = ""

    def is_walkable(self, gx: int, gy: int) -> bool:
        """Check if a tile is walkable (non-wall)."""
        if not (0 <= gx < self.width and 0 <= gy < self.height):
            return False
        return self.walkability[gy][gx]

    def get_tile(self, layer: int, gx: int, gy: int) -> int:
        """Get tile ID at position in layer."""

    def set_tile(self, layer: int, gx: int, gy: int, tile_id: int):
        """Set tile ID (used by editor)."""

    def set_walkable(self, gx: int, gy: int, walkable: bool):
        """Set walkability (used by editor)."""
```

---

## 5. Data Formats

### 5.1 Area JSON

Each area is a separate JSON file representing one map/room/zone.

```json
{
    "id": "dungeon_entrance",
    "name": "Dungeon Entrance",
    "width": 20,
    "height": 15,
    "tile_size": 16,
    "movement_mode": "grid",
    "turn_based": false,
    "tileset": "dungeon_tiles",

    "tile_layers": [
        [
            [0, 0, 1, 1, 1, 1, 0, 0, "..."],
            [0, 2, 3, 3, 3, 3, 2, 0, "..."],
            "..."
        ]
    ],

    "walkability": [
        [false, false, true, true, true, true, false, false, "..."],
        [false, true, true, true, true, true, true, false, "..."],
        "..."
    ],

    "variables": {
        "gate_opened": false,
        "lever_count": 0,
        "boss_defeated": false
    },

    "transitions": [
        {
            "position": [19, 7],
            "target_area": "dungeon_hall",
            "target_position": [1, 7],
            "condition": null
        },
        {
            "position": [0, 7],
            "target_area": "overworld",
            "target_position": [15, 10],
            "condition": {"variable": "boss_defeated", "operator": "==", "value": true}
        }
    ],

    "on_load": [
        {"type": "play_music", "params": {"music_id": "dungeon_theme", "volume": 0.7}}
    ],

    "entities": [
        {
            "id": "player_spawn",
            "template": "spawn_point",
            "position": [3, 5],
            "tags": ["spawn_default"]
        },
        {
            "id": "lever_1",
            "template": "lever",
            "position": [5, 3],
            "persist": true,
            "overrides": {
                "Interactable": {
                    "command_chain": [
                        {
                            "type": "filter",
                            "params": {
                                "condition": {"scope": "entity", "entity": "self", "variable": "activated", "operator": "==", "value": false},
                                "on_true": [
                                    {
                                        "type": "play_animation",
                                        "params": {"entity": "self", "animation": "activate", "wait": true},
                                        "next": [
                                            {"type": "set_variable", "params": {"scope": "entity", "entity": "self", "variable": "activated", "value": true}},
                                            {"type": "set_variable", "params": {"scope": "world", "variable": "gate_opened", "value": true}},
                                            {"type": "set_visibility", "params": {"entity": "gate_1", "visible": false}},
                                            {"type": "remove_from_map", "params": {"entity": "gate_1"}},
                                            {"type": "play_sound", "params": {"sound_id": "gate_open"}},
                                            {"type": "set_enabled", "params": {"entity": "self", "enabled": false}}
                                        ]
                                    }
                                ],
                                "on_false": [
                                    {"type": "dialogue", "params": {"texts": ["The lever is already pulled."]}}
                                ]
                            }
                        }
                    ]
                }
            }
        },
        {
            "id": "gate_1",
            "template": "iron_gate",
            "position": [10, 7],
            "persist": true
        },
        {
            "id": "guard_npc",
            "template": "npc_guard",
            "position": [8, 5],
            "overrides": {
                "Interactable": {
                    "command_chain": [
                        {
                            "type": "dialogue",
                            "params": {"texts": ["Halt! Who goes there?", "...Oh, it's you. The dungeon lies ahead."]},
                            "next": [
                                {
                                    "type": "choices_dialogue",
                                    "params": {
                                        "text": "Do you need anything before you go?",
                                        "choices": ["Give me a key", "Tell me about the dungeon", "No thanks"]
                                    },
                                    "select_next": true,
                                    "next": [
                                        {
                                            "type": "check_item",
                                            "params": {
                                                "entity": "trigger",
                                                "item": "key_gold",
                                                "on_success": [
                                                    {"type": "dialogue", "params": {"texts": ["You already have a key!"]}}
                                                ],
                                                "on_fail": [
                                                    {"type": "dialogue", "params": {"texts": ["Here, take this."]}},
                                                    {"type": "add_item", "params": {"entity": "trigger", "item": "key_gold"}},
                                                    {"type": "dialogue", "params": {"texts": ["You received a Gold Key!"]}}
                                                ]
                                            }
                                        },
                                        {"type": "dialogue", "params": {"texts": ["The dungeon is full of traps.", "Be careful with the levers — some are rigged."]}},
                                        {"type": "dialogue", "params": {"texts": ["Good luck in there."]}}
                                    ]
                                }
                            ]
                        }
                    ]
                }
            }
        }
    ]
}
```

### 5.2 Entity Template JSON

Templates define default components for an entity type. Area entities reference templates and can override any component property.

```json
{
    "id": "lever",
    "components": {
        "Sprite": {
            "sheet_id": "lever_sheet",
            "frame": 0,
            "layer": 1
        },
        "AnimationState": {
            "animations": {
                "idle": {"frames": [0], "speed": 0.0, "loop": false},
                "activate": {"frames": [0, 1, 2, 3], "speed": 0.12, "loop": false},
                "deactivate": {"frames": [3, 2, 1, 0], "speed": 0.12, "loop": false}
            },
            "current_anim": "idle"
        },
        "Collision": {"solid": true},
        "Interactable": {"command_chain": []},
        "Variables": {"data": {"activated": false}},
        "Tags": {"values": ["lever", "interactable"]}
    }
}
```

```json
{
    "id": "player",
    "components": {
        "Sprite": {
            "sheet_id": "player_sheet",
            "frame": 0,
            "layer": 2
        },
        "AnimationState": {
            "animations": {
                "idle_down": {"frames": [0], "speed": 0.0, "loop": false},
                "idle_up": {"frames": [3], "speed": 0.0, "loop": false},
                "idle_left": {"frames": [6], "speed": 0.0, "loop": false},
                "idle_right": {"frames": [9], "speed": 0.0, "loop": false},
                "walk_down": {"frames": [0, 1, 2], "speed": 0.12, "loop": true},
                "walk_up": {"frames": [3, 4, 5], "speed": 0.12, "loop": true},
                "walk_left": {"frames": [6, 7, 8], "speed": 0.12, "loop": true},
                "walk_right": {"frames": [9, 10, 11], "speed": 0.12, "loop": true}
            },
            "current_anim": "idle_down"
        },
        "Collision": {"solid": true},
        "GridMovement": {"speed": 5.0, "facing": "down"},
        "Inventory": {"items": [], "max_size": 20},
        "Stats": {"hp": 20, "max_hp": 20, "attack": 3, "defense": 1},
        "Tags": {"values": ["player"]}
    }
}
```

```json
{
    "id": "iron_gate",
    "components": {
        "Sprite": {
            "sheet_id": "gate_sheet",
            "frame": 0,
            "layer": 1
        },
        "Collision": {"solid": true},
        "Tags": {"values": ["gate", "obstacle"]}
    }
}
```

```json
{
    "id": "npc_guard",
    "components": {
        "Sprite": {
            "sheet_id": "guard_sheet",
            "frame": 0,
            "layer": 2
        },
        "AnimationState": {
            "animations": {
                "idle_down": {"frames": [0], "speed": 0.0, "loop": false}
            },
            "current_anim": "idle_down"
        },
        "Collision": {"solid": true},
        "Interactable": {"command_chain": []},
        "Inventory": {"items": []},
        "Stats": {"hp": 15, "max_hp": 15, "attack": 2, "defense": 2},
        "AIBehavior": {"behavior_type": "idle"},
        "Tags": {"values": ["npc", "guard"]}
    }
}
```

### 5.3 Item Definitions

```json
{
    "items": {
        "key_gold": {
            "name": "Gold Key",
            "description": "A shiny golden key. Opens golden locks.",
            "sprite": {"sheet_id": "items_sheet", "frame": 0},
            "stackable": false,
            "tags": ["key"],
            "use_commands": null
        },
        "potion_health": {
            "name": "Health Potion",
            "description": "Restores 5 HP.",
            "sprite": {"sheet_id": "items_sheet", "frame": 3},
            "stackable": true,
            "max_stack": 10,
            "tags": ["consumable", "healing"],
            "use_commands": [
                {"type": "heal", "params": {"entity": "trigger", "amount": 5}},
                {"type": "remove_item", "params": {"entity": "trigger", "item": "potion_health", "count": 1}},
                {"type": "play_sound", "params": {"sound_id": "heal"}},
                {"type": "dialogue", "params": {"texts": ["You feel better!"]}}
            ]
        },
        "sword_iron": {
            "name": "Iron Sword",
            "description": "A sturdy iron sword. +2 Attack.",
            "sprite": {"sheet_id": "items_sheet", "frame": 10},
            "stackable": false,
            "tags": ["weapon", "equippable"],
            "equip_stat_bonus": {"attack": 2},
            "use_commands": null
        }
    }
}
```

---

## 6. Modularity: How Everything Connects

The core modularity principle: **any command can be placed in any command chain**. This means any trigger (interaction, area effect, item use, cinematic step, AI action) can cause any effect (open door, damage entity, give item, start dialogue, change variable, play animation, warp player, etc.).

### Example: Lever opens door

```json
{
    "type": "play_animation", "params": {"entity": "self", "animation": "activate", "wait": true},
    "next": [
        {"type": "set_variable", "params": {"scope": "entity", "entity": "self", "variable": "activated", "value": true}},
        {"type": "set_visibility", "params": {"entity": "gate_1", "visible": false}},
        {"type": "remove_from_map", "params": {"entity": "gate_1"}},
        {"type": "play_sound", "params": {"sound_id": "gate_open"}}
    ]
}
```

### Example: Lever damages player (trapped lever)

```json
{
    "type": "play_animation", "params": {"entity": "self", "animation": "activate", "wait": true},
    "next": [
        {"type": "damage", "params": {"entity": "trigger", "amount": 5}},
        {"type": "shake_camera", "params": {"intensity": 3, "duration": 0.3}},
        {"type": "dialogue", "params": {"texts": ["Ouch! The lever was trapped!"]}}
    ]
}
```

### Example: Lever gives player an action/ability

```json
{
    "type": "play_animation", "params": {"entity": "self", "animation": "activate", "wait": true},
    "next": [
        {"type": "dialogue", "params": {"texts": ["You feel a surge of power!"]}},
        {"type": "add_item", "params": {"entity": "trigger", "item": "scroll_fireball"}},
        {"type": "modify_stat", "params": {"entity": "trigger", "stat": "max_hp", "amount": 5}},
        {"type": "heal", "params": {"entity": "trigger", "amount": 5}}
    ]
}
```

### Example: Door that requires key

On the door entity's `Interactable`:

```json
{
    "type": "check_item",
    "params": {
        "entity": "trigger",
        "item": "key_gold",
        "on_success": [
            {"type": "dialogue", "params": {"texts": ["The key fits! The door opens."]}},
            {"type": "remove_item", "params": {"entity": "trigger", "item": "key_gold"}},
            {"type": "play_animation", "params": {"entity": "self", "animation": "open", "wait": true}},
            {"type": "remove_from_map", "params": {"entity": "self"}},
            {"type": "set_visibility", "params": {"entity": "self", "visible": false}}
        ],
        "on_fail": [
            {"type": "dialogue", "params": {"texts": ["The door is locked. You need a key."]}}
        ]
    }
}
```

### Example: Pressure plate triggered by pushing a box onto it

On the pressure plate entity's `AreaEffect.on_enter`:

```json
[
    {
        "type": "filter",
        "params": {
            "condition": {"scope": "entity", "entity": "trigger", "tag": "pushable_box"},
            "on_true": [
                {"type": "play_animation", "params": {"entity": "self", "animation": "pressed"}},
                {"type": "set_visibility", "params": {"entity": "secret_door", "visible": false}},
                {"type": "remove_from_map", "params": {"entity": "secret_door"}},
                {"type": "play_sound", "params": {"sound_id": "secret"}}
            ]
        }
    }
]
```

### Example: NPC dialogue that gives quest item and checks progress

```json
{
    "type": "check_variable",
    "params": {
        "scope": "world",
        "variable": "quest_started",
        "operator": "==",
        "value": false,
        "on_true": [
            {
                "type": "dialogue",
                "params": {"texts": ["Please help me find my lost ring in the dungeon!"]},
                "next": [
                    {
                        "type": "choices_dialogue",
                        "params": {"text": "Will you help?", "choices": ["Sure!", "Not now"]},
                        "select_next": true,
                        "next": [
                            {
                                "type": "set_variable",
                                "params": {"scope": "world", "variable": "quest_started", "value": true},
                                "next": [
                                    {"type": "dialogue", "params": {"texts": ["Thank you! Here, take this map."]}},
                                    {"type": "add_item", "params": {"entity": "trigger", "item": "dungeon_map"}}
                                ]
                            },
                            {"type": "dialogue", "params": {"texts": ["Oh... come back if you change your mind."]}}
                        ]
                    }
                ]
            }
        ],
        "on_false": [
            {
                "type": "check_item",
                "params": {
                    "entity": "trigger",
                    "item": "lost_ring",
                    "on_success": [
                        {"type": "dialogue", "params": {"texts": ["You found it! Thank you so much!"]}},
                        {"type": "remove_item", "params": {"entity": "trigger", "item": "lost_ring"}},
                        {"type": "add_item", "params": {"entity": "trigger", "item": "reward_gem"}},
                        {"type": "set_variable", "params": {"scope": "world", "variable": "quest_completed", "value": true}}
                    ],
                    "on_fail": [
                        {"type": "dialogue", "params": {"texts": ["Any luck finding my ring?"]}}
                    ]
                }
            }
        ]
    }
}
```

### Example: Cinematic sequence (entering a room triggers cutscene)

On a trigger entity's `AreaEffect.on_enter`:

```json
[
    {
        "type": "filter",
        "params": {
            "condition": {"scope": "world", "variable": "intro_played", "operator": "==", "value": false},
            "on_true": [
                {"type": "set_variable", "params": {"scope": "world", "variable": "intro_played", "value": true}},
                {"type": "sequence", "params": {"commands": [
                    {"type": "move_camera", "params": {"target": "boss_npc", "speed": 2.0, "wait": true}},
                    {"type": "wait_seconds", "params": {"seconds": 0.5}},
                    {"type": "dialogue", "params": {"texts": ["So... you've made it this far."]}},
                    {"type": "play_animation", "params": {"entity": "boss_npc", "animation": "laugh", "wait": true}},
                    {"type": "dialogue", "params": {"texts": ["But you won't leave here alive!"]}},
                    {"type": "move_entity", "params": {"entity": "boss_npc", "direction": "down", "tiles": 3, "wait": true}},
                    {"type": "reset_camera", "params": {}},
                    {"type": "play_music", "params": {"music_id": "boss_battle"}}
                ]}}
            ]
        }
    }
]
```

---

## 7. Area Persistence Model

### How it works

1. **Leaving an area:** The `AreaManager` snapshots the state of all entities with `Persist` component. It saves:
   - `Variables.data` — entity-local variables
   - `Sprite.visible` — visibility state
   - `Sprite.frame` — current frame (for animation state)
   - `Position.grid_x, grid_y` — current position
   - `Collision.solid` — collision state
   - Whether the entity has been removed from map
   - World-scoped variables (`World.variables`)

2. **State store:** Per-area state is stored in a dict: `area_states[area_id] = {entity_states, world_variables}`. This lives in memory during gameplay and is serialized to a save file.

3. **Re-entering an area:** The area JSON is loaded fresh (base state), then the saved state is applied on top:
   - For each persisted entity, overwrite its component values with saved values
   - If an entity was removed from map, remove it again
   - Restore world variables

4. **Entity `persist` flag:** Set per-entity in the area JSON. Default is `false`. Objects like levers, doors, quest-related NPCs, and collectible items should have `persist: true`. Decorations and static objects don't need it.

### Save file format

```json
{
    "save_version": 1,
    "current_area": "dungeon_entrance",
    "player_position": [5, 7],
    "player_state": {
        "Inventory": {"items": ["key_gold", "potion_health"]},
        "Stats": {"hp": 15, "max_hp": 20, "attack": 3, "defense": 1}
    },
    "global_variables": {
        "quest_started": true,
        "boss_defeated": false
    },
    "area_states": {
        "dungeon_entrance": {
            "world_variables": {"gate_opened": true},
            "entities": {
                "lever_1": {
                    "Variables": {"data": {"activated": true}},
                    "Sprite": {"visible": true, "frame": 3},
                    "enabled": false
                },
                "gate_1": {
                    "Sprite": {"visible": false},
                    "removed_from_map": true
                }
            }
        }
    }
}
```

---

## 8. Turn-Based System

When `turn_based: true` is set on an area, the game operates in Mystery Dungeon style:

1. **Player's turn:** Game waits for player input. When the player moves or performs an action, that's their turn.
2. **NPC turns:** After the player acts, each NPC with a `TurnActor` component gets one action (move, attack, use ability, etc.). NPCs act in order of `speed_points` (highest first).
3. **Resolution:** After all NPCs have acted, return to step 1.

```python
# systems/turn_system.py

class TurnSystem:
    class State(Enum):
        WAITING_FOR_PLAYER = "waiting_for_player"
        ANIMATING_PLAYER = "animating_player"
        PROCESSING_NPCS = "processing_npcs"
        ANIMATING_NPC = "animating_npc"

    def on_player_action(self):
        """Called when player makes a move or action."""
        self.state = State.ANIMATING_PLAYER
        # Wait for player movement animation to finish
        # Then: self.state = State.PROCESSING_NPCS

    def update(self, dt):
        if self.state == State.PROCESSING_NPCS:
            # Get next NPC that hasn't acted
            # Run its AI for one action
            # Wait for animation
            # When all done: self.state = State.WAITING_FOR_PLAYER

    def can_player_act(self) -> bool:
        return self.state == State.WAITING_FOR_PLAYER
```

**In real-time mode:** The turn system is not active. Movement and AI run every frame based on `dt`. The same `MovementSystem` and `AISystem` are used — the turn system just controls *when* they're allowed to tick.

---

## 9. NPC AI System

Modular behavior handlers registered by name. Each NPC's `AIBehavior.behavior_type` determines which handler runs.

```python
# systems/ai_system.py

class AISystem:
    def __init__(self, world, movement_system):
        self.handlers = {
            "idle": self._idle,
            "patrol": self._patrol,
            "chase": self._chase,
            "flee": self._flee,
            "scripted": self._scripted,
        }

    def update(self, dt):
        """In real-time mode, called every frame.
        In turn-based mode, called once per NPC per turn."""
        for eid, ai, pos in self.world.query(AIBehavior, Position):
            handler = self.handlers.get(ai.behavior_type, self._idle)
            handler(eid, ai, pos, dt)

    def _idle(self, eid, ai, pos, dt):
        """Do nothing. Optional: random facing changes."""

    def _patrol(self, eid, ai, pos, dt):
        """Move between patrol_points in sequence."""
        target = ai.patrol_points[ai.patrol_index]
        if (pos.grid_x, pos.grid_y) == tuple(target):
            ai.patrol_index = (ai.patrol_index + 1) % len(ai.patrol_points)
        else:
            direction = self._direction_toward(pos, target)
            self.movement_system.request_move(eid, direction)

    def _chase(self, eid, ai, pos, dt):
        """Move toward chase_target if within range."""
        target_pos = self.world.get_component(ai.chase_target, Position)
        if target_pos:
            dist = abs(pos.grid_x - target_pos.grid_x) + abs(pos.grid_y - target_pos.grid_y)
            if dist <= ai.chase_range:
                direction = self._direction_toward(pos, (target_pos.grid_x, target_pos.grid_y))
                self.movement_system.request_move(eid, direction)

    def _flee(self, eid, ai, pos, dt):
        """Move away from chase_target."""

    def _scripted(self, eid, ai, pos, dt):
        """Follow a scripted command sequence (used for cinematic NPCs)."""
```

**Adding new behaviors:** Register a new handler function in the `handlers` dict. No existing code changes needed.

---

## 10. Dialogue System

State machine for text display with character-by-character reveal.

```python
# systems/dialogue_system.py

class DialogueSystem:
    class State(Enum):
        IDLE = "idle"
        REVEALING = "revealing"     # Characters appearing one by one
        WAITING = "waiting"         # Full text shown, waiting for input
        CHOICES = "choices"         # Showing choice options

    CHAR_RATE = 0.03  # Seconds per character

    def start_dialogue(self, texts: list[str], command, context):
        """Begin showing dialogue texts one by one."""

    def start_choices(self, text: str, choices: list[str], command, context):
        """Show text, then present choices."""

    def advance(self):
        """Called on action button press.
        REVEALING -> show full text instantly
        WAITING -> next text in queue, or finish
        CHOICES -> confirm selected choice"""

    def select_up(self): ...
    def select_down(self): ...

    def update(self, dt):
        """Advance character reveal timer."""

    def is_active(self) -> bool:
        return self.state != State.IDLE
```

---

## 11. Level Editor

The editor runs as a game state within the same Pygame window. Toggle between editor and play-test with a hotkey.

### Editor Modes

1. **Tile Mode:** Select tile from palette, paint on grid. Left click = paint, right click = erase (set to tile 0).
2. **Walkability Mode:** Toggle tiles as walkable/unwalkable. Visual overlay shows blocked tiles.
3. **Entity Mode:** Select entity template from palette, click to place. Right click to remove.
4. **Property Mode:** Click entity to select, edit its properties (command chains, overrides, variables) via a property panel.
5. **Transition Mode:** Define area transitions — click tile, specify target area and spawn position.

### Editor Features

- **Save/Load:** Export area as JSON, load area from JSON
- **Play-test:** Switch to game mode to test the area. Switch back to editor preserving state.
- **Grid overlay:** Shows tile boundaries, entity positions
- **Entity palette:** Scrollable list of available templates
- **Tile palette:** Visual tile selector from loaded tileset
- **Property inspector:** Edit component values for selected entity
- **Command chain editor:** Tree view of commands with add/edit/remove (later phase — initially edit JSON directly)

### Editor Data Flow

```
Editor UI
    |
    v
TileMap + Entity list (in-memory)
    |
    v
level_loader.save_area(area_data, "data/levels/my_area.json")
    |
    v
JSON file on disk
```

---

## 12. Implementation Phases

### Phase 1a: Core Engine + Grid Movement
**Goal:** Player moves on grid, tiles render, camera follows.

| File | Purpose |
|------|---------|
| `main.py` | Entry point, pygame init, game loop start |
| `config.py` | TILE_SIZE, INTERNAL_WIDTH, INTERNAL_HEIGHT, SCALE, FPS, paths |
| `engine/game.py` | Game state machine, main loop |
| `engine/renderer.py` | Internal surface + scaling, tile rendering, entity rendering |
| `engine/camera.py` | Follow target entity, bounds clamping |
| `engine/input_handler.py` | Keyboard input -> action names |
| `engine/asset_manager.py` | Load PNGs, slice sprite sheets, cache frames |
| `ecs/world.py` | Entity registry, component storage, queries |
| `ecs/component.py` | Position, Sprite, AnimationState, Collision, Movable, GridMovement, Tags |
| `map/tile_map.py` | Tile grid, walkability, layers |
| `map/spatial_grid.py` | 2D entity tracking per tile |
| `map/level_loader.py` | JSON -> World (parse area, spawn entities from templates) |
| `systems/movement_system.py` | Grid movement with interpolation |
| `systems/collision_system.py` | Tile-based collision checks |
| `systems/animation_system.py` | Frame advancing |
| `data/levels/test_area.json` | Hand-written test area |
| `data/entities/player.json` | Player template |

### Phase 1b: Command System + Interactions
**Goal:** Interact with levers, open doors, push blocks.

| File | Purpose |
|------|---------|
| `commands/command.py` | Command dataclass + CommandRunner |
| `commands/registry.py` | Registration decorator |
| `commands/animation.py` | play_animation |
| `commands/visibility.py` | set_visibility, toggle_visibility |
| `commands/variables.py` | set_variable, check_variable |
| `commands/flow.py` | filter, sequence |
| `commands/map_ops.py` | remove_from_map, restore_on_map |
| `commands/enable.py` | set_enabled |
| `systems/interaction_system.py` | Action button dispatch, area effects |
| `ecs/component.py` additions | Interactable, AreaEffect, Variables, Persist |
| `data/entities/lever.json` | Lever template |
| `data/entities/iron_gate.json` | Gate template |

### Phase 1c: Basic Editor
**Goal:** Paint tiles, set walkability, place entities, save/load JSON.

| File | Purpose |
|------|---------|
| `map/level_editor.py` | Editor logic: modes, tile painting, entity placement |
| `ui/editor_ui.py` | Tile palette, entity palette, mode toolbar |
| `ui/ui_manager.py` | UI layer management |

### Phase 2: Dialogue System
| File | Purpose |
|------|---------|
| `systems/dialogue_system.py` | Text state machine, character reveal |
| `ui/textbox.py` | Dialogue box rendering |
| `ui/choices_panel.py` | Choice list rendering |
| `commands/dialogue.py` | dialogue, choices_dialogue commands |

### Phase 3: Area Transitions + Persistence
| File | Purpose |
|------|---------|
| `map/area_manager.py` | Load/unload areas, state snapshots |
| `engine/save_manager.py` | Save/load to disk |
| `commands/level.py` | change_area, warp commands |

### Phase 4: Inventory + Items + Stats
| File | Purpose |
|------|---------|
| `systems/inventory_system.py` | Item operations |
| `systems/stats_system.py` | HP, damage, stats |
| `commands/inventory.py` | add_item, remove_item, check_item |
| `commands/stats.py` | damage, heal, modify_stat, check_stat |
| `ui/inventory_ui.py` | Inventory display |
| `ui/hud.py` | HP bar, stats overlay |
| `data/items/items.json` | Item definitions |

### Phase 5: Turn-Based Mode
| File | Purpose |
|------|---------|
| `systems/turn_system.py` | Turn scheduler |
| `ecs/component.py` addition | TurnActor |

### Phase 6: NPC AI
| File | Purpose |
|------|---------|
| `systems/ai_system.py` | Behavior handlers |
| `ecs/component.py` addition | AIBehavior |

### Phase 7: Cinematics
| File | Purpose |
|------|---------|
| `systems/cinematic_system.py` | Sequence playback, input blocking |
| `commands/camera_cmd.py` | move_camera, shake_camera, reset_camera |
| `commands/wait.py` | wait_seconds, wait_frames |
| `commands/movement.py` | move_entity (scripted) |

### Phase 8: Free Movement Mode
| File | Purpose |
|------|---------|
| `ecs/component.py` addition | FreeMovement |
| `systems/movement_system.py` extension | Velocity-based movement |
| `systems/collision_system.py` extension | AABB collision |
| Editor: collider shape editing | |

### Phase 9: Audio + Polish
| File | Purpose |
|------|---------|
| `commands/sound.py` | play_sound, play_music, stop_music |

---

## 13. Patterns from Existing Godot Project

The existing `dungeon-puzzle-2/` project provides proven patterns that this architecture translates:

| Godot Pattern | Python Translation |
|---------------|-------------------|
| Godot node tree composition (Sprite, Collision, Interaction children) | ECS components on entities (Sprite, Collision, Interactable) |
| GDScript command base class with `execute_command()` / `command_finished_executing()` | `CommandRunner.execute()` / `CommandRunner.finish()` |
| `execute_specific_command(argument)` for dialogue choices | `Command.select_next = True` + `finish(argument=index)` |
| `array_of_items[y][x]` in `create_map.gd` | `SpatialGrid.grid[y][x] = set()` |
| Export variables in Godot inspector | JSON `overrides` on entities in area files |
| `Area_Enter_Effect` / `Area_Leave_Effect` child nodes | `AreaEffect` component with `on_enter` / `on_leave` command lists |
| `filter_command.gd` with `allow_command` flag | `filter` command with `condition` + `on_true` / `on_false` |
| `check_if_have_item_command.gd` with `execute_on_success` / `execute_on_failure` | `check_item` command with `on_success` / `on_fail` |
| `change_variables_command.gd` modifying node properties | `set_variable` command writing to `Variables.data` or `World.variables` |
| `StaticVariables.gd` autoload singleton | `World.variables` dict |
| `.tscn` scene files | JSON area files + JSON entity templates |
| Godot scene editor for level building | In-game level editor |

---

## 14. Code Style

This codebase is worked on by different people and agents across many separate sessions. The code should be understandable by someone seeing it for the first time.

### What that means in practice

- **Module-level docstrings** on every `.py` file — what the module does, how it fits in, what depends on it. This is the most important one: it orients a new reader immediately.
- **Docstrings on classes and non-obvious methods.** Self-explanatory one-liners like `get_entities_at()` don't need them. Complex methods with subtle behavior do.
- **Comments explain "why", not "what."** Comment non-obvious decisions, ordering dependencies, and workarounds. Don't comment obvious code.
- **Type hints** on function signatures. They serve as inline documentation.
- **Error messages with context** — include what entity/command/operation was involved, not just the raw error.

### Naming

Standard Python conventions: `snake_case` for files, functions, variables; `PascalCase` for classes and components; `UPPER_SNAKE_CASE` for constants. Entity IDs, command types, and JSON keys all use `snake_case` strings.

---

## 15. Game Loop

```python
# Simplified main game loop

def game_loop():
    clock = pygame.time.Clock()
    running = True

    while running:
        dt = clock.tick(FPS) / 1000.0

        # 1. Input
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                running = False

        if game_state == "play":
            input_handler.update(events)

            # 2. Handle player input
            if not dialogue_system.is_active() and not cinematic_system.is_active():
                if turn_system.active:
                    if turn_system.can_player_act():
                        handle_player_input()  # May call turn_system.on_player_action()
                else:
                    handle_player_input()

            # 3. Update systems
            if turn_system.active:
                turn_system.update(dt)
            else:
                ai_system.update(dt)

            movement_system.update(dt)
            animation_system.update(dt)
            command_runner.update(dt)
            dialogue_system.update(dt)
            cinematic_system.update(dt)
            camera.update(dt)

            # 4. Render
            renderer.render_world(world, camera, tile_map)
            dialogue_system.render(renderer.display)
            hud.render(renderer.display)

        elif game_state == "editor":
            level_editor.handle_input(events)
            level_editor.update(dt)
            level_editor.render(renderer.display)

        pygame.display.flip()
```
