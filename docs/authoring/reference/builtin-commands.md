# Built-in Commands

This page is the quick inventory. For the exact signatures and edge-case notes, use the full [Engine JSON Interface](../manuals/engine-json-interface.md).

## Movement And Position

- `set_entity_grid_position` sets a world entity in grid coordinates.
- `set_entity_world_position` sets a world entity in world-pixel coordinates.
- `set_entity_screen_position` sets a screen-space entity in screen-pixel coordinates.
- `move_in_direction` performs standard grid movement with engine physics support.
- `push_facing` pushes in a direction, usually from the actor's facing.
- `move_entity_world_position` interpolates movement in world-pixel space.
- `move_entity_screen_position` interpolates movement in screen space.
- `wait_for_move` waits for a moving entity to finish.
- `interact_facing` resolves a standard facing interaction target.

## Dialogue

- `open_dialogue_session` opens the engine-owned dialogue runtime for a dialogue JSON file.
- `close_dialogue_session` closes the current engine-owned dialogue session.

## Inventory

- `add_inventory_item` adds stacks or quantities to an entity-owned inventory.
- `remove_inventory_item` removes stacks or quantities from an entity-owned inventory.
- `use_inventory_item` runs an item's use flow and only consumes on success.
- `set_inventory_max_stacks` changes inventory capacity.
- `open_inventory_session` opens the engine-owned inventory UI.
- `close_inventory_session` closes the current inventory session.

## Animation, Audio, And Visuals

- `play_animation` plays a named animation clip on an entity visual.
- `wait_for_animation` waits for an entity animation to finish.
- `stop_animation` stops an entity animation.
- `set_visual_frame` forces one visual frame.
- `set_visual_flip_x` changes horizontal flipping.
- `play_audio` plays a one-shot sound effect.
- `set_sound_volume` changes the default SFX volume.
- `play_music` plays or swaps the music track.
- `stop_music` stops music, optionally with fade.
- `pause_music` pauses the music channel.
- `resume_music` resumes the music channel.
- `set_music_volume` changes music volume.

## Screen-Space UI Elements

- `show_screen_image` creates or updates a screen image element.
- `show_screen_text` creates or updates a screen text element.
- `set_screen_text` updates the text for an existing element.
- `remove_screen_element` removes one screen element.
- `clear_screen_elements` clears all screen elements or one layer.
- `play_screen_animation` animates a screen-space element.
- `wait_for_screen_animation` waits for a screen animation to finish.

## Time And Flow Composition

- `wait_frames` waits a fixed number of simulation frames.
- `wait_seconds` waits a fixed number of seconds.
- `spawn_flow` starts a child flow without blocking the caller.
- `run_sequence` runs an inline command list as a child flow.
- `run_parallel` starts multiple child flows together.
- `run_commands_for_collection` iterates a collection and runs one command list per item.
- `if` branches on a comparison result.

These flow-composition commands can also carry `source_entity_id`, `entity_refs`, and `refs_mode` so the child flow has the right calling context.

Timing note: command chains are eager. A sequence keeps running in the same
simulation tick until a command actually waits. `spawn_flow` starts its child
immediately and the parent continues immediately; use `run_parallel` when you
want grouped children with an explicit completion policy.

## Entity And Project Command Dispatch

- `run_entity_command` calls a named command on a specific entity.
- `run_project_command` calls a reusable project command by path-derived id.

When a called flow needs referenced entities, author `entity_refs` on the caller and then use `$ref_ids.name` inside entity-target fields or `$refs.name.some_var` for variable reads.

## Entity-Command And Input Routing

- `set_entity_command_enabled` enables or disables one named entity command.
- `set_entity_commands_enabled` gates the entity command system as a whole.
- `set_input_target` routes one logical action to one entity.
- `route_inputs_to_entity` routes many actions to one entity at once.
- `push_input_routes` stores the current routing for later restore.
- `pop_input_routes` restores the most recently pushed routing snapshot.

## Area, Save, And Game Flow

- `change_area` transitions to another area and can transfer travelers.
- `new_game` resets into a fresh session and optional destination.
- `load_game` restores from a save path.
- `save_game` writes the current session to a save path.
- `quit_game` exits play mode.

`change_area`, `new_game`, and `load_game` are scene boundaries. Once one runs,
old-scene command work is cancelled and later commands in that old-scene
sequence do not continue.

## Debug Runtime

- `set_simulation_paused` sets the simulation paused state.
- `toggle_simulation_paused` toggles paused state.
- `step_simulation_tick` advances one paused tick.
- `adjust_output_scale` changes the output scale.

These debug commands are gated behind `debug_inspection_enabled`.

## Camera

- `set_camera_follow` sets follow behavior.
- `set_camera_state` updates follow, bounds, or deadzone in one command.
- `push_camera_state` saves the current camera state.
- `pop_camera_state` restores the most recently pushed camera state.
- `set_camera_bounds` defines camera bounds.
- `set_camera_deadzone` defines a camera deadzone.
- `move_camera` interpolates camera movement.
- `teleport_camera` jumps the camera immediately.

## Entity State

- `set_entity_field` changes one supported entity field.
- `set_entity_fields` performs a validated batch mutation.
- `set_visible` toggles entity visibility.
- `set_present` toggles whether an entity exists in play.
- `set_color` changes tint or color.
- `destroy_entity` removes an entity.
- `spawn_entity` creates a new entity from a full definition or partial inputs.

## Current-Area Variables, Entity Variables, And Cross-Area Writes

- `set_current_area_var` writes one current-area runtime variable.
- `set_entity_var` writes one entity variable.
- `add_current_area_var` and `add_entity_var` add numeric amounts.
- `toggle_current_area_var` and `toggle_entity_var` flip booleans.
- `set_current_area_var_length` and `set_entity_var_length` resize collections.
- `append_current_area_var` and `append_entity_var` append to collections.
- `pop_current_area_var` and `pop_entity_var` pop from collections.
- `set_area_var` writes persistent state into another area.
- `set_area_entity_var` writes persistent state into another area's entity.
- `set_area_entity_field` writes a persistent field into another area's entity.

## Reset And Persistence Helpers

- `reset_transient_state` clears selected transient state now or on reentry.
- `reset_persistent_state` clears selected persistent overrides now or on reentry.

## Occupancy Hooks

These are not separate built-ins, but they are important standard command-entry names on entities:

- `on_occupant_enter`
- `on_occupant_leave`
- `on_blocked`

## Exact Signatures And Current Rules

Use the canonical reference when you need:

- exact parameter names
- required vs optional fields
- persistent behavior rules
- validation-mode details
- deferred nested command fields
- completion behavior for `run_parallel`

That level of detail lives in [Engine JSON Interface](../manuals/engine-json-interface.md).
