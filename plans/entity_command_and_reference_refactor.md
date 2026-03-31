# Entity Command And Reference Refactor

## Status

This is a design proposal, not implemented behavior.

Its purpose is to capture a likely next-step refactor of the command authoring
model, focused on:

- replacing the current entity `events` framing with a clearer command model
- keeping `self` as the only special automatic entity role
- removing special `actor` / `caller` runtime roles
- replacing them with explicit named entity references
- keeping reference passing ergonomic without making it magical

This document is intentionally detailed so it can survive handoff, context
compression, or phased implementation.

The detailed future dot-notation proposal now lives in
`plans/dot_notation_future_spec.md`.

## Why This Refactor Exists

The current engine works, but several concepts are harder to reason about than
they should be.

The biggest friction points are:

- entity-local named command chains are called `events`, even when they are
  really just named behaviors or routines
- `run_event` sounds event-driven, but in practice it often behaves more like
  "invoke this named command chain on that entity"
- `self` is clear, but `actor` and `caller` are partially magical runtime roles
- `actor` is seeded by engine input routing, which makes authors ask "who
  decided this?"
- `caller` is explicit, but still depends on a reserved magical slot rather than
  a general mechanism for passing entity context
- cross-entity context is useful, but the current model bakes in a small fixed
  vocabulary instead of giving authors a more general explicit tool

The current system is therefore usable, but conceptually uneven:

- some context is automatic
- some context is engine-inferred
- some context is caller-passed
- all of it is exposed through special hardcoded names

That is functional, but not especially elegant.

## High-Level Goals

The refactor should aim for these goals:

- make the authoring model easier to explain
- reduce engine-magic in authored gameplay logic
- preserve the ergonomic parts of the current system
- make cross-entity context explicit and general
- avoid boilerplate-heavy "manual repassing" on every command
- keep the command system data-driven and composable
- create a better base for future dot-notation decisions

## Core Design Position

The recommended direction is:

- keep `self` as the only special automatic entity role
- remove `actor` and `caller` as special engine-defined roles
- replace them with explicit named entity references
- keep entity-owned named command chains, but stop calling them `events`

In other words:

- automatic owner context remains
- all other entity context becomes explicit and named

This keeps the part that is genuinely intuitive and removes the parts that feel
arbitrary or magical.

## Current Model Summary

Today, the model is roughly:

- `self`
  - automatic
  - means "the entity whose event is currently running"
- `actor`
  - a special runtime slot
  - often seeded by input routing
  - then forwarded through the chain unless overridden
- `caller`
  - another special runtime slot
  - explicitly passed by commands like `run_event`
  - then forwarded through the chain unless overridden

Entity-local named command chains are currently stored under `events`, for
example:

```json
{
  "events": {
    "interact": {
      "enabled": true,
      "commands": [
        {
          "type": "set_entity_var",
          "entity_id": "$self_id",
          "name": "opened",
          "value": true
        }
      ]
    }
  }
}
```

This works, but the terminology is misleading:

- the thing called `interact` is not one primitive command
- it is not inherently asynchronous
- it is not always an external "event" in the everyday sense
- it is simply a named entity-owned command chain

That is why the current naming feels wrong.

## Proposed Replacement For `events`

### Main idea

Keep the concept, replace the framing.

The engine still needs entity-owned named command chains. Input needs a way to
invoke one. Other entities need a way to invoke one. Dialogue controllers,
switches, doors, NPCs, and puzzle pieces all benefit from entity-local named
entry points.

So the proposal is not:

- remove entity-local named command chains entirely

The proposal is:

- stop calling them `events`
- treat them as named entity commands or behaviors

### Naming options

Reasonable names include:

- `entity_commands`
- `behaviors`
- `actions`
- `routines`

Current recommendation:

- favor `entity_commands` if the priority is conceptual consistency with
  "everything should be a command"
- favor `behaviors` if the priority is readability and avoiding confusion with
  project-level command files

At the moment, `entity_commands` is the most faithful to the intended
direction, but it creates naming pressure because the engine already has
project-level command files under `commands/`.

For that reason, the practical naming decision is still open.

### Recommended framing

Regardless of the final field name, the concept should be explained as:

- a named entity-owned command chain
- invokable by input, other entities, or project commands
- executed sequentially unless explicit parallelism is authored inside it

