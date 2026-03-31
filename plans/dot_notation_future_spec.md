# Future Dot Notation Specification

## Status

This document is a proposal, not implemented behavior.

It describes the intended future dot-notation surface after the entity-command
and explicit-reference refactor is implemented.

Nothing in this file should be treated as current engine truth until the runtime
and permanent docs are updated.

When the implementation is complete, the normative parts of this document should
be moved into the permanent docs, primarily:

- `ENGINE_JSON_INTERFACE.md`
- `AUTHORING_GUIDE.md`

At that point, this plan file should either be removed or reduced to a short
historical note.

## Purpose

The current engine already supports runtime tokens and dot notation, but the
current surface is tied to legacy roles such as:

- `actor`
- `caller`
- `$entity.<entity_id>...`

This proposal defines a clearer future model that:

- keeps `self`
- removes legacy `actor` / `caller`
- removes direct arbitrary-entity token access
- supports explicit named references
- keeps dot notation useful without turning the entire entity object into public
  scripting API

## Core Design Decisions

These are the central decisions of the proposed design.

### 1. Dot notation remains available

Dot notation is still valuable in a data-driven engine.

It keeps command JSON readable and avoids replacing every nested read with a
larger explicit helper object.

### 2. Dot notation stays read-only

Dot notation resolves values for use in command data.

It does not:

- mutate state
- expose imperative engine APIs
- replace explicit mutation commands

### 3. `self` remains special

`self` is the only special automatic entity role that remains in the future
model.

It means:

- the current owning entity of the running entity-owned command chain

### 4. Legacy `actor` and `caller` are gone

These are not part of the future design.

The future dot-notation spec does not include:

- `$actor...`
- `$caller...`
- `$actor_id`
- `$caller_id`

If gameplay logic needs those ideas, it should use explicit named refs such as:

- `instigator`
- `switch`
- `speaker`
- `target_door`

### 5. Live entity dot access is limited to `variables`

This is the most important safety rule in the design.

For live entity handles such as:

- `self`
- `refs.<name>`

dot notation exposes only the entity's `variables`.

It does not expose raw built-in entity fields like:

- `entity_id`
- `kind`
- `grid_x`
- `grid_y`
- `pixel_x`
- `pixel_y`
- `visible`
- `present`
- `render_order`
- `movement`
- `animation_playback`
- or any other internal/runtime-only fields

### 6. Explicit id access is separate from variable access

Named refs should support explicit entity-id reads through a separate namespace:

- `ref_ids`

This keeps the meaning clear:

- `refs.<name>` = access the referenced entity's variables
- `ref_ids.<name>` = get the referenced entity's raw id string

### 7. Built-in entity fields must stay explicit

If authored logic needs built-in entity fields, it should use explicit query or
snapshot helpers such as:

- `$entity_ref`
- `$entity_at`
- `$entities_at`
- `$entity_query`
- `$entities_query`
- `$area_entity_ref`

Those helpers already require explicit `select` blocks and return plain data.

That explicitness is good and should remain part of the public contract.

### 8. Query results are plain data, not live handles

Entity query helpers should continue returning selected plain objects, not
live entity handles.

That means:

- dot notation may traverse a stored query result as ordinary data
- but a query result should not become a special live-entity dot root

This distinction prevents the engine from becoming too magical.

## Scope Of This Specification

This spec answers:

- which token roots support dot notation in the future design
- what each allowed root returns
- whether deeper traversal is allowed
- whether list indexes are allowed
- which roots are fixed-shape versus open-ended
- which roots are forbidden
- how query snapshots interact with dot notation

This spec does not define:

- the full mutation-command API
- every possible future query helper
- every validation error message

## General Traversal Rules

These rules apply everywhere dot notation is supported unless a root explicitly
overrides them.

### Object traversal

If the current resolved value is an object/dict, dot notation may descend by
property name.

Example:

- `$project.dialogue.max_lines`

### List traversal

If the current resolved value is a list, dot notation may descend by numeric
index.

Example:

- `$self.inventory.0.item_id`

### Depth

Traversal depth is unbounded in principle.

In practice, authored paths may continue as long as each next step is valid for
the current value.

Examples:

- `$self.puzzle_state.phase`
- `$self.inventory.0.item_id`
- `$project.dialogues.intro.pages.0.text`
- `$current_area.wave_state.enemies_remaining`
- `$camera.follow.mode`

### Invalid traversal

Traversal fails if any step tries to descend into a value that does not support
the requested lookup.

Examples of invalid paths:

- asking for a missing object key
- using a string key on a list
- using a list index on a non-list
- trying to continue past a string, number, boolean, or null

