"""Camera utilities for following the player around an area."""

from __future__ import annotations

import math
from dataclasses import dataclass

from dungeon_engine import config
from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity
from dungeon_engine.world.world import World


@dataclass(slots=True)
class CameraMotionState:
    """Runtime interpolation state for manual camera moves."""

    active: bool = False
    start_x: float = 0.0
    start_y: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    elapsed_ticks: int = 0
    total_ticks: int = 0


class Camera:
    """A lightweight camera that follows an entity and clamps to map bounds."""

    def __init__(
        self,
        viewport_width: int,
        viewport_height: int,
        area: Area,
        *,
        clamp_to_area: bool = True,
    ) -> None:
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.area = area
        self.clamp_to_area = clamp_to_area
        self.x = 0.0
        self.y = 0.0
        self.render_x = 0.0
        self.render_y = 0.0
        self.follow_mode: str = "active_entity"
        self.follow_entity_id: str | None = None
        self.motion = CameraMotionState()

    def set_area(self, area: Area) -> None:
        """Rebind the camera to a different area and keep its position valid."""
        self.area = area
        self.set_position(self.x, self.y)

    def set_position(self, x: float, y: float) -> None:
        """Set the camera position directly while respecting area bounds."""
        if self.clamp_to_area:
            max_x = max(0, self.area.pixel_width - self.viewport_width)
            max_y = max(0, self.area.pixel_height - self.viewport_height)
            self.x = min(max(x, 0), max_x)
            self.y = min(max(y, 0), max_y)
        else:
            self.x = x
            self.y = y
        self._update_render_position()

    def pan(self, delta_x: float, delta_y: float) -> None:
        """Move the camera by a delta and clamp the result to map bounds."""
        self.set_position(self.x + delta_x, self.y + delta_y)

    def update(self, world: World | None, *, advance_tick: bool = False) -> None:
        """Advance camera motion/follow state and refresh render coordinates."""
        if advance_tick and self.motion.active:
            self._advance_motion_tick()

        if not self.motion.active:
            self._follow_target(self._resolve_follow_target(world))
        else:
            self._update_render_position()

    def is_moving(self) -> bool:
        """Return True when the camera is in a manual interpolated move."""
        return self.motion.active

    def follow_active_entity(self) -> None:
        """Bind the camera to whichever entity currently receives direct input."""
        self.follow_mode = "active_entity"
        self.follow_entity_id = None
        self.motion.active = False

    def follow_entity(self, entity_id: str) -> None:
        """Bind the camera to a specific entity id."""
        self.follow_mode = "entity"
        self.follow_entity_id = str(entity_id)
        self.motion.active = False

    def clear_follow(self) -> None:
        """Stop automatically following any entity."""
        self.follow_mode = "none"
        self.follow_entity_id = None

    def start_move_to(
        self,
        target_x: float,
        target_y: float,
        *,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
    ) -> None:
        """Start an interpolated camera move and leave follow mode."""
        total_ticks = self._resolve_total_ticks(
            math.hypot(target_x - self.x, target_y - self.y),
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
        )
        self.clear_follow()
        if total_ticks <= 0:
            self.motion.active = False
            self.set_position(target_x, target_y)
            return

        self.motion = CameraMotionState(
            active=True,
            start_x=self.x,
            start_y=self.y,
            target_x=float(target_x),
            target_y=float(target_y),
            elapsed_ticks=0,
            total_ticks=total_ticks,
        )

    def teleport_to(self, target_x: float, target_y: float) -> None:
        """Jump the camera instantly to a new logical position and leave follow mode."""
        self.clear_follow()
        self.motion.active = False
        self.set_position(target_x, target_y)

    def _follow_target(self, target: Entity | None) -> None:
        """Center the camera on the target while staying inside the area."""
        if target is None:
            return

        target_center_x = target.pixel_x + (self.area.tile_size / 2)
        target_center_y = target.pixel_y + (self.area.tile_size / 2)

        desired_x = target_center_x - (self.viewport_width / 2)
        desired_y = target_center_y - (self.viewport_height / 2)

        if self.clamp_to_area:
            max_x = max(0, self.area.pixel_width - self.viewport_width)
            max_y = max(0, self.area.pixel_height - self.viewport_height)
            self.x = min(max(desired_x, 0), max_x)
            self.y = min(max(desired_y, 0), max_y)
        else:
            self.x = desired_x
            self.y = desired_y
        self._update_render_position()

    def _resolve_follow_target(self, world: World | None) -> Entity | None:
        """Return the entity the camera should follow right now, if any."""
        if world is None:
            return None
        if self.follow_mode == "active_entity":
            return world.get_active_entity()
        if self.follow_mode == "entity" and self.follow_entity_id:
            return world.get_entity(self.follow_entity_id)
        return None

    def _advance_motion_tick(self) -> None:
        """Advance one fixed camera-motion tick."""
        motion = self.motion
        if not motion.active:
            return

        if motion.total_ticks <= 0:
            progress = 1.0
        else:
            motion.elapsed_ticks = min(motion.elapsed_ticks + 1, motion.total_ticks)
            progress = motion.elapsed_ticks / motion.total_ticks

        self.set_position(
            motion.start_x + ((motion.target_x - motion.start_x) * progress),
            motion.start_y + ((motion.target_y - motion.start_y) * progress),
        )

        if motion.total_ticks <= 0 or motion.elapsed_ticks >= motion.total_ticks:
            motion.active = False
            self.set_position(motion.target_x, motion.target_y)

    def _update_render_position(self) -> None:
        """Compute the final render-space camera position from the logical camera."""
        if config.PIXEL_ART_MODE:
            self.render_x = round(self.x)
            self.render_y = round(self.y)
        else:
            self.render_x = self.x
            self.render_y = self.y

    def _resolve_total_ticks(
        self,
        distance_in_pixels: float,
        *,
        duration: float | None,
        frames_needed: int | None,
        speed_px_per_second: float | None,
    ) -> int:
        """Resolve a camera movement length in fixed simulation ticks."""
        if duration is not None and duration < 0:
            raise ValueError("Camera movement duration cannot be negative.")
        if frames_needed is not None and frames_needed < 0:
            raise ValueError("Camera frames_needed cannot be negative.")
        if speed_px_per_second is not None and speed_px_per_second <= 0:
            raise ValueError("Camera speed must be positive.")

        if frames_needed is not None:
            return int(frames_needed)
        if duration is not None:
            return self._seconds_to_ticks(duration)
        if speed_px_per_second is not None:
            if distance_in_pixels <= 0:
                return 0
            return self._seconds_to_ticks(distance_in_pixels / speed_px_per_second)
        return self._seconds_to_ticks(config.MOVE_DURATION_SECONDS)

    def _seconds_to_ticks(self, seconds: float) -> int:
        """Convert seconds into a whole-number simulation tick count."""
        if seconds <= 0 or config.FPS <= 0:
            return 0
        return max(1, round(seconds * config.FPS))

