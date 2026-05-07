"""Camera-oriented builtin commands."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dungeon_engine.commands.context_services import CommandServices

from dungeon_engine.commands.context_types import CameraLike

from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import CommandHandle, ImmediateHandle


class CameraCommandHandle(CommandHandle):
    """Wait until an interpolated camera move finishes."""

    def __init__(self, camera: CameraLike | None) -> None:
        super().__init__()
        self.camera = camera
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when the camera stops moving."""
        self.complete = self.camera is None or not self.camera.is_moving()


def _resolve_camera(
    *,
    services: CommandServices | None,
    camera: CameraLike | None,
) -> CameraLike | None:
    """Return the active camera, preferring command services when available."""
    if services is not None and services.ui is not None:
        return services.ui.camera
    return camera


def _resolve_world_and_area(
    *,
    services: CommandServices | None,
    world: Any,
    area: Any,
) -> tuple[Any, Any]:
    """Return the world and area, preferring command services when available."""
    if services is not None and services.world is not None:
        return services.world.world, services.world.area
    return world, area


def register_camera_commands(
    registry: CommandRegistry,
    *,
    normalize_camera_follow_spec: Callable[..., dict[str, Any]],
    normalize_camera_rect_spec: Callable[..., dict[str, float]],
) -> None:
    """Register builtin commands that operate on runtime camera state."""

    @registry.register(
        "set_camera_policy",
        additional_authored_params={
            "follow",
            "bounds",
            "deadzone",
            "source_entity_id",
            "entity_refs",
        },
    )
    def set_camera_policy(
        services: CommandServices | None,
        world: Any,
        area: Any,
        camera: CameraLike | None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Apply one validated partial camera-policy update atomically."""
        resolved_camera = _resolve_camera(services=services, camera=camera)
        if resolved_camera is None:
            raise ValueError("Cannot change camera policy without an active camera.")
        resolved_world, resolved_area = _resolve_world_and_area(
            services=services,
            world=world,
            area=area,
        )

        allowed_keys = {
            "follow",
            "bounds",
            "deadzone",
            "source_entity_id",
            "entity_refs",
        }
        unknown_keys = set(runtime_params) - allowed_keys
        if unknown_keys:
            unknown_list = ", ".join(sorted(unknown_keys))
            raise ValueError(f"set_camera_policy contains unknown field(s): {unknown_list}.")

        next_state = resolved_camera.to_state_dict()
        if "follow" in runtime_params:
            raw_follow = runtime_params.get("follow")
            if raw_follow is None:
                next_state["follow"] = {"mode": "none", "offset_x": 0.0, "offset_y": 0.0}
            else:
                next_state["follow"] = normalize_camera_follow_spec(
                    raw_follow,
                    command_name="set_camera_policy",
                    world=resolved_world,
                    require_exact_entity=True,
                )
        if "bounds" in runtime_params:
            raw_bounds = runtime_params.get("bounds")
            if raw_bounds is None:
                next_state.pop("bounds", None)
            else:
                next_state["bounds"] = normalize_camera_rect_spec(
                    resolved_area,
                    raw_bounds,
                    command_name="set_camera_policy",
                    rect_name="bounds",
                    pixel_space_name="world_pixel",
                    grid_space_name="world_grid",
                )
        if "deadzone" in runtime_params:
            raw_deadzone = runtime_params.get("deadzone")
            if raw_deadzone is None:
                next_state.pop("deadzone", None)
            else:
                next_state["deadzone"] = normalize_camera_rect_spec(
                    resolved_area,
                    raw_deadzone,
                    command_name="set_camera_policy",
                    rect_name="deadzone",
                    pixel_space_name="viewport_pixel",
                    grid_space_name="viewport_grid",
                )

        resolved_camera.apply_state_dict(next_state, resolved_world)
        return ImmediateHandle()

    @registry.register("push_camera_state")
    def push_camera_state(
        services: CommandServices | None,
        camera: CameraLike | None,
        **_: Any,
    ) -> CommandHandle:
        """Push the current camera state onto the runtime camera-state stack."""
        resolved_camera = _resolve_camera(services=services, camera=camera)
        if resolved_camera is None:
            raise ValueError("Cannot push camera state without an active camera.")
        resolved_camera.push_state()
        return ImmediateHandle()

    @registry.register("pop_camera_state")
    def pop_camera_state(
        services: CommandServices | None,
        world: Any,
        camera: CameraLike | None,
        **_: Any,
    ) -> CommandHandle:
        """Restore the most recently pushed camera state."""
        resolved_camera = _resolve_camera(services=services, camera=camera)
        if resolved_camera is None:
            raise ValueError("Cannot pop camera state without an active camera.")
        resolved_world, _ = _resolve_world_and_area(
            services=services,
            world=world,
            area=None,
        )
        resolved_camera.pop_state(resolved_world)
        return ImmediateHandle()

    @registry.register("move_camera")
    def move_camera(
        services: CommandServices | None,
        area: Any,
        camera: CameraLike | None,
        *,
        x: int | float,
        y: int | float,
        space: str = "world_pixel",
        mode: str = "absolute",
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Move the camera in world pixel/grid space, absolute or relative."""
        resolved_camera = _resolve_camera(services=services, camera=camera)
        if resolved_camera is None:
            raise ValueError("Cannot move camera without an active camera.")
        _, resolved_area = _resolve_world_and_area(
            services=services,
            world=None,
            area=area,
        )
        if space not in {"world_pixel", "world_grid"}:
            raise ValueError("move_camera space must be 'world_pixel' or 'world_grid'.")
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown camera movement mode '{mode}'.")

        target_x = float(x)
        target_y = float(y)
        if space == "world_grid":
            target_x *= resolved_area.tile_size
            target_y *= resolved_area.tile_size
        if mode == "relative":
            target_x += resolved_camera.x
            target_y += resolved_camera.y

        resolved_camera.start_move_to(
            target_x,
            target_y,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
        )
        if not resolved_camera.is_moving():
            return ImmediateHandle()
        return CameraCommandHandle(resolved_camera)

__all__ = ["register_camera_commands"]
