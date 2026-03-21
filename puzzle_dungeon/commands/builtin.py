"""Starter command implementations used by the first prototype slice."""

from __future__ import annotations

import copy
import logging
from typing import Any

from puzzle_dungeon.commands.registry import CommandRegistry
from puzzle_dungeon.commands.runner import (
    CommandContext,
    CommandHandle,
    ImmediateHandle,
    SequenceCommandHandle,
)
from puzzle_dungeon.world.loader import instantiate_entity

logger = logging.getLogger(__name__)


class MovementCommandHandle(CommandHandle):
    """Wait until all entities started by a move command finish interpolating."""

    def __init__(self, context: CommandContext, entity_ids: list[str]) -> None:
        super().__init__()
        self.context = context
        self.entity_ids = entity_ids
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when every moved entity has stopped moving."""
        self.complete = not any(
            self.context.movement_system.is_entity_moving(entity_id)
            for entity_id in self.entity_ids
        )


class AnimationCommandHandle(CommandHandle):
    """Wait until all entities started by an animation command finish playback."""

    def __init__(self, context: CommandContext, entity_ids: list[str]) -> None:
        super().__init__()
        self.context = context
        self.entity_ids = entity_ids
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when every animated entity has finished."""
        self.complete = not any(
            self.context.animation_system.is_entity_animating(entity_id)
            for entity_id in self.entity_ids
        )


def _resolve_entity_id(
    entity_id: str,
    *,
    source_entity_id: str | None,
    actor_entity_id: str | None,
) -> str:
    """Resolve special entity references used inside command specs.

    Returns an empty string when *entity_id* is blank (unconfigured parameter).
    Callers should treat an empty result as "nothing to do".
    """
    if not entity_id:
        return ""
    if entity_id == "self":
        if source_entity_id is None:
            raise ValueError("Command used 'self' without a source entity context.")
        return source_entity_id
    if entity_id == "actor":
        if actor_entity_id is None:
            raise ValueError("Command used 'actor' without an actor entity context.")
        return actor_entity_id
    return entity_id


def _resolve_variables(
    context: CommandContext,
    *,
    scope: str,
    entity_id: str | None = None,
    source_entity_id: str | None = None,
    actor_entity_id: str | None = None,
) -> dict[str, Any]:
    """Return the variables dict for the given scope."""
    if scope == "world":
        return context.world.variables
    if scope == "entity":
        if entity_id is None:
            raise ValueError("Entity scope requires entity_id.")
        resolved = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        entity = context.world.get_entity(resolved)
        if entity is None:
            raise KeyError(f"Entity '{resolved}' not found.")
        return entity.variables
    raise ValueError(f"Unknown variable scope '{scope}'.")


def _persist_entity_field(
    context: CommandContext,
    *,
    entity_id: str,
    field_name: str,
    value: Any,
) -> None:
    """Persist a single entity field when runtime persistence is available."""
    if context.persistence_runtime is None:
        return
    context.persistence_runtime.set_entity_field(entity_id, field_name, value)


def _persist_entity_event_enabled(
    context: CommandContext,
    *,
    entity_id: str,
    event_id: str,
    enabled: bool,
) -> None:
    """Persist an event enabled-state change when runtime persistence is available."""
    if context.persistence_runtime is None:
        return
    context.persistence_runtime.set_entity_event_enabled(entity_id, event_id, enabled)


_COMPARE_OPS: dict[str, Any] = {
    "eq": lambda a, b: a == b,
    "neq": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and b is not None and a > b,
    "lt": lambda a, b: a is not None and b is not None and a < b,
    "gte": lambda a, b: a is not None and b is not None and a >= b,
    "lte": lambda a, b: a is not None and b is not None and a <= b,
}


