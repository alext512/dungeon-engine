# Editor Entity Workflow UX Plan

This is a planning document for improving entity-focused editor workflows.
It describes intended UX direction and implementation slices, not current
behavior. Do not treat this file as the canonical editor manual until pieces
are implemented and documented in the active editor docs.

This document merges the original editor-entity UX discussion with the useful
critique from `plans/editor_entity_workflow_ux_plan_v2.md`. The v2 file should
be treated as review material, while this file is the active planning target.

## Purpose

The external editor already supports area editing, entity placement, structured
entity-instance editing, template editing, render-property editing, and guarded
JSON fallback workflows. The next quality pass should make entity work feel more
like direct object editing and less like a permanent JSON/document inspector.

The goals are:

- save screen space by moving entity-instance editing out of always-visible dock
  space
- make entity actions discoverable through explicit tools and context menus
- make overlapping entities easy to inspect, select, edit, and delete
- prepare entity-reference parameter picking without changing the authored JSON
  contract
- keep raw JSON available as an escape hatch, but make it less central for
  routine entity work
- keep destructive actions centralized so future undo/redo remains practical

## Planning Status

This is not a promise that every phase will be implemented exactly as written.
The implementation should be allowed to split or reorder steps if the codebase
shows a safer path.

The intended implementation style is incremental:

- ship visible UX value in small, testable slices
- avoid mandatory large refactors before the first useful workflow improvement
- extract helper widgets/modules when new behavior would otherwise make
  `main_window.py` worse
- keep the runtime/editor authored JSON contract unchanged unless explicitly
  discussed elsewhere

## Current Friction

- The entity-instance editor currently occupies persistent dock space even when
  the user is mostly selecting, dragging, painting, or navigating.
- Right click currently performs delete-style behavior in some modes, which is
  useful after discovery but not obvious. It also blocks right click from
  becoming a consistent context-menu gesture.
- Multiple entities can occupy the same world cell. The count badge tells the
  user there is overlap, but not which entity they are about to select or
  delete.
- Screen-space entities can overlap too, but their overlap is based on pixel
  hit areas or sprite/marker bounds rather than a shared grid cell.
- Entity parameters that reference other entities are still too close to
  free-text editing, even though typed `parameter_specs` now give the editor
  enough information to offer safer pickers.
- The toolbar/mode surface is growing. Tiles, entities, and flags all need
  select/pencil/erase-style actions, so the UI needs a model that can scale.
- Easier deletion increases the impact of the editor's current lack of undo.

## Agreed UX Decisions

- Entity Select mode is the main object manipulation mode.
- Left click should perform the active tool's primary action.
- Right click should answer "what can I do here?" through context menus.
- Double click in entity select mode should open the focused entity-instance
  editor.
- Selecting an entity should stay cheap. A normal selection should not always
  open a large editor.
- Entity editing should move to an on-demand pinned/modeless dialog.
- The dialog should not automatically follow selection changes.
- Dirty entity edits need explicit Apply / Discard / Cancel behavior.
- The old persistent dock should not remain the normal face of entity editing,
  but it may be kept temporarily as a fallback while the dialog proves itself.
- Right-click delete should be replaced by explicit eraser behavior.
- The first stacked-entity picker should be action-triggered, not hover-first.
  Hover can be reconsidered later as an optional hint.
- Stacked picking should be generalized as "entities under pointer", with
  different hit logic for world and screen entities.
- Entity list rows should integrate with the same select/edit/context workflows.
- Template render defaults should be respected consistently during placement.
- A Help / Shortcuts surface should make mouse and keyboard gestures visible.
- Undo/redo should not block this UX work, but mutation paths should stay
  centralized so undo can be added later.

## Non-Goals

These are intentionally outside the first implementation pass:

- gameplay simulation inside the editor
- multi-entity selection
- entity group authoring
- stack drag-reordering
- configurable shortcuts
- a full visual entity-reference picker before the list picker exists
- rewriting entity/template structured editors from scratch
- changing the stored entity-reference parameter shape from a string id to a
  compound area/entity object

## Entity Select Mode

Entity Select mode should become the object-level editing mode.

Expected behavior:

- left click selects an entity
- dragging a selected world entity moves it by tile cell
- dragging a selected screen entity moves it by pixel offset
- double click opens `Edit Instance...`
- right click opens an entity context menu
- right click over overlapping entities asks which entity is the target
- pressing a context-menu key or Shift+F10 should eventually open the selected
  entity's context menu

