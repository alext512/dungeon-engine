"""Starter command implementations used by the first prototype slice."""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any

from dungeon_engine import config
from dungeon_engine.commands.library import (
    instantiate_named_command_commands,
    load_named_command_definition,
)
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import (
    AreaTransitionRequest,
    CameraFollowRequest,
    CommandContext,
    CommandHandle,
    ImmediateHandle,
    SequenceCommandHandle,
    WaitFramesHandle,
)
from dungeon_engine.world.entity import DIRECTION_VECTORS
from dungeon_engine.world.loader import instantiate_entity

logger = logging.getLogger(__name__)

_JSON_FILE_CACHE: dict[Path, Any] = {}


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

    def __init__(
        self,
        context: CommandContext,
        entity_ids: list[str],
        *,
        visual_id: str | None = None,
    ) -> None:
        super().__init__()
        self.context = context
        self.entity_ids = entity_ids
        self.visual_id = visual_id
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when every animated entity has finished."""
        self.complete = not any(
            self.context.animation_system.is_entity_animating(entity_id, visual_id=self.visual_id)
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


class WaitSecondsHandle(CommandHandle):
    """Complete after a fixed amount of real dt has elapsed."""

    def __init__(self, seconds: float) -> None:
        super().__init__()
        self.seconds_remaining = max(0.0, float(seconds))
        if self.seconds_remaining <= 0.0:
            self.complete = True

    def update(self, dt: float) -> None:
        """Advance the timer using real elapsed seconds."""
        if self.complete or dt <= 0:
            return
        self.seconds_remaining -= float(dt)
        if self.seconds_remaining <= 0.0:
            self.complete = True


class ForEachCommandHandle(CommandHandle):
    """Run one generic command list once for every item in a collection."""

    def __init__(
        self,
        registry: CommandRegistry,
        context: CommandContext,
        *,
        items: list[Any],
        commands: list[dict[str, Any]],
        item_param: str,
        index_param: str,
        base_params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.registry = registry
        self.context = context
        self.items = [copy.deepcopy(item) for item in items]
        self.commands = [dict(command) for command in commands]
        self.item_param = str(item_param)
        self.index_param = str(index_param)
        self.base_params = dict(base_params or {})
        self.current_index = 0
        self.current_handle: CommandHandle | None = None
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Advance the active iteration and start the next one when needed."""
        if self.complete:
            return

        if self.current_handle is not None:
            self.current_handle.update(dt)
            self.captures_menu_input = self.current_handle.captures_menu_input
            self.allow_entity_input = self.current_handle.allow_entity_input
            if not self.current_handle.complete:
                return
            self.current_handle = None
            self.captures_menu_input = False
            self.allow_entity_input = False

        while self.current_handle is None and self.current_index < len(self.items):
            item_index = self.current_index
            base_params = dict(self.base_params)
            base_params[self.item_param] = copy.deepcopy(self.items[item_index])
            base_params[self.index_param] = item_index
            self.current_index += 1
            self.current_handle = SequenceCommandHandle(
                self.registry,
                self.context,
                self.commands,
                base_params=base_params,
            )
            if self.current_handle.complete:
                self.current_handle = None
                continue
            self.captures_menu_input = self.current_handle.captures_menu_input
            self.allow_entity_input = self.current_handle.allow_entity_input
            return

        if self.current_handle is None and self.current_index >= len(self.items):
            self.complete = True


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
        self.captures_menu_input = self.sequence_handle.captures_menu_input
        self.allow_entity_input = self.sequence_handle.allow_entity_input
        if self.sequence_handle.complete:
            self._pop_stack()
            self.complete = True
            self.captures_menu_input = False
            self.allow_entity_input = False

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
    caller_entity_id: str | None = None,
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
    if entity_id == "caller":
        if caller_entity_id is None:
            raise ValueError("Command used 'caller' without a caller entity context.")
        return caller_entity_id
    return entity_id


def _get_action_press_count(context: CommandContext) -> int:
    """Return the current action-button press counter, if available."""
    input_handler = context.input_handler
    return input_handler.get_action_press_count() if input_handler is not None else 0


def _get_menu_press_count(context: CommandContext) -> int:
    """Return the current menu-button press counter, if available."""
    input_handler = context.input_handler
    return input_handler.get_menu_press_count() if input_handler is not None else 0


def _get_direction_press_count(context: CommandContext, direction: str) -> int:
    """Return the keydown press counter for one logical direction."""
    input_handler = context.input_handler
    return input_handler.get_direction_press_count(direction) if input_handler is not None else 0


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


