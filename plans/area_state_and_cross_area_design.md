# Area State, Cross-Area Access, And Naming Notes

This note collects the recent design discussion about:

- the misleading `world` variable naming
- current-area runtime state vs truly global state
- persistence semantics
- cross-area variable/entity access
- cross-area querying
- globals and travelers
- why travelers exist as a separate runtime/persistence concept
- likely next API steps
- other still-pending engine/API issues

The goal is to preserve the reasoning, not just the final conclusions, so future work can follow the same logic instead of rediscovering it.

## Current Implementation Status

Implemented:

- `set_current_area_var`
- `add_current_area_var`
- `toggle_current_area_var`
- `set_current_area_var_length`
- `append_current_area_var`
- `pop_current_area_var`
- `check_current_area_var`
- `$current_area...`
- `set_area_var`
- `set_area_entity_var`
- `set_area_entity_field`
- `$area_entity_ref`

Current first-pass cross-area semantics:

- reads use area-owned state only
- data source = authored area entities + that area's persistent overrides
- no globals
- no travelers
- cross-area writes are always persistent
- if the target area is the currently loaded area, live runtime is also updated when possible

## Current Reality

### `set_world_var` Is Not Really "Global"

The current command family:

- `set_world_var`
- `add_world_var`
- `toggle_world_var`
- `set_world_var_length`
- `append_world_var`
- `pop_world_var`
- `check_world_var`

does **not** mean "global across the whole game/session" in the ordinary human sense of "world".

In normal play, this family operates on the active runtime `world.variables` store, and persistence stores that under the **current area's** state. So in practice these are **current-area runtime variables**, not universal global variables.

That means this mental model is correct:

- `set_world_var("gate_open", true)`
  - really means: set a runtime variable for the **currently active area/session state**

This mental model is **incorrect**:

- `set_world_var("gate_open", true)`
  - means: set one universal variable shared by all areas forever

This mismatch is why the naming now feels misleading.

### Globals Are A Different Concept

The engine also has **global entities**:

- `scope: "global"`

These are different from current-area vars.

Global entities:

- are installed into the live world regardless of which area is loaded
- are session-wide runtime entities
- are not simply "variables attached to the world"

So the word "global" already means something else in the engine.

## Agreed Rename Direction

We agreed that the current `world`-var family should be renamed to reflect its true meaning.

### Recommended rename

- `set_world_var` -> `set_current_area_var`
- `add_world_var` -> `add_current_area_var`
- `toggle_world_var` -> `toggle_current_area_var`
- `set_world_var_length` -> `set_current_area_var_length`
- `append_world_var` -> `append_current_area_var`
- `pop_world_var` -> `pop_current_area_var`
- `check_world_var` -> `check_current_area_var`

This would make the current contract much clearer:

- current-area runtime state is current-area state
- truly global entities remain "global"

### Token rename

The current token family is:

- `$world...`

This was also misleading for the same reason. The authored token family has now been renamed to:

- `$current_area...`

## Persistence Semantics

### Who chooses whether something is persistent?

The current model is:

- **the command that performs the mutation chooses**
- `persistent: true` means save the change
- omitted / `false` means runtime-only

Example:

```json
{
  "type": "set_entity_var",
  "entity_id": "lever_1",
  "name": "toggled",
  "value": true,
  "persistent": true
}
```

This means:

- update runtime now
- also write the change into persistent state

Without `persistent: true`, the same command changes only the live runtime.

### Is this a good design?

We concluded that this is **okay** and probably should stay.

Reasoning:

- persistence here is more naturally a property of the **write operation**
- it keeps authoring explicit at the mutation site
- it avoids inventing a variable declaration system just to say whether a variable is saved
- it fits generic mutation commands well

The downside is:

- the same variable could accidentally be written persistently in one place and transiently in another

So the current guidance should be:

- keep each important variable **consistently** persistent or transient
- treat that as an authoring convention
- later, optionally add linting if inconsistency becomes a real pain point