The editor should avoid opening forms during ordinary selection. The user can
select, drag, and inspect quickly, then deliberately open editing when needed.

## Pinned Modeless Entity Dialog

The existing entity-instance editor should be reused inside a floating dialog.
The editor already has structured fields, typed parameter handling, raw JSON,
validation, and preservation behavior. The plan is to move that surface, not
rebuild it.

Definitions:

- modeless: the dialog does not freeze the rest of the editor
- pinned: the dialog keeps editing one area/entity target until explicitly
  retargeted or closed

Target identity:

- the dialog should track both area/document id and entity id
- selection changes in the canvas do not retarget the dialog
- explicit edit requests can retarget the dialog after dirty-state handling

Opening paths:

- double click an entity in Entity Select mode
- choose `Edit Instance...` from the entity context menu
- double click an entity row in the Area Entity List
- later: keyboard action such as F2 or Enter on the selected entity

Dialog content:

- default to the structured `Entity Instance Editor`
- keep raw `Entity Instance JSON` as an advanced tab
- show the target area id and entity id clearly
- use Apply / Revert or Apply / Cancel semantics consistent with the current
  editor panel
- pass through the existing reference picker callbacks

One-dialog rule:

- first implementation should allow one entity edit dialog at a time
- multiple dialogs can be reconsidered later, but they create duplicate-edit and
  rename/delete edge cases that are not worth solving yet

Persistent dock transition:

- preferred first stable state: entity editing happens on demand in the dialog
- the old dock can remain accessible through a View menu during transition
- once the dialog workflow is proven, the dock can be removed or reduced to a
  debug/advanced fallback

## Dirty-State Rules

"Dirty" means the dialog has unapplied edits.

Selection changes:

- selecting another entity on the canvas does not retarget the dialog
- the dialog stays pinned to its current area/entity target

Explicit retarget:

- if the dialog is clean, double-clicking or choosing `Edit Instance...` on
  another entity retargets the dialog
- if the dialog is dirty, prompt with Apply / Discard / Cancel
- Apply saves the old target, then retargets
- Discard throws away old edits, then retargets
- Cancel keeps editing the old target

Closing:

- if clean, close immediately
- if dirty, prompt with Apply / Discard / Cancel

Deleting the entity being edited:

- if clean, close the dialog after delete
- if dirty, prompt with Discard and Delete / Cancel
- do not offer Apply and Delete in the first pass because saving immediately
  before deletion is confusing

Renaming the entity being edited:

- if clean, update the dialog title/target id after rename
- if dirty, require Apply / Discard / Cancel before rename, or block rename
  until edits are resolved

Document/tab changes:

- applying should update the pinned document, not whichever area tab happens to
  be active, if practical
- if the pinned document is closed while the dialog is dirty, prompt first
- if the pinned entity no longer exists, show a clear message and close or
  disable the dialog after dirty-state handling

## Entity Context Menu

Right click should become the consistent way to discover entity actions.

First menu items:

- `Edit Instance...`
- `Edit JSON...`
- `Rename...`
- `Duplicate`
- `Delete`
- `Copy ID`

Possible later items:

- `Open Template`
- `Find References`
- `Select Group`
- `Bring Forward In Stack`
- `Send Backward In Stack`

Context targeting:

- exactly one entity under pointer: menu targets that entity
- multiple entities under pointer: show a chooser/submenu first
- empty space: no menu in the first pass, but canvas-level actions can come
  later

Mode rule:

- right click should eventually work as a context menu in select, pencil, and
  eraser modes
- first implementation may limit this to Entity Select mode if needed, but the
  end direction is not right-click no-op

## Entity Pencil And Entity Eraser

Right-click-delete should be replaced with explicit tool behavior.

Short-term entity tool model:

- Entity Select: left click selects, drag moves, double click edits, right click
  opens context menu
- Entity Pencil: left click places the selected template
- Entity Eraser: left click deletes an entity instance
- Shift may temporarily switch pencil to eraser behavior if it feels clear and
  does not interfere with selection/dragging

This can be implemented before the full target/tool toolbar exists.

The entity eraser should use the same deletion operation as context-menu delete
and list-based delete. Do not create separate mutation paths per UI gesture.

## Longer-Term Target/Tool Toolbar

A scalable final direction is a composed target/tool model:

```text
Target: Tiles | Entities | Flags
Tool:   Select | Pencil | Eraser
```

