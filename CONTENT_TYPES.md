# Content Types Reference

## Purpose

This document explains how the engine connects to project JSON files, what the
five content types are, and how they relate to each other. It is written for
both content authors and developers working on the engine.

## How the Engine Connects to JSON

### The Entry Point: `project.json`

Every project starts with a `project.json` file. This manifest tells the engine
where to find content by declaring search paths for each content type:

```json
{
  "entity_paths": ["entities/"],
  "asset_paths": ["assets/"],
  "area_paths": ["areas/"],
  "command_paths": ["commands/"],
  "dialogue_paths": ["dialogues/"]
}
```

All paths inside the manifest are relative to the folder that contains
`project.json`. That folder is the **project root**.

### Key Names Are Fixed, Folder Names Are Not

The engine looks for specific key names in `project.json`:

| Key | What it configures |
|---|---|
| `entity_paths` | Where to find entity template JSON files |
| `area_paths` | Where to find area/map JSON files |
| `command_paths` | Where to find named command JSON files |
| `dialogue_paths` | Where to find dialogue JSON files |
| `asset_paths` | Where to find images, sounds, and fonts |

You **cannot** rename these keys (e.g., `level_paths` instead of `area_paths`
will not work). But you **can** point them at any folder you want:

```json
{
  "area_paths": ["world/levels/", "world/dungeons/"],
  "entity_paths": ["data/characters/", "data/objects/"]
}
```

### Convention Over Configuration

If you omit a key from `project.json`, the engine falls back to a conventional
folder name inside the project root:

| Omitted key | Falls back to |
|---|---|
| `entity_paths` | `entities/` |
| `area_paths` | `areas/` |
| `command_paths` | `commands/` |
| `dialogue_paths` | `dialogues/` |
| `asset_paths` | `assets/` |

If the fallback folder does not exist, the engine treats it as an empty list.

### Multiple Search Paths

Each key accepts a list of paths. The engine searches them in order:

```json
{
  "command_paths": ["commands/", "shared_commands/"]
}
```

This allows projects to mix shared and project-specific content.

---

## The ID System

### IDs Are Derived From File Paths

Every JSON content file gets an ID automatically based on its location relative
to its type's search root. The engine strips the root directory and the `.json`
extension.

**Example:** If `command_paths` includes `commands/`, then:

| File path | Derived ID |
|---|---|
| `commands/push_one_tile.json` | `push_one_tile` |
| `commands/dialogue/blue_guide_intro.json` | `dialogue/blue_guide_intro` |
| `commands/puzzles/lever_toggle.json` | `puzzles/lever_toggle` |

### No Explicit ID Field Needed

You do not need to write an `id` field in your JSON files. The file's location
**is** its identity. For commands and dialogues, authored `id` fields are
rejected entirely. Areas work the same way with `area_id`: do not author it in
the JSON file.

### IDs Are Stable

An ID stays the same as long as the file does not move within its search root.
You can reorganize the folder structure above the root without affecting IDs.

### Duplicate Detection

If two files in different search paths produce the same ID, the engine reports
an error at startup. This prevents silent conflicts.

---

## The Five Content Types

### Overview Table

| Property | Areas | Entities | Commands | Dialogues | Assets |
|---|---|---|---|---|---|
| Config key | `area_paths` | `entity_paths` | `command_paths` | `dialogue_paths` | `asset_paths` |
| Default folder | `areas/` | `entities/` | `commands/` | `dialogues/` | `assets/` |
| File format | JSON | JSON | JSON | JSON | PNG, WAV, JSON |
| ID system | Path-derived | Path-derived | Path-derived | Path-derived | Path string |
| Subfolder support | Yes | Yes | Yes | Yes | Yes |
| Can be inline | No | Yes | Yes | Yes | No |
| Referenced via | `area_id` | `template` | `command_id` | `dialogue_id` | Asset path |
| Startup scan | Yes | Yes | Yes | Yes | On demand |
| Duplicate detection | Yes | Yes | Yes | Yes | N/A |

---

### Areas

**What it is:** A playable map with tile layers, cell-flag walkability data, and placed
entities. Each area is a self-contained room or screen.

**Runtime behavior:** Loaded into memory when the player enters. Only one area
is active at a time. The renderer draws its tile layers, and the world system
manages its entities.

**Key JSON fields:**

```json
{
  "name": "Village Square",
  "tile_size": 16,
  "player_id": "player",
  "variables": {},
  "tilesets": [
    {
      "firstgid": 1,
      "path": "assets/project/tiles/basic_tiles.png",
      "tile_width": 16,
      "tile_height": 16
    }
  ],
  "tile_layers": [ ... ],
  "cell_flags": [ ... ],
  "entities": [
    {"id": "guard", "x": 5, "y": 3, "template": "npc_guard"},
    {"id": "door_1", "x": 9, "y": 0, "template": "door", "parameters": {"target_area": "village_house"}}
  ]
}
```

