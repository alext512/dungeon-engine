"""Movement-oriented builtin commands."""

from __future__ import annotations

from collections.abc import Callable
from logging import Logger
from typing import Any

from dungeon_engine.commands.context_services import CommandServices

from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import CommandContext, CommandHandle, ImmediateHandle
from dungeon_engine.world.entity import DIRECTION_VECTORS


class MovementCommandHandle(CommandHandle):
    """Wait until all entities started by a move command finish interpolating."""

    def __init__(self, movement_system: Any, entity_ids: list[str]) -> None:
        super().__init__()
        self.movement_system = movement_system
        self.entity_ids = entity_ids
        self._move_signatures = {
            entity_id: self._movement_signature(entity_id)
            for entity_id in self.entity_ids
        }
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when every moved entity has stopped moving."""
        self.complete = not any(
            self._movement_signature(entity_id) == self._move_signatures.get(entity_id)
            for entity_id in self.entity_ids
        )

    def _movement_signature(self, entity_id: str) -> tuple[float, float, float, float, int] | None:
        """Return one stable snapshot for the entity's currently active move."""
        entity = self.movement_system.world.get_entity(entity_id)
        if entity is None or not entity.movement_state.active:
            return None
        movement = entity.movement_state
        return (
            float(movement.start_pixel_x),
            float(movement.start_pixel_y),
            float(movement.target_pixel_x),
            float(movement.target_pixel_y),
            int(movement.total_ticks),
        )


def _resolve_world_services(
    *,
    services: CommandServices | None,
    world: Any,
    area: Any,
    movement_system: Any,
    collision_system: Any,
    interaction_system: Any,
) -> tuple[Any, Any, Any, Any, Any]:
    """Return world services, preferring command services when available."""
    if services is not None and services.world is not None:
        return (
            services.world.world,
            services.world.area,
            services.world.movement_system,
            services.world.collision_system,
            services.world.interaction_system,
        )
    return world, area, movement_system, collision_system, interaction_system


def _resolve_standard_direction(entity: Any, direction: str | None) -> str:
    """Resolve one standard movement/interact direction."""
    if direction is None:
        return entity.get_effective_facing()
    resolved_direction = str(direction).strip().lower()
    if resolved_direction not in DIRECTION_VECTORS:
        raise ValueError("direction must be 'up', 'down', 'left', or 'right'.")
    return resolved_direction


def _run_on_blocked_if_present(
    *,
    dispatch_named_entity_command: Callable[..., CommandHandle],
    context: CommandContext,
    actor: Any,
    runtime_params: dict[str, Any] | None = None,
) -> CommandHandle:
    """Dispatch the actor's generic on_blocked hook when it exists."""
    return dispatch_named_entity_command(
        context=context,
        entity_id=actor.entity_id,
        command_id="on_blocked",
        runtime_params=runtime_params,
        entity_refs={"instigator": actor.entity_id},
        refs_mode="merge",
    )


def _iter_nested_command_specs(commands: Any) -> list[dict[str, Any]]:
    """Return direct and simply nested command specs from an authored command list."""
    if not isinstance(commands, list):
        return []
    specs: list[dict[str, Any]] = []
    for command in commands:
        if not isinstance(command, dict):
            continue
        specs.append(command)
        for nested_key in ("commands", "on_start", "on_end"):
            specs.extend(_iter_nested_command_specs(command.get(nested_key)))
    return specs


def _can_entity_enter_cell(world: Any, grid_x: int, grid_y: int, entrant: Any) -> bool:
    """Return False when a kind-gated active transition rejects this entrant."""
    entrant_kind = str(entrant.kind).strip()
    for receiver in world.get_entities_at(
        grid_x,
        grid_y,
        exclude_entity_id=entrant.entity_id,
        include_hidden=True,
    ):
        if not receiver.has_enabled_entity_command("on_occupant_enter"):
            continue
        entity_command = receiver.get_entity_command("on_occupant_enter")
        if entity_command is None:
            continue
        for command in _iter_nested_command_specs(entity_command.commands):
            if str(command.get("type", "")).strip() != "change_area":
                continue
            if "allowed_instigator_kinds" not in command:
                continue
            allowed = command["allowed_instigator_kinds"]
            if not isinstance(allowed, list):
                continue
            allowed_kinds = {
                str(kind).strip()
                for kind in allowed
                if str(kind).strip()
            }
            if entrant_kind not in allowed_kinds:
                return False
    return True


