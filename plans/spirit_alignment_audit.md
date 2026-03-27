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

Current examples:

- `Escape` still has engine-owned fallback behavior that can become quit when not consumed
- debug keys are still handled directly in the engine input layer

Why this conflicts with the spirit:

- most logical input meaning is now owned by routed entities, but a few engine-owned escape/debug paths still bypass that rule
- this is exactly the kind of hidden convenience that can become a design trap later

Likely future direction:

- keep routed entities or explicit controller logic owning meaning for gameplay inputs
- decide whether `Escape` quit fallback should remain a low-level shell/app behavior or be pushed higher
- keep only true low-level input plumbing in the engine

### 3. Generic per-command lifecycle wrappers are now removed from the active model

Status:

- resolved in the active runtime surface
- generic command-level `on_start` / `on_end` wrapper syntax is gone
- `LifecycleChainHandle` is gone
- explicit sequencing now goes through `run_commands`
- overlapping/background work now goes through `run_detached_commands`

Remaining follow-through:

- keep the docs/examples aligned so old wrapper syntax does not reappear

### 4. There is still a transitional layer of removed command-name knowledge in validation

Files:

- `dungeon_engine/world/loader.py`
- `dungeon_engine/commands/library.py`

Examples:

- `run_dialogue`
- `start_dialogue_session`
- `dialogue_advance`
- `dialogue_move_selection`
- `dialogue_confirm_choice`
- `dialogue_cancel`
- `close_dialogue`
- `prepare_text_session`
- `read_text_session`
- `advance_text_session`
- `reset_text_session`
- `set_var_from_camera`
- `set_var`
- `increment_var`
- `set_var_length`
- `append_to_var`
- `pop_var`
- `check_var`

What is happening:

- many old command names are no longer in the active builtin registry
- loader/library still hardcode validation rejection for many of these old names/forms so outdated content fails fast before launch

Why this conflicts with the spirit:

- this is acceptable as a migration step
- it is not a good final shape
- the active engine surface is cleaner now, but the validation layer still carries a large amount of historical baggage

Likely future direction:

- once the replacement model is stable, reduce the validation rejection surface too
- keep only the docs/tests needed to explain the final active model

## Likely Mismatches / Needs Design Review

### 5. Facing/interaction helpers are still broad and gameplay-opinionated

Files:

- `dungeon_engine/commands/builtin.py`
- `projects/test_project/named_commands/attempt_move_one_tile.json`

Current examples:

- `run_facing_event`
- `interact_facing`

What is happening:

- these commands combine several concerns:
  - resolve a source entity
  - inspect facing/collision/interactions
  - sometimes write variables
  - sometimes dispatch events
- sample movement logic still depends on them heavily

Why this might conflict with the spirit:

- they may be too "smart" for true primitives
- they look closer to high-level gameplay convenience than low-level runtime substrate

Open question:

- should these stay as acceptable high-level orchestration helpers
- or be broken into smaller explicit primitives over time

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

- docs list `set_var_from_json_file`, `set_var_from_wrapped_lines`, `set_var_from_text_window`, `set_world_var_from_camera`, and `set_entity_var_from_camera` as standard active commands
- docs also still teach project-level `input_events` fallback as part of the normal model
- the sample project still uses the helper-command layer heavily

Why this matters:

- the docs are accurate about the current code
- but they also risk solidifying transitional shapes that already look suspect under the spirit of the project

Likely future direction:

- keep the docs honest about current behavior until implementation changes
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
3. Decide the final shape of engine-owned fallback input behavior such as `Escape`
4. Once replacement paths are stable, remove the legacy rejection-shim layer

## Working Rule

This note is a punch list, not a verdict.

If later implementation or design discussion shows that one of these items is actually acceptable infrastructure, this file should be updated deliberately.
If an item is resolved, the permanent docs should be updated and this file should eventually be deleted.