This is much easier to explain than "an event that contains commands."

## Recommended Invocation Model

The current `run_event(entity_id, event_id, ...)` concept should evolve into a
clearer invocation command.

Possible names:

- `run_entity_command`
- `invoke_entity_command`
- `run_behavior`

Current recommendation:

- `run_entity_command` if consistency and explicitness are more important
- `run_behavior` if readability is more important

The engine should also keep project-level reusable commands, likely through a
separate command such as:

- `run_command`
- or a renamed explicit form like `run_project_command`

That keeps two distinct concepts:

- entity-owned named command chains
- project-owned reusable command files

## Proposed Runtime Roles

### Keep `self`

`self` should remain automatic.

Meaning:

- `self` is the entity that owns the currently executing entity command chain
- `self_id` is that entity's id

Why keep it:

- it is genuinely intuitive
- it removes noise from common authoring
- it maps to a real stable concept
- almost every entity-owned chain naturally needs it

### Remove `actor`

`actor` is useful in practice, but not clean in concept.

Problems:

- it is special
- it is seeded by engine routing in some cases
- it can also be manually overridden
- it looks semantic, but is really just a partially magical runtime slot

This makes it harder to teach and reason about.

Recommendation:

- remove `actor` as a built-in role
- if a flow needs an instigator reference, pass one explicitly as a named ref

For example:

```json
"entity_refs": {
  "instigator": "$self_id"
}
```

or:

```json
"entity_refs": {
  "player": "player"
}
```

### Remove `caller`

`caller` is simpler than `actor`, but it is still a hardcoded special role.

What is good about it:

- it is explicit at the call site
- it often matches a real gameplay need

What is bad about it:

- it is only one special named lane out of many possible useful references
- once you allow one special caller slot, authors quickly need two or three
  more special slots
- the design stays narrow and magical instead of becoming general

Recommendation:

- remove `caller` as a special role
- replace it with explicit named references

For example:

```json
"entity_refs": {
  "switch": "$self_id"
}
```

This says exactly what the reference means, instead of forcing everything into
the vague word `caller`.

## Proposed Replacement: `entity_refs`

### Main idea

Introduce one general mechanism for passing cross-entity context:

- `entity_refs`

This should be a named map of reference names to entity ids.

Example:

```json
{
  "type": "run_entity_command",
  "entity_id": "door_1",
  "command_id": "open_from_switch",
  "entity_refs": {
    "switch": "$self_id",
    "player": "player"
  }
}
```

The called flow would then have access to:

- `self` for the target entity
- `switch` for the passed switch entity
- `player` for the passed player entity

### Why a named map, not an array

An unnamed array of entity references was considered, but it is not recommended.

Problems with arrays:

- order becomes meaning
- meaning becomes invisible at the use site
- adding one new ref can silently shift every later index
- the design invites rules like "the first ref is the important one," which
  becomes a new kind of hidden magic
- it scales poorly once more than one reference matters

Example of the bad version:

```json
"entity_refs": ["$self_id", "player", "door_1"]
```

This forces the reader to remember:

- what index 0 means
- what index 1 means
- whether the callee assumes a specific order

That is fragile and hard to maintain.

By contrast, a named map is self-documenting:

```json
"entity_refs": {
  "switch": "$self_id",
  "player": "player",
  "target_door": "door_1"
}
```

This is much clearer.

## Reference Scope And Propagation

### Core rule

References should survive within a flow by default.

The goal is:

- avoid re-passing everything manually
- avoid hidden loss of context
- keep authored JSON readable

So the model should be:

- once a flow has a reference map, it stays available to downstream commands
- new invoked flows inherit refs unless the call site explicitly changes them

### Universal context rule

The cleanest way to think about the system is:

- every executing command runs inside one current context
- that context contains:
  - `self`
  - `entity_refs`
  - normal runtime params
- every next command sees that same context by default
- every child command chain also starts from that same context by default

So the universal inheritance rule is:

- child chains inherit the parent context unless something explicitly changes it

This should be true uniformly across the whole authoring model, including:

- ordinary next commands in a list
- sequential blocks
- parallel branches
- named entity-command calls
- named project-command calls
- spawned flows
- dialogue-owned command chains
- start/end hooks
- any future nested command-chain mechanism

This is intentionally a general engine rule, not a special case for a few
command types.