**How it is loaded:** `dungeon_engine/world/loader.py` → `load_area()` parses
the JSON, builds tile layers, instantiates entities from templates, and applies
any persistent state overrides.

**How it is referenced:** By ID from commands:

```json
{"type": "change_area", "area_id": "village_square"}
```

**Inline usage:** Areas cannot be defined inline. They are always separate
files.

**ID rule:** The area id comes from the file path under `area_paths`. For
example, `areas/village_square.json` becomes `village_square`.

---

### Entities

**What it is:** A runtime object in the game world — player, NPC, lever, gate,
door, block, trigger, or any other interactive thing.

**Runtime behavior:** Instantiated from a template when an area loads. Has
position, sprite, collision, events, variables, and optional input handling.
Systems (movement, animation, collision) operate on entities.

**Key JSON fields (template):**

```json
{
  "solid": true,
  "pushable": true,
  "sprite": {
    "path": "assets/project/sprites/block.png",
    "frame_width": 16,
    "frame_height": 16,
    "frames": [0]
  },
  "events": {
    "on_pushed": {
      "enabled": true,
      "commands": [
        {"type": "run_named_command", "command_id": "push_one_tile", "parameters": {"direction": "$direction"}}
      ]
    }
  },
  "variables": {
    "push_attempt_state": "free"
  }
}
```

**How it is loaded:** `dungeon_engine/world/loader.py` →
`_resolve_entity_instance()` merges the template with per-instance overrides
from the area JSON, then substitutes parameters.

**How it is referenced:** By template ID in area JSON:

```json
{"id": "block_1", "x": 4, "y": 5, "template": "block"}
```

**Inline usage:** Entities can be defined fully inline in area JSON by omitting
the `template` field:

```json
{
  "id": "custom_sign",
  "x": 3,
  "y": 7,
  "solid": true,
  "sprite": {
    "path": "assets/project/sprites/sign.png",
    "frame_width": 16,
    "frame_height": 16,
    "frames": [0]
  },
  "events": {
    "interact": {
      "enabled": true,
      "commands": [
        {"type": "run_dialogue", "text": "This path leads north."}
      ]
    }
  }
}
```

**Hybrid usage:** Template with per-instance overrides:

```json
{
  "id": "special_gate",
  "x": 8,
  "y": 4,
  "template": "gate",
  "variables": {"starts_open": true}
}
```

---

### Commands

**What it is:** A reusable action chain authored in JSON. Commands orchestrate
gameplay — movement, interaction, dialogue, animation, persistence, and more.

**Runtime behavior:** Indexed into an in-memory database at startup. When
referenced by ID at runtime, the engine loads the definition from memory (no
disk I/O during play), substitutes parameters, and executes the command chain.

**Key JSON fields:**

```json
{
  "params": ["direction", "frames_needed"],
  "commands": [
    {"type": "query_facing_state", "entity_id": "$entity_id", "direction": "$direction"},
    {
      "type": "check_var",
      "entity_id": "$entity_id",
      "name": "push_attempt_state",
      "op": "eq",
      "value": "free",
      "then": [
        {"type": "play_audio", "path": "assets/project/sounds/push.wav"},
        {"type": "move_entity_one_tile", "entity_id": "$entity_id", "direction": "$direction", "frames_needed": "$frames_needed"}
      ]
    }
  ]
}
```

**How it is loaded:** `dungeon_engine/commands/library.py` →
`build_named_command_database()` scans all configured command paths at startup,
validates JSON, checks for duplicates, and caches everything in memory.

**How it is referenced:** By command ID:

```json
{"type": "run_named_command", "command_id": "push_one_tile", "parameters": {"direction": "right"}}
```

**Inline usage:** Commands are commonly defined inline inside entity events or
inside other command chains:

```json
{
  "events": {
    "interact": {
      "enabled": true,
      "commands": [
        {"type": "face_direction", "direction": "up"},
        {"type": "run_dialogue", "text": "Hello!"}
      ]
    }
  }
}
```

Inline commands and named commands are the same thing — the difference is just
whether the chain lives in its own file (reusable) or directly where it is used
(one-off).

**Parameter substitution:** Named commands support `$variable` and `${variable}`
syntax. Parameters passed at invocation replace these tokens throughout the
command chain.

---

### Dialogues

**What it is:** A reusable text payload. Dialogues are the simplest content
type — essentially structured text plus optional metadata like `speaker`.

**Runtime behavior:** Validated at startup, then resolved from cache when a
command references a dialogue ID. The command system handles display,
pagination, and input.

**Key JSON fields:**

Single-page:

```json
{
  "speaker": "Village Guard",
  "text": "Stop right there."
}
```

Multi-page:

