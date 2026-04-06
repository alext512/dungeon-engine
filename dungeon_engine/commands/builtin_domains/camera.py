"""Camera-oriented builtin commands."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import CommandHandle, ImmediateHandle


class CameraCommandHandle(CommandHandle):
    """Wait until an interpolated camera move finishes."""

    def __init__(self, camera: Any) -> None:
        super().__init__()
        self.camera = camera
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when the camera stops moving."""
        self.complete = self.camera is None or not self.camera.is_moving()


def register_camera_commands(
    registry: CommandRegistry,
    *,
    normalize_camera_follow_spec: Callable[..., dict[str, Any]],
    normalize_camera_rect_spec: Callable[..., dict[str, float]],
) -> None:
    """Register builtin commands that operate on runtime camera state."""

    @registry.register("set_camera_follow")
    def set_camera_follow(
        world: Any,
        camera: Any | None,
        *,
        follow: dict[str, Any],
        **_: Any,
    ) -> CommandHandle:
        """Replace the current follow policy with one explicit structured follow spec."""
        if camera is None:
            raise ValueError("Cannot change camera follow without an active camera.")
        follow_spec = normalize_camera_follow_spec(
            follow,
            command_name="set_camera_follow",
            world=world,
            require_exact_entity=True,
        )
        if follow_spec["mode"] == "entity":
            camera.follow_entity(
                str(follow_spec["entity_id"]),
                offset_x=float(follow_spec.get("offset_x", 0.0)),
                offset_y=float(follow_spec.get("offset_y", 0.0)),
            )
        elif follow_spec["mode"] == "input_target":
            camera.follow_input_target(
                str(follow_spec["action"]),
                offset_x=float(follow_spec.get("offset_x", 0.0)),
                offset_y=float(follow_spec.get("offset_y", 0.0)),
            )
        else:
            camera.clear_follow()
        camera.update(world, advance_tick=False)
        return ImmediateHandle()

    @registry.register(
        "set_camera_state",
        additional_authored_params={"follow", "bounds", "deadzone", "source_entity_id"},
    )
    def set_camera_state(
        world: Any,
        area: Any,
        camera: Any | None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Apply one validated partial camera state update atomically."""
        if camera is None:
            raise ValueError("Cannot change camera state without an active camera.")

        allowed_keys = {
            "follow",
            "bounds",
            "deadzone",
            "source_entity_id",
        }
        unknown_keys = set(runtime_params) - allowed_keys
        if unknown_keys:
            unknown_list = ", ".join(sorted(unknown_keys))
            raise ValueError(f"set_camera_state contains unknown field(s): {unknown_list}.")

        next_state = camera.to_state_dict()
        if "follow" in runtime_params:
            raw_follow = runtime_params.get("follow")
            if raw_follow is None:
                next_state["follow"] = {"mode": "none", "offset_x": 0.0, "offset_y": 0.0}
            else:
                next_state["follow"] = normalize_camera_follow_spec(
                    raw_follow,
                    command_name="set_camera_state",
                    world=world,
                    require_exact_entity=True,
                )
        if "bounds" in runtime_params:
            raw_bounds = runtime_params.get("bounds")
            if raw_bounds is None:
                next_state.pop("bounds", None)
            else:
                next_state["bounds"] = normalize_camera_rect_spec(
                    area,
                    raw_bounds,
                    command_name="set_camera_state",
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
                    area,
                    raw_deadzone,
                    command_name="set_camera_state",
                    rect_name="deadzone",
                    pixel_space_name="viewport_pixel",
                    grid_space_name="viewport_grid",
                )

        camera.apply_state_dict(next_state, world)
        return ImmediateHandle()

    @registry.register("push_camera_state")
    def push_camera_state(
        camera: Any | None,
        **_: Any,
    ) -> CommandHandle:
        """Push the current camera state onto the runtime camera-state stack."""
        if camera is None:
            raise ValueError("Cannot push camera state without an active camera.")
        camera.push_state()
        return ImmediateHandle()

    @registry.register("pop_camera_state")
    def pop_camera_state(
        world: Any,
        camera: Any | None,
        **_: Any,
    ) -> CommandHandle:
        """Restore the most recently pushed camera state."""
        if camera is None:
            raise ValueError("Cannot pop camera state without an active camera.")
        camera.pop_state(world)
        return ImmediateHandle()

    @registry.register("set_camera_bounds")
    def set_camera_bounds(
        world: Any,
        area: Any,
        camera: Any | None,
        *,
        x: int | float,
        y: int | float,
        width: int | float,
        height: int | float,
        space: str = "world_pixel",
        **_: Any,
    ) -> CommandHandle:
        """Clamp camera movement and follow to one world-space rectangle."""
        if camera is None:
            raise ValueError("Cannot set camera bounds without an active camera.")
        rect = normalize_camera_rect_spec(
            area,
            {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "space": space,
            },
            command_name="set_camera_bounds",
            rect_name="bounds",
            pixel_space_name="world_pixel",
            grid_space_name="world_grid",
        )
        camera.set_bounds_rect(rect["x"], rect["y"], rect["width"], rect["height"])
        camera.update(world, advance_tick=False)
        return ImmediateHandle()

    @registry.register("set_camera_deadzone")
    def set_camera_deadzone(
        world: Any,
        area: Any,
        camera: Any | None,
        *,
        x: int | float,
        y: int | float,
        width: int | float,
        height: int | float,
        space: str = "viewport_pixel",
        **_: Any,
    ) -> CommandHandle:
        """Keep followed targets inside one viewport-space deadzone rectangle."""
        if camera is None:
            raise ValueError("Cannot set a camera deadzone without an active camera.")
        rect = normalize_camera_rect_spec(
            area,
            {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "space": space,
            },
            command_name="set_camera_deadzone",
            rect_name="deadzone",
            pixel_space_name="viewport_pixel",
            grid_space_name="viewport_grid",
        )
        camera.set_deadzone_rect(rect["x"], rect["y"], rect["width"], rect["height"])
        camera.update(world, advance_tick=False)
        return ImmediateHandle()

    @registry.register("move_camera")
    def move_camera(
        area: Any,
        camera: Any | None,
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
        if camera is None:
            raise ValueError("Cannot move camera without an active camera.")
        if space not in {"world_pixel", "world_grid"}:
            raise ValueError("move_camera space must be 'world_pixel' or 'world_grid'.")
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown camera movement mode '{mode}'.")

        target_x = float(x)
        target_y = float(y)
        if space == "world_grid":
            target_x *= area.tile_size
            target_y *= area.tile_size
        if mode == "relative":
            target_x += camera.x
            target_y += camera.y

        camera.start_move_to(
            target_x,
            target_y,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
        )
        if not camera.is_moving():
            return ImmediateHandle()
        return CameraCommandHandle(camera)

    @registry.register("teleport_camera")
    def teleport_camera(
        area: Any,
        camera: Any | None,
        *,
        x: int | float,
        y: int | float,
        space: str = "world_pixel",
        mode: str = "absolute",
        **_: Any,
    ) -> CommandHandle:
        """Move the camera instantly in world pixel/grid space."""
        if camera is None:
            raise ValueError("Cannot teleport camera without an active camera.")
        if space not in {"world_pixel", "world_grid"}:
            raise ValueError("teleport_camera space must be 'world_pixel' or 'world_grid'.")
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown camera teleport mode '{mode}'.")

        target_x = float(x)
        target_y = float(y)
        if space == "world_grid":
            target_x *= area.tile_size
            target_y *= area.tile_size
        if mode == "relative":
            target_x += camera.x
            target_y += camera.y

        camera.teleport_to(target_x, target_y)
        return ImmediateHandle()


__all__ = ["register_camera_commands"]
