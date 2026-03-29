# Decisions

This file records settled decisions for the future area editor.

Add new entries when the user explicitly makes or approves a meaningful decision.

## 2026-03-28

### The new editor lives outside the runtime

Decision:

- the future tool belongs under `tools/area_editor/`

Why:

- the runtime should not carry editor code anymore
- the boundary should be obvious from the folder structure

### Bootstrap with docs before code

Decision:

- create folders and docs now, but do not start implementation yet

Why:

- the user wants the boundary and planning in place first

Status:

- completed as the initial bootstrap step
- Phase 1 now exists, so this entry is historical context rather than current status

### The tool must not import `dungeon_engine`

Decision:

- the future editor should not communicate with runtime code through imports

Why:

- the shared contract should be JSON files, not live Python objects

### The tool uses the same JSON structure as the runtime

Decision:

- the future editor reads and writes the same authored JSON files the runtime already consumes

Why:

- this keeps tooling and runtime aligned without direct code coupling

### The tool is a convenience authoring tool, not a second engine

Decision:

- focus on tilemaps, entity placement, and selected parameter editing

Why:

- that is where the biggest authoring pain currently lives
- the user does not want to rebuild runtime behavior inside the editor

### The tool should especially help with entity-reference parameters

Decision:

- entity-instance reference editing is a first-class use case

Why:

- the user explicitly called out this workflow as important

### Unknown authored data should be preserved

Decision:

- future saves should preserve fields the tool does not actively own whenever practical

Why:

- runtime content will continue to evolve
- the tool should not become destructive just because it is narrower than the runtime

## 2026-03-29

### UI framework: PySide6

Decision:

- the editor uses PySide6 (Qt for Python) for its UI

Why:

- QGraphicsView provides a native zoomable/pannable tile canvas
- dockable panels, tree views, and form widgets are first-class in Qt
- cross-platform (Windows and Linux) out of the box
- the editor's scope is panel-heavy (tileset browser, entity inspector, layer list) which suits a traditional widget toolkit

### The editor folder is fully portable

Decision:

- `tools/area_editor/` must be self-contained and copyable to another location
- its own `requirements.txt`, its own launcher script
- no imports from `dungeon_engine` or any sibling package

Why:

- the user wants the editor to be usable independently of the engine repo layout

### Content ids should use type-prefixed relative ids without extensions

Decision:

- area ids should include the type prefix but omit the file extension: `areas/village_square` instead of `village_square`
- template ids should follow the same pattern: `entity_templates/area_door` instead of `area_door`
- command ids should follow the same pattern: `commands/dialogue/open` instead of `dialogue/open`
- this is now the implemented runtime/editor contract

Why:

- makes ids structurally unique across content types - `areas/door` can never collide with `entity_templates/door` or `commands/door`
- enables safe project-wide find-and-replace when renaming or moving files
- self-documenting - reading a reference tells you exactly what kind of content it points to and where the file lives
- avoids baking the storage format into the gameplay/content contract

### Content type folders stay mandatory

Decision:

- areas must live under area roots, templates under template roots, etc.
- mixing content types in a single folder (e.g. `level_1/map.area.json` alongside `level_1/boss.template.json`) is rejected

Why:

- the folder prefix is what makes type-prefixed ids unambiguous by content kind
- removing it would require a replacement mechanism (file extensions like `.area.json`, or a type field in every file) adding complexity for little gain
- per-level grouping is already achievable with matching subfolder names within each type root (`areas/level_1/map.json`, `entity_templates/level_1/boss.json`, `commands/level_1/boss_intro.json`)
- the current structure is understood by the engine, the editor, and the OS file manager without any special conventions
