# Entity Identity And Persistence Refactor

## Status

Partially implemented.

Implemented already:

- Phase 1: strict duplicate-id rejection and project-wide authored entity-id validation
- Phase 2: traveler identity keyed by real `entity_id`; `session_entity_id` and
  `origin_entity_id` removed
- Phase 5A: entity/template `persistence` policy plus command-level
  override-or-inherit behavior for entity-targeted mutation commands
- Phase 5B: movement/position and inventory persistence now follow entity
  policy by default, with explicit command override support
- Phase 5C: transient traveler/entity state now drops on active-area change
  while exact current-area save/load still preserves the full live snapshot
- Phase 5D: manual transient cleanup can now target one entity directly through
  `reset_transient_state(entity_id?/entity_ids?)`

Still pending:

- persistent spawn identity tightening
- later global-id cross-area lookup / transfer features

This document is the concrete implementation plan for the next engine direction:

- make runtime-addressable entity ids project-wide unique
- simplify traveler identity around that invariant
- remove legacy identity layers that become redundant
- prepare a cleaner persistence model where entity policy provides defaults and
  commands can explicitly override them

This plan intentionally assumes a one-way migration is acceptable.
Backward compatibility is not a goal.

## Why This Refactor Exists

The current engine mostly treats `entity_id` as the author-facing identity, but
it still has several places where identity is only room-local or where runtime
plumbing introduces a second internal identity:

- authored area entities are only validated against global entity ids, not
  against entities in other areas
- duplicate entity ids inside one authored area currently collapse silently to
  the last loaded entity
- traveler save data is keyed by `session_entity_id`, not the entity's real id
- `origin_entity_id` duplicates information that is already present in the
  entity payload for authored travelers
- mutable commands treat `persistent` as a required explicit boolean choice
  rather than something that can inherit from entity policy

This works, but it creates long-term friction for:

- cross-area entity transfer
- future "find entity anywhere by id" APIs
- persistent puzzle objects that move between areas
- reliable validation and tooling
- clean save semantics

## Main Design Decisions

### 1. `entity_id` becomes the single author-facing identity

For runtime-addressable entities, `entity_id` should be:

- unique across all authored area entities in the project
- unique across `project.json` global entities
- unique across persistent spawned entities

This means:

- no two authored area entities in different areas may share the same id
- no authored area entity may share an id with a project global
- persistent spawned entities must also avoid collisions with the same global
  namespace

This is intentionally stricter than the current behavior.

### 2. Remove `session_entity_id`

Once entity ids are globally unique and stable, `session_entity_id` becomes
redundant.

Traveler save data, transition skip logic, and live traveler refresh should all
use `entity_id` directly.

This also removes:

- `SaveData.next_session_entity_serial`
- traveler save keys like `"traveler_1"`
- runtime fields that only exist to support those keys

### 3. Keep original-area tracking, remove `origin_entity_id`

Original area tracking is still useful and should remain.

Recommended traveler metadata:

- `current_area`
- `entity`
- `origin_area`

Do not keep `origin_entity_id`.

With globally unique ids, `origin_entity_id` is redundant because:

- the traveler payload already contains the real `entity.id`
- that id is enough to suppress the authored placeholder in the origin area

### 4. Make duplicate ids a hard error everywhere

The runtime should stop silently replacing entities on duplicate id insert.

That means:

- loader should reject duplicate entity ids inside one area
- project validation should reject duplicate area-entity ids across all areas
- project validation should reject area/global collisions
- world insertion should reject duplicate ids instead of replacing same-scope
  entities

If code truly needs "replace this entity object", that should be an explicit
operation with a different helper name.

### 5. Keep the layered persistence model

The current persistence architecture is still good at a high level:

- authored room data remains the source of truth
- per-area overrides remain layered diffs
- exact current-area/current-global snapshots remain special save-time captures
- travelers remain the mechanism for cross-area entity relocation