### Where explicit ref-changing syntax matters

Even though the inheritance rule is universal, not every command needs its own
special ref-passing syntax.

Most commands should simply run in the current context without saying anything
about refs.

The main places where explicit ref-changing syntax is likely to matter are
commands that deliberately create or configure child chains.

The distinction here is not about whether inheritance happens. Inheritance
happens everywhere by default. The distinction is about where authors may want
an explicit way to alter the inherited refs for a child chain.

The most common examples are:

- named entity-command calls
- named project-command calls
- spawned flows
- any other command that intentionally configures the child chain's starting
  context

Structural composition commands such as sequential or parallel composition still
inherit context exactly the same way. They just usually do not need extra
ceremony because their default behavior is almost always already correct.

### Recommended default behavior

The recommended ref behavior is:

- if `entity_refs` is omitted:
  - inherit current refs unchanged
- if `entity_refs` is provided and no mode is specified:
  - merge the provided refs into the inherited refs
- `replace` and `clear` should always be explicit

This gives the most intuitive default model:

- saying nothing means "keep context"
- adding refs means "add or override these refs"
- destructive behaviors are never hidden

## Proposed `refs_mode`

To make reference updates clear and predictable, invocation commands should
support a `refs_mode` field.

Recommended modes:

- `inherit`
  - keep current refs unchanged
  - mainly implied when `entity_refs` is omitted
- `merge`
  - start with inherited refs, then add or override the provided refs
  - recommended default when `entity_refs` is present
- `replace`
  - discard inherited refs and use only the provided refs
- `clear`
  - remove inherited refs before continuing
  - optionally combined with an empty or absent `entity_refs`

### Why these modes

This set covers the important use cases without making the model too clever.

`inherit`:

- the most natural default
- avoids accidental context loss

`merge`:

- the most natural interpretation of "I provided some refs"
- low boilerplate

`replace`:

- important for hard call boundaries
- should be explicit because it is easy to misuse

`clear`:

- useful for deliberately isolated subflows
- should also be explicit because it is destructive
- best treated as "start with an empty ref map"
- if a caller wants a brand new non-empty ref map, `replace` is the clearer mode

## Recommended defaults

### If `entity_refs` is omitted

Recommended implicit behavior:

- `refs_mode = "inherit"`

Meaning:

- no changes to the current reference map

### If `entity_refs` is present and `refs_mode` is omitted

Recommended implicit behavior:

- `refs_mode = "merge"`

Meaning:

- inherit existing refs
- then add or override the provided ones

This is the best balance between ergonomics and predictability.

### What should never be implicit

These should always be explicit:

- `replace`
- `clear`

That avoids surprising ref loss.

## Authoring Examples

### Example 1: simple invocation with inherited refs

```json
{
  "type": "run_entity_command",
  "entity_id": "door_1",
  "command_id": "open"
}
```

Meaning:

- invoke `open` on `door_1`
- keep all currently available refs unchanged

### Example 2: add one new ref

```json
{
  "type": "run_entity_command",
  "entity_id": "door_1",
  "command_id": "open_from_switch",
  "entity_refs": {
    "switch": "$self_id"
  }
}
```

Meaning:

- invoke `open_from_switch` on `door_1`
- inherit existing refs
- add or override `switch`

### Example 3: explicit replacement

```json
{
  "type": "run_entity_command",
  "entity_id": "door_1",
  "command_id": "open_from_switch",
  "refs_mode": "replace",
  "entity_refs": {
    "switch": "$self_id"
  }
}
```

Meaning:

- invoke `open_from_switch` on `door_1`
- discard inherited refs
- provide only `switch`

### Example 4: explicit clearing

```json
{
  "type": "spawn_flow",
  "refs_mode": "clear",
  "commands": [
    {
      "type": "run_project_command",
      "command_id": "commands/reset_ui"
    }
  ]
}
```

Meaning:

- start a new flow with no inherited refs

### Example 5: replacing former `caller`

Current conceptual pattern:

```json
{
  "type": "run_event",
  "entity_id": "door_1",
  "event_id": "open_from_switch",
  "caller_entity_id": "$self_id"
}
```

Proposed replacement:

```json
{
  "type": "run_entity_command",
  "entity_id": "door_1",
  "command_id": "open_from_switch",
  "entity_refs": {
    "switch": "$self_id"
  }
}
```

