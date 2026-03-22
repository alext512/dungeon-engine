"""Starter command implementations used by the first prototype slice."""

from __future__ import annotations

import copy
import logging
from typing import Any

from dungeon_engine import config
from dungeon_engine.commands.library import (
    instantiate_named_command_commands,
    load_named_command_definition,
)
from dungeon_engine.dialogue_library import load_dialogue_definition
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import (
    CommandContext,
    CommandHandle,
    ImmediateHandle,
    SequenceCommandHandle,
    WaitFramesHandle,
)
from dungeon_engine.world.entity import DIRECTION_VECTORS
from dungeon_engine.world.loader import instantiate_entity

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


class CameraCommandHandle(CommandHandle):
    """Wait until an interpolated camera move finishes."""

    def __init__(self, context: CommandContext) -> None:
        super().__init__()
        self.context = context
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when the camera stops moving."""
        camera = self.context.camera
        self.complete = camera is None or not camera.is_moving()


class ScreenAnimationCommandHandle(CommandHandle):
    """Wait until a screen-space animation finishes playback."""

    def __init__(self, context: CommandContext, element_id: str) -> None:
        super().__init__()
        self.context = context
        self.element_id = element_id
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when the screen element stops animating."""
        screen_manager = self.context.screen_manager
        self.complete = screen_manager is None or not screen_manager.is_animating(self.element_id)


class ActionPressCommandHandle(CommandHandle):
    """Wait for the next action-button press after the handle starts."""

    def __init__(self, context: CommandContext) -> None:
        super().__init__()
        self.context = context
        input_handler = context.input_handler
        self.start_press_count = (
            input_handler.get_action_press_count() if input_handler is not None else 0
        )
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Complete only after a later action-button press occurs."""
        input_handler = self.context.input_handler
        if input_handler is None:
            self.complete = True
            return
        self.complete = input_handler.get_action_press_count() > self.start_press_count


class DirectionReleaseCommandHandle(CommandHandle):
    """Wait until one or more logical directions are no longer held."""

    def __init__(self, context: CommandContext, directions: list[str]) -> None:
        super().__init__()
        self.context = context
        self.directions = [str(direction) for direction in directions]
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Complete when every watched direction has been released."""
        input_handler = self.context.input_handler
        if input_handler is None:
            self.complete = True
            return
        self.complete = not any(
            input_handler.is_direction_held(direction)
            for direction in self.directions
        )


class DialogueCommandHandle(CommandHandle):
    """Show blocking paginated dialogue text inside one existing screen-space box."""

    def __init__(
        self,
        context: CommandContext,
        *,
        pages: list[str],
        element_id: str,
        x: float,
        y: float,
        layer: int,
        anchor: str,
        font_id: str,
        text_color: tuple[int, int, int],
    ) -> None:
        super().__init__()
        self.context = context
        self.pages = list(pages) or [""]
        self.element_id = str(element_id)
        self.x = float(x)
        self.y = float(y)
        self.layer = int(layer)
        self.anchor = str(anchor)
        self.font_id = str(font_id)
        self.text_color = text_color
        self.current_page_index = 0

        if context.screen_manager is None:
            raise ValueError("run_dialogue requires a screen manager.")
        self.last_action_press_count = _get_action_press_count(context)
        self._show_current_page()
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Advance to the next dialogue page after each new action press."""
        if self.complete:
            return

        current_press_count = _get_action_press_count(self.context)
        if current_press_count <= self.last_action_press_count:
            return

        self.last_action_press_count = current_press_count
        if self.current_page_index + 1 < len(self.pages):
            self.current_page_index += 1
            self._show_current_page()
            return

        self.complete = True

    def _show_current_page(self) -> None:
        """Show or update the current dialogue page."""
        assert self.context.screen_manager is not None
        self.context.screen_manager.show_text(
            element_id=self.element_id,
            text=self.pages[self.current_page_index],
            x=self.x,
            y=self.y,
            layer=self.layer,
            anchor=self.anchor,  # type: ignore[arg-type]
            color=self.text_color,
            font_id=self.font_id,
        )


class NamedCommandHandle(CommandHandle):
    """Run a project-level named command definition while tracking recursion."""

    def __init__(
        self,
        context: CommandContext,
        command_id: str,
        sequence_handle: CommandHandle,
    ) -> None:
        super().__init__()
        self.context = context
        self.command_id = command_id
        self.sequence_handle = sequence_handle
        self._stack_pushed = False
        self._push_stack()
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Advance the underlying command sequence and pop the call stack when done."""
        if self.complete:
            return

        self.sequence_handle.update(dt)
        if self.sequence_handle.complete:
            self._pop_stack()
            self.complete = True

    def _push_stack(self) -> None:
        """Record entry into a named-command invocation."""
        if self._stack_pushed:
            return
        self.context.named_command_stack.append(self.command_id)
        self._stack_pushed = True

    def _pop_stack(self) -> None:
        """Remove this invocation from the named-command call stack."""
        if not self._stack_pushed:
            return
        if self.context.named_command_stack and self.context.named_command_stack[-1] == self.command_id:
            self.context.named_command_stack.pop()
        self._stack_pushed = False


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