This refactor should simplify identity and lookup, not replace the whole
layered persistence model.

### 6. Entity persistence policy should exist, but it is a phased change

Entity-level persistence policy is the right long-term direction, but it is not
the main architecture blocker.

Recommended future shape:

```json
{
  "persistence": {
    "entity_state": true,
    "variables": {
      "temp_hint_visible": false,
      "times_pushed": true
    }
  }
}
```

Command semantics should later become:

- explicit `persistent: true` -> force persistent
- explicit `persistent: false` -> force transient
- omitted `persistent` -> inherit entity policy

This requires a tri-state command surface. The command-driven part is now in
place for entity-targeted mutation commands, but movement, inventory, and
traveler cleanup still need to be brought into the same model.

## Target End State

After this refactor:

- any runtime-addressable entity has one meaningful project-wide id
- authored logic targets `entity_id`, not a second identity layer
- traveler save state is keyed by `entity_id`
- original-area suppression uses `origin_area + entity_id`
- duplicate ids fail early during validation and loading
- current and future cross-area features can be built on top of the real entity
  id namespace

Conceptual traveler save shape:

```json
{
  "travelers": {
    "player_main": {
      "current_area": "areas/room_b",
      "entity": {
        "id": "player_main",
        "grid_x": 2,
        "grid_y": 5
      },
      "origin_area": "areas/room_a"
    }
  }
}
```

## Files And Systems Affected

### Runtime identity and storage

- `dungeon_engine/world/entity.py`
- `dungeon_engine/world/world.py`
- `dungeon_engine/world/loader.py`
- `dungeon_engine/world/serializer.py`

### Persistence and save format

- `dungeon_engine/world/persistence.py`
- save slot JSON format

### Transition flow

- `dungeon_engine/engine/game.py`

### Commands and cross-area APIs

- `dungeon_engine/commands/builtin.py`

### Validation and project lookup

- `dungeon_engine/project.py`
- `dungeon_engine/world/loader.py`
- startup validation entry points

### Documentation and samples

- `ENGINE_JSON_INTERFACE.md`
- `AUTHORING_GUIDE.md`
- `architecture.md`
- any sample project content that relies on duplicate ids or old traveler save
  assumptions

## Concrete Refactor Plan

## Phase 1: Enforce Identity Invariants

### Goal

Make the engine reject ambiguous entity identity before changing traveler
plumbing.

### Changes

1. Reject duplicate entity ids inside one authored area.
2. Reject duplicate area-entity ids across different authored areas.
3. Reject authored area entity ids that conflict with project globals.
4. Make `World.add_entity()` reject duplicate ids rather than replacing
   same-scope entities.
5. Add or rename an explicit replacement helper for the few code paths that
   intentionally replace a live entity object.

### Notes

This phase should also fix the current silent overwrite bug in authored area
loads.

### Verification

Add tests for:

- duplicate ids inside one area
- duplicate ids across two areas
- duplicate area/global collisions
- world duplicate add rejection
- authored area load failure instead of silent collapse

## Phase 2: Replace Traveler Identity With `entity_id`

### Goal

Remove `session_entity_id` and make traveler state keyed by the real entity id.

### Changes

1. Remove these fields from `Entity`:
   - `session_entity_id`
   - `origin_entity_id`
2. Keep:
   - `origin_area_id`
3. Remove these fields from `SaveData`:
   - `next_session_entity_serial`
4. Change `TravelerState` to:
   - `entity_id`
   - `current_area`
   - `entity_data`
   - `origin_area`
5. Key `save_data.travelers` by `entity_id`.
6. Update `prepare_traveler_for_area()` to:
   - use `entity.entity_id` directly
   - store `origin_area` only when first leaving authored origin
7. Update `refresh_live_travelers()` to refresh by `entity_id`.
8. Update `apply_area_travelers()` to:
   - suppress origin placeholders by `entity_id`
   - skip reinstalls by `entity_id`
