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


def _store_variable(
    context: CommandContext,
    *,
    scope: str,
    name: str,
    value: Any,
    entity_id: str | None = None,
    source_entity_id: str | None = None,
    actor_entity_id: str | None = None,
) -> None:
    """Store one resolved value into entity/world variables."""
    variables = _resolve_variables(
        context,
        scope=scope,
        entity_id=entity_id,
        source_entity_id=source_entity_id,
        actor_entity_id=actor_entity_id,
    )
    variables[str(name)] = copy.deepcopy(value)


def _resolve_text_session_source(
    context: CommandContext,
    *,
    dialogue_id: str | None = None,
    text: str | None = None,
    pages: list[str] | None = None,
    font_id: str = config.DEFAULT_DIALOGUE_FONT_ID,
    max_lines: int | None = None,
) -> tuple[str | None, list[str] | None, str, int | None]:
    """Resolve dialogue/text-session source data from inline text or a dialogue asset."""
    dialogue_data: dict[str, Any] = {}
    if dialogue_id is not None:
        if context.project is None:
            raise ValueError("Text sessions with dialogue_id require an active project.")
        dialogue_definition = load_dialogue_definition(context.project, str(dialogue_id))
        dialogue_data = dict(dialogue_definition.raw_data)

    resolved_text = text
    resolved_pages = pages
    resolved_font_id = str(font_id)
    resolved_max_lines = max_lines

    if resolved_text is None and dialogue_data.get("text") is not None:
        resolved_text = str(dialogue_data["text"])
    if resolved_pages is None and dialogue_data.get("pages") is not None:
        raw_pages = dialogue_data["pages"]
        if isinstance(raw_pages, list):
            resolved_pages = [str(page) for page in raw_pages]
    if resolved_font_id == config.DEFAULT_DIALOGUE_FONT_ID and dialogue_data.get("font_id") is not None:
        resolved_font_id = str(dialogue_data["font_id"])
    if resolved_max_lines is None and dialogue_data.get("max_lines") is not None:
        resolved_max_lines = int(dialogue_data["max_lines"])

    if resolved_text is None and not resolved_pages:
        raise ValueError("Text session preparation requires text or pages.")

    return resolved_text, resolved_pages, resolved_font_id, resolved_max_lines


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
    entity: Any,
) -> None:
    """Persist a single entity field when runtime persistence is available."""
    if context.persistence_runtime is None:
        return
    context.persistence_runtime.set_entity_field(
        entity_id,
        field_name,
        value,
        entity=entity,
        tile_size=context.area.tile_size,
    )


def _persist_entity_event_enabled(
    context: CommandContext,
    *,
    entity_id: str,
    event_id: str,
    enabled: bool,
    entity: Any,
) -> None:
    """Persist an event enabled-state change when runtime persistence is available."""
    if context.persistence_runtime is None:
        return
    context.persistence_runtime.set_entity_event_enabled(
        entity_id,
        event_id,
        enabled,
        entity=entity,
        tile_size=context.area.tile_size,
    )


def _normalize_input_map(value: Any) -> dict[str, str]:
    """Convert JSON-like input-map data into a stable string-to-string mapping."""
    if not isinstance(value, dict):
        raise ValueError("input_map must be an object.")
    return {
        str(action): str(event_name)
        for action, event_name in value.items()
    }