def _attempt_standard_push(
    *,
    actor: Any,
    direction: str,
    world: Any,
    area: Any,
    collision_system: Any,
    movement_system: Any,
    push_strength: int,
    duration: float | None,
    frames_needed: int | None,
    speed_px_per_second: float | None,
    wait: bool,
    persistent: bool | None = None,
) -> tuple[bool, list[str]]:
    """Try to push one blocking entity one cell in the requested direction."""
    delta_x, delta_y = DIRECTION_VECTORS[direction]  # type: ignore[index]
    blocker_x = actor.grid_x + delta_x
    blocker_y = actor.grid_y + delta_y
    blockers = collision_system.get_blocking_entities(
        blocker_x,
        blocker_y,
        ignore_entity_id=actor.entity_id,
    )
    if len(blockers) != 1:
        return False, []
    blocker = blockers[0]
    if not blocker.is_effectively_pushable():
        return False, []
    if int(push_strength) < int(blocker.weight):
        return False, []

    target_x = blocker.grid_x + delta_x
    target_y = blocker.grid_y + delta_y
    if area.is_blocked(target_x, target_y):
        return False, []
    if collision_system.get_blocking_entities(
        target_x,
        target_y,
        ignore_entity_id=blocker.entity_id,
    ):
        return False, []
    if not _can_entity_enter_cell(world, target_x, target_y, blocker):
        return False, []

    moved_entity_ids = movement_system.request_grid_step(
        blocker.entity_id,
        direction,  # type: ignore[arg-type]
        duration=duration,
        frames_needed=frames_needed,
        speed_px_per_second=speed_px_per_second,
        grid_sync="immediate",
        persistent=persistent,
    )
    if not moved_entity_ids:
        return False, []
    if not wait:
        return True, moved_entity_ids
    return True, moved_entity_ids


def _require_entity_space(
    world: Any,
    entity_id: str,
    *,
    require_exact_entity: Callable[[Any, str], Any],
    expected_space: str,
    command_name: str,
) -> Any:
    entity = require_exact_entity(world, entity_id)
    if entity.space != expected_space:
        raise ValueError(
            f"{command_name} requires entity '{entity.entity_id}' to use space "
            f"'{expected_space}', but it uses '{entity.space}'."
        )
    return entity


def _set_entity_grid_position(
    *,
    require_exact_entity: Callable[[Any, str], Any],
    world: Any,
    movement_system: Any,
    entity_id: str,
    x: int,
    y: int,
    mode: str = "absolute",
    persistent: bool | None = None,
    **_: Any,
) -> CommandHandle:
    entity = _require_entity_space(
        world,
        entity_id,
        require_exact_entity=require_exact_entity,
        expected_space="world",
        command_name="set_entity_grid_position",
    )
    if mode not in {"absolute", "relative"}:
        raise ValueError(f"Unknown grid-position mode '{mode}'.")
    target_x = int(x) if mode == "absolute" else entity.grid_x + int(x)
    target_y = int(y) if mode == "absolute" else entity.grid_y + int(y)
    movement_system.set_grid_position(
        entity.entity_id,
        target_x,
        target_y,
        persistent=persistent,
    )
    return ImmediateHandle()


def _set_entity_pixel_position(
    *,
    require_exact_entity: Callable[[Any, str], Any],
    world: Any,
    movement_system: Any,
    entity_id: str,
    x: int | float,
    y: int | float,
    mode: str = "absolute",
    expected_space: str,
    command_name: str,
    persistent: bool | None = None,
    **_: Any,
) -> CommandHandle:
    entity = _require_entity_space(
        world,
        entity_id,
        require_exact_entity=require_exact_entity,
        expected_space=expected_space,
        command_name=command_name,
    )
    if mode not in {"absolute", "relative"}:
        raise ValueError(f"Unknown {expected_space}-position mode '{mode}'.")
    target_x = float(x) if mode == "absolute" else entity.pixel_x + float(x)
    target_y = float(y) if mode == "absolute" else entity.pixel_y + float(y)
    movement_system.set_pixel_position(
        entity.entity_id,
        target_x,
        target_y,
        persistent=persistent,
    )
    return ImmediateHandle()


