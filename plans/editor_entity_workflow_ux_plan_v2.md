# Editor Entity Workflow UX Plan v2

This is a reviewed and updated version of the original
`editor_entity_workflow_ux_plan.md`. It preserves the original plan's goals and
UX principles while adding concrete critique, risk analysis, suggestions, and
revised implementation phases based on a thorough codebase review.

This is a planning document. Do not treat it as describing current behavior.

---

## Review of the Original Plan

### Strengths

1. **Sound UX principles.** The plan correctly identifies that selection should
   be cheap, editing should be deliberate, and right-click should mean "what can
   I do here?" These align with standard direct-manipulation editor conventions.

2. **Preservation-first attitude.** The plan repeatedly emphasizes that the JSON
   contract must not change, that `_extra` fields must survive round-trips, and
   that UI browsing context must not leak into authored data. This matches the
   codebase's existing `EntityDocument._extra` round-trip pattern and the
   `_filtered_unmanaged_extra` handling in the structured fields editor.

3. **Incremental phasing.** Six phases form a reasonable progression from
   low-risk (dock-to-dialog) to high-risk (unified toolbar). Each phase has
   deliverables and test criteria.

4. **Reuse over rewrite.** Phase 1 explicitly says to reuse the existing
   `_EntityInstanceFieldsEditor` and `_EntityInstanceJsonEditor` classes
   (~1400 lines of field coverage) rather than rebuilding them.

5. **Correct identification of the composed target/tool model.** The plan
   recognizes the current four mutually-exclusive modes do not scale, and
   proposes the Target x Tool matrix as the endpoint while correctly deferring
   it to the final phase.

### Weaknesses

#### W1: Hover-triggered stacked entity picker is the weakest element

The plan proposes a 0.5-second hover delay to show a disambiguation popup.
Problems include:

- **Platform inconsistency.** Hover event timing depends on OS pointer event
  coalescing, high-DPI scaling, and remote-desktop environments. Qt's
  `QGraphicsView` receives hover events via `mouseMoveEvent` with
  `setMouseTracking(True)` (already enabled at `tile_canvas.py:139`), but the
  event rate varies.
- **Conflict with drag detection.** The canvas uses a ~5px drag threshold
  (`_ENTITY_DRAG_THRESHOLD_PIXELS`). A hover popup could appear mid-drag if the
  user pauses briefly before moving. The plan says "do not appear while
  dragging" but does not address the ambiguous zone between hover-delay-start
  and drag-threshold-crossed.
- **Testability.** Sub-second hover timing with synthetic mouse events in an
  offscreen QPA is unreliable. The existing test infrastructure uses
  `_make_mouse_event` helpers that do not simulate real timing.
- **User frustration.** A popup after 0.5s of hovering will flash repeatedly
  during normal area browsing. The "remain open while pointer moves into popup"
  pattern is widely considered fragile.

#### W2: No plan for main_window.py decomposition

`main_window.py` is already 4362 lines with 3 mixins. Phases 1-3 each add new
code paths (double-click handling, context menu construction, dialog lifecycle,
new tool states, picker popup management) with no stated extraction target. The
plan says "new dialog/widget file if that keeps `main_window.py` from growing
further" but treats it as optional.

#### W3: No undo/redo strategy despite expanding edit surfaces

Phases 1-3 add new editing pathways: dialog-based entity editing, pencil
placement, eraser deletion, drag-and-drop. Every new edit surface without undo
increases the cost of mistakes and makes undo harder to retrofit. The plan does
not even acknowledge undo as a risk.

#### W4: Dialog modality under-specified

The plan says "modal or pinned enough that typing is stable" but does not define
what happens when:
- The dialog is open and the user clicks a different entity on the canvas.
- The user closes the dialog with unsaved changes.
- Multiple dialogs are opened simultaneously.

Currently `_prepare_for_entity_instance_target_change` shows a Save/Discard/
Cancel prompt when selection changes with a dirty dock panel. Moving to a dialog
requires re-thinking this interlock.

