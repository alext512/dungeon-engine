# Asset Registry Ideas

## Purpose

This note captures an idea for making project JSON organization more flexible
without turning the engine into chaos. It is not a final design. It is a place
to resume the discussion later.

## Why This Came Up

Right now different asset types are discovered differently:

- commands are scanned recursively from configured command folders
- dialogue files are scanned recursively from configured dialogue folders
- areas are typically referenced by path
- entity templates are more limited in how they are found

This makes project organization harder than it should be. It also encourages
folder structures that exist for the engine's sake instead of the author's sake.

The broader goal is:

- organize JSON files in a way that makes sense to a project author
- keep reusable content reusable
- keep area-specific content close to the area that uses it
- reduce hardcoded assumptions about folder layout

## Core Idea

When a project starts, the engine loads the JSON assets from the directories
listed in `project.json`, assigns them IDs, and keeps them in memory.

That means:

- assets are referenced primarily by ID, not by exact path
- folder layout becomes more flexible
- moving files around should be less painful

This idea assumes that each loadable JSON asset has an explicit `id` field.

## Important Clarification

This does **not** mean:

- every JSON becomes the same thing
- every system can freely read every field of every loaded asset
- there is one giant untyped global pool

The engine can still keep different registries for different asset kinds, or at
least validate assets differently after loading them.

The point is to make discovery and reference more uniform, not to remove all
structure.

## Desired Benefits

### 1. Flexible Organization

Authors should be able to organize content by actual use:

- shared content in shared folders
- area-specific content near the area
- puzzle-specific content near the puzzle

Instead of forcing everything into a few rigid top-level directories.

### 2. Stable References

If assets are referenced by `id`, then moving a file should not require
rewriting every reference to it.

### 3. More Consistent Engine Rules

Commands, entity templates, dialogue/data assets, prefabs, and perhaps even
areas should follow a more consistent discovery model.

## Main Risk

If every loaded asset can freely access every field from every other loaded
asset, the project can become messy very quickly.

Problems could include:

- hidden coupling
- unclear dependencies
- harder debugging
- accidental ID collisions
- assets depending on internal fields that were never meant to be public

So if we move toward an asset-registry model, we should also think carefully
about access rules.

## Possible Guardrails

These are ideas, not decisions.

### Option A: Typed Registries

Keep separate registries internally, even if discovery becomes more uniform.

Example mental model:

- entity registry
- command registry
- area registry
- data/dialogue registry
- prefab registry

This keeps validation clearer and reduces ambiguity.

### Option B: Explicit Public Data

Allow assets to expose only a public section for cross-asset access.

Example:

```json
{
  "id": "dialogue/village_guard_warning",
  "text": "Stop right there.",
  "speaker_name": "Village Guard",
  "public": {
    "speaker_name": "Village Guard"
  }
}
```

Then generic access could be limited to `public.*`, not every internal field.

### Option C: Explicit Read Commands

Do not allow totally free access. Instead, provide specific commands or helpers
 for reading asset data when needed.

This is stricter, but may keep projects more understandable.

## Questions — Resolved

1. **Should all loadable JSON assets require an explicit `id` field?**
   No. IDs are path-derived (file path relative to type root, minus `.json`).
   Explicit `id` fields are redundant and create a second source of truth.
   The command system already validates that declared IDs match path-derived
   IDs and rejects mismatches.

2. **Should areas also be referenced by ID instead of by path?**
   Yes. Implemented. Areas now support ID-based references via `area_id` in
   commands and `resolve_area_reference()` in the project context. Save data
   stores area IDs instead of filesystem paths, making saves portable.
   Legacy path-based references still work for backward compatibility.

3. **Should dialogues remain their own asset kind, or should they be treated as
   a more general data asset?**
   Keep them as their own kind. They have specific validation (speaker,
   text/pages) and the separation gives translators a clean folder of all
   game text. Dialogues can also be inlined in commands via `text`/`pages`
   parameters, so the separate file is optional when reuse is not needed.

4. **Should entity templates become recursive and ID-based like commands
   already are?**
   Yes. Implemented. Entity templates now use recursive scanning with
   path-derived IDs (e.g., `"npcs/village_guard"`), startup validation,
   and duplicate detection — matching the command library pattern.

5. **How much generic cross-asset access is healthy before things become too
   coupled?**
   None beyond what exists today. Each system loads its own type. Commands
   reference other commands by ID, dialogues are loaded by the dialogue
   system. There is no cross-type field access and none is needed.

6. **Do we want one unified discovery mechanism with type-specific validation,
   or something even more general?**
   Unified discovery pattern (recursive scan, path-derived ID, duplicate
   check), but type-specific validation. Not a generic registry. Each type
   has its own module: `library.py` for commands, `dialogue_library.py` for
   dialogues, `loader.py` for entities, `project.py` for areas.

7. **How should the engine report duplicate IDs clearly?**
   Already solved. All types now detect duplicates at startup and raise
   descriptive errors listing the conflicting file paths.

## Chosen Direction

The implemented approach is:

- IDs are path-derived, not author-declared
- all JSON content types now use the same discovery pattern: recursive scan,
  path-derived ID, duplicate detection, in-memory cache
- areas and entities were brought up to the standard already set by commands
  and dialogues
- type-specific modules are kept separate (no unified registry class)
- backward compatibility is maintained for legacy path-based references
- `CONTENT_TYPES.md` documents the full system

## Non-Goal

This note is **not** proposing that the engine blindly treats every JSON file as
the same schema.

The goal is:

- more flexible discovery
- more stable references
- better organization

while still keeping the project understandable and debuggable.
