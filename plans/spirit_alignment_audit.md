# Temporary Plan - Spirit Alignment Audit

This is a temporary audit note.

Its purpose is to list the parts of the current codebase that still appear to drift away from the spirit described in `PROJECT_SPIRIT.md`, so we can tackle them deliberately instead of rediscovering them piecemeal.

This file is not permanent truth.
Some items below are clear mismatches.
Some are "likely mismatches" or "needs a design decision".
When an item is resolved, the permanent docs should be updated and this file should eventually be removed.

## Audit Lens

This audit was done against the current spirit of the project:

- the engine should provide runtime substrate, not secretly own gameplay meaning
- entities and authored data should own gameplay/UI state where practical
- primitive commands should be narrow and explicit
- higher-level orchestration commands are still allowed to be richer
- hidden privileged concepts and magical fallbacks should be treated with suspicion

## Already Mostly Aligned

These areas look broadly aligned with the intended direction and are not the main target of this note:

- `active_entity` is gone from the active runtime model
- authored `player_id` is gone from the active area schema/runtime model
- dialogue state now lives on controller entities rather than in an engine dialogue session handle
- input routing is per logical action through explicit `input_targets`
- input-route restore is handled through the engine-owned route stack rather than a privileged actor
- camera state is explicit runtime state instead of being derived from a special player concept
- helper "read and store" commands for camera, JSON/text processing, facing state, and collection items have been replaced by runtime tokens or structured value sources in the active authored model
- removed dialogue/data/input helper command names and the old broad variable builtins are no longer part of the active builtin registry

## Definite Mismatches

### 1. `CommandContext` is still a giant shared service bag internally

Files:

- `dungeon_engine/commands/runner.py`
- `dungeon_engine/engine/game.py`

What is happening:

- `CommandContext` still bundles the union of nearly every runtime service:
  - world
  - area
  - collision
  - movement
  - interaction
  - animation
  - project
  - asset manager
  - text renderer
  - camera
  - audio
  - screen manager
  - command runner
  - input handler
  - persistence
  - area/new-game/load/save/quit callbacks
- `Game._install_play_runtime()` still builds one full runtime root for command execution.
- The active runner no longer hands that full bag to every strict primitive by default.
- Many strict primitive families now receive only the explicit engine services named in their Python signatures, while richer orchestration commands still receive full runner context.

Why this conflicts with the spirit:

- the project direction is that primitive commands should receive only what they actually need
- this broad runtime bag is still the opposite shape: one shared "everything" toolbox

Remaining work:

- finish converting the remaining strict primitive families that still take full `context`
- keep the full runtime root internal, but continue shrinking the number of command contracts that effectively depend on it

### 2. Input still has hidden engine fallbacks and engine-owned meaning

Files:

- `dungeon_engine/engine/input_handler.py`
- `dungeon_engine/project.py`
- `MANUAL.md`
- `AUTHORING_GUIDE.md`
- `STATUS.md`

Status:

- mostly addressed

What changed:

- `Escape` now only means the routed logical `menu` action in play mode; it no longer falls back to quit when nothing consumes it
- raw debug keys now route to a normal global `debug_controller` entity in the sample project
- debug effects such as simulation pause, stepping, and zoom are now explicit runtime commands gated by `debug_inspection_enabled`

Residual note:

- physical key-to-logical-action mapping still lives in the engine input layer, which is acceptable so long as action meaning continues to be controller-owned

### 3. Generic per-command lifecycle wrappers are now removed from the active model

Status:

- resolved in the active runtime surface
- generic command-level `on_start` / `on_end` wrapper syntax is gone
- `LifecycleChainHandle` is gone
- explicit sequencing now goes through `run_commands`
- overlapping/background work now goes through `run_detached_commands`

Remaining follow-through:

- keep the docs/examples aligned so old wrapper syntax does not reappear

### 4. Validation historical baggage has mostly been removed

Files:

- `dungeon_engine/world/loader.py`
- `dungeon_engine/commands/library.py`