### Supported list indexes

The future public contract should support non-negative numeric indexes.

This document does not promise negative index support for generic dot traversal,
even if individual helpers support negative indexes in their own dedicated API.

## Allowed Dot Roots

The future dot-notation surface should allow the following roots:

- `self`
- `refs.<ref_name>`
- `ref_ids.<ref_name>`
- `project`
- `current_area`
- `area`
- `camera`
- ordinary runtime param names

Each root is defined in detail below.

## `self`

### Meaning

`self` is the current owning entity of the running entity-owned command chain.

### Allowed forms

- `$self`
- `$self.<variable_name>`
- `$self.<nested_path>`

### What `$self` returns

Bare `$self` returns the entire `variables` object of the current entity.

Examples:

- `$self`
- `$self.toggled`
- `$self.puzzle.phase`
- `$self.inventory.0.item_id`

### What may be accessed through `self`

Only the entity's `variables` tree.

This includes:

- scalar variable values
- nested objects inside variables
- lists inside variables
- arbitrarily deep object/list combinations

### What may not be accessed through `self`

Built-in entity fields must not be accessible through `self`.

Forbidden examples:

- `$self.entity_id`
- `$self.kind`
- `$self.grid_x`
- `$self.grid_y`
- `$self.pixel_x`
- `$self.pixel_y`
- `$self.visible`
- `$self.present`
- `$self.render_order`
- `$self.movement`
- `$self.animation_playback`

### Why this restriction exists

This keeps live entity dot access focused on authored gameplay data rather than
turning the whole runtime entity object into public scripting API.

## `refs.<ref_name>`

### Meaning

`refs.<ref_name>` addresses one explicit named entity reference from the current
context.

Examples of ref names:

- `switch`
- `instigator`
- `speaker`
- `target_door`

### Allowed forms

- `$refs.<ref_name>`
- `$refs.<ref_name>.<variable_name>`
- `$refs.<ref_name>.<nested_path>`

### What `$refs.<ref_name>` returns

Bare `$refs.<ref_name>` returns the referenced entity's entire `variables`
object.

Examples:

- `$refs.switch`
- `$refs.switch.toggled`
- `$refs.instigator.inventory.selected_slot`
- `$refs.target_door.lock.required_key`

### What may be accessed through `refs.<ref_name>`

Only the referenced entity's `variables` tree.

This includes:

- scalar variable values
- nested objects inside variables
- lists inside variables
- arbitrarily deep object/list combinations

### What may not be accessed through `refs.<ref_name>`

Built-in entity fields must not be accessible through live refs.

Forbidden examples:

- `$refs.switch.entity_id`
- `$refs.switch.kind`
- `$refs.switch.grid_x`
- `$refs.switch.grid_y`
- `$refs.switch.pixel_x`
- `$refs.switch.visible`
- `$refs.switch.present`
- `$refs.switch.render_order`

### Why `refs.<name>.id` is not part of the design

The design deliberately avoids mixing raw-id access into the live variable
namespace.

If `.id` were added here, it would create a muddy hybrid where:

- most paths mean variable access
- but some reserved paths mean special built-in metadata

That would create pressure to add more special fields later and weaken the
variables-only rule.

## `ref_ids.<ref_name>`

### Meaning

`ref_ids.<ref_name>` returns the raw entity id string of a named ref.

### Allowed forms

- `$ref_ids.<ref_name>`

### What `$ref_ids.<ref_name>` returns

A string entity id.

Examples:

- if `switch -> "lever_1"`, then `$ref_ids.switch` returns `"lever_1"`
- if `instigator -> "player"`, then `$ref_ids.instigator` returns `"player"`

### Depth

`ref_ids` is one level only.

Allowed:

- `$ref_ids.switch`

Forbidden:

- `$ref_ids.switch.foo`
- `$ref_ids.switch.0`

### Why depth stops there

`$ref_ids.<ref_name>` resolves to a string, not an object.

Allowing deeper access would either be nonsensical or would secretly re-resolve
the string back into a live entity, which would make the API magical again.

### Main purpose

This root exists for cases where authored logic needs the explicit id string for
another command field.

Examples:

```json
{
  "type": "set_entity_var",
  "entity_id": "$self_id",
  "name": "last_switch_id",
  "value": "$ref_ids.switch"
}
```

```json
{
  "type": "set_entity_field",
  "entity_id": "$ref_ids.switch",
  "field_name": "visible",
  "value": false
}
```

## `project`

### Meaning

`project` exposes shared project-level data.

### Allowed forms

- `$project`
- `$project.<path>`

### What `$project` returns

Bare `$project` returns the root shared project data object.

### Shape

Open-ended.