Example convention:

- puzzle progress flags:
  - usually persistent
- temporary UI/controller helpers:
  - usually transient

## Current Cross-Area Limitation

An entity in area A cannot directly target a normal entity that only exists in unloaded area B.

Today, normal entity lookup is by:

- `entity_id`

and that lookup resolves only against the live runtime world:

- current area entities
- global entities

There is **no** built-in current API of the form:

- `(area_id, entity_id)`

So commands like these do **not** directly reach into another unloaded area:

- `set_entity_var`
- `set_entity_field`
- `run_event`
- `$entity_ref`
- `$entity_at`
- `$entities_at`

## Important Distinction: Live Cross-Area Communication vs Cross-Area Persistent State

We concluded that:

- **live cross-area command execution** is a bad direction
- **cross-area persistent/authored state access** is a legitimate missing feature

### Bad idea

Things we do **not** want:

- run events in an unloaded area
- animate/tween entities in an unloaded area
- let JSON pretend there are multiple simultaneously live worlds

### Good idea

Things that make sense:

- query what another area's state currently is
- set area-level state for another area
- set entity vars/fields for an entity in another area
- let those changes become visible when that area is loaded

This means the right model is:

- **cross-area state API**
- not **cross-area live runtime API**

## Proposed Cross-Area API Family

### Area-level state

Potential commands:

- `set_area_var(area_id, name, value)`
- `add_area_var(area_id, name, amount?)`
- `toggle_area_var(area_id, name)`
- `check_area_var(area_id, name, op?, value?, then?, else?)`

These would target the runtime/persistent state of a **specific area by `area_id`**.

Example:

```json
{
  "type": "set_area_var",
  "area_id": "village_square",
  "name": "bridge_lowered",
  "value": true
}
```

This is useful when the state belongs to the room as a whole rather than a specific entity.

### Entity-level cross-area state

Potential commands:

- `set_area_entity_var(area_id, entity_id, name, value)`
- `add_area_entity_var(area_id, entity_id, name, amount?)`
- `toggle_area_entity_var(area_id, entity_id, name)`
- `set_area_entity_field(area_id, entity_id, field_name, value)`
- maybe later `set_area_entity_fields(...)`

These would not mean "mutate a live unloaded entity". They would mean:

- update the target area's authored/persistent state for that entity

Example:

```json
{
  "type": "set_area_entity_field",
  "area_id": "dungeon_b",
  "entity_id": "gate_1",
  "field_name": "present",
  "value": false
}
```

Semantically this means:

- when `dungeon_b` is loaded, `gate_1` should be absent

## Proposed Cross-Area Query Family

### Entity-by-id query

Strong first-pass candidate:

- `"$area_entity_ref"`

Example:

```json
{
  "$area_entity_ref": {
    "area_id": "dungeon_b",
    "entity_id": "gate_1",
    "select": {
      "fields": ["entity_id", "grid_x", "grid_y", "present"],
      "variables": ["locked"]
    },
    "default": null
  }
}
```

This would be the cross-area counterpart to `"$entity_ref"`.

### Possible later query family

- `"$area_entities_at"`
- `"$area_entity_at"`
- `"$area_entities_query"`
- `"$area_entity_query"`

These would mirror the same-area query shape:

- `select`
- `where`
- `index`
- `default`
- ordering

For **queries**, copying the same schema is probably the best design, as long as we clearly define what the source data means.

## A Key Semantic Question

When querying another area, what exactly are we querying?

There are two different answers.

### Simpler interpretation

Query only:

- area-scoped authored entities for that area
- plus that area's own persistent overrides

Meaning:

- no global entities
- no travelers currently visiting the area

This answers:

- "what does this area itself own?"

### Richer interpretation

Query:

- authored area entities
- plus area-specific persistent overrides
- plus global entities
- plus travelers currently in that area
- minus authored placeholders suppressed by travelers being away

This answers:

