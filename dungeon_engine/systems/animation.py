"""Very small animation system for per-visual frame updates."""

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
        visual_id: str | None = None,
        frames_per_sprite_change: int = 1,
        hold_last_frame: bool = True,
    ) -> None:
        """Start a command-driven one-shot frame sequence on an entity visual."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            raise KeyError(f"Cannot animate missing entity '{entity_id}'.")
        if not entity.present:
            return
        if not frame_sequence:
            raise ValueError("Animation frame sequence cannot be empty.")
        if frames_per_sprite_change <= 0:
            raise ValueError("frames_per_sprite_change must be positive.")

        visual = _require_target_visual(entity, visual_id)
        playback = visual.animation_playback
        playback.active = True
        playback.frame_sequence = [int(frame) for frame in frame_sequence]
        playback.frames_per_sprite_change = int(frames_per_sprite_change)
        playback.current_sequence_index = 0
        # Start at -1 so the first update tick displays the opening frame
        # without immediately consuming one of its visible ticks.
        playback.ticks_on_current_frame = -1
        playback.time_accumulator = 0.0
        playback.hold_last_frame = hold_last_frame
        visual.current_frame = playback.frame_sequence[0]

    def stop_animation(
        self,
        entity_id: str,
        *,
        visual_id: str | None = None,
        reset_to_default: bool = False,
    ) -> None:
        """Stop any command-driven animation on an entity visual."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            raise KeyError(f"Cannot stop animation on missing entity '{entity_id}'.")

        visual = _require_target_visual(entity, visual_id)
        playback = visual.animation_playback
        playback.active = False
        playback.frame_sequence = []
        playback.current_sequence_index = 0
        playback.ticks_on_current_frame = 0
        playback.time_accumulator = 0.0
        if reset_to_default and visual.frames:
            visual.current_frame = visual.frames[0]

    def is_entity_animating(self, entity_id: str, *, visual_id: str | None = None) -> bool:
        """Return True when the entity or requested visual is actively animating."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            return False
        if not entity.present:
            return False
        if visual_id is not None:
            visual = entity.get_visual(visual_id)
            return bool(visual is not None and visual.animation_playback.active)
        return any(visual.animation_playback.active for visual in entity.visuals)

    def update(self, dt: float) -> None:
        """Backward-compatible wrapper that advances one fixed animation tick."""
        self.update_tick(dt)

    def update_tick(self, dt: float) -> None:
        """Update visible frames for each entity visual for one simulation tick."""
        for entity in self.world.iter_entities():
            for visual in entity.visuals:
                if self._update_command_playback(visual):
                    continue
                if not visual.frames:
                    visual.current_frame = 0
                    continue
                if visual.animate_when_moving and not entity.movement_state.active:
                    visual.animation_elapsed = 0.0
                    visual.current_frame = visual.frames[0]
                    continue
                if visual.animation_fps <= 0:
                    continue
                if len(visual.frames) == 1:
                    visual.current_frame = visual.frames[0]
                    continue
                visual.animation_elapsed += dt
                frame_step = int(visual.animation_elapsed * visual.animation_fps)
                visual.current_frame = visual.frames[
                    frame_step % len(visual.frames)
                ]

    def _update_command_playback(self, visual) -> bool:
        """Advance command-driven playback and return True when it handled the frame."""
        playback = visual.animation_playback
        if not playback.active:
            return False

        if not playback.frame_sequence:
            playback.active = False
            return False

        visual.current_frame = playback.frame_sequence[
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
                visual.current_frame = playback.frame_sequence[-1]
            elif visual.frames:
                visual.current_frame = visual.frames[0]
            return True

        visual.current_frame = playback.frame_sequence[playback.current_sequence_index]

        return True


def _require_target_visual(entity, visual_id: str | None):
    """Return the requested visual or the primary visual."""
    if visual_id is not None:
        return entity.require_visual(visual_id)
    visual = entity.get_primary_visual()
    if visual is None:
        raise KeyError(f"Entity '{entity.entity_id}' has no visuals to animate.")
    return visual