def _apply_entity_field_value(
    entity: Any,
    field_name: str,
    value: Any,
) -> tuple[str, Any]:
    """Apply one supported runtime entity field mutation and return its persistent form."""
    path = [segment for segment in str(field_name).split(".") if segment]
    if not path:
        raise ValueError("set_entity_field requires a non-empty field name.")

    root = path[0]
    if root == "facing":
        if len(path) != 1:
            raise ValueError("facing does not support nested field paths.")
        entity.facing = _resolve_facing_direction(entity, str(value))  # type: ignore[assignment]
        return "facing", entity.facing

    if root == "solid":
        if len(path) != 1:
            raise ValueError("solid does not support nested field paths.")
        entity.solid = bool(value)
        return "solid", entity.solid

    if root == "pushable":
        if len(path) != 1:
            raise ValueError("pushable does not support nested field paths.")
        entity.pushable = bool(value)
        return "pushable", entity.pushable

    if root == "present":
        if len(path) != 1:
            raise ValueError("present does not support nested field paths.")
        entity.set_present(bool(value))
        return "present", entity.present

    if root == "visible":
        if len(path) != 1:
            raise ValueError("visible does not support nested field paths.")
        entity.visible = bool(value)
        return "visible", entity.visible

    if root == "events_enabled":
        if len(path) != 1:
            raise ValueError("events_enabled does not support nested field paths.")
        entity.set_events_enabled(bool(value))
        return "events_enabled", entity.events_enabled

    if root == "layer":
        if len(path) != 1:
            raise ValueError("layer does not support nested field paths.")
        entity.layer = int(value)
        return "layer", entity.layer

    if root == "stack_order":
        if len(path) != 1:
            raise ValueError("stack_order does not support nested field paths.")
        entity.stack_order = int(value)
        return "stack_order", entity.stack_order

    if root == "color":
        if len(path) != 1:
            raise ValueError("color does not support nested field paths.")
        if not isinstance(value, (list, tuple)) or len(value) < 3:
            raise ValueError("color must be a list or tuple with at least 3 channels.")
        entity.color = (int(value[0]), int(value[1]), int(value[2]))
        return "color", list(entity.color)

    if root == "sprite_flip_x":
        if len(path) != 1:
            raise ValueError("sprite_flip_x does not support nested field paths.")
        entity.sprite_flip_x = bool(value)
        return "sprite_flip_x", entity.sprite_flip_x

    if root == "input_map":
        if len(path) == 1:
            entity.input_map = _normalize_input_map(value)
        elif len(path) == 2:
            entity.input_map[str(path[1])] = str(value)
        else:
            raise ValueError("input_map only supports one nested key level.")
        return "input_map", copy.deepcopy(entity.input_map)

    raise ValueError(
        f"Unsupported entity field '{field_name}'. "
        "Use set_var for variables and dedicated commands for events/template rebuilds."
    )


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

    def _set_entity_field_handle(
        context: CommandContext,
        *,
        entity_id: str,
        field_name: str,
        value: Any,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
    ) -> CommandHandle:
        """Apply one generic entity field mutation through the shared helper."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("set_entity_field: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set field on missing entity '{resolved_id}'.")
        persisted_field_name, persisted_value = _apply_entity_field_value(
            entity,
            str(field_name),
            value,
        )
        if persistent:
            _persist_entity_field(
                context,
                entity_id=resolved_id,
                field_name=persisted_field_name,
                value=persisted_value,
                entity=entity,
            )
        return ImmediateHandle()

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
        return _set_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="facing",
            value=direction,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )

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
        return _set_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="sprite_flip_x",
            value=flip_x,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )

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

    @registry.register("prepare_text_session")
    def prepare_text_session(
        context: CommandContext,
        *,
        entity_id: str,
        session_id: str,
        mode: str = "pages",
        dialogue_id: str | None = None,
        text: str | None = None,
        pages: list[str] | None = None,
        font_id: str = config.DEFAULT_DIALOGUE_FONT_ID,
        max_width: int | None = None,
        max_lines: int | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Prepare one reusable text session for later reads/advances."""
        if context.text_session_manager is None:
            raise ValueError("Cannot prepare text sessions without a text session manager.")

        resolved_entity_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_entity_id:
            logger.warning("prepare_text_session: skipping because entity_id resolved to blank.")
            return ImmediateHandle()

        resolved_text, resolved_pages, resolved_font_id, resolved_max_lines = _resolve_text_session_source(
            context,
            dialogue_id=dialogue_id,
            text=text,
            pages=pages,
            font_id=font_id,
            max_lines=max_lines,
        )
        dialogue_defaults = _get_project_dialogue_defaults(context)
        resolved_mode = str(mode).strip().lower()
        resolved_max_width = int(max_width) if max_width is not None else None
        if resolved_max_width is None or resolved_max_width <= 0:
            raise ValueError("prepare_text_session requires a positive max_width.")
        if resolved_mode == "pages":
            resolved_max_lines = int(
                resolved_max_lines
                if resolved_max_lines is not None
                else _get_dialogue_setting(dialogue_defaults, "max_lines", 2)
            )
        context.text_session_manager.prepare_session(
            resolved_entity_id,
            str(session_id),
            mode=resolved_mode,
            font_id=resolved_font_id,
            max_width=resolved_max_width,
            max_lines=resolved_max_lines,
            text=resolved_text,
            pages=resolved_pages,
        )
        return ImmediateHandle()

    @registry.register("read_text_session")
    def read_text_session(
        context: CommandContext,
        *,
        entity_id: str,
        session_id: str,
        store_text_var: str,
        store_has_more_var: str | None = None,
        store_position_var: str | None = None,
        store_total_var: str | None = None,
        scope: str = "entity",
        store_entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Read the current visible chunk from one prepared text session into vars."""
        if context.text_session_manager is None:
            raise ValueError("Cannot read text sessions without a text session manager.")

        resolved_entity_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_entity_id:
            logger.warning("read_text_session: skipping because entity_id resolved to blank.")
            return ImmediateHandle()

        resolved_store_entity_id = store_entity_id
        if scope == "entity":
            resolved_store_entity_id = _resolve_entity_id(
                store_entity_id or resolved_entity_id,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
            )
            if not resolved_store_entity_id:
                logger.warning("read_text_session: skipping because store_entity_id resolved to blank.")
                return ImmediateHandle()

        result = context.text_session_manager.read_session(
            resolved_entity_id,
            str(session_id),
        )
        _store_variable(
            context,
            scope=scope,
            entity_id=resolved_store_entity_id,
            name=store_text_var,
            value=result.text,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if store_has_more_var:
            _store_variable(
                context,
                scope=scope,
                entity_id=resolved_store_entity_id,
                name=store_has_more_var,
                value=result.has_more,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
            )
        if store_position_var:
            _store_variable(
                context,
                scope=scope,
                entity_id=resolved_store_entity_id,
                name=store_position_var,
                value=result.position,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
            )
        if store_total_var:
            _store_variable(
                context,
                scope=scope,
                entity_id=resolved_store_entity_id,
                name=store_total_var,
                value=result.total,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
            )
        return ImmediateHandle()

    @registry.register("advance_text_session")
    def advance_text_session(
        context: CommandContext,
        *,
        entity_id: str,
        session_id: str,
        amount: int = 1,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Advance one prepared text session to its next chunk/window."""
        if context.text_session_manager is None:
            raise ValueError("Cannot advance text sessions without a text session manager.")

        resolved_entity_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_entity_id:
            logger.warning("advance_text_session: skipping because entity_id resolved to blank.")
            return ImmediateHandle()

        context.text_session_manager.advance_session(
            resolved_entity_id,
            str(session_id),
            amount=int(amount),
        )
        return ImmediateHandle()

    @registry.register("reset_text_session")
    def reset_text_session(
        context: CommandContext,
        *,
        entity_id: str,
        session_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Reset one prepared text session back to its first chunk/window."""
        if context.text_session_manager is None:
            raise ValueError("Cannot reset text sessions without a text session manager.")

        resolved_entity_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_entity_id:
            logger.warning("reset_text_session: skipping because entity_id resolved to blank.")
            return ImmediateHandle()

        context.text_session_manager.reset_session(
            resolved_entity_id,
            str(session_id),
        )
        return ImmediateHandle()

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

    @registry.register("run_commands")
    def run_commands(
        context: CommandContext,
        *,
        commands: list[dict[str, Any]] | dict[str, Any] | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Run an inline command list on the main lane."""
        if not commands:
            return ImmediateHandle()
        if isinstance(commands, dict):
            normalized_commands = [dict(commands)]
        elif isinstance(commands, list):
            normalized_commands = [dict(command) for command in commands]
        else:
            raise TypeError("run_commands requires a dict, list of dicts, or null.")
        return SequenceCommandHandle(
            registry,
            context,
            normalized_commands,
            base_params={
                **({"source_entity_id": source_entity_id} if source_entity_id is not None else {}),
                **({"actor_entity_id": actor_entity_id} if actor_entity_id is not None else {}),
            },
        )

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
                entity=entity,
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
        return _set_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="events_enabled",
            value=enabled,
            persistent=persistent,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )

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

    @registry.register("set_entity_field")
    def set_entity_field(
        context: CommandContext,
        *,
        entity_id: str,
        field_name: str,
        value: Any,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Change one supported runtime field on an entity."""
        return _set_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name=field_name,
            value=value,
            persistent=persistent,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )

    @registry.register("push_active_entity")
    def push_active_entity(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Remember the current active entity, then switch to a new one."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if not resolved_id:
            logger.warning("push_active_entity: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        context.world.push_active_entity(resolved_id)
        return ImmediateHandle()

    @registry.register("pop_active_entity")
    def pop_active_entity(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Restore the previously pushed active entity, falling back safely when needed."""
        context.world.pop_active_entity()
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

    @registry.register("change_area")
    def change_area(
        context: CommandContext,
        *,
        area_id: str = "",
        **_: Any,
    ) -> CommandHandle:
        """Queue a transition into another authored area once the command lane is idle."""
        if context.request_area_change is None:
            raise ValueError("Cannot change area without an active area-transition handler.")

        resolved_reference = str(area_id).strip()
        if not resolved_reference:
            raise ValueError("change_area requires a non-empty area_id.")

        context.request_area_change(resolved_reference)
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
        return _set_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="visible",
            value=visible,
            persistent=persistent,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )

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
        return _set_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="solid",
            value=solid,
            persistent=persistent,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )

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
        return _set_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="present",
            value=present,
            persistent=persistent,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )

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
        return _set_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="color",
            value=color,
            persistent=persistent,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )

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
        persistent: bool = False,
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

        new_entity = instantiate_entity(
            entity_data,
            context.area.tile_size,
            project=context.project,
            source_name=f"spawned entity '{new_entity_id}'",
        )
        context.world.add_entity(new_entity)
        if persistent and context.persistence_runtime is not None:
            context.persistence_runtime.record_spawned_entity(
                new_entity,
                tile_size=context.area.tile_size,
            )
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
                entity = context.world.get_entity(resolved_id)
                if entity is None:
                    raise KeyError(f"Cannot persist variable on missing entity '{resolved_id}'.")
                context.persistence_runtime.set_entity_variable(
                    resolved_id,
                    name,
                    persisted_value,
                    entity=entity,
                    tile_size=context.area.tile_size,
                )
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
                entity = context.world.get_entity(resolved_id)
                if entity is None:
                    raise KeyError(f"Cannot persist variable on missing entity '{resolved_id}'.")
                context.persistence_runtime.set_entity_variable(
                    resolved_id,
                    name,
                    variables[name],
                    entity=entity,
                    tile_size=context.area.tile_size,
                )
        return ImmediateHandle()

    @registry.register("set_var_length")
    def set_var_length(
        context: CommandContext,
        *,
        name: str,
        value: Any = None,
        scope: str = "entity",
        persistent: bool = False,
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Store the length of a collection-like value."""
        if value is None:
            length_value = 0
        else:
            try:
                length_value = len(value)
            except TypeError as exc:
                raise TypeError("set_var_length requires a sized value or null.") from exc

        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        variables[name] = length_value
        if persistent and context.persistence_runtime is not None:
            if scope == "world":
                context.persistence_runtime.set_world_variable(name, length_value)
            else:
                if entity_id is None:
                    raise ValueError("Persistent entity variable set requires entity_id.")
                resolved_id = _resolve_entity_id(
                    entity_id,
                    source_entity_id=source_entity_id,
                    actor_entity_id=actor_entity_id,
                )
                entity = context.world.get_entity(resolved_id)
                if entity is None:
                    raise KeyError(f"Cannot persist variable on missing entity '{resolved_id}'.")
                context.persistence_runtime.set_entity_variable(
                    resolved_id,
                    name,
                    length_value,
                    entity=entity,
                    tile_size=context.area.tile_size,
                )
        return ImmediateHandle()

    @registry.register("set_var_from_collection_item")
    def set_var_from_collection_item(
        context: CommandContext,
        *,
        name: str,
        value: Any = None,
        index: int | None = None,
        key: str | None = None,
        default: Any = None,
        scope: str = "entity",
        persistent: bool = False,
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Store one item from a list/tuple or dict into a variable."""
        extracted_value = copy.deepcopy(default)
        if key is not None:
            if value is None:
                extracted_value = copy.deepcopy(default)
            elif not isinstance(value, dict):
                raise TypeError("set_var_from_collection_item with key requires a dict value.")
            elif key in value:
                extracted_value = copy.deepcopy(value[key])
        else:
            if index is None:
                raise ValueError("set_var_from_collection_item requires either key or index.")
            if value is None:
                extracted_value = copy.deepcopy(default)
            elif not isinstance(value, (list, tuple)):
                raise TypeError("set_var_from_collection_item with index requires a list or tuple value.")
            else:
                resolved_index = int(index)
                if 0 <= resolved_index < len(value):
                    extracted_value = copy.deepcopy(value[resolved_index])

        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        variables[name] = extracted_value
        if persistent and context.persistence_runtime is not None:
            if scope == "world":
                context.persistence_runtime.set_world_variable(name, extracted_value)
            else:
                if entity_id is None:
                    raise ValueError("Persistent entity variable set requires entity_id.")
                resolved_id = _resolve_entity_id(
                    entity_id,
                    source_entity_id=source_entity_id,
                    actor_entity_id=actor_entity_id,
                )
                entity = context.world.get_entity(resolved_id)
                if entity is None:
                    raise KeyError(f"Cannot persist variable on missing entity '{resolved_id}'.")
                context.persistence_runtime.set_entity_variable(
                    resolved_id,
                    name,
                    extracted_value,
                    entity=entity,
                    tile_size=context.area.tile_size,
                )
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