This is more explicit and more meaningful.

### Example 6: replacing former `actor`

Current conceptual pattern:

- engine input seeds `actor`
- downstream commands read `$actor_id`

Proposed replacement:

- the input/invocation site explicitly decides what named instigator ref exists

Example:

```json
{
  "type": "run_entity_command",
  "entity_id": "dialogue_controller",
  "command_id": "open_dialogue",
  "entity_refs": {
    "instigator": "player"
  }
}
```

This is less magical and easier to explain.

## `self` Under The Proposed Model

`self` should remain special.

That means:

- entity-owned command chains still have an automatic owner context
- project-level commands may inherit the current `self` if they were invoked from
  an entity-owned flow

`self` should not be expressed as just another named entry in `entity_refs`.

Reasons:

- it is fundamentally different from passed references
- it always answers a very specific question: "whose entity-owned chain is
  currently running?"
- keeping it separate keeps the model cleaner

So the recommended mental model is:

- `self` = execution owner
- `entity_refs` = explicit passed relationships

That distinction is valuable.

## Readability Rules

Even with good defaults, readability matters.

Recommended style rules:

- if a call site intentionally changes reference semantics in an important way,
  spell out `refs_mode` explicitly
- use meaningful reference names that describe the relationship, not just the
  entity type
- avoid generic names like `ref1`, `thing`, or `entity`
- prefer names like:
  - `switch`
  - `instigator`
  - `speaker`
  - `target_door`
  - `owner`
  - `selected_target`

This style discipline is part of what makes the system understandable.

## Why This Is Better Than `actor` / `caller`

The proposed model is better because it turns hidden roles into explicit named
relationships.

Examples:

- `caller` becomes `switch`, `speaker`, `source_npc`, or `selected_door`
- `actor` becomes `instigator`, `controller`, `player`, or `interactor`

Benefits:

- fewer hardcoded engine concepts
- better local readability
- fewer "what does this special word really mean here?" moments
- better scalability when more than one external entity matters
- easier future extension

## Why This Is Better Than Positional Arrays

Named refs beat arrays because they make meaning visible.

If a command chain needs multiple entities, the names should travel with them.

Bad:

```json
"entity_refs": ["player", "lever_1", "door_3"]
```

Better:

```json
"entity_refs": {
  "player": "player",
  "source_switch": "lever_1",
  "target_door": "door_3"
}
```

The second version is easier to read, debug, migrate, and review.

## Proposed Runtime Semantics

The intended runtime behavior is:

- every executing flow has:
  - optional `self`
  - a named `entity_refs` map
  - normal scalar/list/object runtime params
- the current context is the default for every next command and every child chain
- child chains inherit the parent context unless explicitly changed
- commands that configure child chains may optionally alter the inherited
  `entity_refs` using `refs_mode`
- commands that target another entity may also change `self` for the child chain
  because ownership changed

This makes the system more uniform.

## Migration Strategy

This change is large enough that it should be staged.

### Phase 1: vocabulary and API design

Decide:

- final naming for entity-owned command chains
- final invocation command names
- final `entity_refs` and `refs_mode` schema
- validate the detailed dot-notation proposal against implementation needs

### Phase 2: runtime support

Add:

- internal reference-map support
- new invocation command behavior
- new docs and validation rules

Keep compatibility temporarily where useful.

### Phase 3: compatibility bridge

Add a transitional layer that can still interpret old `events`, `run_event`,
`actor`, and `caller` while warning about deprecation.

Potential transitional behavior:

- old `events` load into the new entity-owned command-chain model
- `caller_entity_id` maps into `entity_refs` with a compatibility name
- `actor_entity_id` maps into `entity_refs` with a compatibility name

This phase exists only to reduce migration pain. It should not become permanent.

### Phase 4: authored content migration

Migrate:

- sample project content
- test content
- internal docs
- authoring guide examples

### Phase 5: remove old concepts

Remove:

- `events` terminology
- `run_event`
- hardcoded `actor`
- hardcoded `caller`

Keep:

- `self`
- explicit named references

## Compatibility Naming Options

If a compatibility bridge is used, the temporary compatibility ref names could
be:

- `caller`
- `actor`

or more explicit compatibility-only names such as:

- `_legacy_caller`
- `_legacy_actor`