The structure is defined by the shared project data itself.

### Depth

Arbitrary object/list traversal is allowed.

Examples:

- `$project.dialogue.max_lines`
- `$project.display.internal_width`
- `$project.some_list.0`
- `$project.npc_tables.shopkeeper.0.name`

## `current_area`

### Meaning

`current_area` exposes the live current-area runtime variable store for the
active play session.

### Allowed forms

- `$current_area`
- `$current_area.<path>`

### What `$current_area` returns

Bare `$current_area` returns the root current-area runtime variable object.

### Shape

Open-ended.

It reflects the live current-area variable store.

### Depth

Arbitrary object/list traversal is allowed.

Examples:

- `$current_area.puzzle_state.phase`
- `$current_area.opened_doors.0`
- `$current_area.counters.moves`

## `area`

### Meaning

`area` exposes stable metadata about the currently loaded area.

### Allowed forms

- `$area`
- `$area.<field>`
- `$area.camera`
- `$area.camera.<nested_path>`

### What `$area` returns

Bare `$area` returns a fixed-shape public area metadata object.

### Public top-level fields

The planned public top-level area fields are:

- `area_id`
- `name`
- `tile_size`
- `width`
- `height`
- `pixel_width`
- `pixel_height`
- `camera`

### Shape

Fixed-shape at the top level.

The `camera` field is a plain authored camera-default object. Traversal inside
that object follows the area camera-default data shape rather than raw runtime
internals.

### Examples

- `$area.area_id`
- `$area.name`
- `$area.tile_size`
- `$area.width`
- `$area.height`
- `$area.pixel_width`
- `$area.pixel_height`
- `$area.camera`

### Forbidden examples

- `$area.some_random_internal_field`
- `$area.entities`
- `$area.cell_flags`

Those would expose too much runtime or authored surface through one generic
root.

## `camera`

### Meaning

`camera` exposes live runtime camera state.

### Allowed forms

- `$camera`
- `$camera.<field>`
- `$camera.follow.<field>`
- `$camera.bounds.<field>`
- `$camera.deadzone.<field>`

### What `$camera` returns

Bare `$camera` returns a fixed-shape public camera state object.

### Public top-level camera fields

The planned public top-level camera fields are:

- `x`
- `y`
- `follow`
- `bounds`
- `deadzone`
- `has_bounds`
- `has_deadzone`

### Public `follow` fields

- `mode`
- `entity_id`
- `action`
- `offset_x`
- `offset_y`

### Public `bounds` fields

When `bounds` is present and non-null:

- `x`
- `y`
- `width`
- `height`

### Public `deadzone` fields

When `deadzone` is present and non-null:

- `x`
- `y`
- `width`
- `height`

### Shape

Fixed-shape public object.

### Examples

- `$camera.x`
- `$camera.y`
- `$camera.follow.mode`
- `$camera.follow.entity_id`
- `$camera.follow.action`
- `$camera.follow.offset_x`
- `$camera.follow.offset_y`
- `$camera.bounds`
- `$camera.bounds.width`
- `$camera.deadzone.height`
- `$camera.has_bounds`
- `$camera.has_deadzone`

### Forbidden examples

- `$camera.some_internal_runtime_object`
- `$camera.follow.some_internal_field`

Only the documented public camera state should be available.

## Ordinary Runtime Params

### Meaning

Ordinary runtime params are plain values passed into the current chain.

These may come from:

- command-call params
- project command params
- collection-loop item params
- dialogue/menu payload objects
- stored snapshots or other authored plain data

### Allowed forms

- `$param_name`
- `$param_name.<path>`

### Shape

Open-ended.

These are plain data values, not special engine namespaces.

### Depth

Arbitrary object/list traversal is allowed as long as each step is valid for the
current value.

Examples:

- `$dialogue_payload.title`
- `$dialogue_payload.options.0.option_id`
- `$query_result.entity_id`
- `$query_results.0.kind`

## Query And Snapshot Helpers

The following explicit helpers remain important in the future design:

- `$entity_ref`
- `$area_entity_ref`
- `$entity_at`
- `$entities_at`
- `$entity_query`
- `$entities_query`

These are not dot roots.

They are structured value sources that produce plain selected data.

### Core rule

Query helpers return plain selected objects or lists of plain selected objects.

They do not return live entity handles.

### Why this matters

This means a query result can be traversed with dot notation only after it is
being treated as ordinary data.

Good example:

```json
{
  "type": "set_entity_var",
  "entity_id": "$self_id",
  "name": "target_snapshot",
  "value": {
    "$entity_at": {
      "x": "$self.target_x",
      "y": "$self.target_y",
      "index": 0,
      "select": {
        "fields": ["entity_id", "kind", "grid_x", "grid_y"],
        "variables": ["toggled"]
      },
      "default": null
    }
  }
}
```