#### W5: Phase 6 (Composed Toolbar) is under-specified

The Target x Tool matrix is presented but the implementation path is conditional
("if the prototype proves clearer"). Meanwhile phases 2-5 build one interaction
model that Phase 6 then potentially tears down.

#### W6: Keyboard workflows not addressed

The plan focuses on mouse interactions. It does not specify whether Enter or a
shortcut opens the edit dialog, how Tab/Escape interact with the dialog, or
whether keyboard users can trigger the stacked entity picker.

#### W7: Screen-space entity disambiguation missing from stacked picker

The stacked picker is described for world-space cells, but screen-space entities
can also overlap at the same pixel position. `_screen_entities_at_scene_pos`
already returns multiple matches. The plan mentions screen entities in the visual
picker section but not in the stacked picker section.

#### W8: Entity list panel integration under-specified

The `AreaEntityListPanel` (right dock, 164 lines) already provides list-based
entity selection. The plan mentions "optionally open from an entity list entry"
but does not detail signal flow integration or whether double-click in that list
opens the dialog.

#### W9: Template defaults during pencil placement

The entity pencil (Phase 2) places via `place_entity` which uses hardcoded
`render_order=10, y_sort=True`. The plan does not specify whether placement
should inherit render properties from the template or the last-placed entity.

#### W10: Global entities in pickers left unresolved

Listed as an open question without even a tentative answer, despite
`_browse_project_entity_id` already returning all known entity IDs.

---

## Revised Implementation Phases

### Phase 0: Main Window Entity Mixin Extraction

**Goal:** Reduce `main_window.py` complexity before adding new features.

**Rationale:** The entity-related methods in `main_window.py` form a cohesive
cluster of roughly 600 lines: entity selection handling (~lines 2717-2912),
entity paint/delete (~lines 2772-2884), entity drag (~lines 3038-3067), entity
instance apply/revert (~lines 3069-3148), entity instance update (~lines
4181-4264), and entity brush logic (~lines 4321-4362). Extracting these into a
mixin follows the established pattern of `MainWindowProjectContentMixin` and
`MainWindowProjectRefactorMixin`.

**Deliverables:**

- extract entity editing methods into `main_window_entity_editing.py` as a
  mixin
- ensure all existing tests pass without changes
- no behavior changes

**Files:**

- `tools/area_editor/area_editor/app/main_window.py`
- new `tools/area_editor/area_editor/app/main_window_entity_editing.py`

**Test focus:**

- full existing test suite passes
- no new tests needed (pure refactor)

---

### Phase 1a: Entity Instance Edit Dialog

**Goal:** Move entity editing from persistent dock to an on-demand dialog.

**Deliverables:**

- create `tools/area_editor/area_editor/widgets/entity_instance_dialog.py`
  wrapping the existing `_EntityInstanceFieldsEditor` and
  `_EntityInstanceJsonEditor` widgets in a `QDialog`
- dialog opens from double-click in Entity Select mode (not other modes)
- dialog opens from the entity list panel's double-click
- dialog is modeless but application-owned (`Qt.WindowType.Dialog`)
- dialog operates in **pinned mode**: once opened, it stays on that entity even
  if canvas selection changes; an explicit "Follow Selection" toggle can be added
  later if wanted
- Apply/Cancel buttons; closing with unsaved changes shows a discard prompt
- preserve the existing reference picker callbacks by passing them through to the
  inner editors
- old dock panel hidden by default; restorable via View menu as transitional
  fallback

**Modality decision:** Pinned modeless, because live-following risks data loss
when the user is mid-edit and accidentally clicks another entity on the canvas.

**Keyboard access:** `Enter` or `F2` on a selected entity opens the dialog.
`Escape` inside the dialog either closes it (if clean) or focuses the first
dirty field.

**Files:**