Possible meanings:

- `Tiles + Select`: rectangular tile selection/copy/delete/paste
- `Tiles + Pencil`: paint the selected tile or multi-tile stamp
- `Tiles + Eraser`: paint empty tile gid `0`
- `Entities + Select`: select, move, double-click edit, context menu
- `Entities + Pencil`: place the selected entity template
- `Entities + Eraser`: delete an entity instance
- `Flags + Select`: inspect a cell flag and potentially open a future modify
  menu
- `Flags + Pencil`: apply the selected cell-flag brush
- `Flags + Eraser`: clear/default the cell flag

This is a larger interaction-model change and should not be forced into the
first entity pass unless the current toolbar becomes harder to maintain than the
new model.

## Entities Under Pointer

The stacked picker should be based on a shared concept: "entities under this
pointer position."

World-space behavior:

- determine the world tile under the pointer
- gather entities that occupy that cell
- order them by the editor/runtime stable ordering for same-cell entities:
  `render_order`, then `stack_order`, then `entity_id`

Screen-space behavior:

- determine which screen-space entity hit areas contain the pointer
- if a sprite is available, prefer its rendered bounds
- if no sprite is available, use the editor marker box
- support multiple overlapping screen-space entities
- label screen entities clearly in picker rows

Mixed behavior:

- if both world and screen entities are under the pointer, include both if the
  active operation can target both
- rows should show enough context to avoid mistakes: icon/preview, entity id,
  template id, space, and position

The first implementation can use the existing hit-test helpers, then improve
screen hitboxes as needed.

## Stacked Entity Picker

The count badge should be paired with a picker for ambiguous targets.

Primary triggers:

- right click over multiple entities: show a target chooser/context submenu
- left click in Entity Select mode over multiple entities: after mouse release,
  if no drag happened, show the picker instead of guessing
- left click in Entity Eraser mode over multiple entities: show the picker so
  deletion is deliberate
- visual entity-reference picker click over multiple entities: reuse the same
  chooser logic

Possible later trigger:

- delayed hover preview, once the click/right-click picker is stable

Expected picker behavior:

- show only when more than one relevant entity is under the pointer
- do not appear while dragging
- close on outside click, Escape, or successful selection
- list icon/preview, entity id, template id, space, and position
- use deterministic order
- clicking a row performs the active action for that exact entity

Click-cycling:

- existing click-cycling can remain if it does not conflict
- if cycling and picker behavior become confusing together, the explicit picker
  should win

## Stack Reordering

Drag-reordering stacked entities is a good future UX idea, but it should not be
part of the first stacked-picker pass.

Reason:

- current effective order is not one authored list
- order comes from `render_order`, y-sort position where relevant,
  `stack_order`, and `entity_id`
- drag-reordering across different render bands could silently change broader
  rendering behavior

Possible future shape:

- show stacked entities grouped by `render_order`
- allow drag-reorder only within one compatible group
- update `stack_order` values for reordered entities
- keep changing `render_order` as an explicit advanced action

## Template Render Defaults During Placement

Templates can author render defaults:

- `render_order`
- `y_sort`
- `sort_y_offset`
- `stack_order`

The runtime deep-merges entity instances over templates, so instances inherit
template values unless they override them.

Current editor placement already reads template `render_order`, but still
hardcodes some other render fields during placement. That can make the editor's
live state differ from the template/runtime behavior immediately after placing
an entity.

Planned rule:

- when placing from a template, initialize the editor's live entity instance
  from the template's effective render defaults
- do not add a per-brush render-options UI in the first pass
- keep individual instance override editing available through render properties
  and the entity-instance editor
- avoid writing unnecessary render fields to JSON if the serializer can safely
  omit values that match defaults or template inheritance

Potential implementation:

- add template-catalog helpers for `y_sort`, `sort_y_offset`, and `stack_order`
  alongside the existing `render_order` helper
- use those helpers in world and screen placement paths
- add tests proving template render defaults affect newly placed entities

## Entity Parameter Pickers

Typed `parameter_specs` should drive reference pickers. For entity references,
the stored parameter value should remain the entity id string.

Important rule:

- area selection in the picker is browsing context only
- do not store an area id alongside the entity id unless the runtime contract
  later truly requires it

Example authored result:

```json
{
  "parameters": {
    "destination_entity_id": "spawn_marker"
  },
  "parameter_specs": {
    "destination_entity_id": {
      "type": "entity_id",
      "scope": "area"
    }
  }
}
```