- "what would this area actually contain right now if I loaded it?"

This is the stronger, more complete interpretation.

## Why The Two Interpretations Are Different

Example:

Area B authored entities:

- `gate_1`
- `shopkeeper`

There is also:

- a global entity `weather_controller`
- a traveler `player` currently in area B

Then:

### Simpler query result

You would see:

- `gate_1`
- `shopkeeper`

### Richer query result

You would see:

- `gate_1`
- `shopkeeper`
- `weather_controller`
- `player`

That is why "query another area's state" and "query the full session contents of another area" are not the same thing.

## Globals And Travelers

### Globals

Global entities:

- are session-wide runtime entities
- are installed regardless of which area is loaded
- are not ordinary local area entities

So if a future helper says:

- "scan tile `(x, y)` in area B"

then whether globals appear depends on semantics:

- if the query is area-only: no
- if the query is "full resolved room contents": yes

### Travelers

Travelers are not the same as globals.

Travelers:

- begin as ordinary area entities
- then are transferred across areas
- keep one ongoing session identity
- are tracked separately from ordinary area persistence

What matters for travelers is **where they are now**, not their authored home area.

So for a "full resolved contents of area B right now" query:

- travelers whose current area is B should appear

For an "area-owned persistent data only" query:

- they should not

## Why Travelers Exist As A Separate Concept

At one point, the question came up:

- why not simply destroy the entity in area A and recreate it in area B?

That can indeed solve some individual problems, for example:

- preventing the authored placeholder from respawning in the origin room

But travelers still exist because the engine wants to model:

- one moving session entity
- not a chain of unrelated area-local copies

### Reasons travelers help

1. **One continuous session identity**

The same moved entity persists across:

- A -> B -> C
- save/load
- repeated transfers

2. **Centralized current location**

Traveler data records:

- where the entity currently is

instead of scattering that across multiple area-local mutations.

3. **Origin suppression**

If a traveler started as an authored entity in area A, the engine can suppress that authored placeholder while the traveler is away.

4. **Return behavior**

When it comes back, the engine still knows it is the same moved entity, not a fresh spawned copy.

5. **Cleaner save/load**

The engine can restore one moving entity in the correct current area without reconstructing that from layered destroy/spawn breadcrumbs.

6. **Avoid fragmented bookkeeping**

Without travelers, repeated moves could become a trail of:

- removed in A
- spawned in B
- removed in B
- spawned in C

Traveler state collapses that into one moving record.

### Stable identity link

One phrase that came up in discussion was:

- "stable identity link"

What this means:

- the engine wants the moved thing to still be recognized as the same ongoing entity across transfers

That matters because normal runtime references are by:

- `entity_id`

not by:

- `(area_id, entity_id)`

So traveler state helps preserve:

- one moving session entity
- one coherent identity over time

rather than treating every transfer as just another local copy.

## So What Should Cross-Area Queries Probably Mean?

This was the point of most of the confusion.

If the real feature we want is:

- "query what area X would actually contain right now in this session"

then the helper must use more than just per-area persistence.

It must reconstruct the target area using the same ideas the engine uses at load time:

1. authored defaults for target area
2. target area's persistent overrides
3. current global entities
4. current travelers whose `current_area == target_area`
5. suppression of authored placeholders replaced by those travelers

This is not impossible.

But it is a bigger and more meaningful feature than simply:

- "read another area's persistent override dict"

It is really:

- **virtual area resolution without switching areas**

That is probably the best long-term semantics for rich cross-area queries.

## Recommended First-Step Strategy

To avoid doing everything at once, the safest progression is probably:

### Phase 1

Do the rename for current-area vars:

- `set_current_area_var`
- `add_current_area_var`
- etc.

This cleans up the naming problem immediately.

### Phase 2

Add simple area-targeted state access by explicit ids:

- `set_area_var`
- `set_area_entity_var`
- `set_area_entity_field`
- `"$area_entity_ref"`

