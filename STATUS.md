# Project Status

## Current State

This folder contains the new Python project built with `pygame-ce`.

Run it with:

- `Run_Python_Puzzle.cmd`

## Implemented

- project scaffold with `pyproject.toml`
- runnable `pygame-ce` window and launcher
- JSON area loading
- camera and basic sprite/tile rendering
- generated test asset sheets for tiles and sprites
- layered tilemaps with separate walkability cell flags
- reusable entity templates with per-instance parameters
- pixel-art rendering mode with snapped camera/draw positions
- early in-app editor with document/playtest separation
- editor map window plus separate pygame browser window
- configurable bitmap-font system with JSON font definitions
- command runner foundation
- command-driven grid movement
- wall collision
- pushable block behavior
- held movement that starts the next step as soon as the previous move fully finishes
- facing-based interaction input
- interactable entity command chains
- first lever/gate example
- simple player sprite animation while moving
- UI/editor text rendered through the custom `pixelbet` bitmap font atlas
- persistent rotating error log in `logs/error.log`

## Current Test Room

The starter room currently includes:

- player
- one pushable block
- one lever
- one gate
- a wall tile with a painting overlay tile on top of it

Expected behavior:

- move with arrows or `WASD`
- interact with `Space`
- face the lever and press `Space` to open the gate
- the player uses a tiny 2-frame walk animation while moving
- the room uses layered tiles instead of a single character grid
- press `F1` to switch between play mode and editor mode

## Editor Controls

- `F1`: toggle editor/playtest
- `F2`: tile mode
- `F3`: walkability mode
- `F4`: entity mode
- `Tab`: cycle tile layers
- `Q` / `E`: cycle selected tile or entity template
- `Shift` + mouse wheel in tile mode: cycle tile layers
- Left click: paint / apply walk brush / place entity on the selected cell
- Right click: erase / apply inverse walk brush / remove entity from the selected cell
- Drag with left/right mouse in tile or walk mode: paint continuously
- Middle click + drag: pan the map directly
- Use the separate pygame browser window to switch tool, select layers, pick tiles/entities visually, and manage the selected-cell stack
- In entity mode, the first click selects a cell and shows its entity stack; the next click acts on that cell
- Click a stacked entity row in the browser window to select it, then use `Up`, `Down`, or `Delete`
- `Delete`: remove the selected stacked entity
- `Ctrl+S`: save
- `R`: reload room from disk
- Arrow keys or `WASD` in editor: pan camera

## Editor UX Notes

- The map window is now focused on the map itself, while a separate pygame browser window handles layers, visual palettes, and selected-cell/entity management.
- Tile selection in the browser window is now thumbnail-based rather than label-based.
- Editor middle-mouse dragging now pans a free editor camera, so panning is visible even when the room is smaller than the viewport.
- Visual tile layers remain separate from walkability flags, and entities stay independent from both.
- The editor no longer assumes only `ground / structure / overlay`; layers are a general ordered list and can now be added, renamed, or removed.
- Stacked entities are shown in the browser window, with persistent `stack_order` so their order can be saved, reloaded, and rearranged.
- Cells with multiple visible entities still show count badges on the map.
- Hovering a tile previews the currently selected tile or entity before you click.
- If you click without a visible change, the status line explains why, for example when a cell already has the selected tile.

## Important Notes

- Movement is command-driven. Input requests commands rather than mutating position directly.
- Interaction is now also command-driven. The player triggers a top-level interact command, which resolves a target and runs that target's command chain.
- Levels now define tiles through tile-definition data rather than hardcoded wall logic.
- Visual tile layers and walkability are now separate concepts.
- Reusable object definitions live in `puzzle_dungeon/data/entities/`.
- Fonts now live in `puzzle_dungeon/data/fonts/` as named JSON definitions plus atlas PNGs.
- The current UI font is `pixelbet`, which auto-measures per-glyph widths from the atlas so narrow letters do not consume the same width as wide ones.
- Future systems like dialogue can choose fonts by `font_id` through the shared text renderer instead of using hardcoded font objects.
- The current assets are intentionally simple generated test art, not final art.
- Pixel-perfect behavior is currently handled as a renderer/camera policy, not a level-data rule.
- The editor keeps an authoritative document state and launches playtest as a fresh clone, so play interactions do not corrupt what you are editing.
- Runtime interaction now resolves the topmost enabled entity on a tile based on the current stack order, not just insertion order.
- Uncaught runtime errors, thread exceptions, and Tk/browser-window callback failures are logged to `logs/error.log`.
- Entity parameter editing is still minimal. Template placement works, but rich per-instance parameter editing will need a follow-up pass.

## Suggested Next Steps

- add dialogue UI and dialogue commands
- add variables and requirement checks
- add inventory and usable-item commands
- improve the editor with parameter editing, room creation, and tile thumbnails inside the separate browser window
