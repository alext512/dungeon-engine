"""Camera utilities for following explicit runtime targets around an area."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

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


@dataclass(slots=True)
class CameraRect:
    """One rectangle used for camera bounds or deadzone policies."""

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


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
        self.follow_mode: str = "none"
        self.follow_entity_id: str | None = None
        self.follow_input_action: str | None = None
        self.follow_offset_x = 0.0
        self.follow_offset_y = 0.0
        self.bounds_rect: CameraRect | None = None
        self.deadzone_rect: CameraRect | None = None
        self.motion = CameraMotionState()
        self.state_stack: list[dict[str, Any]] = []

    def set_area(self, area: Area) -> None:
        """Rebind the camera to a different area and keep its position valid."""
        self.area = area
        self.set_position(self.x, self.y)

    def set_position(self, x: float, y: float) -> None:
        """Set the camera position directly while respecting area bounds."""
        self.x, self.y = self._clamp_position(float(x), float(y))
        self._update_render_position()

    def pan(self, delta_x: float, delta_y: float) -> None:
        """Move the camera by a delta and clamp the result to map bounds."""
        self.set_position(self.x + delta_x, self.y + delta_y)

    def update(self, world: World | None, *, advance_tick: bool = False) -> None:
        """Advance camera motion/follow state and refresh render coordinates."""
        if advance_tick and self.motion.active:
            self._advance_motion_tick()

        if not self.motion.active:
            target = self._resolve_follow_target(world)
            if target is None:
                self._update_render_position()
            else:
                self._follow_target(target)
        else:
            self._update_render_position()

    def is_moving(self) -> bool:
        """Return True when the camera is in a manual interpolated move."""
        return self.motion.active

    def follow_input_target(
        self,
        action: str,
        *,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
    ) -> None:
        """Bind the camera to whichever entity currently receives one input action."""
        self.follow_mode = "input_target"
        self.follow_entity_id = None
        self.follow_input_action = str(action).strip()
        self.follow_offset_x = float(offset_x)
        self.follow_offset_y = float(offset_y)
        self.motion.active = False

    def follow_entity(
        self,
        entity_id: str,
        *,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
    ) -> None:
        """Bind the camera to a specific entity id."""
        self.follow_mode = "entity"
        self.follow_entity_id = str(entity_id)
        self.follow_input_action = None
        self.follow_offset_x = float(offset_x)
        self.follow_offset_y = float(offset_y)
        self.motion.active = False

    def clear_follow(self) -> None:
        """Stop automatically following any entity."""
        self.follow_mode = "none"
        self.follow_entity_id = None
        self.follow_input_action = None
        self.follow_offset_x = 0.0
        self.follow_offset_y = 0.0

    def set_bounds_rect(self, x: float, y: float, width: float, height: float) -> None:
        """Clamp camera motion/follow to one world-space rectangle."""
        if width <= 0 or height <= 0:
            raise ValueError("Camera bounds width and height must be positive.")
        self.bounds_rect = CameraRect(float(x), float(y), float(width), float(height))
        self.set_position(self.x, self.y)

    def clear_bounds(self) -> None:
        """Remove any extra camera bounds beyond the area limits."""
        self.bounds_rect = None
        self.set_position(self.x, self.y)

    def set_deadzone_rect(self, x: float, y: float, width: float, height: float) -> None:
        """Keep followed targets inside one viewport-space deadzone rectangle."""
        if width <= 0 or height <= 0:
            raise ValueError("Camera deadzone width and height must be positive.")
        self.deadzone_rect = CameraRect(float(x), float(y), float(width), float(height))

    def clear_deadzone(self) -> None:
        """Remove any active follow deadzone."""
        self.deadzone_rect = None

    def push_state(self) -> None:
        """Remember the current camera policy so it can be restored later."""
        self.state_stack.append(self.to_state_dict())

    def pop_state(self, world: World | None) -> None:
        """Restore the most recently pushed camera policy snapshot."""
        if not self.state_stack:
            raise ValueError("Camera state stack is empty.")
        self.apply_state_dict(self.state_stack.pop(), world)

    def get_followed_entity_id(self) -> str | None:
        """Return the explicit entity id currently followed, when any."""
        if self.follow_mode == "entity":
            return self.follow_entity_id
        return None

    def to_state_dict(self) -> dict[str, Any]:
        """Serialize the current runtime camera policy/state into plain data."""
        follow: dict[str, Any] = {
            "mode": self.follow_mode,
            "offset_x": self.follow_offset_x,
            "offset_y": self.follow_offset_y,
        }
        if self.follow_mode == "entity" and self.follow_entity_id is not None:
            follow["entity_id"] = self.follow_entity_id
        elif self.follow_mode == "input_target" and self.follow_input_action is not None:
            follow["action"] = self.follow_input_action
        data: dict[str, Any] = {
            "x": self.x,
            "y": self.y,
            "follow": follow,
        }
        if self.bounds_rect is not None:
            data["bounds"] = self._rect_to_dict(self.bounds_rect)
        if self.deadzone_rect is not None:
            data["deadzone"] = self._rect_to_dict(self.deadzone_rect)
        return data

    def apply_state_dict(self, state: dict[str, Any], world: World | None) -> None:
        """Restore one serialized runtime camera policy/state."""
        self.motion.active = False
        self.bounds_rect = self._rect_from_dict(
            state.get("bounds"),
            rect_name="bounds",
            pixel_space_name="world_pixel",
            grid_space_name="world_grid",
        )
        self.deadzone_rect = self._rect_from_dict(
            state.get("deadzone"),
            rect_name="deadzone",
            pixel_space_name="viewport_pixel",
            grid_space_name="viewport_grid",
        )
        follow_state = state.get("follow")
        if follow_state is None:
            follow_state = {"mode": "none"}
        if not isinstance(follow_state, dict):
            raise ValueError("Camera follow state must be a JSON object.")
        if "mode" not in follow_state:
            raise ValueError("Camera follow state requires an explicit mode.")

        allowed_follow_keys = {"mode", "entity_id", "action", "offset_x", "offset_y"}
        unknown_follow_keys = set(follow_state) - allowed_follow_keys
        if unknown_follow_keys:
            unknown_list = ", ".join(sorted(unknown_follow_keys))
            raise ValueError(f"Unknown camera follow field(s): {unknown_list}.")

        mode = str(follow_state.get("mode", "none")).strip() or "none"
        if mode not in {"none", "entity", "input_target"}:
            raise ValueError(f"Unknown camera follow mode '{mode}'.")
        offset_x = float(follow_state.get("offset_x", 0.0))
        offset_y = float(follow_state.get("offset_y", 0.0))
        saved_x = float(state.get("x", self.x))
        saved_y = float(state.get("y", self.y))
        if mode == "entity":
            entity_id = str(follow_state.get("entity_id", "")).strip()
            if not entity_id:
                raise ValueError("Camera follow mode 'entity' requires a non-empty entity_id.")
            self.set_position(saved_x, saved_y)
            self.follow_entity(entity_id, offset_x=offset_x, offset_y=offset_y)
            self.update(world, advance_tick=False)
            return
        if mode == "input_target":
            action = str(follow_state.get("action", "")).strip()
            if not action:
                raise ValueError("Camera follow mode 'input_target' requires a non-empty action.")
            self.set_position(saved_x, saved_y)
            self.follow_input_target(action, offset_x=offset_x, offset_y=offset_y)
            self.update(world, advance_tick=False)
            return
        self.clear_follow()
        self.set_position(saved_x, saved_y)

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

        target_world_x = target.pixel_x + (self.area.tile_size / 2) + self.follow_offset_x
        target_world_y = target.pixel_y + (self.area.tile_size / 2) + self.follow_offset_y

        if self.deadzone_rect is None:
            desired_x = target_world_x - (self.viewport_width / 2)
            desired_y = target_world_y - (self.viewport_height / 2)
            self.set_position(desired_x, desired_y)
            return

        desired_x = self.x
        desired_y = self.y
        target_screen_x = target_world_x - self.x
        target_screen_y = target_world_y - self.y
        if target_screen_x < self.deadzone_rect.x:
            desired_x = target_world_x - self.deadzone_rect.x
        elif target_screen_x > self.deadzone_rect.right:
            desired_x = target_world_x - self.deadzone_rect.right

        if target_screen_y < self.deadzone_rect.y:
            desired_y = target_world_y - self.deadzone_rect.y
        elif target_screen_y > self.deadzone_rect.bottom:
            desired_y = target_world_y - self.deadzone_rect.bottom

        self.set_position(desired_x, desired_y)

    def _resolve_follow_target(self, world: World | None) -> Entity | None:
        """Return the entity the camera should follow right now, if any."""
        if world is None:
            return None
        if self.follow_mode == "input_target" and self.follow_input_action:
            return world.get_input_target(self.follow_input_action)
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

    def _clamp_position(self, x: float, y: float) -> tuple[float, float]:
        """Clamp one logical camera position to area and optional extra bounds."""
        min_x = 0.0
        min_y = 0.0
        max_x = max(0.0, float(self.area.pixel_width - self.viewport_width))
        max_y = max(0.0, float(self.area.pixel_height - self.viewport_height))
        if self.bounds_rect is not None:
            min_x = max(min_x, self.bounds_rect.x)
            min_y = max(min_y, self.bounds_rect.y)
            max_x = min(max_x, self.bounds_rect.right - self.viewport_width)
            max_y = min(max_y, self.bounds_rect.bottom - self.viewport_height)

        if self.clamp_to_area:
            if max_x < min_x:
                x = (min_x + max_x) / 2
            else:
                x = min(max(x, min_x), max_x)
            if max_y < min_y:
                y = (min_y + max_y) / 2
            else:
                y = min(max(y, min_y), max_y)
            return x, y

        return x, y

    def _rect_to_dict(self, rect: CameraRect) -> dict[str, float]:
        """Serialize one camera rectangle into plain numeric data."""
        return {
            "x": rect.x,
            "y": rect.y,
            "width": rect.width,
            "height": rect.height,
        }

    def _rect_from_dict(
        self,
        raw_rect: Any,
        *,
        rect_name: str,
        pixel_space_name: str,
        grid_space_name: str,
    ) -> CameraRect | None:
        """Parse one camera rectangle payload from plain data."""
        if raw_rect is None:
            return None
        if not isinstance(raw_rect, dict):
            raise ValueError(f"Camera {rect_name} must be a JSON object.")
        allowed_keys = {"x", "y", "width", "height", "space"}
        unknown_keys = set(raw_rect) - allowed_keys
        if unknown_keys:
            unknown_list = ", ".join(sorted(unknown_keys))
            raise ValueError(f"Unknown camera {rect_name} field(s): {unknown_list}.")
        space = str(raw_rect.get("space", pixel_space_name)).strip() or pixel_space_name
        if space not in {pixel_space_name, grid_space_name}:
            raise ValueError(f"Unknown camera {rect_name} space '{space}'.")
        scale = self.area.tile_size if space == grid_space_name else 1
        width = float(raw_rect.get("width", 0.0))
        height = float(raw_rect.get("height", 0.0))
        if width <= 0 or height <= 0:
            raise ValueError(f"Camera {rect_name} width and height must be positive.")
        return CameraRect(
            x=float(raw_rect.get("x", 0.0)) * scale,
            y=float(raw_rect.get("y", 0.0)) * scale,
            width=width * scale,
            height=height * scale,
        )