```json
{
  "speaker": "Elder",
  "pages": [
    "Welcome, traveler.",
    "This village has seen better days.",
    "Perhaps you can help us."
  ]
}
```

**How it is loaded:** `dungeon_engine/dialogue_library.py` →
`load_dialogue_definition()` resolves the ID via configured dialogue paths,
validates the JSON (must have `text` or `pages` but not both; `speaker` is
optional), and caches the result.

**How it is referenced:** By dialogue ID:

```json
{"type": "run_dialogue", "dialogue_id": "npcs/blue_guide"}
```

**Inline usage:** Dialogue text can be passed directly in commands without a
separate file:

```json
{"type": "run_dialogue", "text": "Welcome to the village!"}
```

Or with multiple pages:

```json
{"type": "run_dialogue", "pages": ["Page one.", "Page two."]}
```

**When to use a file vs inline:**

- Use a dialogue file when the same text is referenced from multiple places, or
  when you want all game text collected in one folder (useful for translation).
- Use inline text for one-off messages that only appear in one command chain.

---

### Assets

**What it is:** Binary files — images (PNG), sounds (WAV), and supporting data
files like bitmap font definitions (JSON). Assets are the non-logic content that
the engine renders or plays.

**Runtime behavior:** Loaded on demand and cached in memory. The asset manager
maintains three caches: images, sprite frames, and sounds. Once loaded, assets
are served from cache without further disk reads.

**How they are organized:**

```
assets/
  project/
    fonts/pixelbet.png, pixelbet.json
    portraits/guard.png
    sprites/player.png, block.png
    tiles/basic_tiles.png
    ui/dialogue_panel.png
  third_party_tileset/
    terrain.png
```

**How they are referenced:** By path string relative to the project root:

```json
{
  "sprite": {
    "path": "assets/project/sprites/player.png",
    "frame_width": 16,
    "frame_height": 16,
    "frames": [0]
  }
}
```

**How they are loaded:** `dungeon_engine/engine/asset_manager.py` →
`get_image()`, `get_frame()`, `get_sound()`. The asset manager resolves the
relative path against configured `asset_paths` and caches the result.

**No ID system:** Assets use path strings, not IDs. This is appropriate because
binary files cannot declare metadata about themselves, and the path-based
approach works well for files that do not reference each other.

**Inline usage:** Not applicable. Assets are always external files.

---

## The Inline/Reference Pattern

A consistent pattern runs through the engine: most content types can be either
**defined inline** (one-off, right where they are used) or **referenced by ID**
(reusable, stored in a separate file).

| Content type | Inline example | Reference example |
|---|---|---|
| **Entity** | Full entity definition in area JSON (omit `template`) | `"template": "npc_guard"` |
| **Command** | Command list inside entity events | `"command_id": "push_one_tile"` |
| **Dialogue** | `"text": "Hello!"` in a command | `"dialogue_id": "npcs/blue_guide"` |
| **Area** | Not supported | `"area_id": "village_square"` |
| **Asset** | Not applicable | `"sprite": { "path": "assets/project/sprites/player.png", ... }` |

### When to use inline vs reference

**Use inline when:**

- The content is used in exactly one place
- It is short and simple
- Keeping it close to its context makes it easier to understand

**Use a reference when:**

- The content is reused across multiple areas, entities, or commands
- It is long or complex enough to benefit from its own file
- You want to organize content for easy browsing or translation

There is no performance difference. The engine caches both equally.

---

## How Content Types Reference Each Other

Content types do not exist in isolation. Here is how they connect:

```
project.json
  └── configures search paths for all types

Area JSON
  ├── references tilesets (asset paths)
  ├── places entities (by template ID or inline)
  └── entities reference commands and dialogues

Entity template JSON
  ├── references sprite sheets (asset paths)
  └── events contain command chains (inline or by command ID)

Command JSON
  ├── can reference other commands (by command ID)
  ├── can reference dialogues (by dialogue ID)
  ├── can reference areas (by area ID)
  └── can reference assets (by path, e.g., sounds)

Dialogue JSON
  └── standalone text data, does not reference other types
```

The reference direction is mostly top-down: areas reference entities, entities
reference commands, commands reference dialogues and other commands. Dialogues
are leaf nodes — they reference nothing.

---

## Other Configuration Keys

Beyond the five content type paths, `project.json` also supports:

| Key | Default | Purpose |
|---|---|---|
| `variables_path` | `variables.json` | Project-wide shared variables |
| `save_dir` | `saves/` | Where save slot data is stored |
| `startup_area` | none | The path-derived area id to load first when the game starts |
| `active_entity_id` | `"player"` | Which entity receives input by default |
| `input_events` | move_up/down/left/right, interact | Maps input actions to event names |
| `debug_inspection_enabled` | `false` | Enables debug zoom/pause/step controls |

These are engine configuration, not content type definitions.