This solves the most common cross-area use cases cleanly:

- "open gate in area B"
- "set flag in area C"
- "check whether NPC X in area D is already moved/disabled"

### Phase 3

If needed, add broader cross-area query helpers:

- `"$area_entities_at"`
- `"$area_entity_at"`
- maybe `"$area_entities_query"`
- maybe `"$area_entity_query"`

And explicitly decide whether they mean:

- area-owned state only
- or fully resolved target area contents

My current leaning is:

- richer resolved-contents semantics are probably better
- but only if we implement them intentionally, not accidentally

## Recommended API Shape For Cross-Area Queries

For query helpers, the best design is probably:

- keep the **same schema shape** as current same-area queries
- add `area_id`
- clearly document the data source

Example:

```json
{
  "$area_entity_at": {
    "area_id": "dungeon_b",
    "x": 10,
    "y": 4,
    "index": 0,
    "where": {
      "kind": "door"
    },
    "select": {
      "fields": ["entity_id", "present"],
      "variables": ["locked"]
    },
    "default": null
  }
}
```

This should feel familiar to authors and agents.

## One Important Difference Between Same-Area And Cross-Area APIs

For **queries**, copying the same shape is good.

For **writes**, blindly copying the same semantics is less good.

Why:

- same-area mutation commands affect a live runtime immediately, and may optionally persist
- for another unloaded area, there is no meaningful "live mutation now"

So cross-area mutation commands should probably be defined as:

- persistent/authored-state edits for another area

not:

- live commands on an absent world

## Pending Issues (Current Shortlist)

The following items were still pending or deferred when this note was written.

### High-priority conceptual follow-ups

1. **Rename current-area var family**

- rename `world`-var commands to `current_area` equivalents
- consider token rename later

2. **Cross-area state access**

- area vars
- area entity vars
- area entity fields
- area entity refs

3. **Define semantics for richer cross-area queries**

- area-only state
- vs fully resolved target area contents

### Lower-priority / deferred items

4. **Richer screen/runtime effects**

- fade
- shake
- particles

These were considered useful later, but not urgent now.

5. **Richer visual/runtime presentation**

- easing / non-linear interpolation
- more presentation polish helpers later if needed

6. **Richer audio polish**

- crossfade
- master volume
- more advanced track state if needed later

Current audio support is already good enough for a real game.

7. **String/text helpers**

- only if content authoring starts demanding them

Examples:

- substring
- contains
- simple formatting/interpolation

## Practical Design Principles To Preserve

Throughout this discussion, several principles kept recurring. They are worth preserving:

1. **Avoid re-centralizing gameplay logic in Python**

- queries/helpers are fine
- opaque gameplay-policy commands are not the goal

2. **Prefer structured public surfaces over arbitrary deep-path mutation**

- reads: structured `select`
- writes: structured mutation sections

3. **Keep current-area/live-world APIs separate from cross-area/persistent-state APIs**

This avoids semantic confusion.

4. **Keep identity and ownership semantics explicit**

- area entities
- global entities
- travelers

These should not blur together accidentally.

5. **Use the same JSON shape where possible**

For authoring ergonomics:

- same `select`
- same `where`
- same `index/default`
- same ordering semantics

6. **Be explicit when semantics differ**

If a cross-area helper means:

- "resolved target room contents"

that should be documented loudly.

## Current Best Guess At The Long-Term Direction

If the engine keeps moving in the same direction, the most coherent end state likely looks like this:

- current-area state has clear names (`current_area_var`)
- same-area entity queries remain live-world queries
- cross-area queries become read-only "resolved area state" helpers
- cross-area mutations become explicit persistent/authored-state edit commands
- globals and travelers are included only when the helper's semantics explicitly say they should be

That would preserve:

- explicitness
- data-driven authoring
- separation between runtime orchestration and gameplay policy
- clean mental models for area-local vs cross-area state

---

## External Review Notes