def _move_entity_pixel_position(
    *,
    require_exact_entity: Callable[[Any, str], Any],
    movement_handle_factory: Callable[[Any, list[str]], CommandHandle],
    world: Any,
    movement_system: Any,
    entity_id: str,
    x: int | float,
    y: int | float,
    mode: str = "absolute",
    expected_space: str,
    command_name: str,
    duration: float | None = None,
    frames_needed: int | None = None,
    speed_px_per_second: float | None = None,
    wait: bool = True,
    persistent: bool | None = None,
    **_: Any,
) -> CommandHandle:
    entity = _require_entity_space(
        world,
        entity_id,
        require_exact_entity=require_exact_entity,
        expected_space=expected_space,
        command_name=command_name,
    )
    if mode not in {"absolute", "relative"}:
        raise ValueError(f"Unknown {expected_space}-position mode '{mode}'.")
    if mode == "absolute":
        moved_entity_ids = movement_system.request_move_to_position(
            entity.entity_id,
            float(x),
            float(y),
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync="none",
            persistent=persistent,
        )
    else:
        moved_entity_ids = movement_system.request_move_by_offset(
            entity.entity_id,
            float(x),
            float(y),
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync="none",
            persistent=persistent,
        )
    if not moved_entity_ids or not wait:
        return ImmediateHandle()
    return movement_handle_factory(movement_system, moved_entity_ids)


