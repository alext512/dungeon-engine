# Codebase Health Fixes

## Status: Planned

Issues identified through a full codebase inspection (March 2025). Each item
was verified against the actual code. Grouped by priority.

---

## Quick Fixes — Do First

### 1. Replace `assert` with proper runtime guards

**Location:** `engine/game.py` — 9 assert statements at lines 123-126,
171-174, and 573.

**Problem:** These guard against `None` on `self.input_handler`,
`self.command_runner`, `self.movement_system`, etc. Under `python -O`, asserts
are stripped entirely, removing the guards and causing `AttributeError` crashes
deeper in the call stack.

**Fix:** Replace each `assert x is not None` with:

```python
if x is None:
    raise RuntimeError("...")
```

**Effort:** 15 minutes.

### 2. Validate `tile_size > 0` on area load

**Location:** `world/loader.py` line 83.

**Problem:** `tile_size` is read from JSON with no validation. A value of `0`
or negative causes `ZeroDivisionError` in the renderer and editor (floor
division by tile size).

**Fix:** Add after the `tile_size` parse line:

```python
if tile_size <= 0:
    raise ValueError(f"Area tile_size must be positive, got {tile_size}.")
```

**Effort:** 5 minutes.

---

## Medium Effort — Worthwhile Improvements

### 3. Better JSON validation for entities and areas

**Problem:** Entity and area loading uses direct dict access (`entity_data["x"]`,
`entity_data["id"]`) which crashes with unhelpful `KeyError` when fields are
missing. Commands and dialogues already have proper validation with clear error
messages.

**Fix:** Add explicit key checks with descriptive errors before accessing
required fields in `loader.py`'s `instantiate_entity()` and `load_area()`.
Follow the pattern already established in `library.py` and
`dialogue_library.py`.

**Files:** `dungeon_engine/world/loader.py`

**Effort:** 1-2 hours.

### 4. Type `CommandContext` fields properly

**Location:** `commands/runner.py` lines 32-41.

**Problem:** 10 fields typed as `Any | None` (`project`, `asset_manager`,
`camera`, `audio_player`, etc.). This defeats type checking at every command
implementation site.

**Fix:** Use proper types with `TYPE_CHECKING` imports to avoid circular
dependencies:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dungeon_engine.project import ProjectContext
    from dungeon_engine.engine.asset_manager import AssetManager
    # etc.
```

**Effort:** 1 hour.

### 5. Start a test suite

**Problem:** Zero test files across 11,250 LOC. No regression safety net.

**Suggested first targets:**
- `project.py` — test ID derivation, path resolution, duplicate detection
- `world/loader.py` — test template loading, parameter substitution
- `world/persistence.py` — test save/load round-trip, state layering
- `commands/library.py` — test command database building, validation
- `commands/runner.py` — test command execution, parameter substitution

**Setup:** Add `pytest` to dev dependencies, create `tests/` directory,
add `[tool.pytest.ini_options]` to `pyproject.toml`.

**Effort:** Large (ongoing), but even 10 tests covering the core loaders
would catch most regressions.

---

## Low Priority — Nice to Have

### 6. Command error recovery

**Location:** `commands/runner.py` lines 456-471.

**Problem:** `_handle_command_error` clears `background_handles` and `pending`
entirely when any command fails. Background animations, audio, or entity state
changes are silently killed.

**Assessment:** The nuclear cleanup is aggressive but safe — a half-finished
command chain with unknown state is dangerous to leave running. This only
matters if background commands are used for visual effects that need graceful
teardown. Consider adding a cancel/cleanup callback to `CommandHandle`.

**Effort:** Medium.

### 7. Named constant for float tolerance

**Location:** `systems/movement.py` lines 462-465, also `world/persistence.py`
and `world/serializer.py`.

**Problem:** `math.isclose(..., abs_tol=0.001)` hardcoded in 3 places.

**Fix:** Define `GRID_SNAP_TOLERANCE = 0.001` in `config.py` and reference it.

**Effort:** 10 minutes.

### 8. Dev-mode warning for frame clamping

**Location:** `engine/asset_manager.py` line 51, `systems/animation.py`
line 118.

**Problem:** Out-of-range frame indices are silently clamped with
`min(index, len(frames) - 1)`. Misconfigured animations display the wrong
frame instead of raising an error.

**Fix:** Add a `logger.warning()` when clamping occurs, so content authors
can spot issues during development.

**Effort:** 10 minutes.

---

## Not Worth Fixing

These were flagged but do not warrant changes:

- **Unbounded module-level caches** — A puzzle game loads at most ~50
  templates. These caches will never matter. A `clear_caches()` function would
  only help if the editor needs hot reload.

- **Path traversal in save slot resolution** — The containment check
  (`resolve().relative_to(save_dir)`) correctly blocks traversal. The absolute
  path acceptance is fine because the resolved path is still checked. Not a
  real vulnerability.

- **`copy.deepcopy()` usage** — 71 uses, mostly necessary for returning cached
  data safely. The performance impact in a 60fps tile game is negligible. Only
  optimize if profiling shows it matters.

- **Entity sort every frame** — Python's timsort is very fast on nearly-sorted
  data (entity positions rarely change between frames). Only optimize if entity
  counts reach hundreds and profiling confirms a bottleneck.

- **Per-frame `pygame.transform.flip()`** — Only matters if many entities are
  flipped simultaneously. Not worth a flip cache at current scale.

- **No license file** — Acknowledged in README. Only matters if the project is
  shared publicly.