The following section was added after a full codebase review, as input for future implementation work.

### Overall Assessment

The design above is well-reasoned and the phased plan is sound. The engine architecture (layered persistence, command-driven gameplay, traveler system) supports the proposed direction cleanly. A few specific observations follow.

### Query Semantics: Default To Simple, Extend Later

The doc leans toward "richer" resolved-contents semantics for cross-area queries (authored entities + persistent overrides + globals + travelers + suppression). This is the more powerful interpretation, but it's also harder to reason about as an author because the result depends on session state.

**Agreed approach:** start with the simpler interpretation — area-owned state only (authored entities + that area's persistent overrides). This answers "what does this area itself own?" which is stable and predictable.

To keep the door open for the richer interpretation later, the recommended design is:

- Default cross-area queries return area-owned state only
- Add an optional `resolved: true` parameter that triggers full area resolution (globals, travelers, suppression)
- The `resolved` path uses the same logic the engine uses at area load time, applied read-only to the target area
- Document the distinction clearly: "area-owned" vs "resolved contents"

This way the simple case ships first and stays the default, but the richer semantics are a backward-compatible addition when needed — not a redesign.

### Token Rename Is A Clean Break

The `$world...` → `$current_area...` token rename can be done as a straight replacement with no compatibility layer. The only authored content is the small test project bundled in the repo, so there is no external migration burden. Just rename the tokens in the engine and update the test project content to match.

### Cross-Area Writes Are Implicitly Persistent

The doc correctly identifies that cross-area mutations can only mean "write to persistent state" since there is no live runtime for an unloaded area. This is actually simpler than same-area commands, which have the `persistent: true/false` duality.

Worth making this explicit in the API contract:

- `set_area_var`, `set_area_entity_var`, `set_area_entity_field` — always persistent, no `persistent` flag needed
- Document that these commands edit the save-state layer for the target area
- If the target area happens to be the currently loaded area, the command should also update the live runtime (otherwise the persistent and runtime states would diverge until the next area reload)

That last point — "what if the target area is the current area?" — is a small but important edge case to handle explicitly.

### Implementation Concern: Writes To Unloaded Areas

The current `PersistenceRuntime` is oriented around the currently-loaded area. Cross-area write commands (Phase 2) will need to write persistent overrides for areas that have no authored baseline in memory.

This should be straightforward because `SaveData.areas` is a dict of `PersistentAreaState` keyed by `area_id` — writing an override just means ensuring the target area's entry exists in that dict and updating it. No need to load the full area JSON. But it's worth verifying that:

- `PersistentAreaState` can be created/updated without the area being loaded
- Entity-level overrides for unloaded areas don't require the entity's authored baseline to validate against (they're just stored and applied later at load time)

If those hold (and from reading `persistence.py` they should), then Phase 2 writes are a clean addition to the existing persistence layer.

### The Traveler System Is Sound

The doc's explanation of why travelers exist as a separate concept (rather than destroy+recreate) is convincing. The stable identity link matters for:

- Save/load round-tripping without reconstructing from breadcrumbs
- Future cross-area queries that ask "where is entity X right now?"
- Origin suppression without fragmented bookkeeping

No changes recommended here.

### Summary Of Recommended Implementation Order

1. **Phase 1**: Rename `world`-var commands to `current_area` equivalents. Rename `$world...` tokens to `$current_area...` and update the test project content. This is pure cleanup with no compatibility concerns.

2. **Phase 2**: Add cross-area state commands (`set_area_var`, `set_area_entity_var`, `set_area_entity_field`). These are always-persistent writes to `SaveData.areas[target_area_id]`. Handle the "target is current area" edge case by also updating the live runtime. Add `$area_entity_ref` as the first cross-area query (area-owned state only by default).

3. **Phase 3**: Add broader cross-area query helpers (`$area_entities_at`, `$area_entity_at`, etc.) with area-owned-state-only as the default. Add `resolved: true` option for full area resolution when the need arises.