def _get_action_press_count(context: CommandContext) -> int:
    """Return the current action-button press counter, if available."""
    input_handler = context.input_handler
    return input_handler.get_action_press_count() if input_handler is not None else 0
def _get_project_dialogue_defaults(context: CommandContext) -> dict[str, Any]:
    """Return project-authored dialogue defaults when available."""
    if context.project is None:
        return {}
    try:
        defaults = context.project.resolve_shared_variable("dialogue")
    except KeyError:
        return {}
    return defaults if isinstance(defaults, dict) else {}


def _get_dialogue_setting(
    dialogue_defaults: dict[str, Any],
    key: str,
    default: Any,
) -> Any:
    """Return one dialogue setting, falling back cleanly when absent."""
    return copy.deepcopy(dialogue_defaults.get(key, default))


def _normalize_color_tuple(
    value: Any,
    *,
    default: tuple[int, int, int],
) -> tuple[int, int, int]:
    """Convert a JSON color list/tuple into an RGB tuple."""
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return (int(value[0]), int(value[1]), int(value[2]))
        except (TypeError, ValueError):
            return default
    return default


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


def _resolve_facing_direction(entity, direction: str | None) -> str:
    """Return an explicit direction, defaulting to the entity's current facing."""
    resolved_direction = str(direction or entity.facing)
    if resolved_direction not in DIRECTION_VECTORS:
        raise ValueError(f"Unknown direction '{resolved_direction}'.")
    return resolved_direction


def _get_facing_tile(entity, direction: str | None = None) -> tuple[int, int, str]:
    """Return the tile in front of an entity for a resolved direction."""
    resolved_direction = _resolve_facing_direction(entity, direction)
    delta_x, delta_y = DIRECTION_VECTORS[resolved_direction]  # type: ignore[index]
    return entity.grid_x + delta_x, entity.grid_y + delta_y, resolved_direction