- new `tools/area_editor/area_editor/widgets/entity_instance_dialog.py`
- `tools/area_editor/area_editor/app/main_window.py` (or entity mixin)
- `tools/area_editor/area_editor/widgets/tile_canvas.py` (double-click signal)
- `tools/area_editor/area_editor/widgets/area_entity_list_panel.py` (double-click)

**Test focus:**

- double-click opens dialog for selected entity
- Apply writes changes to area document and marks dirty
- Cancel/close-with-dirty shows discard prompt
- raw JSON escape hatch preserves unknown fields
- old dock still works when re-enabled via View menu

---

### Phase 1b: Entity Context Menu

**Goal:** Make right-click the consistent way to discover entity actions.

**Deliverables:**

- right-click on an entity in Entity Select mode opens a context menu
- right-click on a stacked cell (multiple entities) shows a submenu with one
  entry per entity, each opening the entity's context menu (this is the
  lightweight stacked-entity disambiguation approach)
- menu items for the first pass: `Edit Instance...`, `Edit JSON...`,
  `Duplicate`, `Delete`, `Copy ID`
- context menu construction lives in the main window (or entity mixin); the
  canvas emits `entity_context_menu_requested(entity_id, QPoint)` signal
- for stacked cells, canvas emits
  `stacked_entity_context_menu_requested(entity_ids, QPoint)` and the main
  window builds the submenu

**Context targeting rules:**

- exactly one entity at pointer: menu targets that entity
- multiple entities at pointer: submenu lists entities (icon + id + template);
  hovering or clicking an entry shows that entity's context menu
- empty space: no menu in the first pass

**Keyboard access:** the context menu key (or Shift+F10) on a selected entity
opens its context menu.

**Files:**

- `tools/area_editor/area_editor/widgets/tile_canvas.py` (new signals)
- `tools/area_editor/area_editor/app/main_window.py` (or entity mixin)

**Test focus:**

- right-click on entity opens context menu
- right-click on stacked cell shows disambiguation submenu
- `Edit Instance...` opens the dialog from Phase 1a
- `Delete` removes the entity and clears selection if needed
- `Copy ID` places entity id in clipboard

---

### Phase 2: Entity Pencil/Eraser and Right-Click Cleanup

**Goal:** Make entity placement and deletion explicit; free right-click for
context menus.

**Deliverables:**

- add explicit entity pencil and entity eraser tool states
- in entity pencil mode: left-click places the selected template
- in entity eraser mode: left-click deletes the topmost entity at cell
- right-click no longer deletes entities in any mode
- right-click opens context menu when Entity Select mode is active (Phase 1b)
- right-click is a no-op in entity pencil/eraser modes (or opens canvas-level
  context menu later)
- optional: `Shift` modifier temporarily switches pencil to eraser behavior

**Template defaults:** When placing via pencil, the new entity should inherit
`render_order`, `y_sort`, `sort_y_offset`, and `stack_order` from the template
if the template specifies them. If the template does not, use the current
defaults (`render_order=10, y_sort=True`). This matches the runtime's template
merge behavior.

**Undo note:** Pencil placement and eraser deletion are destructive and not
undoable. This is the same as the current paint-mode behavior -- no regression,
but acknowledge the gap.

**Files:**

- `tools/area_editor/area_editor/widgets/tile_canvas.py`
- `tools/area_editor/area_editor/app/main_window.py` (or entity mixin)
- `tools/area_editor/area_editor/operations/entities.py`

**Test focus:**

- entity pencil places a template with left-click
- entity eraser deletes with left-click
- right-click does not delete entities
- template render defaults are inherited during placement
- screen-space pencil still works in screen pane

---

### Phase 3: List-Based Entity Parameter Picker

**Goal:** Make entity-id parameters browsable without free-text editing.

**Rationale:** Moved before the stacked picker because it is lower risk, builds
on existing infrastructure (`_browse_known_reference` at `main_window.py:3708`),
and delivers immediate user value for the most common entity-reference editing
task.

