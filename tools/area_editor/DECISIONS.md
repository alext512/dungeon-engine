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

### The new editor is documentation-only for now

Decision:

- create folders and docs now, but do not start implementation yet

Why:

- the user wants the boundary and planning in place first

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