def _get_facing_target_entity(
    context: CommandContext,
    *,
    actor_entity_id: str,
    direction: str | None = None,
    prefer_blocking: bool = False,
):
    """Return the topmost entity ahead of the actor, optionally preferring blockers."""
    actor = context.world.get_entity(actor_entity_id)
    if actor is None:
        raise KeyError(f"Cannot resolve facing target for missing entity '{actor_entity_id}'.")

    target_x, target_y, _ = _get_facing_tile(actor, direction)
    if prefer_blocking:
        blocking_entity = context.collision_system.get_blocking_entity(
            target_x,
            target_y,
            ignore_entity_id=actor.entity_id,
        )
        if blocking_entity is not None:
            return blocking_entity

    for entity in reversed(
        context.world.get_entities_at(
            target_x,
            target_y,
            exclude_entity_id=actor.entity_id,
        )
    ):
        return entity
    return None


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
        wait: bool = True,
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
        if not wait:
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
        wait: bool = True,
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
        if not wait:
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
        wait: bool = True,
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
                wait=wait,
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
            if not wait:
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
            if not wait:
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
        if not wait:
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

    @registry.register("set_facing")
    def set_facing(
        context: CommandContext,
        *,
        entity_id: str,
        direction: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Set an entity's facing direction without moving it."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("set_facing: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set facing on missing entity '{resolved_id}'.")
        entity.facing = _resolve_facing_direction(entity, direction)  # type: ignore[assignment]
        return ImmediateHandle()

    @registry.register("query_facing_state")
    def query_facing_state(
        context: CommandContext,
        *,
        entity_id: str,
        store_state_var: str,
        store_entity_id_var: str | None = None,
        direction: str | None = None,
        movable_event_id: str | None = None,
        scope: str = "entity",
        variable_entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Store whether the tile in front is free, movable, or blocked."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("query_facing_state: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        actor = context.world.get_entity(resolved_id)
        if actor is None:
            raise KeyError(f"Cannot query facing state for missing entity '{resolved_id}'.")

        target_x, target_y, _ = _get_facing_tile(actor, direction)
        blocking_entity = context.collision_system.get_blocking_entity(
            target_x,
            target_y,
            ignore_entity_id=resolved_id,
        )
        if blocking_entity is None:
            state = (
                "free"
                if context.collision_system.can_move_to(
                    target_x,
                    target_y,
                    ignore_entity_id=resolved_id,
                )
                else "blocked"
            )
            blocking_entity_id = ""
        else:
            blocking_entity_id = blocking_entity.entity_id
            if movable_event_id and blocking_entity.has_enabled_event(str(movable_event_id)):
                state = "movable"
            elif blocking_entity.pushable:
                state = "movable"
            else:
                state = "blocked"

        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=variable_entity_id if scope == "entity" and variable_entity_id is not None else resolved_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        variables[store_state_var] = state
        if store_entity_id_var:
            variables[store_entity_id_var] = blocking_entity_id
        return ImmediateHandle()

    @registry.register("run_facing_event")
    def run_facing_event(
        context: CommandContext,
        *,
        entity_id: str,
        event_id: str,
        direction: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Run a named event on the entity directly in front of an actor."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("run_facing_event: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        target_entity = _get_facing_target_entity(
            context,
            actor_entity_id=resolved_id,
            direction=direction,
            prefer_blocking=True,
        )
        if target_entity is None:
            return ImmediateHandle()
        event = target_entity.get_event(event_id)
        if not target_entity.has_enabled_event(event_id) or event is None or not event.commands:
            return ImmediateHandle()
        return SequenceCommandHandle(
            registry,
            context,
            event.commands,
            base_params={
                "source_entity_id": target_entity.entity_id,
                "actor_entity_id": resolved_id,
            },
        )

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
        wait: bool = True,
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
            wait=wait,
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
        wait: bool = True,
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
            wait=wait,
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

    @registry.register("set_sprite_flip_x")
    def set_sprite_flip_x(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        flip_x: bool,
        **_: Any,
    ) -> CommandHandle:
        """Set whether an entity's sprite should be mirrored horizontally."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("set_sprite_flip_x: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set sprite flip on missing entity '{resolved_id}'.")
        entity.sprite_flip_x = bool(flip_x)
        return ImmediateHandle()

    @registry.register("play_audio")
    def play_audio(
        context: CommandContext,
        *,
        path: str,
        **_: Any,
    ) -> CommandHandle:
        """Play a one-shot audio asset from the active project's assets."""
        if context.audio_player is None:
            return ImmediateHandle()
        context.audio_player.play_audio(str(path))
        return ImmediateHandle()

    @registry.register("show_screen_image")
    def show_screen_image(
        context: CommandContext,
        *,
        element_id: str,
        path: str,
        x: int | float,
        y: int | float,
        frame_width: int | None = None,
        frame_height: int | None = None,
        frame: int = 0,
        layer: int = 0,
        anchor: str = "topleft",
        flip_x: bool = False,
        tint: tuple[int, int, int] = (255, 255, 255),
        visible: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Create or replace a screen-space image element."""
        if context.screen_manager is None:
            raise ValueError("Cannot show a screen image without a screen manager.")
        context.screen_manager.show_image(
            element_id=str(element_id),
            asset_path=str(path),
            x=float(x),
            y=float(y),
            frame_width=int(frame_width) if frame_width is not None else None,
            frame_height=int(frame_height) if frame_height is not None else None,
            frame=int(frame),
            layer=int(layer),
            anchor=str(anchor),  # type: ignore[arg-type]
            flip_x=bool(flip_x),
            tint=tuple(int(channel) for channel in tint),
            visible=bool(visible),
        )
        return ImmediateHandle()

    @registry.register("show_screen_text")
    def show_screen_text(
        context: CommandContext,
        *,
        element_id: str,
        text: str,
        x: int | float,
        y: int | float,
        layer: int = 0,
        anchor: str = "topleft",
        color: tuple[int, int, int] = config.COLOR_TEXT,
        font_id: str = config.DEFAULT_UI_FONT_ID,
        max_width: int | None = None,
        visible: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Create or replace a screen-space text element."""
        if context.screen_manager is None:
            raise ValueError("Cannot show screen text without a screen manager.")
        context.screen_manager.show_text(
            element_id=str(element_id),
            text=str(text),
            x=float(x),
            y=float(y),
            layer=int(layer),
            anchor=str(anchor),  # type: ignore[arg-type]
            color=tuple(int(channel) for channel in color),
            font_id=str(font_id),
            max_width=int(max_width) if max_width is not None else None,
            visible=bool(visible),
        )
        return ImmediateHandle()

    @registry.register("set_screen_text")
    def set_screen_text(
        context: CommandContext,
        *,
        element_id: str,
        text: str,
        **_: Any,
    ) -> CommandHandle:
        """Replace the text content of an existing screen-space text element."""
        if context.screen_manager is None:
            raise ValueError("Cannot set screen text without a screen manager.")
        context.screen_manager.set_text(str(element_id), str(text))
        return ImmediateHandle()

    @registry.register("remove_screen_element")
    def remove_screen_element(
        context: CommandContext,
        *,
        element_id: str,
        **_: Any,
    ) -> CommandHandle:
        """Remove one screen-space element."""
        if context.screen_manager is None:
            raise ValueError("Cannot remove a screen element without a screen manager.")
        context.screen_manager.remove(str(element_id))
        return ImmediateHandle()

    @registry.register("clear_screen_elements")
    def clear_screen_elements(
        context: CommandContext,
        *,
        layer: int | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Clear all screen-space elements, optionally only one layer."""
        if context.screen_manager is None:
            raise ValueError("Cannot clear screen elements without a screen manager.")
        context.screen_manager.clear(layer=layer)
        return ImmediateHandle()

    @registry.register("play_screen_animation")
    def play_screen_animation(
        context: CommandContext,
        *,
        element_id: str,
        frame_sequence: list[int],
        ticks_per_frame: int = 1,
        hold_last_frame: bool = True,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Start a one-shot frame animation on an existing screen image."""
        if context.screen_manager is None:
            raise ValueError("Cannot play a screen animation without a screen manager.")
        context.screen_manager.start_animation(
            element_id=str(element_id),
            frame_sequence=[int(frame) for frame in frame_sequence],
            ticks_per_frame=int(ticks_per_frame),
            hold_last_frame=bool(hold_last_frame),
        )
        if not wait:
            return ImmediateHandle()
        return ScreenAnimationCommandHandle(context, str(element_id))

    @registry.register("wait_for_screen_animation")
    def wait_for_screen_animation(
        context: CommandContext,
        *,
        element_id: str,
        **_: Any,
    ) -> CommandHandle:
        """Block until the requested screen-space animation finishes."""
        if context.screen_manager is None:
            raise ValueError("Cannot wait for a screen animation without a screen manager.")
        if not context.screen_manager.is_animating(str(element_id)):
            return ImmediateHandle()
        return ScreenAnimationCommandHandle(context, str(element_id))

    @registry.register("wait_frames")
    def wait_frames(
        context: CommandContext,
        *,
        frames: int,
        **_: Any,
    ) -> CommandHandle:
        """Pause the current command lane for a fixed number of simulation ticks."""
        return WaitFramesHandle(int(frames))

    @registry.register("wait_for_action_press")
    def wait_for_action_press(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Pause until the next Space/Enter-style action press occurs."""
        return ActionPressCommandHandle(context)

    @registry.register("wait_for_direction_release")
    def wait_for_direction_release(
        context: CommandContext,
        *,
        direction: str | None = None,
        directions: list[str] | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Pause until the watched logical direction keys are released."""
        watched_directions: list[str]
        if directions is not None:
            watched_directions = [str(item) for item in directions]
        elif direction is not None:
            watched_directions = [str(direction)]
        else:
            raise ValueError("wait_for_direction_release requires direction or directions.")
        if not watched_directions:
            return ImmediateHandle()
        valid_directions = {"up", "down", "left", "right"}
        for watched_direction in watched_directions:
            if watched_direction not in valid_directions:
                raise ValueError(f"Unknown direction '{watched_direction}'.")
        return DirectionReleaseCommandHandle(context, watched_directions)

    @registry.register("run_dialogue")
    def run_dialogue(
        context: CommandContext,
        *,
        dialogue_id: str | None = None,
        text: str | None = None,
        pages: list[str] | None = None,
        element_id: str = "dialogue_text",
        x: int | float = 0,
        y: int | float = 0,
        layer: int = 101,
        anchor: str = "topleft",
        font_id: str = config.DEFAULT_DIALOGUE_FONT_ID,
        max_width: int | None = None,
        max_lines: int | None = None,
        text_color: list[int] | tuple[int, int, int] | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Show blocking paginated dialogue text inside a caller-defined text box."""
        if context.screen_manager is None:
            raise ValueError("Cannot run dialogue without a screen manager.")
        if context.text_renderer is None:
            raise ValueError("Cannot run dialogue without a text renderer.")

        dialogue_data: dict[str, Any] = {}
        if dialogue_id is not None:
            if context.project is None:
                raise ValueError("run_dialogue with dialogue_id requires an active project.")
            dialogue_definition = load_dialogue_definition(context.project, str(dialogue_id))
            dialogue_data = dict(dialogue_definition.raw_data)

        if text is None and dialogue_data.get("text") is not None:
            text = str(dialogue_data["text"])
        if pages is None and dialogue_data.get("pages") is not None:
            raw_pages = dialogue_data["pages"]
            if isinstance(raw_pages, list):
                pages = [str(page) for page in raw_pages]
        if font_id == config.DEFAULT_DIALOGUE_FONT_ID and dialogue_data.get("font_id") is not None:
            font_id = str(dialogue_data["font_id"])
        if max_lines is None and dialogue_data.get("max_lines") is not None:
            max_lines = int(dialogue_data["max_lines"])
        if text_color is None and dialogue_data.get("text_color") is not None:
            text_color = dialogue_data["text_color"]

        dialogue_defaults = _get_project_dialogue_defaults(context)
        resolved_font_id = str(font_id)
        resolved_max_lines = int(
            max_lines
            if max_lines is not None
            else _get_dialogue_setting(dialogue_defaults, "max_lines", 2)
        )
        if resolved_max_lines <= 0:
            raise ValueError("run_dialogue requires max_lines > 0.")
        resolved_max_width = int(max_width) if max_width is not None else None
        if resolved_max_width is None or resolved_max_width <= 0:
            raise ValueError("run_dialogue requires a positive max_width for pagination.")

        resolved_pages: list[str] = []
        if pages:
            for page_text in pages:
                resolved_pages.extend(
                    context.text_renderer.paginate_text(
                        str(page_text),
                        resolved_max_width,
                        resolved_max_lines,
                        font_id=resolved_font_id,
                    )
                )
        elif text is not None:
            resolved_pages = context.text_renderer.paginate_text(
                str(text),
                resolved_max_width,
                resolved_max_lines,
                font_id=resolved_font_id,
            )
        else:
            raise ValueError("run_dialogue requires text or pages.")

        return DialogueCommandHandle(
            context,
            pages=resolved_pages,
            element_id=str(element_id),
            x=float(x),
            y=float(y),
            layer=int(layer),
            anchor=str(anchor),
            font_id=resolved_font_id,
            text_color=_normalize_color_tuple(
                text_color if text_color is not None else _get_dialogue_setting(dialogue_defaults, "text_color", None),
                default=config.COLOR_TEXT,
            ),
        )

    @registry.register("run_detached_commands")
    def run_detached_commands(
        context: CommandContext,
        *,
        commands: list[dict[str, Any]],
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Run a command list in the background without blocking the main lane."""
        if context.command_runner is None:
            raise ValueError("Cannot run detached commands without an active command runner.")
        handle = SequenceCommandHandle(
            registry,
            context,
            commands,
            base_params={
                **({"source_entity_id": source_entity_id} if source_entity_id is not None else {}),
                **({"actor_entity_id": actor_entity_id} if actor_entity_id is not None else {}),
            },
        )
        context.command_runner.spawn_background_handle(handle)
        return ImmediateHandle()

    @registry.register("interact_facing")
    def interact_facing(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Activate the first enabled interact target in front of an actor."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("interact_facing: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        target_entity = context.interaction_system.get_facing_target(resolved_id)
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
                "actor_entity_id": resolved_id,
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
        **event_parameters: Any,
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

        base_params: dict[str, Any] = dict(event_parameters)
        base_params["source_entity_id"] = resolved_id
        if actor_entity_id is not None:
            base_params["actor_entity_id"] = actor_entity_id
        return SequenceCommandHandle(
            registry,
            context,
            event.commands,
            base_params=base_params,
        )

    @registry.register("run_named_command")
    def run_named_command(
        context: CommandContext,
        *,
        command_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **command_parameters: Any,
    ) -> CommandHandle:
        """Execute a reusable project-level command definition from the command library."""
        if context.project is None:
            raise ValueError("Cannot run a named command without an active project context.")

        resolved_command_id = str(command_id).strip()
        if not resolved_command_id:
            logger.warning("run_named_command: skipping because command_id resolved to blank.")
            return ImmediateHandle()

        if resolved_command_id in context.named_command_stack:
            stack_preview = " -> ".join([*context.named_command_stack, resolved_command_id])
            raise ValueError(f"Detected recursive named-command cycle: {stack_preview}")

        definition = load_named_command_definition(context.project, resolved_command_id)
        instantiated_commands = instantiate_named_command_commands(definition, command_parameters)
        if not instantiated_commands:
            return ImmediateHandle()

        base_params: dict[str, Any] = {}
        if source_entity_id is not None:
            base_params["source_entity_id"] = source_entity_id
        if actor_entity_id is not None:
            base_params["actor_entity_id"] = actor_entity_id

        sequence_handle = SequenceCommandHandle(
            registry,
            context,
            instantiated_commands,
            base_params=base_params,
            auto_start=False,
        )
        if sequence_handle.complete:
            return ImmediateHandle()
        return NamedCommandHandle(context, resolved_command_id, sequence_handle)

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

    @registry.register("set_active_entity")
    def set_active_entity(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Switch which entity currently receives direct input."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("set_active_entity: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        context.world.set_active_entity(resolved_id)
        return ImmediateHandle()

    @registry.register("set_input_event_name")
    def set_input_event_name(
        context: CommandContext,
        *,
        action: str,
        event_name: str,
        **_: Any,
    ) -> CommandHandle:
        """Change which event name the engine looks up for an input action."""
        if context.input_handler is None:
            raise ValueError("Cannot change input event names without an input handler.")
        context.input_handler.set_action_event_name(str(action), str(event_name))
        return ImmediateHandle()

    @registry.register("set_camera_follow_entity")
    def set_camera_follow_entity(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Make the camera follow a specific entity."""
        if context.camera is None:
            raise ValueError("Cannot change camera follow without an active camera.")
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("set_camera_follow_entity: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        if context.world.get_entity(resolved_id) is None:
            raise KeyError(f"Cannot follow missing entity '{resolved_id}'.")
        context.camera.follow_entity(resolved_id)
        context.camera.update(context.world, advance_tick=False)
        return ImmediateHandle()

    @registry.register("set_camera_follow_active_entity")
    def set_camera_follow_active_entity(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Make the camera follow whichever entity currently receives direct input."""
        if context.camera is None:
            raise ValueError("Cannot change camera follow without an active camera.")
        context.camera.follow_active_entity()
        context.camera.update(context.world, advance_tick=False)
        return ImmediateHandle()

    @registry.register("clear_camera_follow")
    def clear_camera_follow(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Stop automatically following any entity."""
        if context.camera is None:
            raise ValueError("Cannot clear camera follow without an active camera.")
        context.camera.clear_follow()
        return ImmediateHandle()

    @registry.register("move_camera")
    def move_camera(
        context: CommandContext,
        *,
        x: int | float,
        y: int | float,
        space: str = "pixel",
        mode: str = "absolute",
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Move the camera in pixel or grid space, absolute or relative."""
        if context.camera is None:
            raise ValueError("Cannot move camera without an active camera.")
        if space not in {"pixel", "grid"}:
            raise ValueError(f"Unknown camera movement space '{space}'.")
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown camera movement mode '{mode}'.")

        target_x = float(x)
        target_y = float(y)
        if space == "grid":
            target_x *= context.area.tile_size
            target_y *= context.area.tile_size
        if mode == "relative":
            target_x += context.camera.x
            target_y += context.camera.y

        context.camera.start_move_to(
            target_x,
            target_y,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
        )
        if not context.camera.is_moving():
            return ImmediateHandle()
        return CameraCommandHandle(context)

    @registry.register("teleport_camera")
    def teleport_camera(
        context: CommandContext,
        *,
        x: int | float,
        y: int | float,
        space: str = "pixel",
        mode: str = "absolute",
        **_: Any,
    ) -> CommandHandle:
        """Move the camera instantly in pixel or grid space."""
        if context.camera is None:
            raise ValueError("Cannot teleport camera without an active camera.")
        if space not in {"pixel", "grid"}:
            raise ValueError(f"Unknown camera teleport space '{space}'.")
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown camera teleport mode '{mode}'.")

        target_x = float(x)
        target_y = float(y)
        if space == "grid":
            target_x *= context.area.tile_size
            target_y *= context.area.tile_size
        if mode == "relative":
            target_x += context.camera.x
            target_y += context.camera.y

        context.camera.teleport_to(target_x, target_y)
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
            logger.warning("set_visible: skipping - entity_id is empty (unconfigured parameter?)")
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
            logger.warning("set_solid: skipping - entity_id is empty (unconfigured parameter?)")
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
            logger.warning("set_color: skipping - entity_id is empty (unconfigured parameter?)")
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

