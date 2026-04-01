# Physics V1 Plan

This document captures the first explicit engine-level physics contract for the
grid puzzle RPG engine.

It is a planning and alignment document, not the canonical implementation
reference. The canonical runtime/JSON contract should be updated only after the
implementation changes are real.

## Why This Change Exists

The engine has become highly data-driven, but too much core movement/collision
behavior is currently authored through low-level JSON orchestration.

The goal of this rework is to make core physics:

- explicit
- predictable
- easy to author
- usable without tags
- extensible later through tags and structured rules

This rework is not an attempt to build a generic physics engine.
It is a focused grid-physics contract for dungeon/puzzle RPG behavior.

The goal is to make common physics behavior easier and more explicit, not to
remove the ability to author unusual behavior with low-level commands.

## Design Rules

- The engine owns generic physical semantics.
- JSON owns configuration, content, and project-specific exceptions.
- Templates remain project content; they are not privileged engine objects.
- Tags are supported from day one, but optional.
- Tags extend the default rules; they do not replace the base contract.
- The engine uses fixed engine defaults only.
- Shared project values may still exist, but only through explicit reads.
- V1 stays grid-only.
- Low-level JSON command power remains available as an escape hatch.

## Core Cell Contract

Cells support:

- `blocked: bool`
- `tags: string[]`

Meaning:

- `blocked` means the standard grid mover cannot enter that cell.
- `tags` are optional metadata for advanced movement/pushing logic.

Recommended engine defaults:

- `blocked = false`
- `tags = []`

Examples:

```json
{ "blocked": false, "tags": ["floor"] }
{ "blocked": true, "tags": ["wall"] }
{ "blocked": false, "tags": ["water"] }
{ "blocked": false, "tags": ["mud"] }
{ "blocked": false, "tags": ["ice"] }
```

## Core Entity Contract

Entities gain explicit engine-known physics fields:

- `solid: bool`
- `pushable: bool`
- `weight: int`
- `space: "world" | "screen"`
- `present: bool`
- `visible: bool`
- `facing: "up" | "down" | "left" | "right"`
- `grid_x`
- `grid_y`
- `pixel_x`
- `pixel_y`
- `tags: string[]`

Recommended engine defaults:

- `solid = false`
- `pushable = false`
- `weight = 1`
- `space = "world"`
- `present = true`
- `visible = true`
- `facing = "down"`
- `tags = []`

Clarifications:

- `solid` means the entity blocks standard movement.
- `pushable` means the entity participates in the standard push system.
- `pushable` does not mean "always pushable in all contexts."
- `weight` stays intentionally dumb and puzzle-oriented.

## Core Movement Contract

For V1, the engine supports one standard grid movement behavior.

Suggested authored shape:

```json
{
  "movement": {
    "move_frames": 16,
    "push_strength": 1,
    "collision_push_strength": 0
  }
}
```

Meaning:

- the entity uses the engine's standard grid mover
- `move_frames` controls step timing
- `push_strength` is used for deliberate push attempts
- `collision_push_strength` is reserved for later optional sliding collision transfer

Recommended engine defaults:

- `move_frames = 16`
- `push_strength = 1`
- `collision_push_strength = 0`

There is no automatic project-level default fallback in V1.
If a project wants shared movement values, content must read them explicitly.

## Core Pushing Contract

Pushing is part of the standard grid physics model.

Standard V1 rules:

- a push may only be attempted against a blocking entity
- the blocking entity must be `solid: true`
- the blocking entity must be `pushable: true`
- push succeeds only if `actor.push_strength >= target.weight`
- standard pushing handles one blocking entity only
- if multiple solid blockers exist in the target cell, push fails
- chain-pushing is out of scope for V1

## Push Action Types

The engine supports two distinct push contexts.

### 1. Push While Moving

An entity attempts to step into a cell blocked by one pushable solid.

If the push succeeds:

- the blocking entity moves first
- the actor then moves into the target's old cell

### 2. Push Without Moving

The engine should support a standard `push_facing` action.

When used:

- the actor checks the adjacent cell in its current `facing`
- the same push rules are applied
- if the push succeeds, the target moves
- the actor stays in place

Both forms should reuse the same push-resolution logic.

## Standard Grid Movement Resolution Order

When an entity attempts to move one grid step:

1. Ignore the request if the entity is not currently movable.
2. Update `facing` immediately.
3. Compute the target cell from the requested direction.
4. If the target cell is out of bounds, treat it as blocked.
5. If the target cell `blocked == true`, movement fails.
6. Gather entities occupying the target cell.
7. Filter to `present == true`, `space == "world"`, `solid == true`.
8. If no solid blockers exist, movement succeeds.
9. If more than one solid blocker exists, movement fails.
10. If exactly one solid blocker exists:
11. If blocker is not `pushable`, movement fails.
12. If actor `push_strength < blocker.weight`, movement fails.
13. Compute blocker destination cell.
14. If blocker destination is out of bounds, push fails.
15. If blocker destination cell is `blocked == true`, push fails.
16. If blocker destination contains any solid entity, push fails in V1.
17. If all checks pass, move blocker.
18. Then move actor.
19. Snap moved entities cleanly to their final grid/pixel positions.
20. Run configured success hooks.
21. On failure, run configured blocked or push-failed hooks if present.