**Deliverables:**

- add `Pick...` button for parameter specs with `type: "entity_id"`
- picker dialog shows: area list (defaulting to current area), entity list for
  selected area, search/filter
- entity list shows: id, template id, scope, position
- respect `scope` constraint (area vs global) and `space` constraint (world vs
  screen) from parameter_specs when present
- confirm writes only the entity id string to the parameter value
- broken/missing current values are highlighted but preserved until changed
- global entities appear in a separate "Global" section or a dedicated area-like
  entry in the area list

**Files:**

- `tools/area_editor/area_editor/widgets/entity_instance_json_panel.py` (or
  extracted parameter picker module)
- `tools/area_editor/area_editor/app/main_window.py` (or entity mixin)
- `tools/area_editor/area_editor/project_io/project_manifest.py` (entity
  discovery across areas)

**Test focus:**

- picker appears for entity-id parameter specs
- picker writes only the entity id string
- current area is the default browsing area
- scope filtering excludes inappropriate entities
- global entities appear when scope allows

---

### Phase 4: Stacked Entity Picker

**Goal:** Make overlapping entities easy to target deliberately.

**Key design change from original plan:** Replace the 0.5-second hover trigger
with a click-triggered approach. The hover popup is deferred as an optional
later enhancement.

**Trigger mechanism:**

- **Click on a stacked cell** (count badge visible) in Entity Select mode: if
  the cell has multiple entities, show the picker popup immediately instead of
  selecting the topmost entity. Single-entity cells behave as before.
- **Right-click on a stacked cell**: the context menu (Phase 1b) already shows
  a submenu; this phase enhances it with a richer picker widget if needed.
- **Ctrl+click** on any stacked cell: force-opens the picker even if a single
  entity would normally be selected.

**Alternative consideration:** Click-cycling (the current behavior) is already
functional and tested. The stacked picker is additive, not a replacement.
Click-cycling should be preserved as a secondary mechanism. If the user clicks
the same stacked cell again while the picker is visible, the picker closes and
falls back to cycling.

**Deliverables:**

- small popup widget (not a full dialog) listing entities at the clicked cell
- shows: icon/preview, entity id, template id, position
- order: `render_order` then `stack_order` then `entity_id` (stable, matching
  canvas z-order)
- clicking a row selects that exact entity
- Escape or outside-click closes the popup
- integration with entity eraser: clicking a row in eraser mode deletes that
  entity
- screen-space support: the same picker works for overlapping screen-space
  entities

**Popup architecture:** Use a `QFrame` with `Qt.WindowType.Popup` flag rather
than a `QMenu`. This provides proper focus handling (popups close on outside
click), avoids the hover-menu fragility, and allows custom item rendering.

**Files:**

- new `tools/area_editor/area_editor/widgets/stacked_entity_picker.py`
- `tools/area_editor/area_editor/widgets/tile_canvas.py`
- `tools/area_editor/area_editor/app/main_window.py` (or entity mixin)

**Test focus:**

- picker appears on click for stacked cells (count > 1)
- picker does not appear for single-entity cells
- clicking a picker row selects the correct entity
- Escape closes the picker
- eraser mode + picker row deletes the correct entity
- order is deterministic

---

### Phase 5: Visual Entity Reference Picker

**Goal:** Make selecting entity references feel spatial and intuitive.

**Implementation approach:** Build a lightweight `AreaThumbnailRenderer` that
renders an area to a `QPixmap` at a fixed scale, without interactive editing
infrastructure. Use this pixmap as the background of a simple `QGraphicsView`
in the picker dialog, with clickable overlay rectangles for entities. This
avoids the complexity of adapting `TileCanvas` for read-only use and avoids
duplicating its 40+ instance variables of editing state.

**Deliverables:**

- read-only area preview in the picker dialog
- zoom with mouse wheel, pan with middle mouse
- hover shows entity hints (id, template, position)
- click to select entity
- stacked-entity picker integration (reuse Phase 4 popup)
- area selection dropdown (defaults to current area)
- support or clearly filter screen-space entities based on parameter scope

