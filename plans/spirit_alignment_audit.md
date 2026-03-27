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

## Definite Mismatches

### 1. `CommandContext` is still a giant shared service bag

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
- `Game._install_play_runtime()` builds and passes this full bag to all command execution.

Why this conflicts with the spirit:

- the project direction is that primitive commands should receive only what they actually need
- this broad runtime bag is still the opposite shape: one shared "everything" toolbox

What to do later:

- move toward command-specific dependency injection for true primitives
- keep a full runtime root internally if needed, but stop letting primitive command contracts effectively depend on the whole bag

### 2. A helper-command layer still combines "read/compute" plus "store into a variable"

Files:

- `dungeon_engine/commands/builtin.py`
- `MANUAL.md`
- `AUTHORING_GUIDE.md`

Current examples:

- `set_var_from_json_file`
- `set_var_from_wrapped_lines`
- `set_var_from_text_window`
- `set_world_var_from_camera`
- `set_entity_var_from_camera`
- `query_facing_state`

What is happening:

- these commands are still doing two things at once:
  - read/compute something from engine services or input data
  - store the result into a variable
- several of them also still carry `scope`, `entity_id`, and rich symbolic/runtime resolution behavior

Why this conflicts with the spirit:

- these are no longer clean primitives
- they act like mini convenience scripting helpers
- the user direction is moving toward patterns like:
  - read a value from a runtime source
  - then use an ordinary explicit variable command

Likely future direction:

- replace these with clearer value-source mechanisms plus ordinary explicit variable commands
- example direction already discussed:
  - instead of `set_world_var_from_camera`, prefer something in the spirit of `set_world_var(name, value="$camera.x")`

### 3. Input still has hidden engine fallbacks and engine-owned meaning

Files:

- `dungeon_engine/engine/input_handler.py`
- `dungeon_engine/project.py`
- `MANUAL.md`
- `AUTHORING_GUIDE.md`
- `STATUS.md`

Current examples:

- project-level `input_events` fallback mapping
- `InputHandler._resolve_input_target_event_name()` falls back to project/global event names when an entity has no `input_map` entry
- `set_input_event_name` mutates that fallback mapping at runtime
- `Escape` still has engine-owned fallback behavior that can become quit when not consumed
- debug keys are still handled directly in the engine input layer

Why this conflicts with the spirit:

- input meaning is still not fully owned by routed entities
- the engine still decides fallback meaning for logical actions
- this is exactly the kind of hidden convenience that can become a design trap later

Likely future direction:

- remove or sharply reduce project/global fallback event mappings
- make routed entities or explicit controller logic own meaning for inputs
- keep only true low-level input plumbing in the engine

### 4. `wait_for_action_press` and `wait_for_direction_release` still poll raw engine input state

Files:

- `dungeon_engine/commands/builtin.py`
- `dungeon_engine/engine/input_handler.py`

What is happening:

- `wait_for_action_press` watches `InputHandler` press counts
- `wait_for_direction_release` watches `InputHandler` held-direction state
- both commands depend on raw engine-side counters/held flags rather than routed entity events

Why this conflicts with the spirit:

- these commands bypass the explicit input-routing model
- they make authored logic depend on hidden engine-owned input state instead of routed entity behavior
- they also do not fit the desired future direction of separate press/hold/release input ownership

Likely future direction:

- replace them with explicit routed input phase handling
- or with authored controller/entity state rather than engine-side raw wait handles

### 5. The runner still has hidden command lifecycle wrappers and dialogue-specific deferred plumbing

Files:

- `dungeon_engine/commands/runner.py`
- `MANUAL.md`
- `AUTHORING_GUIDE.md`

Current examples:

- generic per-command `on_start` / `on_end` wrapper syntax
- `LifecycleChainHandle`
- runner-level special deferred params for `run_event`:
  - `dialogue_on_start`
  - `dialogue_on_end`
  - `segment_hooks`

What is happening:

- any command can quietly gain extra wrapper command chains through special keys
- the generic runner still knows about dialogue-branded deferred parameter names even after dialogue state moved into entities

Why this conflicts with the spirit:

- this is hidden engine authorship/composition syntax rather than explicit command chaining
- the dialogue-specific deferred parameter handling is still a special-case residue inside the generic runner

Likely future direction:

- decide whether `on_start` / `on_end` should remain as a generic composition feature or be replaced by more explicit command-chain structure
- remove dialogue-branded deferred parameter knowledge from the generic runner

### 6. There is still a large transitional layer of removed builtins kept alive as rejection shims

Files:

- `dungeon_engine/commands/builtin.py`
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
- the old broad variable builtins

What is happening:

- many old command names are still registered only to fail fast
- loader/library also hardcode validation rejection for many of these old names/forms

Why this conflicts with the spirit:

- this is acceptable as a migration step
- it is not a good final shape
- the active engine API is still partly carrying historical baggage in its registry and validation logic

Likely future direction:

- once the replacement model is stable, remove the historical shims and reduce the rejection surface
- keep only the docs/tests needed to explain the final active model

## Likely Mismatches / Needs Design Review

### 7. Facing/interaction helpers are still broad and gameplay-opinionated

Files:

- `dungeon_engine/commands/builtin.py`
- `projects/test_project/named_commands/attempt_move_one_tile.json`

Current examples:

- `query_facing_state`
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

### 8. Background command execution and input-while-busy are still hidden scheduling semantics

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

### 9. The sample and docs still normalize transitional helper commands as part of the active authoring surface

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

1. Replace helper commands that both compute and store:
   - `set_var_from_json_file`
   - `set_var_from_wrapped_lines`
   - `set_var_from_text_window`
   - camera query-to-var helpers
2. Revisit input fallbacks:
   - `input_events`
   - `set_input_event_name`
   - engine-owned fallback action meaning
3. Revisit raw input wait commands:
   - `wait_for_action_press`
   - `wait_for_direction_release`
4. Clean runner-level hidden composition/deferred plumbing:
   - `on_start`
   - `on_end`
   - dialogue-branded deferred parameter handling
5. Review whether facing/interaction helpers should remain high-level orchestration helpers or be decomposed
6. Once replacement paths are stable, remove the legacy rejection-shim layer
7. Later, revisit the broader `CommandContext` dependency shape after the command surface is cleaner

## Working Rule

This note is a punch list, not a verdict.

If later implementation or design discussion shows that one of these items is actually acceptable infrastructure, this file should be updated deliberately.
If an item is resolved, the permanent docs should be updated and this file should eventually be deleted.
