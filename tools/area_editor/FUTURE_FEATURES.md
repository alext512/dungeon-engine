# Future Features

Planned features that are not part of the current phase.
Add notes here when ideas come up during development.

---

## Move / Rename Areas and Templates via Editor Tree

### What

The user should be able to drag or right-click rename areas and entity
templates directly in the editor's tree panels. When a file is moved or
renamed, the editor should automatically update all references across the
project so nothing breaks.

### Area Moves and Renames

Moving or renaming an area file changes its area_id. References that need
updating:

- `project.json` `startup_area`
- entity instance parameters that reference the area by id
  (e.g. `"target_area": "village_square"` in area_door parameters)
- `change_area` commands anywhere in event chains or project commands
- cross-area commands: `set_area_var`, `set_area_entity_var`,
  `set_area_entity_field`, `$area_entity_ref` - all take an `area_id`
- save files: persistent state is keyed by area_id under
  `SaveData.areas[area_id]`

### Template Moves and Renames

Moving or renaming a template file changes its template_id. References that
need updating:

- every entity instance in every area that uses `"template": "<id>"`
- global entities in `project.json` that use `"template": "<id>"`
- `spawn_entity` commands that reference a template

### Entity Instance Renames

Renaming an entity's `id` within an area. References that need updating:

- same-area `input_targets` (action -> entity_id mapping)
- same-area `camera.follow_entity_id`
- other entities' parameters that reference the id
  (e.g. `"target_gate": "gate_1"`)
- `enter_commands` and entity event command chains that use the id
- cross-area references from other areas (commands targeting this entity
  by area_id + entity_id)

### Implementation

With the current type-prefixed id contract (see DECISIONS.md), ids like
`areas/village_square`, `entity_templates/area_door`, and
`commands/dialogue/open` are structurally
unique across all content types. This makes the rename operation a safe
blind find-and-replace:

1. Move or rename the file on disk (the new root-relative path updates the id)
2. Scan every JSON file in the project for string values matching the old id and replace with the new id
3. No false positives are possible - `areas/door` cannot collide with `entity_templates/door`, `commands/door`, or an entity instance called `door`
4. Show the user a preview of matches before applying (for confidence)
5. Write all changed files

Save files can be handled the same way - re-key the area_id entry in
the save data dict.

Entity instance renames (within an area) still require scoped
replacement since entity ids are plain strings, not file paths. But
these are scoped to a single area's references plus cross-area commands
that target that area, which is a smaller search space.

### Prerequisites

- type-prefixed id convention adopted in the runtime (see DECISIONS.md)
- Phase 2 (saving) must be complete before file moves can be safe
- the same scanning logic could later power "find all references" and
  "broken reference warnings"

---

## Richer Project Browser Tabs (Implemented)

The editor now has five content browser tabs in the left dock (Areas,
Entity Templates, Dialogues, Commands, Assets) plus a tabbed document
area in the center. Double-clicking any item opens it in a tab.

Remaining work:

- rename/move with reference updating (see above)
- richer asset preview (metadata display, animation preview)
- drag-and-drop from template panel onto area canvas (Phase 4)