**Non-goals (carried from original plan):**

- no painting, no entity editing, no simulation, no central editor tab hijack

**Files:**

- new `tools/area_editor/area_editor/widgets/area_thumbnail_renderer.py`
- new `tools/area_editor/area_editor/widgets/visual_entity_picker.py`
- `tools/area_editor/area_editor/widgets/entity_instance_json_panel.py`

**Test focus:**

- visual picker opens with selected/default area
- clicking an entity selects the expected id
- stacked tile uses the picker from Phase 4
- screen entities are selectable or filtered by scope
- zoom and pan work correctly

---

### Phase 6: Composed Target/Tool Toolbar

**Goal:** Unify tiles, entities, and flags under a cleaner tool model.

This phase is intentionally left at a high level because it is a significant
interaction model change that should be designed in detail only after phases 1-5
are validated by actual use.

**Target/Tool matrix:**

```text
Target: Tiles | Entities | Flags
Tool:   Select | Pencil | Eraser
```

**Key constraint:** This phase must not break muscle memory without visible
replacement. Every existing edit mode must map to an accessible target/tool
combination.

**Risk:** This is effectively a refactor of the entire canvas interaction model.
It touches every mode toggle handler (4 methods in main_window.py), the
`_handle_edit_pointer_event` dispatch in tile_canvas.py, cursor management, and
status bar messaging. Plan for this as a focused effort, not a side project.

**Deliverables:**

- replace scattered mode buttons with target/tool controls
- map existing actions into the composed model
- keep keyboard shortcuts discoverable
- right-click consistently opens context menus where implemented

**Test focus:**

- every existing edit mode has an accessible target/tool combination
- mode switching remains mutually exclusive
- right-click consistently opens context menus

---

## Open Questions (With Recommended Answers)

**Q: Should the persistent entity-instance dock be removed immediately?**
A: No. Hide it by default, keep it accessible via View menu. Remove it entirely
only after the dialog has been validated by actual use across multiple sessions.

**Q: Should double-click edit only work in Entity Select mode?**
A: Yes. In other modes, double-click should be ignored for entities. Opening an
edit dialog unexpectedly while painting or erasing is confusing.

**Q: Should click-cycling remain?**
A: Yes. It is already working, tested, and costs nothing. The stacked picker is
additive. If cycling causes proven conflicts with picker behavior later, it can
be revisited.

**Q: How should global entities appear in pickers?**
A: In list pickers, show them in a separate "Global" group at the top. In the
visual picker, show them in a distinct section or omit them when the parameter
scope is `"area"`.

**Q: How much of stack reordering belongs in the picker?**
A: None in the first pass. Stack reordering should be a separate future
improvement after selecting/deleting stacked entities is reliable, as the
original plan correctly states.

**Q: Should multi-entity selection be supported?**
A: Not in these phases. Acknowledge as a future direction (rubber-band select
for bulk delete/move/edit). The current single-selection model is sufficient for
the planned workflows.

---

## Alternative Approaches Worth Considering

### Inspector Panel Instead of Dialog

Instead of converting the dock to a dialog, convert it to a collapsible
inspector panel that appears at the bottom of the right dock when an entity is
selected and collapses when nothing is selected. This avoids the "dialog
obscures canvas" problem and does not require modal/modeless decisions. The
downside is it still uses dock space, but only when relevant.

### Inline Canvas Editing

For the most common edits (rename, change a single parameter), a small inline
editor overlay on the canvas at the entity's position could be faster than any
dialog. Double-click shows a compact editor with ID and template, plus a "More..."
button for the full dialog. Higher implementation cost, but lower interaction
cost for quick tweaks.

### Keyboard-Enhanced Cycling