def register_movement_commands(
    registry: CommandRegistry,
    *,
    logger: Logger,
    require_exact_entity: Callable[[Any, str], Any],
    resolve_entity_id: Callable[..., str | None],
    dispatch_named_entity_command: Callable[..., CommandHandle],
) -> None:
    """Register builtin commands that move entities or use facing interactions."""

    @registry.register("set_entity_grid_position")
    def set_entity_grid_position(
        services: CommandServices | None,
        world: Any,
        movement_system: Any,
        *,
        entity_id: str,
        x: int,
        y: int,
        mode: str = "absolute",
        persistent: bool | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Instantly update a world-space entity's logical grid position."""
        resolved_world, _, resolved_movement_system, _, _ = _resolve_world_services(
            services=services,
            world=world,
            area=None,
            movement_system=movement_system,
            collision_system=None,
            interaction_system=None,
        )
        return _set_entity_grid_position(
            require_exact_entity=require_exact_entity,
            world=resolved_world,
            movement_system=resolved_movement_system,
            entity_id=entity_id,
            x=x,
            y=y,
            mode=mode,
            persistent=persistent,
        )

    @registry.register("set_entity_world_position")
    def set_entity_world_position(
        services: CommandServices | None,
        world: Any,
        movement_system: Any,
        *,
        entity_id: str,
        x: int | float,
        y: int | float,
        mode: str = "absolute",
        persistent: bool | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Instantly update a world-space entity's pixel position."""
        resolved_world, _, resolved_movement_system, _, _ = _resolve_world_services(
            services=services,
            world=world,
            area=None,
            movement_system=movement_system,
            collision_system=None,
            interaction_system=None,
        )
        return _set_entity_pixel_position(
            require_exact_entity=require_exact_entity,
            world=resolved_world,
            movement_system=resolved_movement_system,
            entity_id=entity_id,
            x=x,
            y=y,
            mode=mode,
            expected_space="world",
            command_name="set_entity_world_position",
            persistent=persistent,
        )

    @registry.register("set_entity_screen_position")
    def set_entity_screen_position(
        services: CommandServices | None,
        world: Any,
        movement_system: Any,
        *,
        entity_id: str,
        x: int | float,
        y: int | float,
        mode: str = "absolute",
        persistent: bool | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Instantly update a screen-space entity's pixel position."""
        resolved_world, _, resolved_movement_system, _, _ = _resolve_world_services(
            services=services,
            world=world,
            area=None,
            movement_system=movement_system,
            collision_system=None,
            interaction_system=None,
        )
        return _set_entity_pixel_position(
            require_exact_entity=require_exact_entity,
            world=resolved_world,
            movement_system=resolved_movement_system,
            entity_id=entity_id,
            x=x,
            y=y,
            mode=mode,
            expected_space="screen",
            command_name="set_entity_screen_position",
            persistent=persistent,
        )

    @registry.register("move_entity_world_position")
    def move_entity_world_position(
        services: CommandServices | None,
        world: Any,
        movement_system: Any,
        *,
        entity_id: str,
        x: int | float,
        y: int | float,
        mode: str = "absolute",
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        wait: bool = True,
        persistent: bool | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Interpolate a world-space entity's pixel position."""
        resolved_world, _, resolved_movement_system, _, _ = _resolve_world_services(
            services=services,
            world=world,
            area=None,
            movement_system=movement_system,
            collision_system=None,
            interaction_system=None,
        )
        return _move_entity_pixel_position(
            require_exact_entity=require_exact_entity,
            movement_handle_factory=MovementCommandHandle,
            world=resolved_world,
            movement_system=resolved_movement_system,
            entity_id=entity_id,
            x=x,
            y=y,
            mode=mode,
            expected_space="world",
            command_name="move_entity_world_position",
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            wait=wait,
            persistent=persistent,
        )

    @registry.register("move_entity_screen_position")
    def move_entity_screen_position(
        services: CommandServices | None,
        world: Any,
        movement_system: Any,
        *,
        entity_id: str,
        x: int | float,
        y: int | float,
        mode: str = "absolute",
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        wait: bool = True,
        persistent: bool | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Interpolate a screen-space entity's pixel position."""
        resolved_world, _, resolved_movement_system, _, _ = _resolve_world_services(
            services=services,
            world=world,
            area=None,
            movement_system=movement_system,
            collision_system=None,
            interaction_system=None,
        )
        return _move_entity_pixel_position(
            require_exact_entity=require_exact_entity,
            movement_handle_factory=MovementCommandHandle,
            world=resolved_world,
            movement_system=resolved_movement_system,
            entity_id=entity_id,
            x=x,
            y=y,
            mode=mode,
            expected_space="screen",
            command_name="move_entity_screen_position",
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            wait=wait,
            persistent=persistent,
        )

    @registry.register("move_in_direction", validation_mode="mixed")
    def move_in_direction(
        context: CommandContext,
        services: CommandServices | None,
        world: Any,
        area: Any,
        movement_system: Any,
        collision_system: Any,
        *,
        entity_id: str,
        direction: str | None = None,
        push_strength: int | None = None,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        wait: bool = True,
        persistent: bool | None = None,
        source_entity_id: str | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Resolve one standard grid step using blocked cells and solid/pushable entities."""
        resolved_world, resolved_area, resolved_movement_system, resolved_collision_system, _ = _resolve_world_services(
            services=services,
            world=world,
            area=area,
            movement_system=movement_system,
            collision_system=collision_system,
            interaction_system=None,
        )
        if resolved_movement_system is None:
            raise ValueError("move_in_direction requires an active movement system.")
        if resolved_collision_system is None:
            raise ValueError("move_in_direction requires an active collision system.")

        resolved_id = resolve_entity_id(entity_id, source_entity_id=source_entity_id)
        if not resolved_id:
            logger.warning("move_in_direction: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        actor = resolved_world.get_entity(resolved_id)
        if actor is None:
            raise KeyError(f"Cannot move missing entity '{resolved_id}'.")
        if not actor.present:
            return ImmediateHandle()
        if actor.space != "world":
            raise ValueError("move_in_direction only supports world-space entities.")
        if actor.movement_state.active:
            return ImmediateHandle()

        resolved_direction = _resolve_standard_direction(actor, direction)
        actor.set_facing_value(resolved_direction)
        delta_x, delta_y = DIRECTION_VECTORS[resolved_direction]  # type: ignore[index]
        target_x = actor.grid_x + delta_x
        target_y = actor.grid_y + delta_y

        if resolved_collision_system.can_move_to(
            target_x,
            target_y,
            ignore_entity_id=actor.entity_id,
        ) and _can_entity_enter_cell(resolved_world, target_x, target_y, actor):
            moved_entity_ids = resolved_movement_system.request_grid_step(
                actor.entity_id,
                resolved_direction,  # type: ignore[arg-type]
                duration=duration,
                frames_needed=frames_needed,
                speed_px_per_second=speed_px_per_second,
                grid_sync="immediate",
                persistent=persistent,
            )
            if not moved_entity_ids or not wait:
                return ImmediateHandle()
            return MovementCommandHandle(resolved_movement_system, moved_entity_ids)

        resolved_push_strength = int(actor.push_strength if push_strength is None else push_strength)
        if resolved_push_strength < 0:
            raise ValueError("move_in_direction push_strength must be zero or positive.")

        if (
            resolved_push_strength > 0
            and not resolved_area.is_blocked(target_x, target_y)
            and _can_entity_enter_cell(resolved_world, target_x, target_y, actor)
        ):
            pushed, pushed_entity_ids = _attempt_standard_push(
                actor=actor,
                direction=resolved_direction,
                world=resolved_world,
                area=resolved_area,
                collision_system=resolved_collision_system,
                movement_system=resolved_movement_system,
                push_strength=resolved_push_strength,
                duration=duration,
                frames_needed=frames_needed,
                speed_px_per_second=speed_px_per_second,
                wait=wait,
                persistent=persistent,
            )
            if pushed:
                moved_entity_ids = resolved_movement_system.request_grid_step(
                    actor.entity_id,
                    resolved_direction,  # type: ignore[arg-type]
                    duration=duration,
                    frames_needed=frames_needed,
                    speed_px_per_second=speed_px_per_second,
                    grid_sync="immediate",
                    persistent=persistent,
                )
                combined_entity_ids = list(dict.fromkeys([*pushed_entity_ids, *moved_entity_ids]))
                if not combined_entity_ids or not wait:
                    return ImmediateHandle()
                return MovementCommandHandle(resolved_movement_system, combined_entity_ids)

        blocked_runtime_params = dict(runtime_params)
        blocked_runtime_params.update(
            {
                "direction": resolved_direction,
                "from_x": int(actor.grid_x),
                "from_y": int(actor.grid_y),
                "target_x": int(target_x),
                "target_y": int(target_y),
            }
        )
        blockers = resolved_collision_system.get_blocking_entities(
            target_x,
            target_y,
            ignore_entity_id=actor.entity_id,
        )
        if len(blockers) == 1:
            blocked_runtime_params["blocking_entity_id"] = blockers[0].entity_id
        return _run_on_blocked_if_present(
            dispatch_named_entity_command=dispatch_named_entity_command,
            context=context,
            actor=actor,
            runtime_params=blocked_runtime_params,
        )

    @registry.register("push_facing", validation_mode="mixed")
    def push_facing(
        context: CommandContext,
        services: CommandServices | None,
        world: Any,
        area: Any,
        movement_system: Any,
        collision_system: Any,
        *,
        entity_id: str,
        direction: str | None = None,
        push_strength: int | None = None,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        wait: bool = True,
        persistent: bool | None = None,
        source_entity_id: str | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Try to push exactly one blocker in the actor's facing direction without moving the actor."""
        resolved_world, resolved_area, resolved_movement_system, resolved_collision_system, _ = _resolve_world_services(
            services=services,
            world=world,
            area=area,
            movement_system=movement_system,
            collision_system=collision_system,
            interaction_system=None,
        )
        if resolved_movement_system is None:
            raise ValueError("push_facing requires an active movement system.")
        if resolved_collision_system is None:
            raise ValueError("push_facing requires an active collision system.")

        resolved_id = resolve_entity_id(entity_id, source_entity_id=source_entity_id)
        if not resolved_id:
            logger.warning("push_facing: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        actor = resolved_world.get_entity(resolved_id)
        if actor is None:
            raise KeyError(f"Cannot push with missing entity '{resolved_id}'.")
        if not actor.present:
            return ImmediateHandle()
        if actor.space != "world":
            raise ValueError("push_facing only supports world-space entities.")

        resolved_direction = _resolve_standard_direction(actor, direction)
        actor.set_facing_value(resolved_direction)
        resolved_push_strength = int(actor.push_strength if push_strength is None else push_strength)
        if resolved_push_strength < 0:
            raise ValueError("push_facing push_strength must be zero or positive.")

        pushed, moved_entity_ids = _attempt_standard_push(
            actor=actor,
            direction=resolved_direction,
            world=resolved_world,
            area=resolved_area,
            collision_system=resolved_collision_system,
            movement_system=resolved_movement_system,
            push_strength=resolved_push_strength,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            wait=wait,
            persistent=persistent,
        )
        if pushed:
            if not moved_entity_ids or not wait:
                return ImmediateHandle()
            return MovementCommandHandle(resolved_movement_system, moved_entity_ids)

        delta_x, delta_y = DIRECTION_VECTORS[resolved_direction]  # type: ignore[index]
        blocked_runtime_params = dict(runtime_params)
        blocked_runtime_params.update(
            {
                "direction": resolved_direction,
                "from_x": int(actor.grid_x),
                "from_y": int(actor.grid_y),
                "target_x": int(actor.grid_x + delta_x),
                "target_y": int(actor.grid_y + delta_y),
            }
        )
        blockers = resolved_collision_system.get_blocking_entities(
            actor.grid_x + delta_x,
            actor.grid_y + delta_y,
            ignore_entity_id=actor.entity_id,
        )
        if len(blockers) == 1:
            blocked_runtime_params["blocking_entity_id"] = blockers[0].entity_id
        return _run_on_blocked_if_present(
            dispatch_named_entity_command=dispatch_named_entity_command,
            context=context,
            actor=actor,
            runtime_params=blocked_runtime_params,
        )

    @registry.register("interact_facing", validation_mode="mixed")
    def interact_facing(
        context: CommandContext,
        services: CommandServices | None,
        world: Any,
        interaction_system: Any,
        *,
        entity_id: str,
        direction: str | None = None,
        source_entity_id: str | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Resolve the standard facing target and dispatch its normal interact command."""
        resolved_world, _, _, _, resolved_interaction_system = _resolve_world_services(
            services=services,
            world=world,
            area=None,
            movement_system=None,
            collision_system=None,
            interaction_system=interaction_system,
        )
        if resolved_interaction_system is None:
            raise ValueError("interact_facing requires an active interaction system.")

        resolved_id = resolve_entity_id(entity_id, source_entity_id=source_entity_id)
        if not resolved_id:
            logger.warning("interact_facing: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        actor = resolved_world.get_entity(resolved_id)
        if actor is None:
            raise KeyError(f"Cannot interact with missing entity '{resolved_id}'.")
        if not actor.present:
            return ImmediateHandle()
        if actor.space != "world":
            raise ValueError("interact_facing only supports world-space entities.")

        resolved_direction = _resolve_standard_direction(actor, direction)
        actor.set_facing_value(resolved_direction)
        target = resolved_interaction_system.get_facing_target(actor.entity_id)
        if target is None:
            return ImmediateHandle()
        return dispatch_named_entity_command(
            context=context,
            entity_id=target.entity_id,
            command_id="interact",
            runtime_params=runtime_params,
            entity_refs={"instigator": actor.entity_id},
            refs_mode="merge",
        )

    @registry.register("wait_for_move")
    def wait_for_move(
        services: CommandServices | None,
        world: Any,
        movement_system: Any,
        *,
        entity_id: str,
        **_: Any,
    ) -> CommandHandle:
        """Block the command lane until the requested entity stops moving."""
        resolved_world, _, resolved_movement_system, _, _ = _resolve_world_services(
            services=services,
            world=world,
            area=None,
            movement_system=movement_system,
            collision_system=None,
            interaction_system=None,
        )
        resolved_id = require_exact_entity(resolved_world, entity_id).entity_id
        if not resolved_movement_system.is_entity_moving(resolved_id):
            return ImmediateHandle()
        return MovementCommandHandle(resolved_movement_system, [resolved_id])