## Standard Push-Facing Resolution Order

When an entity uses `push_facing`:

1. Read actor `facing`.
2. Compute the adjacent cell in that direction.
3. Gather solid blockers in that cell.
4. If not exactly one valid blocking entity exists, push fails.
5. Apply the same standard push rules as movement pushing.
6. If push succeeds, move the target.
7. Actor does not move.
8. Run push success or push fail hooks if configured.

## Weight System

Weight stays intentionally minimal.

Fields:

- `weight`
- `push_strength`
- `collision_push_strength`

Rules:

- standard push succeeds if `push_strength >= target.weight`
- no momentum system exists
- no force accumulation exists
- no formulas beyond threshold comparison should be introduced

This is puzzle logic, not generalized physics.

## Tags

Cells and entities both support optional `tags`.

Examples:

- cell tags: `floor`, `wall`, `water`, `mud`, `ice`
- entity tags: `crate`, `ghost`, `npc`, `metal`, `heavy`

Important:

- core physics must work with no tags at all
- tags exist from day one
- tag-based movement and push restrictions are an advanced extension layer
- advanced projects may still bypass or extend the standard rules through
  explicit low-level command logic when needed

## Advanced Optional Tag-Based Extensions

These are allowed in the long-term plan from the start, but they are not part
of the minimum beginner model.

Examples of future structured extensions:

- `forbidden_cell_tags`
- `pushable_entity_tags`
- `forbid_push_when_on_cell_tags`
- `forbid_push_into_cell_tags`

Examples of later use:

- ghost cannot enter `water`, but can ignore `wall`
- object can be pushed into `mud`, but cannot be pushed while already on `mud`
- actor can push `crate` but not `statue`

Rule:

- advanced tag rules refine or veto default physics
- they do not replace the default physics contract

## Escape Hatch Rule

Physics V1 should define a clear standard contract for ordinary movement and
pushing, but it should not eliminate the existing low-level command escape
hatch.

This means:

- ordinary projects should be able to rely on the built-in physics defaults
- advanced projects should still be able to author custom movement-adjacent
  behavior with explicit command logic
- the engine should become easier by default without becoming weaker for unusual
  puzzle cases

## Ice and Sliding

Ice is explicitly not part of the V1 base physics behavior, but the design
should leave room for it later.

Likely future direction:

- cells may use tags such as `ice`
- movement may later support sliding on certain cell tags
- sliding means continuing in the same direction until a stop condition occurs

Future optional extension:

- `sliding_collision_transfer: bool`

If later enabled:

- sliding collision transfer is treated as a normal push attempt
- it uses `collision_push_strength`
- if transfer succeeds, the struck object starts moving
- the sliding collider stops behind it

Important:

- this is a discrete puzzle rule, not momentum simulation
- in a `1 weight` into `100 weight` collision, transfer fails unless collision
  push strength is high enough

## What The Engine Owns

The engine owns:

- meaning of `blocked`
- meaning of `solid`
- meaning of `pushable`
- meaning of `weight`
- meaning of `push_strength`
- meaning of `collision_push_strength`
- standard grid movement resolution
- standard push resolution
- standard `push_facing` resolution
- bounds behavior
- single-blocker V1 push rules

## What Projects Own

Projects own:

- entity templates
- area data
- tag vocabulary
- timing choices
- puzzle hooks
- which entities are solid, pushable, and heavy
- whether tags are used at all
- future advanced tag-based restrictions
- optional shared project values and helper conventions

The engine should not own privileged gameplay templates like `player`,
`crate`, or `ice_boulder`.

## Generic Spatial Hooks

The engine should support a small set of generic spatial hooks as part of the
physics/event contract.

Recommended V1 hooks:

- mover-side: `on_blocked`
- target-side: `on_occupant_enter`
- target-side: `on_occupant_leave`

Why this split exists:

- `on_blocked` belongs to the mover because it describes a failed movement
  attempt by that actor.
- `on_occupant_enter` and `on_occupant_leave` belong to the target entity
  because reusable spatial objects such as buttons, pressure plates, holes, and
  traps should own their own response logic.

Important:

- these are generic spatial events, not special button or hole systems
- the engine should not hardcode "heavy button," "triangle hole," or similar
  puzzle mechanics
- the engine only needs to provide the event and the relevant context

Typical event context should include:

- the target entity (`self`)
- the entering or leaving entity as a reference or entity id
- the relevant grid cell
- direction when applicable

## Generic Spatial Hook Resolution

### `on_blocked`