Instead of a popup, enhance existing click-cycling with keyboard shortcuts:
Tab cycles forward, Shift+Tab backward through stacked entities. Combined with
the existing status bar cycle indicator, this provides disambiguation without
any popup infrastructure.

### Lightweight Area Renderer for Phase 5

Build a small `AreaThumbnailRenderer` class that renders an area to a `QPixmap`
at a fixed scale. Use this as the background of a simple `QGraphicsView` in the
picker dialog, with clickable entity overlays. This avoids adapting `TileCanvas`
(40+ instance variables of editing state) for read-only use.

---

## Risk Register

| Phase | Risk Level | Key Risks |
|-------|-----------|-----------|
| 0 | Low | Pure refactor; risk is missing a method dependency |
| 1a | Medium | Dirty-state interlock must survive transition; reference picker callbacks access main-window state; dialog focus management |
| 1b | Low-Medium | Context menu is straightforward; stacked submenu needs entity ordering |
| 2 | Low | Adds tool states to understood mode system; main risk is right-click transition |
| 3 | Low | Builds on existing infrastructure; scoped to list-based UI |
| 4 | Medium | Popup focus handling; coexistence with drag detection and cycling |
| 5 | High | Requires rendering arbitrary areas in a dialog; tileset/entity load for other areas; custom renderer design |
| 6 | High | Refactors entire canvas interaction model; touches every mode handler |

## Undo/Redo Impact

| Phase | Destructive Operations | Undo Gap |
|-------|----------------------|----------|
| 0 | None | N/A |
| 1a | Dialog-based editing (same as current dock) | Same gap, no regression |
| 1b | Delete via context menu | Same as current delete, no regression |
| 2 | Pencil placement, eraser deletion | Same as current paint mode, no regression |
| 3 | Parameter value change (via picker) | Same as current editing, no regression |
| 4 | Delete via picker row (eraser mode) | New path, same underlying operation |
| 5 | Parameter value change (via visual picker) | Same as Phase 3 |
| 6 | No new destructive operations | N/A |

None of these phases make the undo gap worse than it already is. An undo/redo
system remains desirable as a separate project but is not a prerequisite for
this plan.

---

## Validation Expectations

For every implementation slice:

- run the focused editor tests for changed widgets and main-window flows
- run the full editor suite from `tools/area_editor/`
- add regression coverage for preservation of unknown/engine-owned fields when
  editing through dialogs
- manually smoke-test the workflow in a sample project when the change affects
  pointer behavior or context menus

Commands:

```text
cd tools/area_editor
..\..\. venv\Scripts\python -m unittest discover -s tests -v
```

If project content or parameter specs change:

```text
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python tools\validate_projects.py
```

---

## Summary of Changes From Original Plan

| Original | This Version | Rationale |
|----------|-------------|-----------|
| No decomposition step | Added Phase 0 (mixin extraction) | main_window.py is too large for safe feature work |
| Single Phase 1 | Split into 1a (dialog) and 1b (context menu) | Separable risk profiles; dialog is testable alone |
| Phase 3: Hover-triggered picker | Phase 4: Click-triggered picker | Hover is fragile, platform-dependent, hard to test |
| Phase 4: List picker | Phase 3: List picker (moved earlier) | Lower risk, immediate value, no dependencies on picker |
| Hover delay 0.5s | Removed as primary trigger | Click is more reliable, testable, and accessible |
| Dialog modality unspecified | Pinned modeless with explicit rationale | Prevents data loss from accidental selection changes |
| Keyboard access unspecified | Enter/F2/Escape/context-menu-key defined | Completeness for non-mouse workflows |
| Open questions unresolved | Recommended answers provided | Reduces ambiguity before implementation |
| No undo/redo acknowledgement | Risk register with undo impact per phase | Honest about the gap without blocking progress |
| Visual picker via embedded TileCanvas | Lightweight AreaThumbnailRenderer | Avoids 40+ instance variables of editing state |
| Global entities left as open question | Separate "Global" group in list pickers | Concrete answer using existing infrastructure |