9. Update area transition logic in `Game` to:
   - collect transferred entity ids
   - pass `skip_entity_ids` instead of `skip_session_entity_ids`

### Save format

Bump the save version and remove all support for the old traveler key format.

### Verification

Add tests for:

- traveler survives area changes without `session_entity_id`
- origin placeholder suppression still works
- destination reinstall skip still works
- save/load restores traveler state keyed by `entity_id`

## Phase 3: Build Project-Wide Entity Lookup Foundations

### Goal

Make the unique-id model useful, not just strict.

### Changes

1. Add a project-level authored entity index.
   - shape: `entity_id -> authored area id`
2. Build it during project validation or startup validation.
3. Expose a clean lookup helper through `ProjectContext`.
4. Use this index in validation, tooling, and future runtime lookup helpers.

### Important boundary

Do not load every entity from every area as a live runtime entity.

The engine should keep:

- one active area
- project globals
- active travelers

The new entity index should be metadata only, not a second live simulation.

### Future use

This index is the foundation for later features such as:

- transfer entity by project-wide id
- jump-to-definition in editor tooling
- project-wide rename helpers
- project-wide collision checks for spawned persistent entities

## Phase 4: Tighten Spawn And Persistent-Spawn Identity

### Goal

Make persistent spawned entities fit the same global-id model.

### Changes

1. Audit `spawn_entity`.
   - current duplicate checks only look at the current live world
2. Introduce a project/session-wide duplicate check for persistent spawns.
3. Decide whether persistent spawned entities must always supply an explicit id.

Recommended answer:

- yes, persistent spawned entities should require explicit ids
- non-persistent temporary spawns may still use current-world uniqueness only
  if needed later

4. Move id-generation helpers toward project-wide uniqueness, not current-world
   uniqueness.

This affects:

- runtime spawn helpers
- editor new-entity id suggestions
- any future project scaffolding or duplication tooling

## Phase 5: Add Entity Persistence Policy

### Goal

Allow entities and templates to define persistence defaults, while commands and
runtime systems can still override explicitly.

### Phase 5A - Command-layer inheritance

Status: implemented.

Completed changes:

1. entity/template JSON now accepts a `persistence` block
2. loader/serializer round-trip that block
3. entity-targeted mutation commands now use tri-state `persistent`
4. omitted `persistent` now inherits from entity policy on those commands

Covered command families:

- entity variable commands
- entity field commands
- visibility/presence/color commands
- spawn/destroy
- entity-command enable-state commands

### Phase 5B - Movement and inventory as entity state

Status: implemented.

Goal:

Bring movement and inventory under the same persistence model.

Changes:

1. Treat movement/position changes as entity state.
2. Teach direct position/movement paths to consult entity persistence policy.
   This includes:
   - grid movement
   - push movement
   - teleports and direct position setters
3. Treat inventory as entity state.
4. Make inventory mutations inherit entity persistence by default.
5. Keep inventory persistence coarse-grained for now.

Important boundary:

- do not add per-item-instance persistence yet
- do not attempt mixed transient/persistent copies of the same stackable item
- inventory should persist as a whole entity-state property for now

### Phase 5C - Traveler transient cleanup boundary

Status: implemented.

Goal:

Keep exact current-area save behavior while stripping transient traveler/entity
state at the right boundary.

Agreed rule:

- exact save/load of the currently active area should preserve the full live
  snapshot
- transient entity/traveler state should be dropped when the active area
  changes
- this cleanup should not depend on whether a traveler was teleported in the
  background while the active area stayed the same

Changes:

1. define which parts of entity state are considered transient vs persistent
   under entity policy
2. strip transient portions from traveler/entity state when the active area
   changes
3. preserve exact current-area snapshot save/load behavior

### Phase 5D - Manual transient cleanup commands

Status: implemented.

Goal:

Allow authored logic to explicitly drop temporary state before an active-area
change when a project needs that behavior.

