# Content Type ID System — Implementation Record

## Status: Completed

This plan was implemented in full. It is kept here as a reference for the
decisions made and the reasoning behind them.

## Context

The engine has 5 content types (areas, entities, commands, dialogues, assets)
but they were discovered and referenced inconsistently. Commands and dialogues
already used clean ID-based references with recursive scanning. Entities and
areas did not — entities used flat filename stems, areas used fragile filesystem
paths. This made project reorganization painful and caused area paths to leak
into save data.

## What Was Done

### 1. Documentation — `CONTENT_TYPES.md`

Created a comprehensive reference document covering:

- How `project.json` connects the engine to project content
- The path-derived ID system used by all JSON content types
- Per-type deep dive with JSON examples and loading details
- The inline/reference pattern (inline for one-off, reference for reuse)
- How content types reference each other

### 2. Entity Template Loading Upgrade

**Problem:** Entity templates used flat `stem`-only lookup, no recursive scan,
no startup validation, no duplicate detection. Could not organize into
subfolders.

**Solution:** Mirrored the command library pattern.

Files modified:

- `dungeon_engine/project.py` — added `entity_template_id()`,
  `list_entity_template_files()`, `find_entity_template_matches()` to
  `ProjectContext`. Updated `find_entity_template()` to use ID-based lookup
  with duplicate detection.
- `dungeon_engine/world/loader.py` — updated `_load_entity_template()` to
  normalize IDs and support subdirectory paths. Added
  `EntityTemplateValidationError`, `validate_project_entity_templates()`,
  `log_entity_template_validation_error()`.
- `dungeon_engine/startup_validation.py` — integrated entity template
  validation alongside command validation.

Backward compatible: bare stems like `"player"` still work.

### 3. Area ID-Based Referencing

**Problem:** Areas were referenced by filesystem path. Moving an area file
broke all references and save data.

**Solution:** Gave areas path-derived IDs, same as commands.

Files modified:

- `dungeon_engine/project.py` — added `area_id()`, `list_area_ids()`,
  `find_area_by_id()`, `resolve_area_reference()` (tries ID first, falls back
  to path). Updated `area_path_to_reference()` to return IDs instead of paths
  for save data portability.
- `dungeon_engine/commands/builtin.py` — updated `change_area` to accept both
  `area_id` (preferred) and `area_path` (legacy).
- `dungeon_engine/engine/game.py` — updated `_resolve_area_path()` to use
  `resolve_area_reference()` which tries ID-based resolution first.

Backward compatible: legacy path-based references still work.

### 4. Updated `asset_registry_ideas.md`

All 7 open questions answered. Chosen direction documented: typed registries
with uniform discovery pattern, path-derived IDs, no generic registry class.

## Key Design Decisions

1. **IDs are path-derived, not author-declared.** The file's location is its
   identity. Explicit `id` fields are validated against the path and rejected
   if mismatched.

2. **No unified registry.** Each content type keeps its own module. The shared
   pattern is the discovery approach (recursive scan, path-derived ID, duplicate
   check), not a shared base class.

3. **Backward compatibility maintained.** Legacy path-based references resolve
   via fallback. Save data migration happens transparently.