Later, because `target_snapshot` is now just plain stored data, these are valid:

- `$self.target_snapshot.entity_id`
- `$self.target_snapshot.kind`
- `$self.target_snapshot.grid_x`
- `$self.target_snapshot.grid_y`
- `$self.target_snapshot.toggled`

### Important distinction

The allowed reads above are okay because they are reading a stored snapshot
object, not a live entity handle.

That is very different from allowing:

- `$refs.switch.grid_x`
- `$self.visible`

The snapshot path is explicit and selected.
The live-handle path would be magical and overly broad.

## Binding Query Results Into Named Refs

One useful future pattern is to allow explicit binding of queried entities into
named refs at flow boundaries.

Example:

```json
{
  "type": "run_entity_command",
  "entity_id": "door_1",
  "command_id": "open",
  "entity_refs": {
    "switch": {
      "$entity_at": {
        "x": 10,
        "y": 4,
        "index": 0,
        "select": {
          "fields": ["entity_id"]
        },
        "default": null
      }
    }
  }
}
```

This pattern is not implemented today, but it is a good future direction.

The important design rule is:

- query first
- bind explicitly to a named ref
- then access through the normal ref model

This is much cleaner than making anonymous query outputs into live magical dot
roots.

## Explicitly Forbidden Future Roots And Forms

The future design should explicitly forbid these legacy or overly broad forms:

- `$actor...`
- `$caller...`
- `$entity.<entity_id>...`
- `$self.<built_in_entity_field>`
- `$refs.<name>.<built_in_entity_field>`
- `$ref_ids.<name>.<anything_more>`

Concrete forbidden examples:

- `$actor.inventory_key`
- `$caller.toggled`
- `$entity.door_1.locked`
- `$self.grid_x`
- `$self.visible`
- `$refs.switch.kind`
- `$refs.target.pixel_x`
- `$ref_ids.switch.foo`

## Why Full Live-Entity Exposure Is Rejected

The design deliberately rejects "just expose everything on the entity."

Reasons:

- it would turn the entity's full internal shape into public authoring API
- it would blur the line between authored gameplay data and engine runtime state
- it would make internal refactors much harder
- it would create collisions between variables and engine-owned fields
- it would create constant pressure to allow more hidden magical access

The safer design is:

- live entity handles expose only `variables`
- engine-owned fields remain behind explicit query/snapshot mechanisms

## Quick Reference Summary

### Allowed live-handle dot access

- `$self`
- `$self.<variable_path>`
- `$refs.<ref_name>`
- `$refs.<ref_name>.<variable_path>`

### Allowed explicit id access

- `$ref_ids.<ref_name>`

### Allowed open-ended plain-data roots

- `$project`
- `$project.<path>`
- `$current_area`
- `$current_area.<path>`
- `$param_name`
- `$param_name.<path>`

### Allowed fixed-shape public roots

- `$area`
- `$area.<public_field>`
- `$camera`
- `$camera.<public_field>`

### Allowed deep traversal

- object property chaining
- list indexing
- mixed object/list traversal

### Forbidden live-handle field access

- direct built-in entity fields through `self` or `refs`
- raw arbitrary-entity lookup roots like `$entity.<id>...`
- legacy `actor` / `caller` roots

## Examples

### Good examples

```json
"$self.toggled"
```

```json
"$refs.switch.puzzle.color"
```

```json
"$ref_ids.switch"
```

```json
"$project.dialogue.max_lines"
```

```json
"$current_area.wave_state.enemies_remaining"
```

```json
"$area.tile_size"
```

```json
"$camera.follow.mode"
```

```json
"$dialogue_payload.options.0.option_id"
```

```json
"$self.target_snapshot.entity_id"
```

### Bad examples

```json
"$actor.choice"
```

```json
"$caller.source_color"
```

```json
"$entity.door_1.locked"
```

```json
"$self.grid_x"
```

```json
"$refs.switch.visible"
```

```json
"$ref_ids.switch.foo"
```

## Final Recommendation

The recommended future public contract is:

- keep dot notation
- keep `self`
- remove legacy `actor` / `caller`
- use explicit named refs
- expose only `variables` on live entity handles
- expose ref ids separately through `ref_ids`
- keep explicit query/snapshot helpers for built-in entity fields
- allow deep traversal for plain data and documented public objects
- do not expose raw full live entities through dot notation

This gives the engine a useful and ergonomic read surface without turning the
entire runtime object graph into implicit scripting API.