Confirming a picker choice writes only:

```json
"destination_entity_id": "spawn_marker"
```

### List Picker First

The first picker should be list-based.

Behavior:

- parameter row has a `Pick...` button for `type: "entity_id"`
- dialog defaults to current area when useful
- area dropdown/list lets the user browse another area
- entity list shows id, template id, scope/space, and position
- search/filter helps in larger projects
- broken/missing current values are highlighted but preserved until changed
- global entities appear in a separate `Global` group when the parameter scope
  allows them
- `scope` and `space` constraints filter invalid choices where present

This delivers immediate value without waiting for visual area preview work.

### Visual Picker Later

The stronger later picker can be visual and spatial.

Behavior:

- open from the same `Pick...` button
- choose area from a side list or dropdown, defaulting to current area
- render a read-only preview of the selected area
- mouse wheel zooms
- middle mouse pans
- hover shows entity hints
- click selects an entity
- clicking overlapping entities opens the stacked picker
- confirm writes the selected entity id

Non-goals:

- no painting
- no moving entities
- no entity field editing
- no gameplay simulation
- no hijacking the central editor tab

Implementation choice:

- choose the most convenient implementation when this phase starts
- avoid embedding the full editing `TileCanvas` unless that proves simpler and
  safe
- prefer a lightweight read-only preview that shares rendering helpers where
  practical so the preview does not visually drift from the main canvas

Screen entities:

- list picker should include screen entities with clear `screen` labels
- visual picker should either show a screen-space preview region or offer
  `World`, `Screen`, and `All` filters
- parameter specs with `space` should prevent invalid choices

## Help And Shortcuts

The editor should expose its gestures directly.

First version:

- add a Help / Shortcuts menu item or toolbar `?` action
- open a simple dialog listing current mouse and keyboard controls
- include mode-specific sections for Entity Select, Entity Pencil, Entity
  Eraser, Tiles, Flags, and Canvas navigation

Likely entries:

- left click: active tool action
- right click: context menu where supported
- double click in Entity Select: edit instance
- drag selected entity: move
- mouse wheel: zoom
- middle mouse drag: pan
- Escape: close popup/cancel temporary interaction
- F2 or Enter: edit selected entity, once implemented
- Shift+F10 or context-menu key: open selected entity context menu, once
  implemented

Later:

- configurable shortcuts can be considered after the default shortcut surface is
  stable

## Undo/Redo Readiness

Undo/redo is desirable, especially once deletion is easier and more visible, but
it is not a prerequisite for this UX pass.

Immediate guardrail:

- centralize mutations
- keep delete/duplicate/place/update flows going through shared operations
- avoid one-off mutation code in each UI path

Future undo shape:

- place entity: undo removes created entity
- delete entity: undo restores captured entity JSON
- move entity: undo restores old grid/pixel position
- edit entity: undo restores previous serialized entity object

This plan should not implement undo, but it should avoid making undo harder.

## Main Window Complexity

`main_window.py` is already large. The plan should not force a pure refactor
before useful UX lands, but new work should avoid making the file materially
worse.

Extraction guidance:

- new reusable dialogs/widgets should live under `tools/area_editor/area_editor/widgets/`
- shared entity operations should live under `tools/area_editor/area_editor/operations/`
- if entity workflow wiring grows substantially, extract an entity workflow
  mixin or helper module rather than continuing to grow `main_window.py`
- refactor only around the slice being implemented, and keep behavior changes
  separately testable where possible

## Implementation Phases

The phases below are a recommended order. They may be split differently during
implementation if that reduces risk.

### Phase 1: Entity Edit Dialog

Goal:

- move routine entity editing out of permanent dock space

Deliverables:

- create an entity-instance edit dialog around the existing editor panel
- make it pinned/modeless with one-dialog behavior
- default to structured editor tab
- retain raw JSON tab
- implement dirty-state Apply / Discard / Cancel behavior
- open from double click in Entity Select mode
- open from Area Entity List double click
- keep or hide the old dock as a transitional fallback

Test focus:

- double-click opens the dialog for the exact entity
- entity list double-click opens the same dialog
- changing canvas selection does not retarget a dirty dialog
- explicit retarget prompts when dirty
- Apply updates the area document and marks dirty
- raw JSON tab still preserves unknown fields

### Phase 2: Entity Context Menu

Goal:

- make right click the discoverable entity action surface

Deliverables:

- add context-menu signals from the canvas or route context events cleanly
- right click a single entity opens its menu
- right click overlapping entities asks for the target first
- first menu items: edit instance, edit JSON, rename, duplicate, delete, copy id
- context menu can also be used from the Area Entity List

Test focus:

- right-click on entity targets the correct id
- stacked right-click exposes all possible targets
- Edit Instance opens the dialog
- Delete uses the centralized delete path
- Copy ID writes to clipboard

### Phase 3: Explicit Entity Pencil/Eraser

Goal:

- replace invisible right-click delete with visible tools

Deliverables:

- add entity pencil and entity eraser tool states
- left click places in pencil mode
- left click deletes in eraser mode
- right click no longer deletes
- right click remains available for context menus where supported
- optionally support Shift as temporary eraser
- placement respects template render defaults consistently

Test focus:

- entity pencil places world and screen templates correctly
- entity eraser deletes with left click
- right click does not delete
- template `render_order`, `y_sort`, `sort_y_offset`, and `stack_order` are
  respected during placement
- destructive flows use the same delete operation

### Phase 4: Stacked Entity Picker

Goal:

- make ambiguous entity targets explicit

Deliverables:

- add shared stacked-entity picker widget
- support world same-cell overlap
- support screen entity hit overlap where practical
- integrate with select, eraser, and context menu targeting
- keep click-cycling only if it remains understandable

Test focus:

- picker appears for multiple entities under pointer
- picker does not appear for a single entity
- picking a row selects/deletes/targets the exact entity
- screen overlaps are handled or intentionally covered by fallback behavior
- picker order is deterministic

### Phase 5: List-Based Entity Parameter Picker

Goal:

- make entity-id parameters browsable without visual preview complexity

Deliverables:

- add `Pick...` button for `entity_id` parameter specs
- area list defaults to current area
- entity list supports search/filter
- global entities show in a separate group where valid
- scope and space constraints filter choices
- picker writes only the entity id string

Test focus:

- picker appears only for appropriate parameter specs
- current area is the default browsing area
- choosing an entity writes only the id
- broken current values are preserved until changed
- scope/space constraints are honored

### Phase 6: Help / Shortcuts Dialog

Goal:

- make gestures discoverable as the interaction model grows

Deliverables:

- add Help / Shortcuts action
- list current canvas, entity, tile, flag, and dialog shortcuts
- keep it static/read-only in the first pass

Test focus:

- menu action opens the dialog
- dialog content includes the active implemented gestures

### Phase 7: Visual Entity Reference Picker

Goal:

- make entity-reference selection spatial and intuitive

Deliverables:

- read-only area preview
- zoom and pan
- hover hints
- click-to-select entity
- stacked picker integration
- screen entity support or clear filtering

Test focus:

- visual picker opens the default/selected area
- clicking an entity selects the expected id
- overlapping entities use the picker
- screen entities are selectable or filtered by parameter constraints

### Phase 8: Composed Target/Tool Toolbar

Goal:

- unify tile/entity/flag editing under a cleaner model if the incremental tools
  prove the direction

Deliverables:

- replace scattered mode buttons with target/tool controls
- map all existing edit modes into the composed model
- keep shortcuts discoverable
- preserve per-area mode behavior where needed

Test focus:

- every existing mode remains accessible
- target/tool combinations are mutually consistent
- right click is consistently contextual where implemented
- existing tile and flag workflows do not regress

## Open Questions

- Should the old dock be hidden immediately after Phase 1, or kept visible until
  the dialog survives a few workflow passes?
- Should F2 or Enter be the primary keyboard edit shortcut, or should both work?
- How should context menus behave over empty canvas space?
- Should hover stacked previews come back after the explicit picker is stable?
- Should click-cycling remain long-term if the picker feels better?
- How should visual pickers represent global entities that have no area
  position?
- Should stack reordering eventually live in the stacked picker, a render-order
  panel, or both?

## Validation Expectations

For every implementation slice:

- run focused editor tests for changed widgets and main-window flows
- run the full editor suite from `tools/area_editor/`
- add regression coverage for preservation of unknown/engine-owned fields when
  editing through dialogs
- manually smoke-test pointer behavior and context menus when practical

Editor command:

```text
cd tools/area_editor
..\..\.venv\Scripts\python -m unittest discover -s tests -v
```

If project content, parameter specs, or runtime/editor contract surfaces change,
also run from the repository root:

```text
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python tools\validate_projects.py
```

