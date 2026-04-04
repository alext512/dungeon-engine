# Future Features

Planned features that are not part of the current phase.
Add notes here when ideas come up during development.

The main editor catch-up plan is now tracked in ROADMAP.md Phases 4-9.

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
unique across all content types. This makes reference detection and targeted
replacement much safer than plain-name matching, but it should still use a
previewed update flow instead of assuming blind replacement is always safe:

1. Move or rename the file on disk (the new root-relative path updates the id)
2. Scan every JSON file in the project for candidate references to the old id
3. Preview matches before applying replacements
4. Apply targeted updates to the accepted matches
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

---

## Guided Command-Chain Builder For Custom Entities And Items

### What

Add a guided editor surface for building command chains visually without
requiring users to hand-write the underlying JSON command arrays.

This is aimed at a "custom enough" workflow rather than a full unrestricted
visual scripting system. The editor would still produce the real engine JSON
shapes:

- sequences
- parallels
- spawns
- ordinary built-in command payloads

The user-facing goal is to make it practical to author reusable custom
entities/items such as:

- levers
- doors
- pressure plates
- simple puzzle controllers
- usable items with behavior

without needing to expose the entire runtime surface at once.

### Likely First Shape

The first useful version should be narrow and explicit:

- named command slots such as entity `interact` or custom named
  `entity_commands`
- item `use_commands`
- a block-based stack editor for:
  - `sequence`
  - `parallel`
  - `spawn`
  - leaf commands from the command library

This should feel like assembling known command blocks, not programming in a
new language.

### Why This Is Valuable

This could become one of the strongest editor features for template-driven
projects because it would let authors:

- build reusable behavior-rich templates
- expose only the intended tuning points
- compose interactions without writing raw JSON for every variation

Example direction:

- a lever template contains an `interact` command chain
- that chain can call a reusable "open door" behavior
- the template exposes `door_id` as the parameter the user edits when placing
  the lever

### Architectural Direction

This should build on the existing runtime model rather than inventing a second
behavior system.

The editor should:

- edit the real command-chain JSON
- use command-library metadata to present the available commands
- use the existing parameter/exposed-parameter workflow where appropriate
- keep full raw JSON available as the escape hatch

Recommended constraints for an early version:

- prefer a linear block-stack UI over a freeform node graph
- support only known command schemas from the runtime registry
- use pickers for entity/template/item/area references where possible
- allow parameter exposure for curated templates/items rather than exposing
  every command field equally

### Non-Goals For The First Version

- a fully general visual scripting graph language
- solving every command in the runtime at once
- removing raw JSON from advanced workflows
- replacing the need for a curated template library

### Relationship To Controller Entities

This feature would complement, not replace, controller entities.

Controller entities remain a practical current pattern for room-local reusable
logic. A future command-chain builder would simply make authoring the
controller's commands, or a lever/door/item's own commands, much more
comfortable.