The safer option is probably the explicit compatibility names, to avoid letting
old semantics silently become new "official" semantics.

This needs a deliberate choice later.

## Risks And Tradeoffs

### Risk: too much verbosity

If every call site must spell out every ref manually, the system becomes noisy.

Mitigation:

- inherit refs by default
- merge on provided refs by default

### Risk: too much hidden inheritance

If everything always inherits silently, readers may miss where a ref came from.

Mitigation:

- keep destructive modes explicit
- encourage explicit `refs_mode` where it materially affects meaning
- provide tooling or debugging views that show active refs during execution

### Risk: bad reference names

A flexible system can still become unreadable if authors choose poor names.

Mitigation:

- style guidance
- examples
- validation or linting later if needed

### Risk: naming collision with project commands

If entity-owned chains are called `entity_commands`, authors may confuse them
with project command files.

Mitigation:

- choose naming carefully
- document the distinction aggressively

### Risk: partial migration confusion

If old and new systems coexist for too long, the model becomes harder to teach.

Mitigation:

- keep the compatibility window intentionally temporary
- clearly label legacy syntax

## Recommendation Summary

The current strongest recommendation is:

- keep `self`
- remove `actor`
- remove `caller`
- replace special role passing with explicit named `entity_refs`
- use a named map, not an array
- inherit refs by default
- merge when `entity_refs` is provided without a mode
- require explicit `replace` and `clear`
- replace `events` terminology with a clearer entity-owned command-chain model

This keeps the best part of the current ergonomics while making the system more
general and less magical.

## Open Questions

The following points are still open:

- final name for entity-owned named command chains
- final name for the invocation command
- whether project-level `run_command` should be renamed too
- whether compatibility ref names should be preserved during transition
- exactly which composition commands should be allowed to alter refs
- whether ref-map debugging or inspection tooling should be added alongside the
  runtime refactor

## Dot Notation Decisions

The dot-notation redesign is now settled at the design level, even though it is
not implemented yet.

The adopted direction is:

- keep dot notation
- keep `self`
- remove legacy `actor` / `caller`
- remove direct arbitrary-entity access such as `$entity.<entity_id>...`
- support explicit named refs
- expose only `variables` on live entity handles
- expose ref ids separately through `ref_ids`
- keep built-in entity-field access behind explicit query/snapshot helpers

### Main rule

Live entity handles should not expose full raw entity state.

Instead:

- `self` exposes only the current entity's `variables`
- `refs.<name>` exposes only the referenced entity's `variables`
- `ref_ids.<name>` exposes only the referenced entity id string

This means the future design should allow:

- `$self.toggled`
- `$self.inventory.0.item_id`
- `$refs.switch.toggled`
- `$refs.instigator.inventory.selected_slot`
- `$ref_ids.switch`

And it should forbid:

- `$actor...`
- `$caller...`
- `$entity.some_entity...`
- `$self.grid_x`
- `$refs.switch.visible`
- `$ref_ids.switch.foo`

### Query and snapshot interaction

Built-in entity fields should remain available only through explicit selected
plain-data helpers such as:

- `$entity_ref`
- `$entity_at`
- `$entities_at`
- `$entity_query`
- `$entities_query`
- `$area_entity_ref`

Those helpers return plain selected objects rather than live entity handles.
Once such an object is stored into ordinary data, later dot traversal over that
stored plain data is allowed in the normal way.

That means:

- storing a query result snapshot in `self.variables.target_snapshot` and later
  reading `$self.target_snapshot.grid_x` is fine
- reading `$self.grid_x` directly from the live entity is not fine

This distinction is intentional and important.

### Non-entity dot roots

The future design still expects dot notation to remain available for non-entity
public data roots such as:

- `project`
- `current_area`
- `area`
- `camera`
- ordinary runtime param objects/lists

Those roots should keep their own documented public shapes.

### Detailed future spec

The full proposed future dot-notation contract now lives in:

- [dot_notation_future_spec.md](C:/Syncthing/Vault/projects/puzzle_dungeon_v3/python_puzzle_engine/plans/dot_notation_future_spec.md)

That file is intentionally detailed and should be treated as a proposal only.
When the implementation is complete, its normative rules should be moved into
the permanent docs such as `ENGINE_JSON_INTERFACE.md` and
`AUTHORING_GUIDE.md`.