What is happening:

- loader/library now focus on current-architecture invariants such as reserved ids and strict primitive entity targeting
- removed command names are no longer specially memorialized in the startup validators

Why this is better:

- the active engine surface and the validation layer now describe the same current language more closely
- the engine no longer carries a large startup blacklist of obsolete command names just to explain old history

Remaining follow-through:

- keep only current-model guards such as reserved ids and path-derived structural identity
- avoid reintroducing historical blacklist checks unless they protect a live invariant

## Likely Mismatches / Needs Design Review

### 5. Facing/interaction helpers are still broad and gameplay-opinionated

Files:

- `dungeon_engine/commands/builtin.py`
- `projects/test_project/named_commands/attempt_move_one_tile.json`

Current examples:

- none in the active runtime surface

What is happening:

- the old smart facing helpers have been removed from the active runtime surface
- explicit authored replacement is now available through:
  - `"$entity_ref"` for runtime tile/facing data
  - `"$entities_at"` / `"$entity_at"` for tile lookup
  - `"$sum"` for small coordinate math
  - explicit `run_event` for dispatch

Why this might conflict with the spirit:

- this bucket is now mostly aligned
- the remaining risk is only where movement/push flows still use `"$facing_state"` as a convenience helper

Residual note:

- `"$facing_state"` still keeps some facing-derived movement state in one helper value source, so this area is improved but not fully finished

### 7. Background command execution and input-while-busy are still hidden scheduling semantics

Files:

- `dungeon_engine/commands/runner.py`
- `dungeon_engine/commands/builtin.py`
- `dungeon_engine/engine/input_handler.py`

Current examples:

- `CommandRunner.background_handles`
- `run_detached_commands`
- `allow_entity_input`
- `captures_menu_input`

What is happening:

- the runner has a main active lane plus a background-handle lane
- some handles can still allow routed input while the main lane is busy

Why this might conflict with the spirit:

- it is generic runtime infrastructure, so it may be acceptable
- but it is also a hidden scheduling model that authors can only see indirectly
- if it grows more complex, it may become another "secret engine state machine"

Open question:

- keep as internal substrate
- or make the scheduling model more explicit/authored if it starts affecting gameplay reasoning too much

### 8. The sample and docs still normalize transitional helper commands as part of the active authoring surface

Files:

- `MANUAL.md`
- `AUTHORING_GUIDE.md`
- `projects/test_project/project.json`
- `projects/test_project/named_commands/dialogue/*.json`

Current examples:

- the docs/sample still rely on a few convenience value sources such as `"$facing_state"` and helper-heavy dialogue redraw chains
- the sample still demonstrates some transitional composition patterns that may not be the final cleanest authoring style

Why this matters:

- the docs are much closer to the current spirit than before
- but the sample can still normalize convenience patterns that deserve another pass before they harden into the long-term style

Likely future direction:

- keep the docs honest about current behavior while continuing to simplify the helper-heavy sample flows
- but treat these commands/features as transitional, not as the final intended model

## Possible Non-Issues To Leave Alone Unless They Start Causing Problems

These do not currently look like strong spirit violations by themselves:

- `ScreenElementManager` owning render-only screen element state
- explicit camera runtime state and camera math
- global entities for controller/system entities
- explicit area transfer payloads and entry points

They still deserve re-checking later if they start swallowing gameplay meaning, but they are not the main current drift points.

## Suggested Tackling Order

1. Finish the remaining `CommandContext` shrink work for the strict primitive families that still take full runner context
2. Review whether facing/interaction helpers should remain high-level orchestration helpers or be decomposed
3. Review whether the remaining physical key mapping in the input layer should stay fixed or become authored/configured later
4. Once replacement paths are stable, remove the legacy rejection-shim layer

## Working Rule

This note is a punch list, not a verdict.

If later implementation or design discussion shows that one of these items is actually acceptable infrastructure, this file should be updated deliberately.
If an item is resolved, the permanent docs should be updated and this file should eventually be deleted.