Changes:

1. add explicit cleanup command(s) for transient entity/traveler state
2. make them targetable by entity id
3. keep them orthogonal to traveler transfer itself

Recommended first scope:

- clear transient state for one entity
- optionally clear transient state for a filtered/tagged group later

### Remaining general changes

1. Introduce shared helpers so non-command runtime systems also resolve
   effective persistence through the same policy rules.
2. Bring movement, inventory, and traveler cleanup into that model.

### Suggested precedence

1. explicit command persistence
2. variable-specific entity policy
3. entity-state default policy
4. final fallback = transient

### Notes

Travel remains explicit relocation.
The remaining work is about what state survives around that relocation, not
about changing the meaning of travel itself.

## Phase 6: Add Global-Id-Based Cross-Area Runtime Features

### Goal

Once ids are globally unique and traveler state is simplified, add higher-level
runtime operations that benefit from the new identity model.

Possible future features:

- transfer entity by `entity_id` without requiring it to be in the current live
  world
- optional source-area assertion for stricter puzzle logic
- current-location queries

This phase is intentionally later.
The identity refactor should land first.

## Save Format Changes

## Required breaking changes

- bump `SAVE_DATA_VERSION`
- remove `next_session_entity_serial`
- remove traveler `session_entity_id`
- remove traveler `origin_entity_id`
- key travelers by real `entity_id`

## Suggested traveler payload

```json
{
  "travelers": {
    "crate_red_1": {
      "current_area": "areas/room_b",
      "entity": {
        "id": "crate_red_1",
        "grid_x": 5,
        "grid_y": 6
      },
      "origin_area": "areas/room_a"
    }
  }
}
```

## Open Design Choices

### Keep `origin_area_id` field name or rename it?

Recommendation:

- keep `origin_area_id` in Python for the first refactor to minimize churn
- if a naming cleanup pass happens later, consider `home_area_id`

### Do we need a dynamic current-location registry immediately?

Recommendation:

- not in Phase 1 or Phase 2
- the traveler table plus authored entity index are enough to land the identity
  cleanup cleanly
- add a dedicated current-location registry only when the new cross-area lookup
  features are implemented

### Should non-persistent temporary spawns also require globally unique ids?

Recommendation:

- practical requirement: yes if they are addressable by commands
- implementation detail: current-world uniqueness is still sufficient for truly
  transient throwaway entities that never enter persistence and are never looked
  up outside the current world

## Non-Goals

This plan does not attempt to:

- preserve old save compatibility
- preserve old duplicate-id behavior
- solve every future transfer/recall API now
- redesign the full persistence model around a single giant global entity table
- change traveler semantics into a fuzzy "maybe move, maybe hide, maybe destroy"
  concept

## Testing Plan

### Runtime/unit tests

Add or update tests for:

- duplicate entity ids rejected inside one area
- duplicate entity ids rejected across areas
- duplicate area/global collisions rejected
- `World.add_entity()` duplicate rejection
- traveler save/load keyed by `entity_id`
- transition reinstall skip keyed by `entity_id`
- origin placeholder suppression keyed by `origin_area + entity_id`
- persistent spawned entity collision rejection

### Direct project validation

Re-run:

- `projects/test_project`
- `projects/game_copy`

through the normal startup validation path after the refactor lands.

### Manual smoke

At minimum:

- area transition carrying one traveler
- save/load with a traveler present
- save/load with persistent spawned entities

## Recommended Next Implementation Order

1. persistent spawn identity tightening
2. later cross-area lookup/transfer features

## Summary Recommendation

The clean long-term architecture is:

- one real entity identity: `entity_id`
- project-wide uniqueness for that identity
- no `session_entity_id`
- no `origin_entity_id`
- keep `origin_area`
- keep layered per-area persistence
- add entity persistence defaults later through explicit entity policy plus
  command override

That gives the engine a much clearer foundation for both runtime behavior and
future authoring workflows.