def register_builtin_commands(registry: CommandRegistry) -> None:
    """Register the minimal command set needed for the first movement slice."""

    def _step_entity(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        direction: str,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str = "immediate",
        allow_push: bool = True,
        **_: Any,
    ) -> CommandHandle:
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("move_entity_one_tile: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        moved_entity_ids = context.movement_system.request_grid_step(
            resolved_id,
            direction,  # type: ignore[arg-type]
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync=grid_sync,  # type: ignore[arg-type]
            allow_push=allow_push,
        )
        if not moved_entity_ids:
            return ImmediateHandle()
        return MovementCommandHandle(context, moved_entity_ids)

    def _move_entity_to_position(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        target_x: float,
        target_y: float,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str = "none",
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
        **_: Any,
    ) -> CommandHandle:
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("move_entity: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        moved_entity_ids = context.movement_system.request_move_to_position(
            resolved_id,
            target_x,
            target_y,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync=grid_sync,  # type: ignore[arg-type]
            target_grid_x=target_grid_x,
            target_grid_y=target_grid_y,
        )
        if not moved_entity_ids:
            return ImmediateHandle()
        return MovementCommandHandle(context, moved_entity_ids)

    def _move_entity(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        x: int | float,
        y: int | float,
        space: str = "pixel",
        mode: str = "absolute",
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str | None = None,
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
        **_: Any,
    ) -> CommandHandle:
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("move_entity: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        if space not in {"pixel", "grid"}:
            raise ValueError(f"Unknown movement space '{space}'.")
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown movement mode '{mode}'.")

        effective_grid_sync = grid_sync
        if effective_grid_sync is None:
            effective_grid_sync = "on_complete" if space == "grid" else "none"

        if space == "pixel" and mode == "absolute":
            return _move_entity_to_position(
                context,
                entity_id=resolved_id,
                target_x=float(x),
                target_y=float(y),
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                duration=duration,
                frames_needed=frames_needed,
                speed_px_per_second=speed_px_per_second,
                grid_sync=effective_grid_sync,
                target_grid_x=target_grid_x,
                target_grid_y=target_grid_y,
            )

        if space == "pixel" and mode == "relative":
            moved_entity_ids = context.movement_system.request_move_by_offset(
                resolved_id,
                float(x),
                float(y),
                duration=duration,
                frames_needed=frames_needed,
                speed_px_per_second=speed_px_per_second,
                grid_sync=effective_grid_sync,  # type: ignore[arg-type]
                target_grid_x=target_grid_x,
                target_grid_y=target_grid_y,
            )
            if not moved_entity_ids:
                return ImmediateHandle()
            return MovementCommandHandle(context, moved_entity_ids)

        if space == "grid" and mode == "absolute":
            moved_entity_ids = context.movement_system.request_move_to_grid_position(
                resolved_id,
                int(x),
                int(y),
                duration=duration,
                frames_needed=frames_needed,
                speed_px_per_second=speed_px_per_second,
                grid_sync=effective_grid_sync,  # type: ignore[arg-type]
            )
            if not moved_entity_ids:
                return ImmediateHandle()
            return MovementCommandHandle(context, moved_entity_ids)

        moved_entity_ids = context.movement_system.request_move_by_grid_offset(
            resolved_id,
            int(x),
            int(y),
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync=effective_grid_sync,  # type: ignore[arg-type]
        )
        if not moved_entity_ids:
            return ImmediateHandle()
        return MovementCommandHandle(context, moved_entity_ids)

    def _teleport_entity(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        x: int | float,
        y: int | float,
        space: str = "pixel",
        mode: str = "absolute",
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
        **_: Any,
    ) -> CommandHandle:
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("teleport_entity: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        if space not in {"pixel", "grid"}:
            raise ValueError(f"Unknown teleport space '{space}'.")
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown teleport mode '{mode}'.")

        if space == "grid":
            entity = context.world.get_entity(resolved_id)
            if entity is None:
                raise KeyError(f"Cannot teleport missing entity '{resolved_id}'.")
            grid_x = int(x) if mode == "absolute" else entity.grid_x + int(x)
            grid_y = int(y) if mode == "absolute" else entity.grid_y + int(y)
            context.movement_system.teleport_to_grid_position(resolved_id, grid_x, grid_y)
            return ImmediateHandle()

        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot teleport missing entity '{resolved_id}'.")
        pixel_x = float(x) if mode == "absolute" else entity.pixel_x + float(x)
        pixel_y = float(y) if mode == "absolute" else entity.pixel_y + float(y)
        context.movement_system.teleport_to_position(
            resolved_id,
            pixel_x,
            pixel_y,
            target_grid_x=target_grid_x,
            target_grid_y=target_grid_y,
        )
        return ImmediateHandle()

    def _play_animation(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        frame_sequence: list[int],
        frames_per_sprite_change: int = 1,
        hold_last_frame: bool = True,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("play_animation: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        context.animation_system.start_frame_animation(
            resolved_id,
            frame_sequence,
            frames_per_sprite_change=frames_per_sprite_change,
            hold_last_frame=hold_last_frame,
        )
        if not wait:
            return ImmediateHandle()
        return AnimationCommandHandle(context, [resolved_id])

    @registry.register("move_entity_one_tile")
    def move_entity_one_tile(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        direction: str,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str = "immediate",
        allow_push: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Move an entity by one grid tile while keeping motion configurable."""
        return _step_entity(
            context,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            direction=direction,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync=grid_sync,
            allow_push=allow_push,
        )

    @registry.register("move_entity")
    def move_entity(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        x: int | float,
        y: int | float,
        space: str = "pixel",
        mode: str = "absolute",
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str | None = None,
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Move an entity using pixel/grid and absolute/relative addressing."""
        return _move_entity(
            context,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            x=x,
            y=y,
            space=space,
            mode=mode,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync=grid_sync,
            target_grid_x=target_grid_x,
            target_grid_y=target_grid_y,
        )

    @registry.register("teleport_entity")
    def teleport_entity(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        x: int | float,
        y: int | float,
        space: str = "pixel",
        mode: str = "absolute",
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Instantly reposition an entity using pixel/grid and absolute/relative addressing."""
        return _teleport_entity(
            context,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            x=x,
            y=y,
            space=space,
            mode=mode,
            target_grid_x=target_grid_x,
            target_grid_y=target_grid_y,
        )

    @registry.register("wait_for_move")
    def wait_for_move(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Block the command lane until the requested entity stops moving."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("wait_for_move: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        if not context.movement_system.is_entity_moving(resolved_id):
            return ImmediateHandle()
        return MovementCommandHandle(context, [resolved_id])

    @registry.register("play_animation")
    def play_animation(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        frame_sequence: list[int],
        frames_per_sprite_change: int = 1,
        hold_last_frame: bool = True,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Play a one-shot sprite frame sequence on an entity."""
        return _play_animation(
            context,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            frame_sequence=frame_sequence,
            frames_per_sprite_change=frames_per_sprite_change,
            hold_last_frame=hold_last_frame,
            wait=wait,
        )

    @registry.register("wait_for_animation")
    def wait_for_animation(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Block the command lane until the requested entity stops animating."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("wait_for_animation: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        if not context.animation_system.is_entity_animating(resolved_id):
            return ImmediateHandle()
        return AnimationCommandHandle(context, [resolved_id])

    @registry.register("stop_animation")
    def stop_animation(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        reset_to_default: bool = False,
        **_: Any,
    ) -> CommandHandle:
        """Stop command-driven animation playback on an entity."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("stop_animation: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        context.animation_system.stop_animation(
            resolved_id,
            reset_to_default=reset_to_default,
        )
        return ImmediateHandle()

    @registry.register("set_sprite_frame")
    def set_sprite_frame(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        frame: int,
        **_: Any,
    ) -> CommandHandle:
        """Set the currently displayed sprite frame directly."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("set_sprite_frame: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set sprite frame on missing entity '{resolved_id}'.")
        entity.current_frame = int(frame)
        return ImmediateHandle()

    @registry.register("player_interact")
    def player_interact(
        context: CommandContext,
        *,
        entity_id: str,
        **_: Any,
    ) -> CommandHandle:
        """Activate the first enabled entity in front of the actor."""
        target_entity = context.interaction_system.get_facing_target(entity_id)
        if target_entity is None:
            return ImmediateHandle()
        interact_event = target_entity.get_event("interact")
        if (
            not target_entity.has_enabled_event("interact")
            or interact_event is None
            or not interact_event.commands
        ):
            return ImmediateHandle()
        return SequenceCommandHandle(
            registry,
            context,
            interact_event.commands,
            base_params={
                "source_entity_id": target_entity.entity_id,
                "actor_entity_id": entity_id,
            },
        )

    @registry.register("run_event")
    def run_event(
        context: CommandContext,
        *,
        entity_id: str,
        event_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Execute a named event on a target entity when it is enabled."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("run_event: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot run event on missing entity '{resolved_id}'.")
        if not entity.present:
            return ImmediateHandle()
        event = entity.get_event(event_id)
        if not entity.has_enabled_event(event_id) or event is None or not event.commands:
            return ImmediateHandle()

        base_params: dict[str, Any] = {}
        base_params["source_entity_id"] = resolved_id
        if actor_entity_id is not None:
            base_params["actor_entity_id"] = actor_entity_id
        return SequenceCommandHandle(
            registry,
            context,
            event.commands,
            base_params=base_params,
        )

    @registry.register("set_event_enabled")
    def set_event_enabled(
        context: CommandContext,
        *,
        entity_id: str,
        event_id: str,
        enabled: bool,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Enable or disable a named event on an entity."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("set_event_enabled: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set event enabled state on missing entity '{resolved_id}'.")
        entity.set_event_enabled(event_id, enabled)
        if persistent:
            _persist_entity_event_enabled(
                context,
                entity_id=resolved_id,
                event_id=event_id,
                enabled=enabled,
            )
        return ImmediateHandle()

    @registry.register("set_events_enabled")
    def set_events_enabled(
        context: CommandContext,
        *,
        entity_id: str,
        enabled: bool,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Enable or disable all named events on an entity at once."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("set_events_enabled: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set events enabled state on missing entity '{resolved_id}'.")
        entity.set_events_enabled(enabled)
        if persistent:
            _persist_entity_field(
                context,
                entity_id=resolved_id,
                field_name="events_enabled",
                value=enabled,
            )
        return ImmediateHandle()

    @registry.register("set_visible")
    def set_visible(
        context: CommandContext,
        *,
        entity_id: str,
        visible: bool,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Change whether an entity is rendered and targetable."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("set_visible: skipping — entity_id is empty (unconfigured parameter?)")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set visibility on missing entity '{resolved_id}'.")
        entity.visible = visible
        if persistent:
            _persist_entity_field(
                context,
                entity_id=resolved_id,
                field_name="visible",
                value=visible,
            )
        return ImmediateHandle()

    @registry.register("set_solid")
    def set_solid(
        context: CommandContext,
        *,
        entity_id: str,
        solid: bool,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Change whether an entity blocks movement."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("set_solid: skipping — entity_id is empty (unconfigured parameter?)")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set solidity on missing entity '{resolved_id}'.")
        entity.solid = solid
        if persistent:
            _persist_entity_field(
                context,
                entity_id=resolved_id,
                field_name="solid",
                value=solid,
            )
        return ImmediateHandle()

    @registry.register("set_present")
    def set_present(
        context: CommandContext,
        *,
        entity_id: str,
        present: bool,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Change whether an entity participates in the current scene."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("set_present: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set presence on missing entity '{resolved_id}'.")
        entity.set_present(present)
        if persistent:
            _persist_entity_field(
                context,
                entity_id=resolved_id,
                field_name="present",
                value=present,
            )
        return ImmediateHandle()

    @registry.register("set_color")
    def set_color(
        context: CommandContext,
        *,
        entity_id: str,
        color: list[int],
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Change an entity's debug-render color."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("set_color: skipping — entity_id is empty (unconfigured parameter?)")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set color on missing entity '{resolved_id}'.")
        entity.color = (int(color[0]), int(color[1]), int(color[2]))
        if persistent:
            _persist_entity_field(
                context,
                entity_id=resolved_id,
                field_name="color",
                value=list(entity.color),
            )
        return ImmediateHandle()

    @registry.register("destroy_entity")
    def destroy_entity(
        context: CommandContext,
        *,
        entity_id: str,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Destroy an entity instance completely."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("destroy_entity: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        if context.world.get_entity(resolved_id) is None:
            raise KeyError(f"Cannot destroy missing entity '{resolved_id}'.")
        context.world.remove_entity(resolved_id)
        if persistent and context.persistence_runtime is not None:
            context.persistence_runtime.remove_entity(resolved_id)
        return ImmediateHandle()

    @registry.register("spawn_entity")
    def spawn_entity(
        context: CommandContext,
        *,
        entity: dict[str, Any] | None = None,
        entity_id: str | None = None,
        template: str | None = None,
        kind: str | None = None,
        x: int | None = None,
        y: int | None = None,
        parameters: dict[str, Any] | None = None,
        present: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Create a new entity instance in the current world."""
        entity_data = copy.deepcopy(entity) if entity is not None else {}
        if not entity_data:
            if entity_id is None:
                raise ValueError("spawn_entity requires entity_id when no entity dict is provided.")
            if x is None or y is None:
                raise ValueError("spawn_entity requires x and y when no entity dict is provided.")
            entity_data = {
                "id": entity_id,
                "x": int(x),
                "y": int(y),
                "present": bool(present),
            }
            if template is not None:
                entity_data["template"] = template
            if kind is not None:
                entity_data["kind"] = kind
            if parameters:
                entity_data["parameters"] = copy.deepcopy(parameters)
        else:
            entity_data.setdefault("present", bool(present))

        new_entity_id = str(entity_data.get("id", "")).strip()
        if not new_entity_id:
            raise ValueError("spawn_entity requires an entity id.")
        if context.world.get_entity(new_entity_id) is not None:
            raise KeyError(f"Cannot spawn duplicate entity '{new_entity_id}'.")

        new_entity = instantiate_entity(entity_data, context.area.tile_size)
        context.world.add_entity(new_entity)
        return ImmediateHandle()

    @registry.register("set_var")
    def set_var(
        context: CommandContext,
        *,
        name: str,
        value: Any,
        scope: str = "entity",
        persistent: bool = False,
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Set a variable to a value in the given scope."""
        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        persisted_value = copy.deepcopy(value)
        variables[name] = persisted_value
        if persistent and context.persistence_runtime is not None:
            if scope == "world":
                context.persistence_runtime.set_world_variable(name, persisted_value)
            else:
                if entity_id is None:
                    raise ValueError("Persistent entity variable set requires entity_id.")
                resolved_id = _resolve_entity_id(
                    entity_id,
                    source_entity_id=source_entity_id,
                    actor_entity_id=actor_entity_id,
                )
                context.persistence_runtime.set_entity_variable(resolved_id, name, persisted_value)
        return ImmediateHandle()

    @registry.register("increment_var")
    def increment_var(
        context: CommandContext,
        *,
        name: str,
        amount: int | float = 1,
        scope: str = "entity",
        persistent: bool = False,
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Add an amount to a numeric variable (defaults to 0 if missing)."""
        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        variables[name] = variables.get(name, 0) + amount
        if persistent and context.persistence_runtime is not None:
            if scope == "world":
                context.persistence_runtime.set_world_variable(name, variables[name])
            else:
                if entity_id is None:
                    raise ValueError("Persistent entity variable increment requires entity_id.")
                resolved_id = _resolve_entity_id(
                    entity_id,
                    source_entity_id=source_entity_id,
                    actor_entity_id=actor_entity_id,
                )
                context.persistence_runtime.set_entity_variable(resolved_id, name, variables[name])
        return ImmediateHandle()

    @registry.register("check_var")
    def check_var(
        context: CommandContext,
        *,
        name: str,
        op: str = "eq",
        value: Any = None,
        scope: str = "entity",
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        then: list[dict[str, Any]] | None = None,
        **kw: Any,
    ) -> CommandHandle:
        """Branch based on a variable condition."""
        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        current = variables.get(name)
        comparator = _COMPARE_OPS.get(op)
        if comparator is None:
            raise ValueError(f"Unknown comparison operator '{op}'.")
        condition_met = comparator(current, value)
        branch = then if condition_met else kw.get("else")
        if branch:
            base_params: dict[str, Any] = {}
            if source_entity_id is not None:
                base_params["source_entity_id"] = source_entity_id
            if actor_entity_id is not None:
                base_params["actor_entity_id"] = actor_entity_id
            return SequenceCommandHandle(registry, context, branch, base_params=base_params)
        return ImmediateHandle()

    @registry.register("reset_transient_state")
    def reset_transient_state(
        context: CommandContext,
        *,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        apply: str = "immediate",
        **_: Any,
    ) -> CommandHandle:
        """Reset the current room against authored data plus persistent overrides."""
        if context.persistence_runtime is None:
            return ImmediateHandle()
        context.persistence_runtime.request_reset(
            kind="transient",
            apply=apply,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
        )
        return ImmediateHandle()

    @registry.register("reset_persistent_state")
    def reset_persistent_state(
        context: CommandContext,
        *,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        apply: str = "immediate",
        **_: Any,
    ) -> CommandHandle:
        """Clear persistent overrides for the current room or matching tagged entities."""
        if context.persistence_runtime is None:
            return ImmediateHandle()
        context.persistence_runtime.request_reset(
            kind="persistent",
            apply=apply,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
        )
        return ImmediateHandle()