def _normalize_command_specs(
    commands: list[dict[str, Any]] | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return one normalized inline command list."""
    if commands is None:
        return []
    if isinstance(commands, dict):
        return [dict(commands)]
    if isinstance(commands, list):
        return [dict(command) for command in commands]
    raise TypeError("Command hooks must be a dict, list of dicts, or null.")


def _resolve_variables(
    context: CommandContext,
    *,
    scope: str,
    entity_id: str | None = None,
    source_entity_id: str | None = None,
    actor_entity_id: str | None = None,
    caller_entity_id: str | None = None,
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
            caller_entity_id=caller_entity_id,
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
    caller_entity_id: str | None = None,
) -> None:
    """Store one resolved value into entity/world variables."""
    variables = _resolve_variables(
        context,
        scope=scope,
        entity_id=entity_id,
        source_entity_id=source_entity_id,
        actor_entity_id=actor_entity_id,
        caller_entity_id=caller_entity_id,
    )
    variables[str(name)] = copy.deepcopy(value)


def _persist_variable_value(
    context: CommandContext,
    *,
    scope: str,
    name: str,
    value: Any,
    entity_id: str | None = None,
    source_entity_id: str | None = None,
    actor_entity_id: str | None = None,
    caller_entity_id: str | None = None,
) -> None:
    """Mirror one variable write into persistence when requested."""
    if context.persistence_runtime is None:
        return
    if scope == "world":
        context.persistence_runtime.set_world_variable(name, copy.deepcopy(value))
        return
    if entity_id is None:
        raise ValueError("Persistent entity variable set requires entity_id.")
    resolved_id = _resolve_entity_id(
        entity_id,
        source_entity_id=source_entity_id,
        actor_entity_id=actor_entity_id,
        caller_entity_id=caller_entity_id,
    )
    entity = context.world.get_entity(resolved_id)
    if entity is None:
        raise KeyError(f"Cannot persist variable on missing entity '{resolved_id}'.")
    context.persistence_runtime.set_entity_variable(
        resolved_id,
        name,
        copy.deepcopy(value),
        entity=entity,
        tile_size=context.area.tile_size,
    )


def _require_exact_entity(context: CommandContext, entity_id: str) -> Any:
    """Return one explicitly addressed entity or raise a clear error."""
    resolved_id = str(entity_id).strip()
    if not resolved_id:
        raise ValueError("Entity-targeted primitive commands require a non-blank entity_id.")
    if resolved_id in {"self", "actor", "caller"}:
        raise ValueError(
            "Entity-targeted primitive commands require an explicit entity_id; "
            "use '$self_id', '$actor_id', or '$caller_id' in a higher-level command first."
        )
    entity = context.world.get_entity(resolved_id)
    if entity is None:
        raise KeyError(f"Entity '{resolved_id}' not found.")
    return entity


def _require_exact_entity_variables(context: CommandContext, entity_id: str) -> dict[str, Any]:
    """Return the variables dict for one explicitly addressed entity."""
    return _require_exact_entity(context, entity_id).variables


def _persist_world_variable_value(
    context: CommandContext,
    *,
    name: str,
    value: Any,
) -> None:
    """Mirror one explicit world-variable write into persistence when available."""
    if context.persistence_runtime is None:
        return
    context.persistence_runtime.set_world_variable(name, copy.deepcopy(value))


def _persist_exact_entity_variable_value(
    context: CommandContext,
    *,
    entity_id: str,
    name: str,
    value: Any,
) -> None:
    """Mirror one explicit entity-variable write into persistence when available."""
    if context.persistence_runtime is None:
        return
    entity = _require_exact_entity(context, entity_id)
    context.persistence_runtime.set_entity_variable(
        str(entity_id).strip(),
        name,
        copy.deepcopy(value),
        entity=entity,
        tile_size=context.area.tile_size,
    )


def _branch_with_runtime_context(
    registry: CommandRegistry,
    context: CommandContext,
    *,
    condition_met: bool,
    then: list[dict[str, Any]] | None = None,
    else_branch: list[dict[str, Any]] | None = None,
    runtime_params: dict[str, Any] | None = None,
    excluded_param_names: set[str] | None = None,
) -> CommandHandle:
    """Run one command branch while preserving inherited runtime params when present."""
    branch = then if condition_met else else_branch
    if not branch:
        return ImmediateHandle()

    inherited_params = {
        key: value
        for key, value in dict(runtime_params or {}).items()
        if key not in (excluded_param_names or set())
    }
    return SequenceCommandHandle(registry, context, branch, base_params=inherited_params)


def _extract_collection_item(
    value: Any = None,
    *,
    index: int | None = None,
    key: str | None = None,
    default: Any = None,
) -> Any:
    """Return one list/tuple or dict item with a consistent defaulting contract."""
    extracted_value = copy.deepcopy(default)
    if key is not None:
        if value is None:
            return extracted_value
        if not isinstance(value, dict):
            raise TypeError("Collection item lookup with key requires a dict value.")
        if key in value:
            return copy.deepcopy(value[key])
        return extracted_value

    if index is None:
        raise ValueError("Collection item lookup requires either key or index.")
    if value is None:
        return extracted_value
    if not isinstance(value, (list, tuple)):
        raise TypeError("Collection item lookup with index requires a list or tuple value.")
    resolved_index = int(index)
    if 0 <= resolved_index < len(value):
        return copy.deepcopy(value[resolved_index])
    return extracted_value


def _resolve_json_file_path(context: CommandContext, path: str) -> Path:
    """Resolve one JSON file path relative to the active project when needed."""
    resolved_path = Path(str(path).strip())
    if not resolved_path.is_absolute():
        if context.project is not None:
            resolved_path = context.project.project_root / resolved_path
        else:
            resolved_path = Path.cwd() / resolved_path
    return resolved_path.resolve()


def _load_json_file(path: Path) -> Any:
    """Load one JSON file through a small in-memory cache."""
    cached = _JSON_FILE_CACHE.get(path)
    if cached is None:
        cached = json.loads(path.read_text(encoding="utf-8"))
        _JSON_FILE_CACHE[path] = cached
    return copy.deepcopy(cached)


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


def _serialize_entity_visuals(entity: Any) -> list[dict[str, Any]]:
    """Serialize runtime visuals for persistent field mutations."""
    serialized: list[dict[str, Any]] = []
    for visual in entity.visuals:
        serialized.append(
            {
                "id": visual.visual_id,
                "path": visual.path,
                "frame_width": visual.frame_width,
                "frame_height": visual.frame_height,
                "frames": list(visual.frames),
                "animation_fps": visual.animation_fps,
                "animate_when_moving": visual.animate_when_moving,
                "current_frame": visual.current_frame,
                "flip_x": visual.flip_x,
                "visible": visual.visible,
                "tint": list(visual.tint),
                "offset_x": visual.offset_x,
                "offset_y": visual.offset_y,
                "draw_order": visual.draw_order,
            }
        )
    return serialized


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

    if root == "visuals":
        if len(path) < 3:
            raise ValueError("visuals field mutations must use visuals.<visual_id>.<field>.")
        visual = entity.require_visual(str(path[1]))
        visual_field = str(path[2])
        if visual_field == "flip_x":
            visual.flip_x = bool(value)
        elif visual_field == "visible":
            visual.visible = bool(value)
        elif visual_field == "current_frame":
            visual.current_frame = int(value)
        elif visual_field == "tint":
            if not isinstance(value, (list, tuple)) or len(value) < 3:
                raise ValueError("visual tint must be a list or tuple with at least 3 channels.")
            visual.tint = (int(value[0]), int(value[1]), int(value[2]))
        else:
            raise ValueError(f"Unsupported visuals field '{visual_field}'.")
        return "visuals", _serialize_entity_visuals(entity)

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
        "Use set_world_var/set_entity_var for variables and dedicated commands for events/template rebuilds."
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

    def _set_exact_entity_field_handle(
        context: CommandContext,
        *,
        entity_id: str,
        field_name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Apply one generic entity field mutation through the shared helper."""
        entity = _require_exact_entity(context, entity_id)
        persisted_field_name, persisted_value = _apply_entity_field_value(
            entity,
            str(field_name),
            value,
        )
        if persistent:
            _persist_entity_field(
                context,
                entity_id=entity.entity_id,
                field_name=persisted_field_name,
                value=persisted_value,
                entity=entity,
            )
        return ImmediateHandle()

    def _step_entity(
        context: CommandContext,
        *,
        entity_id: str,
        direction: str,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str = "immediate",
        allow_push: bool = True,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        resolved_id = _require_exact_entity(context, entity_id).entity_id
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
        resolved_id = _require_exact_entity(context, entity_id).entity_id
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
        resolved_id = _require_exact_entity(context, entity_id).entity_id
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
        x: int | float,
        y: int | float,
        space: str = "pixel",
        mode: str = "absolute",
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
        **_: Any,
    ) -> CommandHandle:
        entity = _require_exact_entity(context, entity_id)
        resolved_id = entity.entity_id
        if space not in {"pixel", "grid"}:
            raise ValueError(f"Unknown teleport space '{space}'.")
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown teleport mode '{mode}'.")

        if space == "grid":
            grid_x = int(x) if mode == "absolute" else entity.grid_x + int(x)
            grid_y = int(y) if mode == "absolute" else entity.grid_y + int(y)
            context.movement_system.teleport_to_grid_position(resolved_id, grid_x, grid_y)
            return ImmediateHandle()

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

    def _play_exact_animation(
        context: CommandContext,
        *,
        entity_id: str,
        visual_id: str | None = None,
        frame_sequence: list[int],
        frames_per_sprite_change: int = 1,
        hold_last_frame: bool = True,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        resolved_id = _require_exact_entity(context, entity_id).entity_id
        context.animation_system.start_frame_animation(
            resolved_id,
            frame_sequence,
            visual_id=visual_id,
            frames_per_sprite_change=frames_per_sprite_change,
            hold_last_frame=hold_last_frame,
        )
        if not wait:
            return ImmediateHandle()
        return AnimationCommandHandle(context, [resolved_id], visual_id=visual_id)

    @registry.register("set_facing")
    def set_facing(
        context: CommandContext,
        *,
        entity_id: str,
        direction: str,
    ) -> CommandHandle:
        """Set an entity's facing direction without moving it."""
        return _set_exact_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="facing",
            value=direction,
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
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Store whether the tile in front is free, movable, or blocked."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
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
            caller_entity_id=caller_entity_id,
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
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Run a named event on the entity directly in front of an actor."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
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
                **({"caller_entity_id": caller_entity_id} if caller_entity_id is not None else {}),
            },
        )

    @registry.register("move_entity_one_tile")
    def move_entity_one_tile(
        context: CommandContext,
        *,
        entity_id: str,
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
        visual_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Block the command lane until the requested entity stops moving."""
        resolved_id = _require_exact_entity(context, entity_id).entity_id
        if not context.movement_system.is_entity_moving(resolved_id):
            return ImmediateHandle()
        return MovementCommandHandle(context, [resolved_id])

    @registry.register("play_animation")
    def play_animation(
        context: CommandContext,
        *,
        entity_id: str,
        visual_id: str | None = None,
        frame_sequence: list[int],
        frames_per_sprite_change: int = 1,
        hold_last_frame: bool = True,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Play a one-shot sprite frame sequence on an entity."""
        return _play_exact_animation(
            context,
            entity_id=entity_id,
            visual_id=visual_id,
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
        visual_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Block the command lane until the requested entity stops animating."""
        resolved_id = _require_exact_entity(context, entity_id).entity_id
        if not context.animation_system.is_entity_animating(resolved_id, visual_id=visual_id):
            return ImmediateHandle()
        return AnimationCommandHandle(context, [resolved_id], visual_id=visual_id)

    @registry.register("stop_animation")
    def stop_animation(
        context: CommandContext,
        *,
        entity_id: str,
        visual_id: str | None = None,
        reset_to_default: bool = False,
        **_: Any,
    ) -> CommandHandle:
        """Stop command-driven animation playback on an entity."""
        resolved_id = _require_exact_entity(context, entity_id).entity_id
        context.animation_system.stop_animation(
            resolved_id,
            visual_id=visual_id,
            reset_to_default=reset_to_default,
        )
        return ImmediateHandle()

    @registry.register("set_visual_frame")
    def set_visual_frame(
        context: CommandContext,
        *,
        entity_id: str,
        visual_id: str | None = None,
        frame: int,
        **_: Any,
    ) -> CommandHandle:
        """Set the currently displayed visual frame directly."""
        entity = _require_exact_entity(context, entity_id)
        visual = entity.require_visual(visual_id) if visual_id is not None else entity.get_primary_visual()
        if visual is None:
            raise KeyError(f"Entity '{entity.entity_id}' has no visual to set a frame on.")
        visual.current_frame = int(frame)
        return ImmediateHandle()

    @registry.register("set_visual_flip_x")
    def set_visual_flip_x(
        context: CommandContext,
        *,
        entity_id: str,
        visual_id: str | None = None,
        flip_x: bool,
        **_: Any,
    ) -> CommandHandle:
        """Set whether an entity's visual should be mirrored horizontally."""
        entity = _require_exact_entity(context, entity_id)
        visual = entity.require_visual(visual_id) if visual_id is not None else entity.get_primary_visual()
        if visual is None:
            raise KeyError(f"Entity '{entity.entity_id}' has no visual to set flip_x on.")
        visual.flip_x = bool(flip_x)
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

    @registry.register("set_var_from_json_file")
    def set_var_from_json_file(
        context: CommandContext,
        *,
        name: str,
        path: str,
        scope: str = "entity",
        persistent: bool = False,
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Load one JSON file into an entity/world variable."""
        resolved_path = _resolve_json_file_path(context, str(path))
        value = _load_json_file(resolved_path)
        _store_variable(
            context,
            scope=scope,
            entity_id=entity_id,
            name=name,
            value=value,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if persistent:
            _persist_variable_value(
                context,
                scope=scope,
                entity_id=entity_id,
                name=name,
                value=value,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )
        return ImmediateHandle()

    @registry.register("set_var_from_wrapped_lines")
    def set_var_from_wrapped_lines(
        context: CommandContext,
        *,
        name: str,
        text: str | None = None,
        max_width: int,
        font_id: str = config.DEFAULT_UI_FONT_ID,
        scope: str = "entity",
        persistent: bool = False,
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Wrap text into individual lines and store the resulting list."""
        if context.text_renderer is None:
            raise ValueError("Cannot wrap text without an active text renderer.")
        wrapped_lines = context.text_renderer.wrap_lines(
            "" if text is None else str(text),
            int(max_width),
            font_id=str(font_id),
        )
        _store_variable(
            context,
            scope=scope,
            entity_id=entity_id,
            name=name,
            value=wrapped_lines,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if persistent:
            _persist_variable_value(
                context,
                scope=scope,
                entity_id=entity_id,
                name=name,
                value=wrapped_lines,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )
        return ImmediateHandle()

    @registry.register("set_var_from_text_window")
    def set_var_from_text_window(
        context: CommandContext,
        *,
        name: str,
        lines: Any = None,
        start: int = 0,
        max_lines: int = 1,
        separator: str = "\n",
        store_has_more_var: str | None = None,
        store_total_var: str | None = None,
        scope: str = "entity",
        persistent: bool = False,
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Store one visible text window and optional metadata from a wrapped line list."""
        if lines is None:
            normalized_lines: list[str] = []
        elif isinstance(lines, str):
            normalized_lines = [str(lines)]
        elif isinstance(lines, (list, tuple)):
            normalized_lines = [str(item) for item in lines]
        else:
            raise TypeError("set_var_from_text_window requires lines to be a list, tuple, string, or null.")

        resolved_start = max(0, int(start))
        resolved_max_lines = max(0, int(max_lines))
        visible_lines = normalized_lines[resolved_start : resolved_start + resolved_max_lines]
        visible_text = str(separator).join(visible_lines)
        has_more = resolved_start + resolved_max_lines < len(normalized_lines)

        _store_variable(
            context,
            scope=scope,
            entity_id=entity_id,
            name=name,
            value=visible_text,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if store_has_more_var:
            _store_variable(
                context,
                scope=scope,
                entity_id=entity_id,
                name=store_has_more_var,
                value=has_more,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )
        if store_total_var:
            _store_variable(
                context,
                scope=scope,
                entity_id=entity_id,
                name=store_total_var,
                value=len(normalized_lines),
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )

        if persistent:
            _persist_variable_value(
                context,
                scope=scope,
                entity_id=entity_id,
                name=name,
                value=visible_text,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )
            if store_has_more_var:
                _persist_variable_value(
                    context,
                    scope=scope,
                    entity_id=entity_id,
                    name=store_has_more_var,
                    value=has_more,
                    source_entity_id=source_entity_id,
                    actor_entity_id=actor_entity_id,
                    caller_entity_id=caller_entity_id,
                )
            if store_total_var:
                _persist_variable_value(
                    context,
                    scope=scope,
                    entity_id=entity_id,
                    name=store_total_var,
                    value=len(normalized_lines),
                    source_entity_id=source_entity_id,
                    actor_entity_id=actor_entity_id,
                    caller_entity_id=caller_entity_id,
                )
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

    @registry.register("wait_seconds")
    def wait_seconds(
        context: CommandContext,
        *,
        seconds: int | float,
        **_: Any,
    ) -> CommandHandle:
        """Pause the current command lane for a fixed amount of elapsed time."""
        return WaitSecondsHandle(float(seconds))

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
        *_: Any,
        **__: Any,
    ) -> CommandHandle:
        """Reject the removed engine-owned dialogue command path."""
        raise ValueError(
            "run_dialogue was removed. Load dialogue JSON into controller variables and let controller entity events drive the flow."
        )

    @registry.register("start_dialogue_session")
    def start_dialogue_session(
        *args: Any,
        **kwargs: Any,
    ) -> CommandHandle:
        """Reject the removed engine-owned dialogue-session command."""
        _ = args, kwargs
        raise ValueError(
            "start_dialogue_session was removed. Keep dialogue state on the controller entity and drive it with normal commands and input events."
        )

    @registry.register("dialogue_advance")
    def dialogue_advance(
        *args: Any,
        **kwargs: Any,
    ) -> CommandHandle:
        """Reject the removed engine-owned dialogue input helper."""
        _ = args, kwargs
        raise ValueError(
            "dialogue_advance was removed. The controller entity should advance its own dialogue variables through normal commands."
        )

    @registry.register("dialogue_move_selection")
    def dialogue_move_selection(
        *args: Any,
        **kwargs: Any,
    ) -> CommandHandle:
        """Reject the removed engine-owned dialogue input helper."""
        _ = args, kwargs
        raise ValueError(
            "dialogue_move_selection was removed. The controller entity should update its own selection state through normal commands."
        )

    @registry.register("dialogue_confirm_choice")
    def dialogue_confirm_choice(
        *args: Any,
        **kwargs: Any,
    ) -> CommandHandle:
        """Reject the removed engine-owned dialogue input helper."""
        _ = args, kwargs
        raise ValueError(
            "dialogue_confirm_choice was removed. The controller entity should confirm its own selected option through normal commands."
        )

    @registry.register("dialogue_cancel")
    def dialogue_cancel(
        *args: Any,
        **kwargs: Any,
    ) -> CommandHandle:
        """Reject the removed engine-owned dialogue input helper."""
        _ = args, kwargs
        raise ValueError(
            "dialogue_cancel was removed. The controller entity should decide how cancel input affects its own dialogue state."
        )

    @registry.register("prepare_text_session")
    def prepare_text_session(
        *args: Any,
        **kwargs: Any,
    ) -> CommandHandle:
        """Reject the removed stateful text-session helper."""
        _ = args, kwargs
        raise ValueError(
            "prepare_text_session was removed. Store wrapped lines and visible text directly in entity variables instead."
        )

    @registry.register("read_text_session")
    def read_text_session(
        *args: Any,
        **kwargs: Any,
    ) -> CommandHandle:
        """Reject the removed stateful text-session helper."""
        _ = args, kwargs
        raise ValueError(
            "read_text_session was removed. Read visible text from entity variables directly instead."
        )

    @registry.register("advance_text_session")
    def advance_text_session(
        *args: Any,
        **kwargs: Any,
    ) -> CommandHandle:
        """Reject the removed stateful text-session helper."""
        _ = args, kwargs
        raise ValueError(
            "advance_text_session was removed. Advance your entity-owned text state directly through normal commands."
        )

    @registry.register("reset_text_session")
    def reset_text_session(
        *args: Any,
        **kwargs: Any,
    ) -> CommandHandle:
        """Reject the removed stateful text-session helper."""
        _ = args, kwargs
        raise ValueError(
            "reset_text_session was removed. Reset your entity-owned text state directly through normal commands."
        )

    @registry.register("run_detached_commands")
    def run_detached_commands(
        context: CommandContext,
        *,
        commands: list[dict[str, Any]],
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
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
                **({"caller_entity_id": caller_entity_id} if caller_entity_id is not None else {}),
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
        caller_entity_id: str | None = None,
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
                **({"caller_entity_id": caller_entity_id} if caller_entity_id is not None else {}),
            },
        )

    @registry.register("run_commands_for_collection")
    def run_commands_for_collection(
        context: CommandContext,
        *,
        value: Any = None,
        commands: list[dict[str, Any]] | dict[str, Any] | None = None,
        item_param: str = "item",
        index_param: str = "index",
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Run the same inline command list once per item in a list/tuple value."""
        if value is None:
            items: list[Any] = []
        elif isinstance(value, (list, tuple)):
            items = list(value)
        else:
            raise TypeError("run_commands_for_collection requires a list, tuple, or null value.")
        normalized_commands = _normalize_command_specs(commands)
        if not items or not normalized_commands:
            return ImmediateHandle()
        return ForEachCommandHandle(
            registry,
            context,
            items=items,
            commands=normalized_commands,
            item_param=str(item_param),
            index_param=str(index_param),
            base_params={
                **({"source_entity_id": source_entity_id} if source_entity_id is not None else {}),
                **({"actor_entity_id": actor_entity_id} if actor_entity_id is not None else {}),
                **({"caller_entity_id": caller_entity_id} if caller_entity_id is not None else {}),
            },
        )

    @registry.register("interact_facing")
    def interact_facing(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Activate the first enabled interact target in front of an actor."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
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
                **({"caller_entity_id": caller_entity_id} if caller_entity_id is not None else {}),
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
        caller_entity_id: str | None = None,
        **event_parameters: Any,
    ) -> CommandHandle:
        """Execute a named event on a target entity when it is enabled."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
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
        if caller_entity_id is not None:
            base_params["caller_entity_id"] = caller_entity_id
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
        caller_entity_id: str | None = None,
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
        if caller_entity_id is not None:
            base_params["caller_entity_id"] = caller_entity_id

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
    ) -> CommandHandle:
        """Enable or disable a named event on an entity."""
        entity = _require_exact_entity(context, entity_id)
        entity.set_event_enabled(event_id, enabled)
        if persistent:
            _persist_entity_event_enabled(
                context,
                entity_id=entity.entity_id,
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
    ) -> CommandHandle:
        """Enable or disable all named events on an entity at once."""
        return _set_exact_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="events_enabled",
            value=enabled,
            persistent=persistent,
        )

    @registry.register("set_input_target")
    def set_input_target(
        context: CommandContext,
        *,
        action: str,
        entity_id: str | None = None,
    ) -> CommandHandle:
        """Route one logical input action to a specific entity or clear it."""
        resolved_entity_id = None if entity_id in (None, "") else _require_exact_entity(context, entity_id).entity_id
        context.world.set_input_target(str(action), resolved_entity_id)
        return ImmediateHandle()

    @registry.register("set_entity_field")
    def set_entity_field(
        context: CommandContext,
        *,
        entity_id: str,
        field_name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Change one supported runtime field on an entity."""
        return _set_exact_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name=field_name,
            value=value,
            persistent=persistent,
        )

    @registry.register("route_inputs_to_entity")
    def route_inputs_to_entity(
        context: CommandContext,
        *,
        entity_id: str | None = None,
        actions: list[str] | None = None,
    ) -> CommandHandle:
        """Route selected logical inputs, or all inputs, to one entity."""
        if entity_id in (None, ""):
            context.world.route_inputs_to_entity(None, actions=actions)
            return ImmediateHandle()
        context.world.route_inputs_to_entity(
            _require_exact_entity(context, entity_id).entity_id,
            actions=actions,
        )
        return ImmediateHandle()

    @registry.register("push_input_routes")
    def push_input_routes(
        context: CommandContext,
        *,
        actions: list[str] | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Remember the current routed targets for one set of logical inputs."""
        context.world.push_input_routes(actions=actions)
        return ImmediateHandle()

    @registry.register("pop_input_routes")
    def pop_input_routes(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Restore the last remembered routed targets for one set of logical inputs."""
        context.world.pop_input_routes()
        return ImmediateHandle()

    @registry.register("close_dialogue")
    def close_dialogue(
        *args: Any,
        **kwargs: Any,
    ) -> CommandHandle:
        """Reject the removed engine-owned dialogue close helper."""
        _ = args, kwargs
        raise ValueError(
            "close_dialogue was removed. The controller entity should clear and restore its own dialogue state through normal commands."
        )

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
        entry_id: str | None = None,
        transfer_entity_id: str | None = None,
        transfer_entity_ids: list[str] | None = None,
        camera_follow_entity_id: str | None = None,
        camera_follow_input_action: str | None = None,
        camera_offset_x: int | float = 0,
        camera_offset_y: int | float = 0,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Queue a transition into another authored area once the command lane is idle."""
        if context.request_area_change is None:
            raise ValueError("Cannot change area without an active area-transition handler.")

        resolved_reference = str(area_id).strip()
        if not resolved_reference:
            raise ValueError("change_area requires a non-empty area_id.")

        if camera_follow_entity_id not in (None, "") and camera_follow_input_action not in (None, ""):
            raise ValueError(
                "change_area camera follow must target either one entity or one input action, not both."
            )

        resolved_transfer_ids: list[str] = []
        raw_transfer_ids = []
        if transfer_entity_id not in (None, ""):
            raw_transfer_ids.append(transfer_entity_id)
        raw_transfer_ids.extend(list(transfer_entity_ids or []))
        for raw_entity_id in raw_transfer_ids:
            resolved_entity_id = _resolve_entity_id(
                raw_entity_id,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
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
        if camera_follow_entity_id not in (None, ""):
            resolved_camera_entity_id = _resolve_entity_id(
                camera_follow_entity_id,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )
            if resolved_camera_entity_id:
                camera_follow_request = CameraFollowRequest(
                    mode="entity",
                    entity_id=resolved_camera_entity_id,
                    offset_x=float(camera_offset_x),
                    offset_y=float(camera_offset_y),
                )
        elif camera_follow_input_action not in (None, ""):
            camera_follow_request = CameraFollowRequest(
                mode="input_target",
                input_action=str(camera_follow_input_action).strip(),
                offset_x=float(camera_offset_x),
                offset_y=float(camera_offset_y),
            )

        context.request_area_change(
            AreaTransitionRequest(
                area_id=resolved_reference,
                entry_id=str(entry_id).strip() or None,
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
        camera_follow_entity_id: str | None = None,
        camera_follow_input_action: str | None = None,
        camera_offset_x: int | float = 0,
        camera_offset_y: int | float = 0,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Queue a fresh game session and transition into the requested area."""
        if context.request_new_game is None:
            raise ValueError("Cannot start a new game without an active session-reset handler.")

        resolved_reference = str(area_id).strip()
        if not resolved_reference:
            raise ValueError("new_game requires a non-empty area_id.")

        if camera_follow_entity_id not in (None, "") and camera_follow_input_action not in (None, ""):
            raise ValueError(
                "new_game camera follow must target either one entity or one input action, not both."
            )

        camera_follow_request: CameraFollowRequest | None = None
        if camera_follow_entity_id not in (None, ""):
            resolved_camera_entity_id = _resolve_entity_id(
                camera_follow_entity_id,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )
            if resolved_camera_entity_id:
                camera_follow_request = CameraFollowRequest(
                    mode="entity",
                    entity_id=resolved_camera_entity_id,
                    offset_x=float(camera_offset_x),
                    offset_y=float(camera_offset_y),
                )
        elif camera_follow_input_action not in (None, ""):
            camera_follow_request = CameraFollowRequest(
                mode="input_target",
                input_action=str(camera_follow_input_action).strip(),
                offset_x=float(camera_offset_x),
                offset_y=float(camera_offset_y),
            )

        context.request_new_game(
            AreaTransitionRequest(
                area_id=resolved_reference,
                entry_id=str(entry_id).strip() or None,
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

    @registry.register("set_camera_follow_entity")
    def set_camera_follow_entity(
        context: CommandContext,
        *,
        entity_id: str,
        offset_x: int | float = 0,
        offset_y: int | float = 0,
    ) -> CommandHandle:
        """Make the camera follow a specific entity."""
        if context.camera is None:
            raise ValueError("Cannot change camera follow without an active camera.")
        resolved_id = _require_exact_entity(context, entity_id).entity_id
        context.camera.follow_entity(
            resolved_id,
            offset_x=float(offset_x),
            offset_y=float(offset_y),
        )
        context.camera.update(context.world, advance_tick=False)
        return ImmediateHandle()

    @registry.register("set_camera_follow_player")
    def set_camera_follow_player(
        context: CommandContext,
        *,
        offset_x: int | float = 0,
        offset_y: int | float = 0,
        **_: Any,
    ) -> CommandHandle:
        """Fail fast for the removed player-specific camera follow command."""
        raise ValueError(
            "set_camera_follow_player is removed; use 'set_camera_follow_entity' "
            "or 'set_camera_follow_input_target' instead."
        )

    @registry.register("set_camera_follow_input_target")
    def set_camera_follow_input_target(
        context: CommandContext,
        *,
        action: str,
        offset_x: int | float = 0,
        offset_y: int | float = 0,
        **_: Any,
    ) -> CommandHandle:
        """Make the camera follow whichever entity currently receives one logical input."""
        if context.camera is None:
            raise ValueError("Cannot change camera follow without an active camera.")
        context.camera.follow_input_target(
            str(action),
            offset_x=float(offset_x),
            offset_y=float(offset_y),
        )
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

    @registry.register("set_camera_bounds_rect")
    def set_camera_bounds_rect(
        context: CommandContext,
        *,
        x: int | float,
        y: int | float,
        width: int | float,
        height: int | float,
        space: str = "pixel",
        **_: Any,
    ) -> CommandHandle:
        """Clamp camera movement/follow to one rectangle in world or grid space."""
        if context.camera is None:
            raise ValueError("Cannot set camera bounds without an active camera.")
        if space not in {"pixel", "grid"}:
            raise ValueError(f"Unknown camera bounds space '{space}'.")
        scale = context.area.tile_size if space == "grid" else 1
        context.camera.set_bounds_rect(
            float(x) * scale,
            float(y) * scale,
            float(width) * scale,
            float(height) * scale,
        )
        context.camera.update(context.world, advance_tick=False)
        return ImmediateHandle()

    @registry.register("clear_camera_bounds")
    def clear_camera_bounds(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Remove any active camera bounds rectangle."""
        if context.camera is None:
            raise ValueError("Cannot clear camera bounds without an active camera.")
        context.camera.clear_bounds()
        context.camera.update(context.world, advance_tick=False)
        return ImmediateHandle()

    @registry.register("set_camera_deadzone")
    def set_camera_deadzone(
        context: CommandContext,
        *,
        x: int | float,
        y: int | float,
        width: int | float,
        height: int | float,
        space: str = "pixel",
        **_: Any,
    ) -> CommandHandle:
        """Keep followed targets inside one deadzone rectangle in viewport space."""
        if context.camera is None:
            raise ValueError("Cannot set a camera deadzone without an active camera.")
        if space not in {"pixel", "grid"}:
            raise ValueError(f"Unknown camera deadzone space '{space}'.")
        scale = context.area.tile_size if space == "grid" else 1
        context.camera.set_deadzone_rect(
            float(x) * scale,
            float(y) * scale,
            float(width) * scale,
            float(height) * scale,
        )
        context.camera.update(context.world, advance_tick=False)
        return ImmediateHandle()

    @registry.register("clear_camera_deadzone")
    def clear_camera_deadzone(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Remove any active camera deadzone rectangle."""
        if context.camera is None:
            raise ValueError("Cannot clear a camera deadzone without an active camera.")
        context.camera.clear_deadzone()
        context.camera.update(context.world, advance_tick=False)
        return ImmediateHandle()

    @registry.register("set_var_from_camera")
    def set_var_from_camera(
        *args: Any,
        **kwargs: Any,
    ) -> CommandHandle:
        """Reject the removed broad camera-to-variable helper."""
        _ = args, kwargs
        raise ValueError(
            "set_var_from_camera was removed; read camera values through "
            "runtime tokens like '$camera.x' and store them with explicit "
            "variable commands."
        )

    @registry.register("set_world_var_from_camera")
    def set_world_var_from_camera(
        *args: Any,
        **kwargs: Any,
    ) -> CommandHandle:
        """Reject the transitional explicit camera-to-world-variable helper."""
        _ = args, kwargs
        raise ValueError(
            "set_world_var_from_camera was removed; use 'set_world_var' with "
            "a runtime token like '$camera.x' instead."
        )

    @registry.register("set_entity_var_from_camera")
    def set_entity_var_from_camera(
        *args: Any,
        **kwargs: Any,
    ) -> CommandHandle:
        """Reject the transitional explicit camera-to-entity-variable helper."""
        _ = args, kwargs
        raise ValueError(
            "set_entity_var_from_camera was removed; use 'set_entity_var' with "
            "a runtime token like '$camera.follow_entity_id' instead."
        )

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
    ) -> CommandHandle:
        """Change whether an entity is rendered and targetable."""
        return _set_exact_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="visible",
            value=visible,
            persistent=persistent,
        )

    @registry.register("set_solid")
    def set_solid(
        context: CommandContext,
        *,
        entity_id: str,
        solid: bool,
        persistent: bool = False,
    ) -> CommandHandle:
        """Change whether an entity blocks movement."""
        return _set_exact_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="solid",
            value=solid,
            persistent=persistent,
        )

    @registry.register("set_present")
    def set_present(
        context: CommandContext,
        *,
        entity_id: str,
        present: bool,
        persistent: bool = False,
    ) -> CommandHandle:
        """Change whether an entity participates in the current scene."""
        return _set_exact_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="present",
            value=present,
            persistent=persistent,
        )

    @registry.register("set_color")
    def set_color(
        context: CommandContext,
        *,
        entity_id: str,
        color: list[int],
        persistent: bool = False,
    ) -> CommandHandle:
        """Change an entity's debug-render color."""
        return _set_exact_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="color",
            value=color,
            persistent=persistent,
        )

    @registry.register("destroy_entity")
    def destroy_entity(
        context: CommandContext,
        *,
        entity_id: str,
        persistent: bool = False,
    ) -> CommandHandle:
        """Destroy an entity instance completely."""
        entity = _require_exact_entity(context, entity_id)
        context.world.remove_entity(entity.entity_id)
        if persistent and context.persistence_runtime is not None:
            context.persistence_runtime.remove_entity(entity.entity_id, entity=entity)
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

    @registry.register("set_world_var")
    def set_world_var(
        context: CommandContext,
        *,
        name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Set one explicit world variable to a value."""
        persisted_value = copy.deepcopy(value)
        context.world.variables[name] = persisted_value
        if persistent:
            _persist_world_variable_value(context, name=name, value=persisted_value)
        return ImmediateHandle()

    @registry.register("set_entity_var")
    def set_entity_var(
        context: CommandContext,
        *,
        entity_id: str,
        name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Set one explicit entity variable to a value."""
        persisted_value = copy.deepcopy(value)
        variables = _require_exact_entity_variables(context, entity_id)
        variables[name] = persisted_value
        if persistent:
            _persist_exact_entity_variable_value(
                context,
                entity_id=entity_id,
                name=name,
                value=persisted_value,
            )
        return ImmediateHandle()

    @registry.register("increment_world_var")
    def increment_world_var(
        context: CommandContext,
        *,
        name: str,
        amount: int | float = 1,
        persistent: bool = False,
    ) -> CommandHandle:
        """Add an amount to one explicit world variable."""
        current_value = context.world.variables.get(name, 0) + amount
        context.world.variables[name] = current_value
        if persistent:
            _persist_world_variable_value(context, name=name, value=current_value)
        return ImmediateHandle()

    @registry.register("increment_entity_var")
    def increment_entity_var(
        context: CommandContext,
        *,
        entity_id: str,
        name: str,
        amount: int | float = 1,
        persistent: bool = False,
    ) -> CommandHandle:
        """Add an amount to one explicit entity variable."""
        variables = _require_exact_entity_variables(context, entity_id)
        current_value = variables.get(name, 0) + amount
        variables[name] = current_value
        if persistent:
            _persist_exact_entity_variable_value(
                context,
                entity_id=entity_id,
                name=name,
                value=current_value,
            )
        return ImmediateHandle()

    @registry.register("set_world_var_length")
    def set_world_var_length(
        context: CommandContext,
        *,
        name: str,
        value: Any = None,
        persistent: bool = False,
    ) -> CommandHandle:
        """Store the length of a value into one explicit world variable."""
        if value is None:
            length_value = 0
        else:
            try:
                length_value = len(value)
            except TypeError as exc:
                raise TypeError("set_world_var_length requires a sized value or null.") from exc
        context.world.variables[name] = length_value
        if persistent:
            _persist_world_variable_value(context, name=name, value=length_value)
        return ImmediateHandle()

    @registry.register("set_entity_var_length")
    def set_entity_var_length(
        context: CommandContext,
        *,
        entity_id: str,
        name: str,
        value: Any = None,
        persistent: bool = False,
    ) -> CommandHandle:
        """Store the length of a value into one explicit entity variable."""
        if value is None:
            length_value = 0
        else:
            try:
                length_value = len(value)
            except TypeError as exc:
                raise TypeError("set_entity_var_length requires a sized value or null.") from exc
        variables = _require_exact_entity_variables(context, entity_id)
        variables[name] = length_value
        if persistent:
            _persist_exact_entity_variable_value(
                context,
                entity_id=entity_id,
                name=name,
                value=length_value,
            )
        return ImmediateHandle()

    @registry.register("append_world_var")
    def append_world_var(
        context: CommandContext,
        *,
        name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Append one item to one explicit world list variable."""
        current_value = context.world.variables.get(name)
        if current_value is None:
            current_items: list[Any] = []
        elif isinstance(current_value, list):
            current_items = [copy.deepcopy(item) for item in current_value]
        else:
            raise TypeError("append_world_var requires the target variable to be a list or null.")
        current_items.append(copy.deepcopy(value))
        context.world.variables[name] = current_items
        if persistent:
            _persist_world_variable_value(context, name=name, value=current_items)
        return ImmediateHandle()

    @registry.register("append_entity_var")
    def append_entity_var(
        context: CommandContext,
        *,
        entity_id: str,
        name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Append one item to one explicit entity list variable."""
        variables = _require_exact_entity_variables(context, entity_id)
        current_value = variables.get(name)
        if current_value is None:
            current_items: list[Any] = []
        elif isinstance(current_value, list):
            current_items = [copy.deepcopy(item) for item in current_value]
        else:
            raise TypeError("append_entity_var requires the target variable to be a list or null.")
        current_items.append(copy.deepcopy(value))
        variables[name] = current_items
        if persistent:
            _persist_exact_entity_variable_value(
                context,
                entity_id=entity_id,
                name=name,
                value=current_items,
            )
        return ImmediateHandle()

    @registry.register("pop_world_var")
    def pop_world_var(
        context: CommandContext,
        *,
        name: str,
        store_var: str | None = None,
        default: Any = None,
        persistent: bool = False,
    ) -> CommandHandle:
        """Pop the last item from one explicit world list variable."""
        current_value = context.world.variables.get(name)
        if current_value is None:
            current_items: list[Any] = []
        elif isinstance(current_value, list):
            current_items = [copy.deepcopy(item) for item in current_value]
        else:
            raise TypeError("pop_world_var requires the target variable to be a list or null.")

        popped_value = copy.deepcopy(default)
        if current_items:
            popped_value = current_items.pop()
        context.world.variables[name] = current_items
        if store_var:
            context.world.variables[store_var] = copy.deepcopy(popped_value)

        if persistent:
            _persist_world_variable_value(context, name=name, value=current_items)
            if store_var:
                _persist_world_variable_value(context, name=store_var, value=popped_value)
        return ImmediateHandle()

    @registry.register("pop_entity_var")
    def pop_entity_var(
        context: CommandContext,
        *,
        entity_id: str,
        name: str,
        store_var: str | None = None,
        default: Any = None,
        persistent: bool = False,
    ) -> CommandHandle:
        """Pop the last item from one explicit entity list variable."""
        variables = _require_exact_entity_variables(context, entity_id)
        current_value = variables.get(name)
        if current_value is None:
            current_items: list[Any] = []
        elif isinstance(current_value, list):
            current_items = [copy.deepcopy(item) for item in current_value]
        else:
            raise TypeError("pop_entity_var requires the target variable to be a list or null.")

        popped_value = copy.deepcopy(default)
        if current_items:
            popped_value = current_items.pop()
        variables[name] = current_items
        if store_var:
            variables[store_var] = copy.deepcopy(popped_value)

        if persistent:
            _persist_exact_entity_variable_value(
                context,
                entity_id=entity_id,
                name=name,
                value=current_items,
            )
            if store_var:
                _persist_exact_entity_variable_value(
                    context,
                    entity_id=entity_id,
                    name=store_var,
                    value=popped_value,
                )
        return ImmediateHandle()

    @registry.register("set_world_var_from_collection_item")
    def set_world_var_from_collection_item(
        context: CommandContext,
        *,
        name: str,
        value: Any = None,
        index: int | None = None,
        key: str | None = None,
        default: Any = None,
        persistent: bool = False,
    ) -> CommandHandle:
        """Store one item from a collection into an explicit world variable."""
        extracted_value = _extract_collection_item(
            value,
            index=index,
            key=key,
            default=default,
        )
        context.world.variables[name] = extracted_value
        if persistent:
            _persist_world_variable_value(context, name=name, value=extracted_value)
        return ImmediateHandle()

    @registry.register("set_entity_var_from_collection_item")
    def set_entity_var_from_collection_item(
        context: CommandContext,
        *,
        entity_id: str,
        name: str,
        value: Any = None,
        index: int | None = None,
        key: str | None = None,
        default: Any = None,
        persistent: bool = False,
    ) -> CommandHandle:
        """Store one item from a collection into an explicit entity variable."""
        extracted_value = _extract_collection_item(
            value,
            index=index,
            key=key,
            default=default,
        )
        variables = _require_exact_entity_variables(context, entity_id)
        variables[name] = extracted_value
        if persistent:
            _persist_exact_entity_variable_value(
                context,
                entity_id=entity_id,
                name=name,
                value=extracted_value,
            )
        return ImmediateHandle()

    @registry.register("check_world_var")
    def check_world_var(
        context: CommandContext,
        *,
        name: str,
        op: str = "eq",
        value: Any = None,
        then: list[dict[str, Any]] | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Branch based on one explicit world-variable condition."""
        comparator = _COMPARE_OPS.get(op)
        if comparator is None:
            raise ValueError(f"Unknown comparison operator '{op}'.")
        current_value = context.world.variables.get(name)
        return _branch_with_runtime_context(
            registry,
            context,
            condition_met=comparator(current_value, value),
            then=then,
            else_branch=runtime_params.get("else"),
            runtime_params=runtime_params,
            excluded_param_names={"name", "op", "value", "then", "else"},
        )

    @registry.register("check_entity_var")
    def check_entity_var(
        context: CommandContext,
        *,
        entity_id: str,
        name: str,
        op: str = "eq",
        value: Any = None,
        then: list[dict[str, Any]] | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Branch based on one explicit entity-variable condition."""
        comparator = _COMPARE_OPS.get(op)
        if comparator is None:
            raise ValueError(f"Unknown comparison operator '{op}'.")
        variables = _require_exact_entity_variables(context, entity_id)
        current_value = variables.get(name)
        return _branch_with_runtime_context(
            registry,
            context,
            condition_met=comparator(current_value, value),
            then=then,
            else_branch=runtime_params.get("else"),
            runtime_params=runtime_params,
            excluded_param_names={"entity_id", "name", "op", "value", "then", "else"},
        )

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
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Set a variable to a value in the given scope."""
        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
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
                    caller_entity_id=caller_entity_id,
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
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Add an amount to a numeric variable (defaults to 0 if missing)."""
        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
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
                    caller_entity_id=caller_entity_id,
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
        caller_entity_id: str | None = None,
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
            caller_entity_id=caller_entity_id,
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
                    caller_entity_id=caller_entity_id,
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

    @registry.register("append_to_var")
    def append_to_var(
        context: CommandContext,
        *,
        name: str,
        value: Any,
        scope: str = "entity",
        persistent: bool = False,
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Append one value to a list variable, creating the list if needed."""
        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        current_value = variables.get(name)
        if current_value is None:
            current_items: list[Any] = []
        elif isinstance(current_value, list):
            current_items = [copy.deepcopy(item) for item in current_value]
        else:
            raise TypeError("append_to_var requires the target variable to be a list or null.")
        current_items.append(copy.deepcopy(value))
        variables[name] = current_items
        if persistent:
            _persist_variable_value(
                context,
                scope=scope,
                entity_id=entity_id,
                name=name,
                value=current_items,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )
        return ImmediateHandle()

    @registry.register("pop_var")
    def pop_var(
        context: CommandContext,
        *,
        name: str,
        scope: str = "entity",
        persistent: bool = False,
        entity_id: str | None = None,
        store_var: str | None = None,
        default: Any = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Pop the last list item from a variable and optionally store the removed value."""
        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        current_value = variables.get(name)
        if current_value is None:
            current_items: list[Any] = []
        elif isinstance(current_value, list):
            current_items = [copy.deepcopy(item) for item in current_value]
        else:
            raise TypeError("pop_var requires the target variable to be a list or null.")

        popped_value = copy.deepcopy(default)
        if current_items:
            popped_value = current_items.pop()
        variables[name] = current_items
        if store_var:
            variables[store_var] = copy.deepcopy(popped_value)

        if persistent:
            _persist_variable_value(
                context,
                scope=scope,
                entity_id=entity_id,
                name=name,
                value=current_items,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )
            if store_var:
                _persist_variable_value(
                    context,
                    scope=scope,
                    entity_id=entity_id,
                    name=store_var,
                    value=popped_value,
                    source_entity_id=source_entity_id,
                    actor_entity_id=actor_entity_id,
                    caller_entity_id=caller_entity_id,
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
        caller_entity_id: str | None = None,
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
            caller_entity_id=caller_entity_id,
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
                    caller_entity_id=caller_entity_id,
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
        caller_entity_id: str | None = None,
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
            caller_entity_id=caller_entity_id,
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
            if caller_entity_id is not None:
                base_params["caller_entity_id"] = caller_entity_id
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