When a standard movement attempt fails because of a blocked cell or an
unresolved blocker, the mover may run `on_blocked`.

This is useful for:

- bump sounds
- failure animation
- blocked movement feedback

### `on_occupant_enter`

When an entity successfully enters the same world cell as a non-solid entity
that supports occupancy reactions, that target entity may run
`on_occupant_enter`.

The target entity decides what to do with the occupant.

### `on_occupant_leave`

When an entity leaves a world cell containing a target entity with occupancy
reactions, that target entity may run `on_occupant_leave`.

The target entity decides whether anything should change as a result.

## Ownership Model For Buttons, Holes, And Similar Objects

Reusable spatial objects should own their own logic.

Examples:

- a button should decide whether the current occupant is heavy enough
- a button should decide whether the occupant has the required tag
- a hole should decide whether the occupant is accepted

The moving entity should not need button-specific or hole-specific authored
logic by default.

This keeps reusable interaction logic with the reacting object instead of
spreading it across every mover.

## Buttons And Holes As Entities

Objects such as buttons, pressure plates, holes, pickups, and traps may be
better modeled as entities rather than tile metadata.

That does not contradict the physics plan.

Instead, it reinforces the need for generic target-side occupancy hooks.

Tile or cell metadata still matters for things like:

- blocked movement
- mud
- water
- ice
- other terrain-style rules

But many reusable puzzle interactions may reasonably live on entities.

## Conditional Checks In Authored Hook Logic

It is acceptable for authored hook logic to use condition checks such as:

- occupant `weight > 5`
- occupant has tag `triangle`
- occupant does not have tag `ghost`

That is game logic, not a sign that the engine should hardcode every puzzle
type.

However, if the same condition patterns repeat constantly across many projects
or many reusable templates, that repetition is a signal that the engine or
standard authoring layer may later want small generic helper surfaces such as:

- required tags
- forbidden tags
- minimum weight

Those future helpers should remain generic. They should not turn into
special-purpose built-in puzzle mechanics.

## Standard Interaction Resolution

The engine should likely own the standard "interact with what is in front of
me" lookup and dispatch flow.

This means the engine should provide a default interaction process that:

1. reads the actor's `facing`
2. resolves the adjacent target cell
3. gathers candidate interaction targets in that cell
4. selects one target by a deterministic rule
5. dispatches to that target's authored `interact` behavior

This is the interaction equivalent of standard movement resolution: generic
lookup belongs in the engine, but interaction meaning belongs in project
content.

### Suggested Interaction Defaults

Recommended direction:

- only check the adjacent facing cell in V1
- only resolve entity targets in V1
- if no valid target exists, nothing happens
- if multiple targets exist, use a deterministic selection rule

Likely engine-known fields:

- `interactable: bool`
- `interaction_priority: int`

Recommended defaults:

- `interactable = false`
- `interaction_priority = 0`

### Important Clarification

The target entity's `interact` behavior should remain a normal authored command
or event surface.

That means:

- engine-owned standard interaction resolution may dispatch to `interact`
- other authored logic may still call the same `interact` behavior directly

The rework should not make `interact` a privileged engine-only path. It should
remain reusable project-authored behavior.

## Suggested Defaults Summary

Cells:

- `blocked = false`
- `tags = []`

Entities:

- `solid = false`
- `pushable = false`
- `weight = 1`
- `space = "world"`
- `present = true`
- `visible = true`
- `facing = "down"`
- `tags = []`

Movement:

- `move_frames = 16`
- `push_strength = 1`
- `collision_push_strength = 0`

## Naming Guidance

Recommended names:

- cells: `blocked`
- entities: `solid`

Reason:

- `blocked` reads naturally for cells
- `solid` reads naturally for entities
- this avoids the ambiguity of `walkable` or `passable`

## Non-Goals For V1

Do not include:

- free movement
- generalized physics simulation
- chain-pushing
- diagonal movement
- momentum
- friction systems
- collision layers or masks unless a concrete need appears
- automatic project-level fallback defaults
- privileged engine-owned gameplay templates

## Migration Guidance

If existing content uses `walkable`, the engine may temporarily support:

- `walkable: true` -> `blocked: false`
- `walkable: false` -> `blocked: true`

But the forward-facing contract should move toward `blocked`.

## Implementation Order

1. Add engine-known cell `blocked`.
2. Add engine-known entity `solid`, `pushable`, and `weight`.
3. Add `push_strength` and `collision_push_strength` to movement config.
4. Implement standard movement resolution using `blocked` plus `solid`.
5. Implement standard one-entity push using `pushable` plus `weight`.
6. Implement standard `push_facing`.
7. Add validation for the new fields.
8. Update documentation.
9. Migrate sample project content.
10. Add tests for blocked cells, solid blockers, pushable blockers, weight
    checks, and `push_facing`.
11. Later add optional tag-based refinements.
12. Later add ice/sliding.
13. Later add optional sliding collision transfer.
