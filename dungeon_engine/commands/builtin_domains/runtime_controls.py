"""Runtime-control builtin commands."""

from __future__ import annotations

from collections.abc import Callable
from logging import Logger
from typing import Any

from dungeon_engine.commands.runner import (
    AreaTransitionRequest,
    CameraFollowRequest,
    CommandContext,
    CommandHandle,
    ImmediateHandle,
)
from dungeon_engine.commands.registry import CommandRegistry


def register_runtime_control_commands(
    registry: CommandRegistry,
    *,
    logger: Logger,
    require_exact_entity: Callable[[Any, str], Any],
    resolve_entity_id: Callable[..., str | None],
    normalize_camera_follow_spec: Callable[..., dict[str, Any]],
) -> None:
    """Register commands that steer runtime/session control surfaces."""

    @registry.register("set_input_target")
    def set_input_target(
        world: Any,
        *,
        action: str,
        entity_id: str | None = None,
    ) -> CommandHandle:
        """Route one logical input action to a specific entity or clear it."""
        resolved_entity_id = None if entity_id in (None, "") else require_exact_entity(world, entity_id).entity_id
        world.set_input_target(str(action), resolved_entity_id)
        return ImmediateHandle()

    @registry.register("route_inputs_to_entity")
    def route_inputs_to_entity(
        world: Any,
        *,
        entity_id: str | None = None,
        actions: list[str] | None = None,
    ) -> CommandHandle:
        """Route selected logical inputs, or all inputs, to one entity."""
        if entity_id in (None, ""):
            world.route_inputs_to_entity(None, actions=actions)
            return ImmediateHandle()
        world.route_inputs_to_entity(
            require_exact_entity(world, entity_id).entity_id,
            actions=actions,
        )
        return ImmediateHandle()

    @registry.register("push_input_routes")
    def push_input_routes(
        world: Any,
        *,
        actions: list[str] | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Remember the current routed targets for one set of logical inputs."""
        world.push_input_routes(actions=actions)
        return ImmediateHandle()

    @registry.register("pop_input_routes")
    def pop_input_routes(
        world: Any,
        **_: Any,
    ) -> CommandHandle:
        """Restore the last remembered routed targets for one set of logical inputs."""
        world.pop_input_routes()
        return ImmediateHandle()

    @registry.register("change_area")
    def change_area(
        context: CommandContext,
        *,
        area_id: str = "",
        entry_id: str | None = None,
        destination_entity_id: str | None = None,
        transfer_entity_id: str | None = None,
        transfer_entity_ids: list[str] | None = None,
        camera_follow: dict[str, Any] | None = None,
        source_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Queue a transition into another authored area at the next scene boundary."""
        if context.request_area_change is None:
            raise ValueError("Cannot change area without an active area-transition handler.")

        resolved_reference = str(area_id).strip()
        if not resolved_reference:
            raise ValueError("change_area requires a non-empty area_id.")

        resolved_transfer_ids: list[str] = []
        raw_transfer_ids = []
        if transfer_entity_id not in (None, ""):
            raw_transfer_ids.append(transfer_entity_id)
        raw_transfer_ids.extend(list(transfer_entity_ids or []))
        for raw_entity_id in raw_transfer_ids:
            resolved_entity_id = resolve_entity_id(
                raw_entity_id,
                source_entity_id=source_entity_id,
            )
            if not resolved_entity_id:
                logger.warning(
                    "change_area: skipping blank transfer entity reference %r.",
                    raw_entity_id,
                )
                continue
            if resolved_entity_id not in resolved_transfer_ids:
                resolved_transfer_ids.append(resolved_entity_id)

        camera_follow_request: CameraFollowRequest | None = None
        if camera_follow is not None:
            follow_spec = normalize_camera_follow_spec(
                camera_follow,
                command_name="change_area",
                source_entity_id=source_entity_id,
                require_exact_entity=False,
            )
            camera_follow_request = CameraFollowRequest(
                mode=str(follow_spec["mode"]),
                entity_id=(
                    None
                    if follow_spec.get("entity_id") in (None, "")
                    else str(follow_spec["entity_id"])
                ),
                action=(
                    None
                    if follow_spec.get("action") in (None, "")
                    else str(follow_spec["action"])
                ),
                offset_x=float(follow_spec.get("offset_x", 0.0)),
                offset_y=float(follow_spec.get("offset_y", 0.0)),
            )

        context.request_area_change(
            AreaTransitionRequest(
                area_id=resolved_reference,
                entry_id=str(entry_id).strip() or None,
                destination_entity_id=str(destination_entity_id).strip() or None,
                transfer_entity_ids=resolved_transfer_ids,
                camera_follow=camera_follow_request,
            )
        )
        return ImmediateHandle()

    @registry.register("new_game")
    def new_game(
        context: CommandContext,
        *,
        area_id: str = "",
        entry_id: str | None = None,
        destination_entity_id: str | None = None,
        camera_follow: dict[str, Any] | None = None,
        source_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Queue a fresh game session and transition into the requested area."""
        if context.request_new_game is None:
            raise ValueError("Cannot start a new game without an active session-reset handler.")

        resolved_reference = str(area_id).strip()
        if not resolved_reference:
            raise ValueError("new_game requires a non-empty area_id.")

        camera_follow_request: CameraFollowRequest | None = None
        if camera_follow is not None:
            follow_spec = normalize_camera_follow_spec(
                camera_follow,
                command_name="new_game",
                source_entity_id=source_entity_id,
                require_exact_entity=False,
            )
            camera_follow_request = CameraFollowRequest(
                mode=str(follow_spec["mode"]),
                entity_id=(
                    None
                    if follow_spec.get("entity_id") in (None, "")
                    else str(follow_spec["entity_id"])
                ),
                action=(
                    None
                    if follow_spec.get("action") in (None, "")
                    else str(follow_spec["action"])
                ),
                offset_x=float(follow_spec.get("offset_x", 0.0)),
                offset_y=float(follow_spec.get("offset_y", 0.0)),
            )

        context.request_new_game(
            AreaTransitionRequest(
                area_id=resolved_reference,
                entry_id=str(entry_id).strip() or None,
                destination_entity_id=str(destination_entity_id).strip() or None,
                camera_follow=camera_follow_request,
            )
        )
        return ImmediateHandle()

    @registry.register("load_game")
    def load_game(
        context: CommandContext,
        *,
        save_path: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Queue a save-slot load, optionally targeting an explicit relative save path."""
        if context.request_load_game is None:
            raise ValueError("Cannot load a game without an active save-slot loader.")
        context.request_load_game(str(save_path) if save_path is not None else None)
        return ImmediateHandle()

    @registry.register("save_game")
    def save_game(
        context: CommandContext,
        *,
        save_path: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Open a save-slot dialog or write to an explicit relative save path."""
        if context.save_game is None:
            raise ValueError("Cannot save a game without an active save-slot writer.")
        context.save_game(str(save_path) if save_path is not None else None)
        return ImmediateHandle()

    @registry.register("quit_game")
    def quit_game(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Request that the runtime close the game window."""
        if context.request_quit is None:
            raise ValueError("Cannot quit the game without an active runtime quit handler.")
        context.request_quit()
        return ImmediateHandle()

    @registry.register("set_simulation_paused")
    def set_simulation_paused(
        debug_inspection_enabled: bool,
        set_simulation_paused: Any | None,
        *,
        paused: bool,
        **_: Any,
    ) -> CommandHandle:
        """Enable or disable debug simulation pause when debug inspection is allowed."""
        if not debug_inspection_enabled:
            return ImmediateHandle()
        if set_simulation_paused is None:
            raise ValueError("Cannot change simulation pause without an active runtime callback.")
        set_simulation_paused(bool(paused))
        return ImmediateHandle()

    @registry.register("toggle_simulation_paused")
    def toggle_simulation_paused(
        debug_inspection_enabled: bool,
        get_simulation_paused: Any | None,
        set_simulation_paused: Any | None,
        **_: Any,
    ) -> CommandHandle:
        """Toggle debug simulation pause when debug inspection is allowed."""
        if not debug_inspection_enabled:
            return ImmediateHandle()
        if get_simulation_paused is None or set_simulation_paused is None:
            raise ValueError("Cannot toggle simulation pause without active runtime callbacks.")
        set_simulation_paused(not bool(get_simulation_paused()))
        return ImmediateHandle()

    @registry.register("step_simulation_tick")
    def step_simulation_tick(
        debug_inspection_enabled: bool,
        request_step_simulation_tick: Any | None,
        **_: Any,
    ) -> CommandHandle:
        """Request one debug simulation tick when debug inspection is allowed."""
        if not debug_inspection_enabled:
            return ImmediateHandle()
        if request_step_simulation_tick is None:
            raise ValueError("Cannot step simulation without an active runtime callback.")
        request_step_simulation_tick()
        return ImmediateHandle()

    @registry.register("adjust_output_scale")
    def adjust_output_scale(
        debug_inspection_enabled: bool,
        adjust_output_scale: Any | None,
        *,
        delta: int,
        **_: Any,
    ) -> CommandHandle:
        """Adjust debug render zoom when debug inspection is allowed."""
        if not debug_inspection_enabled:
            return ImmediateHandle()
        if adjust_output_scale is None:
            raise ValueError("Cannot adjust output scale without an active runtime callback.")
        adjust_output_scale(int(delta))
        return ImmediateHandle()


__all__ = ["register_runtime_control_commands"]
