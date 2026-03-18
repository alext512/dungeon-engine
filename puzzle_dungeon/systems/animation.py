"""Very small animation system for sprite frame updates."""

from __future__ import annotations

from puzzle_dungeon.world.world import World


class AnimationSystem:
    """Advance entity animation state without embedding it in the renderer."""

    def __init__(self, world: World) -> None:
        self.world = world

    def update(self, dt: float) -> None:
        """Update the visible sprite frame for each entity."""
        for entity in self.world.iter_entities():
            if not entity.animation_frames:
                entity.current_frame = 0
                continue

            if entity.animate_when_moving and not entity.movement.active:
                entity.animation_elapsed = 0.0
                entity.current_frame = entity.animation_frames[0]
                continue

            if len(entity.animation_frames) == 1 or entity.animation_fps <= 0:
                entity.current_frame = entity.animation_frames[0]
                continue

            entity.animation_elapsed += dt
            frame_step = int(entity.animation_elapsed * entity.animation_fps)
            entity.current_frame = entity.animation_frames[
                frame_step % len(entity.animation_frames)
            ]
