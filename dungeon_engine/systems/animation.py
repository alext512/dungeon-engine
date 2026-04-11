"""Very small animation system for per-visual frame updates."""

from __future__ import annotations

from dungeon_engine import config
from dungeon_engine.world.world import World


class AnimationSystem:
    """Advance entity animation state without embedding it in the renderer."""

    def __init__(self, world: World) -> None:
        self.world = world

    def play_animation(
        self,
        entity_id: str,
        animation_id: str,
        *,
        visual_id: str | None = None,
        frame_count: int | None = None,
        duration_ticks: int | None = None,
    ) -> bool:
        """Start a named command-driven animation clip on an entity visual."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            raise KeyError(f"Cannot animate missing entity '{entity_id}'.")
        if not entity.present:
            return False

        visual = _require_target_visual(entity, visual_id)
        clip = visual.animations.get(str(animation_id))
        if clip is None:
            raise KeyError(
                f"Visual '{visual.visual_id}' on entity '{entity_id}' has no animation '{animation_id}'."
            )
        frame_sequence = _select_animation_frames(clip, frame_count=frame_count)
        if clip.flip_x is not None:
            visual.flip_x = bool(clip.flip_x)

        resolved_duration_ticks: int | None
        if duration_ticks is None:
            resolved_duration_ticks = None if len(frame_sequence) == 1 else len(frame_sequence)
        else:
            resolved_duration_ticks = int(duration_ticks)
            if resolved_duration_ticks <= 0:
                raise ValueError("duration_ticks must be positive.")
            if resolved_duration_ticks < len(frame_sequence):
                raise ValueError("duration_ticks must be greater than or equal to frame_count.")

        visual.current_frame = frame_sequence[0]
        playback = visual.animation_playback
        if resolved_duration_ticks is None:
            playback.active = False
            playback.frame_sequence = []
            playback.duration_ticks = 0
            playback.elapsed_ticks = 0
            playback.current_sequence_index = 0
            playback.started_this_tick = False
            return False

        playback.active = True
        playback.frame_sequence = list(frame_sequence)
        playback.duration_ticks = resolved_duration_ticks
        playback.elapsed_ticks = 0
        playback.current_sequence_index = 0
        playback.started_this_tick = True
        return True

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
        playback.duration_ticks = 0
        playback.elapsed_ticks = 0
        playback.started_this_tick = False
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

        if config.FPS <= 0:
            playback.active = False
            return True

        if playback.duration_ticks <= 0:
            playback.active = False
            return True

        frame_count = len(playback.frame_sequence)
        frame_index = min(
            (playback.elapsed_ticks * frame_count) // playback.duration_ticks,
            frame_count - 1,
        )
        playback.current_sequence_index = frame_index
        visual.current_frame = playback.frame_sequence[frame_index]

        if playback.started_this_tick:
            playback.started_this_tick = False
            return True

        playback.elapsed_ticks += 1
        if playback.elapsed_ticks >= playback.duration_ticks:
            playback.active = False
            playback.current_sequence_index = frame_count - 1
            visual.current_frame = playback.frame_sequence[-1]
            return True

        return True


def _require_target_visual(entity, visual_id: str | None):
    """Return the requested visual or the primary visual."""
    if visual_id is not None:
        return entity.require_visual(visual_id)
    visual = entity.get_primary_visual()
    if visual is None:
        raise KeyError(f"Entity '{entity.entity_id}' has no visuals to animate.")
    return visual


def _select_animation_frames(clip, *, frame_count: int | None) -> list[int]:
    """Return the clip frames this play should consume."""
    if not clip.frames:
        raise ValueError("Animation clip cannot be empty.")
    resolved_frame_count = len(clip.frames) if frame_count is None else int(frame_count)
    if resolved_frame_count <= 0:
        raise ValueError("frame_count must be positive.")

    if clip.preserve_phase:
        start_index = clip.phase_index % len(clip.frames)
        frames = [
            clip.frames[(start_index + offset) % len(clip.frames)]
            for offset in range(resolved_frame_count)
        ]
        clip.phase_index = (start_index + resolved_frame_count) % len(clip.frames)
        return frames

    return [
        clip.frames[offset % len(clip.frames)]
        for offset in range(resolved_frame_count)
    ]

