"""Very small animation system for sprite frame updates."""

from __future__ import annotations

from dungeon_engine import config
from dungeon_engine.world.world import World


class AnimationSystem:
    """Advance entity animation state without embedding it in the renderer."""

    def __init__(self, world: World) -> None:
        self.world = world

    def start_frame_animation(
        self,
        entity_id: str,
        frame_sequence: list[int],
        *,
        frames_per_sprite_change: int = 1,
        hold_last_frame: bool = True,
    ) -> None:
        """Start a command-driven one-shot frame sequence on an entity."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            raise KeyError(f"Cannot animate missing entity '{entity_id}'.")
        if not entity.present:
            return
        if not frame_sequence:
            raise ValueError("Animation frame sequence cannot be empty.")
        if frames_per_sprite_change <= 0:
            raise ValueError("frames_per_sprite_change must be positive.")

        playback = entity.animation_playback
        playback.active = True
        playback.frame_sequence = [int(frame) for frame in frame_sequence]
        playback.frames_per_sprite_change = int(frames_per_sprite_change)
        playback.current_sequence_index = 0
        # Start at -1 so the first update tick displays the opening frame
        # without immediately consuming one of its visible ticks.
        playback.ticks_on_current_frame = -1
        playback.time_accumulator = 0.0
        playback.hold_last_frame = hold_last_frame
        entity.current_frame = playback.frame_sequence[0]

    def stop_animation(
        self,
        entity_id: str,
        *,
        reset_to_default: bool = False,
    ) -> None:
        """Stop any command-driven animation on an entity."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            raise KeyError(f"Cannot stop animation on missing entity '{entity_id}'.")

        playback = entity.animation_playback
        playback.active = False
        playback.frame_sequence = []
        playback.current_sequence_index = 0
        playback.ticks_on_current_frame = 0
        playback.time_accumulator = 0.0
        if reset_to_default and entity.animation_frames:
            entity.current_frame = entity.animation_frames[0]

    def is_entity_animating(self, entity_id: str) -> bool:
        """Return True when the entity has an active command-driven animation."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            return False
        if not entity.present:
            return False
        return entity.animation_playback.active

    def update(self, dt: float) -> None:
        """Backward-compatible wrapper that advances one fixed animation tick."""
        self.update_tick(dt)

    def update_tick(self, dt: float) -> None:
        """Update the visible sprite frame for each entity for one simulation tick."""
        for entity in self.world.iter_entities():
            if self._update_command_playback(entity, dt):
                continue

            if not entity.animation_frames:
                entity.current_frame = 0
                continue

            if entity.animate_when_moving and not entity.movement.active:
                entity.animation_elapsed = 0.0
                entity.current_frame = entity.animation_frames[0]
                continue

            if entity.animation_fps <= 0:
                continue

            if len(entity.animation_frames) == 1:
                entity.current_frame = entity.animation_frames[0]
                continue

            entity.animation_elapsed += dt
            frame_step = int(entity.animation_elapsed * entity.animation_fps)
            entity.current_frame = entity.animation_frames[
                frame_step % len(entity.animation_frames)
            ]

    def _update_command_playback(self, entity, dt: float) -> bool:
        """Advance command-driven playback and return True when it handled the frame."""
        playback = entity.animation_playback
        if not playback.active:
            return False

        if not playback.frame_sequence:
            playback.active = False
            return False

        entity.current_frame = playback.frame_sequence[
            min(playback.current_sequence_index, len(playback.frame_sequence) - 1)
        ]

        if config.FPS <= 0:
            playback.active = False
            return True

        playback.ticks_on_current_frame += 1

        if playback.ticks_on_current_frame < playback.frames_per_sprite_change:
            return True

        playback.ticks_on_current_frame = 0
        playback.current_sequence_index += 1
        if playback.current_sequence_index >= len(playback.frame_sequence):
            playback.active = False
            playback.current_sequence_index = len(playback.frame_sequence) - 1
            if playback.hold_last_frame:
                entity.current_frame = playback.frame_sequence[-1]
            elif entity.animation_frames:
                entity.current_frame = entity.animation_frames[0]
            return True

        entity.current_frame = playback.frame_sequence[playback.current_sequence_index]

        return True

