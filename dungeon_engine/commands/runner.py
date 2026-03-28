"""Queue and execute command requests with lightweight async handles."""

from __future__ import annotations

from collections import deque
import copy
from dataclasses import dataclass, field
import json
from pathlib import Path
import random
from typing import Any, Callable

from dungeon_engine import config
from dungeon_engine.systems.collision import CollisionSystem
from dungeon_engine.systems.interaction import InteractionSystem
from dungeon_engine.systems.animation import AnimationSystem
from dungeon_engine.systems.movement import MovementSystem
from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import DIRECTION_VECTORS
from dungeon_engine.world.world import World
from dungeon_engine.logging_utils import get_logger


logger = get_logger(__name__)
_JSON_FILE_CACHE: dict[Path, Any] = {}
_FALLBACK_RANDOM_GENERATOR = random.Random()
_PLAIN_ENTITY_REF_FIELDS = (
    "entity_id",
    "kind",
    "space",
    "scope",
    "grid_x",
    "grid_y",
    "pixel_x",
    "pixel_y",
    "present",
    "visible",
    "events_enabled",
    "layer",
    "stack_order",
    "tags",
)
_PLAIN_ENTITY_VISUAL_FIELDS = (
    "id",
    "path",
    "frame_width",
    "frame_height",
    "frames",
    "animation_fps",
    "animate_when_moving",
    "current_frame",
    "animation_elapsed",
    "flip_x",
    "visible",
    "tint",
    "offset_x",
    "offset_y",
    "draw_order",
)
_ENTITY_QUERY_WHERE_BOOLEAN_FIELDS = ("present", "visible", "events_enabled")
_ENTITY_QUERY_WHERE_STRING_FIELDS = ("kind", "space", "scope")
_ENTITY_QUERY_WHERE_LIST_FIELDS = ("kinds", "tags_any", "tags_all")
_ENTITY_QUERY_ALLOWED_SPACES = ("world", "screen")
_ENTITY_QUERY_ALLOWED_SCOPES = ("area", "global")


@dataclass(slots=True)
class CommandContext:
    """Objects that command implementations need access to at runtime."""

    area: Area
    world: World
    collision_system: CollisionSystem
    movement_system: MovementSystem
    interaction_system: InteractionSystem
    animation_system: AnimationSystem
    project: Any | None = None
    asset_manager: Any | None = None
    text_renderer: Any | None = None
    camera: Any | None = None
    audio_player: Any | None = None
    screen_manager: Any | None = None
    command_runner: Any | None = None
    random_generator: Any | None = None
    persistence_runtime: Any | None = None
    request_area_change: Callable[["AreaTransitionRequest"], None] | None = None
    request_new_game: Callable[["AreaTransitionRequest"], None] | None = None
    request_load_game: Callable[[str | None], None] | None = None
    save_game: Callable[[str | None], bool] | None = None
    request_quit: Callable[[], None] | None = None
    debug_inspection_enabled: bool = False
    set_simulation_paused: Callable[[bool], None] | None = None
    get_simulation_paused: Callable[[], bool] | None = None
    request_step_simulation_tick: Callable[[], None] | None = None
    adjust_output_scale: Callable[[int], None] | None = None
    named_command_stack: list[str] = field(default_factory=list)
    command_trace: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CameraFollowRequest:
    """Requested camera follow state to apply after a transition completes."""

    mode: str = "preserve"
    entity_id: str | None = None
    input_action: str | None = None
    offset_x: float = 0.0
    offset_y: float = 0.0


@dataclass(slots=True)
class AreaTransitionRequest:
    """One deferred area transition plus optional entity/camera transfer data."""

    area_id: str
    entry_id: str | None = None
    transfer_entity_ids: list[str] = field(default_factory=list)
    camera_follow: CameraFollowRequest | None = None


class CommandHandle:
    """Base handle for commands that may take more than one frame to finish."""

    def __init__(self) -> None:
        self.complete = False

    def update(self, dt: float) -> None:
        """Advance the command handle toward completion."""


class ImmediateHandle(CommandHandle):
    """A command handle that finishes immediately."""

    def __init__(self) -> None:
        super().__init__()
        self.complete = True


class WaitFramesHandle(CommandHandle):
    """Complete after a fixed number of simulation ticks."""

    def __init__(self, frames: int) -> None:
        super().__init__()
        self.frames_remaining = max(0, int(frames))
        if self.frames_remaining == 0:
            self.complete = True

    def update(self, dt: float) -> None:
        """Advance only on real simulation ticks, not zero-dt bookkeeping updates."""
        if self.complete or dt <= 0:
            return
        self.frames_remaining -= 1
        if self.frames_remaining <= 0:
            self.complete = True


class CommandExecutionError(RuntimeError):
    """Wrap a command failure with execution-trace context for logging/UI hints."""

    def __init__(
        self,
        message: str,
        *,
        command_name: str,
        params: dict[str, Any],
        trace: list[str],
    ) -> None:
        super().__init__(message)
        self.command_name = command_name
        self.params = dict(params)
        self.trace = list(trace)


@dataclass(slots=True)
class QueuedCommand:
    """A pending command request waiting to be executed by the runner."""

    name: str
    params: dict[str, Any]


def _describe_command(name: str, params: dict[str, Any]) -> str:
    """Return a short readable label for command trace logging."""
    interesting_parts: list[str] = []
    for key in ("command_id", "event_id", "entity_id", "action"):
        if key in params and params[key] not in ("", None):
            interesting_parts.append(f"{key}={params[key]}")
    if interesting_parts:
        return f"{name}({', '.join(interesting_parts)})"
    return name


def _lookup_nested_value(value: Any, path_parts: list[str]) -> Any:
    """Resolve a nested dict/list path against a Python value."""
    current = value
    for part in path_parts:
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(f"Unknown key '{part}'.")
            current = current[part]
            continue
        if isinstance(current, list):
            try:
                index = int(part)
            except ValueError as exc:
                raise KeyError(f"Expected list index, got '{part}'.") from exc
            try:
                current = current[index]
            except IndexError as exc:
                raise KeyError(f"List index '{index}' is out of range.") from exc
            continue
        raise KeyError(f"Cannot descend into '{part}'.")
    return current


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


def _build_text_window(
    lines: Any,
    *,
    start: int = 0,
    max_lines: int = 1,
    separator: str = "\n",
) -> dict[str, Any]:
    """Return one visible text window plus simple metadata."""
    if lines is None:
        normalized_lines: list[str] = []
    elif isinstance(lines, str):
        normalized_lines = [str(lines)]
    elif isinstance(lines, (list, tuple)):
        normalized_lines = [str(item) for item in lines]
    else:
        raise TypeError(
            "Text-window value source requires lines to be a list, tuple, string, or null."
        )

    resolved_start = max(0, int(start))
    resolved_max_lines = max(0, int(max_lines))
    visible_lines = normalized_lines[resolved_start : resolved_start + resolved_max_lines]
    return {
        "visible_lines": visible_lines,
        "visible_text": str(separator).join(visible_lines),
        "has_more": resolved_start + resolved_max_lines < len(normalized_lines),
        "total_lines": len(normalized_lines),
    }


def _extract_collection_item(
    value: Any,
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
    if resolved_index < 0:
        resolved_index += len(value)
    if 0 <= resolved_index < len(value):
        return copy.deepcopy(value[resolved_index])
    return extracted_value


def _coerce_numeric_value(value: Any, *, source_name: str) -> int | float:
    """Return one numeric value or raise a clear error for value-source math helpers."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{source_name} value source expects numeric values.")
    return value


def _coerce_integer_value(value: Any, *, source_name: str, field_name: str) -> int:
    """Return one integer-like value or raise a clear error."""
    numeric_value = _coerce_numeric_value(value, source_name=source_name)
    if isinstance(numeric_value, float) and not numeric_value.is_integer():
        raise TypeError(f"{source_name} {field_name} expects an integer value.")
    return int(numeric_value)


def _serialize_entity_fields(entity: Any, *, fields: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """Return a small plain-data object containing only the requested entity fields."""
    data: dict[str, Any] = {}
    for field_name in fields:
        if field_name == "tags":
            data[field_name] = list(entity.tags)
            continue
        data[field_name] = copy.deepcopy(getattr(entity, field_name))
    return data


def _serialize_visual_fields(visual: Any, *, fields: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """Return one plain-data object containing only the requested visual fields."""
    data: dict[str, Any] = {}
    for field_name in fields:
        if field_name == "id":
            data[field_name] = visual.visual_id
            continue
        data[field_name] = copy.deepcopy(getattr(visual, field_name))
    return data


def _normalize_requested_field_names(
    raw_fields: Any,
    *,
    source_name: str,
    section_name: str,
    allowed_fields: tuple[str, ...],
) -> list[str]:
    """Validate one requested field-name list against a fixed public whitelist."""
    if not isinstance(raw_fields, (list, tuple)) or not raw_fields:
        raise ValueError(f"{source_name} {section_name} requires a non-empty list.")
    resolved_fields: list[str] = []
    invalid_fields: list[str] = []
    for raw_field in raw_fields:
        if not isinstance(raw_field, str):
            invalid_fields.append(str(raw_field))
            continue
        field_name = raw_field.strip()
        if field_name not in allowed_fields:
            invalid_fields.append(field_name)
            continue
        if field_name not in resolved_fields:
            resolved_fields.append(field_name)
    if invalid_fields:
        allowed = ", ".join(allowed_fields)
        invalid = ", ".join(repr(field_name) for field_name in invalid_fields)
        raise ValueError(
            f"{source_name} {section_name} does not support field(s) {invalid}. "
            f"Allowed fields: {allowed}."
        )
    return resolved_fields


def _resolve_entity_select_spec(raw_select: Any, *, source_name: str) -> dict[str, Any]:
    """Validate one shared entity-query selection spec."""
    if not isinstance(raw_select, dict):
        raise TypeError(f"{source_name} select requires a JSON object.")
    supported_keys = {"fields", "variables", "visuals"}
    unsupported_keys = sorted(set(raw_select) - supported_keys)
    if unsupported_keys:
        formatted = ", ".join(repr(key) for key in unsupported_keys)
        raise ValueError(
            f"{source_name} select does not support key(s) {formatted}. "
            "Allowed keys: 'fields', 'variables', 'visuals'."
        )

    select: dict[str, Any] = {}
    if "fields" in raw_select:
        select["fields"] = _normalize_requested_field_names(
            raw_select.get("fields"),
            source_name=source_name,
            section_name="select.fields",
            allowed_fields=_PLAIN_ENTITY_REF_FIELDS,
        )

    if "variables" in raw_select:
        raw_variables = raw_select.get("variables")
        if not isinstance(raw_variables, (list, tuple)) or not raw_variables:
            raise ValueError(f"{source_name} select.variables requires a non-empty list.")
        resolved_variables: list[str] = []
        for raw_variable in raw_variables:
            if not isinstance(raw_variable, str) or not raw_variable.strip():
                raise ValueError(
                    f"{source_name} select.variables only supports non-empty string keys."
                )
            variable_name = raw_variable.strip()
            if variable_name not in resolved_variables:
                resolved_variables.append(variable_name)
        select["variables"] = resolved_variables

    if "visuals" in raw_select:
        raw_visuals = raw_select.get("visuals")
        if not isinstance(raw_visuals, (list, tuple)) or not raw_visuals:
            raise ValueError(f"{source_name} select.visuals requires a non-empty list.")
        resolved_visuals: list[dict[str, Any]] = []
        for raw_visual in raw_visuals:
            if not isinstance(raw_visual, dict):
                raise TypeError(
                    f"{source_name} select.visuals entries require JSON objects."
                )
            visual_id = str(raw_visual.get("id", raw_visual.get("visual_id", ""))).strip()
            if not visual_id:
                raise ValueError(
                    f"{source_name} select.visuals entries require a non-empty 'id'."
                )
            resolved_visuals.append(
                {
                    "id": visual_id,
                    "fields": _normalize_requested_field_names(
                        raw_visual.get("fields"),
                        source_name=source_name,
                        section_name="select.visuals.fields",
                        allowed_fields=_PLAIN_ENTITY_VISUAL_FIELDS,
                    ),
                    "default": copy.deepcopy(raw_visual.get("default")),
                }
            )
        select["visuals"] = resolved_visuals

    if not select:
        raise ValueError(
            f"{source_name} select requires at least one of 'fields', 'variables', or 'visuals'."
        )
    return select


def _normalize_string_filter_list(
    raw_values: Any,
    *,
    source_name: str,
    field_name: str,
) -> list[str]:
    """Validate one non-empty list of distinct string values for query filters."""
    if not isinstance(raw_values, (list, tuple)) or not raw_values:
        raise ValueError(f"{source_name} where.{field_name} requires a non-empty list.")
    resolved_values: list[str] = []
    for raw_value in raw_values:
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(
                f"{source_name} where.{field_name} only supports non-empty string values."
            )
        value = raw_value.strip()
        if value not in resolved_values:
            resolved_values.append(value)
    return resolved_values


def _resolve_entity_where_spec(raw_where: Any, *, source_name: str) -> dict[str, Any]:
    """Validate one shared entity-query filter spec."""
    if raw_where in (None, {}):
        return {}
    if not isinstance(raw_where, dict):
        raise TypeError(f"{source_name} where requires a JSON object.")

    supported_keys = {
        *_ENTITY_QUERY_WHERE_BOOLEAN_FIELDS,
        *_ENTITY_QUERY_WHERE_STRING_FIELDS,
        *_ENTITY_QUERY_WHERE_LIST_FIELDS,
    }
    unsupported_keys = sorted(set(raw_where) - supported_keys)
    if unsupported_keys:
        formatted = ", ".join(repr(key) for key in unsupported_keys)
        raise ValueError(
            f"{source_name} where does not support key(s) {formatted}. "
            "Allowed keys: 'kind', 'kinds', 'tags_any', 'tags_all', 'space', "
            "'scope', 'present', 'visible', 'events_enabled'."
        )
    if "kind" in raw_where and "kinds" in raw_where:
        raise ValueError(f"{source_name} where does not allow both 'kind' and 'kinds'.")

    where: dict[str, Any] = {}

    for field_name in _ENTITY_QUERY_WHERE_BOOLEAN_FIELDS:
        if field_name not in raw_where:
            continue
        raw_value = raw_where.get(field_name)
        if not isinstance(raw_value, bool):
            raise TypeError(f"{source_name} where.{field_name} requires a boolean.")
        where[field_name] = raw_value

    if "kind" in raw_where:
        raw_kind = raw_where.get("kind")
        if not isinstance(raw_kind, str) or not raw_kind.strip():
            raise ValueError(f"{source_name} where.kind requires a non-empty string.")
        where["kind"] = raw_kind.strip()

    if "kinds" in raw_where:
        where["kinds"] = _normalize_string_filter_list(
            raw_where.get("kinds"),
            source_name=source_name,
            field_name="kinds",
        )

    if "tags_any" in raw_where:
        where["tags_any"] = _normalize_string_filter_list(
            raw_where.get("tags_any"),
            source_name=source_name,
            field_name="tags_any",
        )

    if "tags_all" in raw_where:
        where["tags_all"] = _normalize_string_filter_list(
            raw_where.get("tags_all"),
            source_name=source_name,
            field_name="tags_all",
        )

    if "space" in raw_where:
        raw_space = raw_where.get("space")
        if not isinstance(raw_space, str) or not raw_space.strip():
            raise ValueError(f"{source_name} where.space requires a non-empty string.")
        resolved_space = raw_space.strip()
        if resolved_space not in _ENTITY_QUERY_ALLOWED_SPACES:
            allowed = ", ".join(repr(value) for value in _ENTITY_QUERY_ALLOWED_SPACES)
            raise ValueError(
                f"{source_name} where.space does not support {resolved_space!r}. "
                f"Allowed values: {allowed}."
            )
        where["space"] = resolved_space

    if "scope" in raw_where:
        raw_scope = raw_where.get("scope")
        if not isinstance(raw_scope, str) or not raw_scope.strip():
            raise ValueError(f"{source_name} where.scope requires a non-empty string.")
        resolved_scope = raw_scope.strip()
        if resolved_scope not in _ENTITY_QUERY_ALLOWED_SCOPES:
            allowed = ", ".join(repr(value) for value in _ENTITY_QUERY_ALLOWED_SCOPES)
            raise ValueError(
                f"{source_name} where.scope does not support {resolved_scope!r}. "
                f"Allowed values: {allowed}."
            )
        where["scope"] = resolved_scope

    return where


def _entity_matches_where(entity: Any, where: dict[str, Any]) -> bool:
    """Return whether one runtime entity matches the shared query filter spec."""
    if not where:
        return True
    if "kind" in where and entity.kind != where["kind"]:
        return False
    if "kinds" in where and entity.kind not in where["kinds"]:
        return False
    if "space" in where and entity.space != where["space"]:
        return False
    if "scope" in where and entity.scope != where["scope"]:
        return False
    if "present" in where and entity.present is not where["present"]:
        return False
    if "visible" in where and entity.visible is not where["visible"]:
        return False
    if "events_enabled" in where and entity.events_enabled is not where["events_enabled"]:
        return False
    entity_tags = set(entity.tags)
    if "tags_any" in where and not entity_tags.intersection(where["tags_any"]):
        return False
    if "tags_all" in where and not set(where["tags_all"]).issubset(entity_tags):
        return False
    return True


def _serialize_selected_entity(entity: Any, *, select: dict[str, Any]) -> dict[str, Any]:
    """Return one plain-data entity object shaped by the shared selection grammar."""
    data: dict[str, Any] = {}
    selected_fields = select.get("fields")
    if selected_fields:
        data.update(_serialize_entity_fields(entity, fields=selected_fields))

    selected_variables = select.get("variables")
    if selected_variables:
        selected_variable_values: dict[str, Any] = {}
        for variable_name in selected_variables:
            if variable_name in entity.variables:
                selected_variable_values[variable_name] = copy.deepcopy(
                    entity.variables[variable_name]
                )
        data["variables"] = selected_variable_values

    selected_visuals = select.get("visuals")
    if selected_visuals:
        selected_visual_values: dict[str, Any] = {}
        for visual_spec in selected_visuals:
            visual = entity.get_visual(str(visual_spec["id"]))
            if visual is None:
                selected_visual_values[str(visual_spec["id"])] = copy.deepcopy(
                    visual_spec.get("default")
                )
                continue
            selected_visual_values[str(visual_spec["id"])] = _serialize_visual_fields(
                visual,
                fields=visual_spec["fields"],
            )
        data["visuals"] = selected_visual_values

    return data


def _resolve_entity_ref_value(context: CommandContext, resolved_source: Any) -> dict[str, Any] | None:
    """Return one plain-data entity reference for an explicitly chosen entity id."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$entity_ref value source requires a JSON object.")
    entity_id = str(resolved_source.get("entity_id", "")).strip()
    if not entity_id:
        raise ValueError("$entity_ref value source requires a non-empty entity_id.")
    default = copy.deepcopy(resolved_source.get("default"))
    if "select" not in resolved_source:
        raise ValueError("$entity_ref value source requires a select object.")
    select = _resolve_entity_select_spec(
        resolved_source.get("select"),
        source_name="$entity_ref",
    )
    entity = context.world.get_entity(entity_id)
    if entity is None:
        return default
    return _serialize_selected_entity(entity, select=select)


def _resolve_entities_at_value(context: CommandContext, resolved_source: Any) -> list[dict[str, Any]]:
    """Return plain-data refs for world-space entities at one tile."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$entities_at value source requires a JSON object.")
    raw_x = resolved_source.get("x")
    raw_y = resolved_source.get("y")
    if raw_x is None or raw_y is None:
        raise ValueError("$entities_at value source requires both x and y.")
    exclude_entity_id = resolved_source.get("exclude_entity_id")
    where = _resolve_entity_where_spec(
        resolved_source.get("where"),
        source_name="$entities_at",
    )
    include_hidden = bool(resolved_source.get("include_hidden", False)) or (
        where.get("visible") is False
    )
    include_absent = bool(resolved_source.get("include_absent", False)) or (
        where.get("present") is False
    )
    if "select" not in resolved_source:
        raise ValueError("$entities_at value source requires a select object.")
    select = _resolve_entity_select_spec(
        resolved_source.get("select"),
        source_name="$entities_at",
    )
    entities = context.world.get_entities_at(
        int(raw_x),
        int(raw_y),
        exclude_entity_id=None if exclude_entity_id in (None, "") else str(exclude_entity_id),
        include_hidden=include_hidden,
        include_absent=include_absent,
    )
    entities = [entity for entity in entities if _entity_matches_where(entity, where)]
    return [_serialize_selected_entity(entity, select=select) for entity in entities]


def _resolve_entity_at_value(context: CommandContext, resolved_source: Any) -> Any:
    """Return one plain-data entity ref selected from a tile query."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$entity_at value source requires a JSON object.")
    entities = _resolve_entities_at_value(context, resolved_source)
    return _extract_collection_item(
        entities,
        index=resolved_source.get("index", 0),
        default=resolved_source.get("default"),
    )


def _resolve_entities_query_value(context: CommandContext, resolved_source: Any) -> list[dict[str, Any]]:
    """Return selected plain-data refs for one filtered world/entity scan."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$entities_query value source requires a JSON object.")
    where = _resolve_entity_where_spec(
        resolved_source.get("where"),
        source_name="$entities_query",
    )
    include_hidden = bool(resolved_source.get("include_hidden", False)) or (
        where.get("visible") is False
    )
    include_absent = bool(resolved_source.get("include_absent", False)) or (
        where.get("present") is False
    )
    if "select" not in resolved_source:
        raise ValueError("$entities_query value source requires a select object.")
    select = _resolve_entity_select_spec(
        resolved_source.get("select"),
        source_name="$entities_query",
    )
    entities = sorted(
        [
            entity
            for entity in context.world.iter_entities(include_absent=include_absent)
            if include_hidden or entity.visible
            if _entity_matches_where(entity, where)
        ],
        key=context.world.entity_sort_key,
    )
    return [_serialize_selected_entity(entity, select=select) for entity in entities]


def _resolve_entity_query_value(context: CommandContext, resolved_source: Any) -> Any:
    """Return one selected plain-data ref chosen from a filtered world/entity scan."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$entity_query value source requires a JSON object.")
    entities = _resolve_entities_query_value(context, resolved_source)
    return _extract_collection_item(
        entities,
        index=resolved_source.get("index", 0),
        default=resolved_source.get("default"),
    )


def _resolve_sum_value(resolved_source: Any) -> int | float:
    """Return the numeric sum of a small authored value list."""
    if not isinstance(resolved_source, (list, tuple)):
        raise TypeError("$sum value source requires a list or tuple.")
    numeric_values = [_coerce_numeric_value(value, source_name="$sum") for value in resolved_source]
    if any(isinstance(value, float) for value in numeric_values):
        return float(sum(float(value) for value in numeric_values))
    return int(sum(int(value) for value in numeric_values))


def _resolve_product_value(resolved_source: Any) -> int | float:
    """Return the numeric product of a small authored value list."""
    if not isinstance(resolved_source, (list, tuple)):
        raise TypeError("$product value source requires a list or tuple.")
    numeric_values = [_coerce_numeric_value(value, source_name="$product") for value in resolved_source]
    if not numeric_values:
        raise ValueError("$product value source requires at least one value.")
    product: int | float = 1
    for value in numeric_values:
        product *= value
    if any(isinstance(value, float) for value in numeric_values):
        return float(product)
    return int(product)


def _resolve_join_text_value(resolved_source: Any) -> str:
    """Join a small authored value list into one text string."""
    if not isinstance(resolved_source, (list, tuple)):
        raise TypeError("$join_text value source requires a list or tuple.")
    return "".join("" if value is None else str(value) for value in resolved_source)


def _resolve_slice_collection_value(resolved_source: Any) -> list[Any]:
    """Return a bounded list slice from a list/tuple value."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$slice_collection value source requires a JSON object.")
    collection = resolved_source.get("value")
    if collection is None:
        return []
    if not isinstance(collection, (list, tuple)):
        raise TypeError("$slice_collection value source requires a list or tuple value.")
    start = int(resolved_source.get("start", 0))
    count = resolved_source.get("count")
    if start < 0:
        start = max(0, len(collection) + start)
    if count is None:
        end = len(collection)
    else:
        resolved_count = int(count)
        if resolved_count <= 0:
            return []
        end = start + resolved_count
    return [copy.deepcopy(item) for item in list(collection)[start:end]]


def _resolve_wrap_index_value(resolved_source: Any) -> int:
    """Wrap one integer index around a positive collection size."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$wrap_index value source requires a JSON object.")
    count = int(resolved_source.get("count", 0))
    default = int(resolved_source.get("default", 0))
    if count <= 0:
        return default
    value = int(resolved_source.get("value", default))
    return value % count


def _resolve_and_value(resolved_source: Any) -> bool:
    """Return True when every authored value in the list is truthy."""
    if not isinstance(resolved_source, (list, tuple)):
        raise TypeError("$and value source requires a list or tuple.")
    return all(bool(value) for value in resolved_source)


def _resolve_or_value(resolved_source: Any) -> bool:
    """Return True when any authored value in the list is truthy."""
    if not isinstance(resolved_source, (list, tuple)):
        raise TypeError("$or value source requires a list or tuple.")
    return any(bool(value) for value in resolved_source)


def _resolve_not_value(resolved_source: Any) -> bool:
    """Return the authored truthiness negation of one value."""
    return not bool(resolved_source)


def _runtime_random_generator(context: CommandContext) -> Any:
    """Return the active RNG for authored runtime helpers."""
    if context.random_generator is not None:
        return context.random_generator
    return _FALLBACK_RANDOM_GENERATOR


def _resolve_random_int_value(context: CommandContext, resolved_source: Any) -> int:
    """Return one inclusive authored random integer."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$random_int value source requires a JSON object.")
    if "min" not in resolved_source or "max" not in resolved_source:
        raise ValueError("$random_int value source requires both min and max.")
    minimum = _coerce_integer_value(
        resolved_source.get("min"),
        source_name="$random_int",
        field_name="min",
    )
    maximum = _coerce_integer_value(
        resolved_source.get("max"),
        source_name="$random_int",
        field_name="max",
    )
    if minimum > maximum:
        raise ValueError("$random_int value source requires min <= max.")
    return int(_runtime_random_generator(context).randint(minimum, maximum))


def _resolve_random_choice_value(context: CommandContext, resolved_source: Any) -> Any:
    """Return one random collection item or the supplied default."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$random_choice value source requires a JSON object.")
    collection = resolved_source.get("value")
    if collection is None:
        return copy.deepcopy(resolved_source.get("default"))
    if not isinstance(collection, (list, tuple)):
        raise TypeError("$random_choice value source requires a list or tuple value.")
    if not collection:
        return copy.deepcopy(resolved_source.get("default"))
    return copy.deepcopy(_runtime_random_generator(context).choice(list(collection)))


def _resolve_cell_flags_at_value(context: CommandContext, resolved_source: Any) -> dict[str, Any] | Any:
    """Return plain per-cell flag data for one explicit tile coordinate."""
    if context.area is None:
        raise ValueError("Cannot resolve cell flags without an active area.")
    if not isinstance(resolved_source, dict):
        raise TypeError("$cell_flags_at value source requires a JSON object.")
    raw_x = resolved_source.get("x")
    raw_y = resolved_source.get("y")
    if raw_x is None or raw_y is None:
        raise ValueError("$cell_flags_at value source requires both x and y.")
    grid_x = int(raw_x)
    grid_y = int(raw_y)
    if context.area.in_bounds(grid_x, grid_y):
        return copy.deepcopy(context.area.cell_flags_at(grid_x, grid_y))
    if "default" in resolved_source:
        return copy.deepcopy(resolved_source.get("default"))
    raise KeyError(f"Cell flag lookup ({grid_x}, {grid_y}) is out of bounds.")


def _resolve_collection_field_value(item: Any, field_path: str | None) -> Any:
    """Resolve one optional dotted field path against a collection item."""
    if field_path in (None, ""):
        return item
    parts = [part for part in str(field_path).split(".") if part]
    return _lookup_nested_value(item, parts)


def _collection_comparator(op: str) -> Any:
    """Return a small generic comparator for collection helpers."""
    comparators = {
        "eq": lambda left, right: left == right,
        "neq": lambda left, right: left != right,
        "gt": lambda left, right: left > right,
        "gte": lambda left, right: left >= right,
        "lt": lambda left, right: left < right,
        "lte": lambda left, right: left <= right,
    }
    comparator = comparators.get(str(op))
    if comparator is None:
        raise ValueError(f"Unknown comparison operator '{op}'.")
    return comparator


def _resolve_find_in_collection_value(resolved_source: Any) -> Any:
    """Return the first matching collection item or the supplied default."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$find_in_collection value source requires a JSON object.")
    collection = resolved_source.get("value")
    if collection is None:
        return copy.deepcopy(resolved_source.get("default"))
    if not isinstance(collection, (list, tuple)):
        raise TypeError("$find_in_collection value source requires a list or tuple value.")
    comparator = _collection_comparator(str(resolved_source.get("op", "eq")))
    field_path = resolved_source.get("field")
    match_value = resolved_source.get("match")
    for item in collection:
        try:
            candidate_value = _resolve_collection_field_value(item, field_path)
        except KeyError:
            continue
        if comparator(candidate_value, match_value):
            return copy.deepcopy(item)
    return copy.deepcopy(resolved_source.get("default"))


def _resolve_any_in_collection_value(resolved_source: Any) -> bool:
    """Return True when any collection item matches the supplied predicate."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$any_in_collection value source requires a JSON object.")
    collection = resolved_source.get("value")
    if collection is None:
        return False
    if not isinstance(collection, (list, tuple)):
        raise TypeError("$any_in_collection value source requires a list or tuple value.")
    comparator = _collection_comparator(str(resolved_source.get("op", "eq")))
    field_path = resolved_source.get("field")
    match_value = resolved_source.get("match")
    for item in collection:
        try:
            candidate_value = _resolve_collection_field_value(item, field_path)
        except KeyError:
            continue
        if comparator(candidate_value, match_value):
            return True
    return False


def _resolve_runtime_value_source(
    source_name: str,
    source_value: Any,
    context: CommandContext,
    runtime_params: dict[str, Any],
) -> Any:
    """Resolve one structured value source before primitive execution."""
    resolved_source = _resolve_runtime_values(source_value, context, runtime_params)

    if source_name == "$json_file":
        if resolved_source in (None, ""):
            raise ValueError("JSON file value source requires a non-empty path.")
        return _load_json_file(_resolve_json_file_path(context, str(resolved_source)))

    if source_name == "$wrapped_lines":
        if context.text_renderer is None:
            raise ValueError("Cannot wrap text without an active text renderer.")
        if not isinstance(resolved_source, dict):
            raise TypeError("$wrapped_lines value source requires a JSON object.")
        return context.text_renderer.wrap_lines(
            "" if resolved_source.get("text") is None else str(resolved_source.get("text")),
            int(resolved_source.get("max_width", 0)),
            font_id=str(resolved_source.get("font_id", config.DEFAULT_UI_FONT_ID)),
        )

    if source_name == "$text_window":
        if not isinstance(resolved_source, dict):
            raise TypeError("$text_window value source requires a JSON object.")
        return _build_text_window(
            resolved_source.get("lines"),
            start=int(resolved_source.get("start", 0)),
            max_lines=int(resolved_source.get("max_lines", 1)),
            separator=str(resolved_source.get("separator", "\n")),
        )

    if source_name == "$entity_ref":
        return _resolve_entity_ref_value(context, resolved_source)

    if source_name == "$sum":
        return _resolve_sum_value(resolved_source)

    if source_name == "$product":
        return _resolve_product_value(resolved_source)

    if source_name == "$join_text":
        return _resolve_join_text_value(resolved_source)

    if source_name == "$slice_collection":
        return _resolve_slice_collection_value(resolved_source)

    if source_name == "$wrap_index":
        return _resolve_wrap_index_value(resolved_source)

    if source_name == "$and":
        return _resolve_and_value(resolved_source)

    if source_name == "$or":
        return _resolve_or_value(resolved_source)

    if source_name == "$not":
        return _resolve_not_value(resolved_source)

    if source_name == "$random_int":
        return _resolve_random_int_value(context, resolved_source)

    if source_name == "$random_choice":
        return _resolve_random_choice_value(context, resolved_source)

    if source_name == "$entities_at":
        return _resolve_entities_at_value(context, resolved_source)

    if source_name == "$entity_at":
        return _resolve_entity_at_value(context, resolved_source)

    if source_name == "$entities_query":
        return _resolve_entities_query_value(context, resolved_source)

    if source_name == "$entity_query":
        return _resolve_entity_query_value(context, resolved_source)

    if source_name == "$cell_flags_at":
        return _resolve_cell_flags_at_value(context, resolved_source)

    if source_name == "$collection_item":
        if not isinstance(resolved_source, dict):
            raise TypeError("$collection_item value source requires a JSON object.")
        return _extract_collection_item(
            resolved_source.get("value"),
            index=resolved_source.get("index"),
            key=resolved_source.get("key"),
            default=resolved_source.get("default"),
        )

    if source_name == "$find_in_collection":
        return _resolve_find_in_collection_value(resolved_source)

    if source_name == "$any_in_collection":
        return _resolve_any_in_collection_value(resolved_source)

    raise KeyError(f"Unknown value source '{source_name}'.")


def _resolve_runtime_token(
    token: str,
    context: CommandContext,
    runtime_params: dict[str, Any],
) -> Any:
    """Resolve a $token against event params, project values, or runtime variables."""
    if token.startswith("half:"):
        base_value = _resolve_runtime_token(token[5:], context, runtime_params)
        if not isinstance(base_value, (int, float)):
            raise TypeError(f"$half: expects a numeric value, got {type(base_value).__name__}.")
        if isinstance(base_value, int):
            return max(1, base_value // 2)
        return base_value / 2

    if token in runtime_params:
        return copy.deepcopy(runtime_params[token])

    if token == "self_id":
        entity_id = runtime_params.get("source_entity_id")
        if not entity_id:
            raise KeyError("Token '$self_id' requires a source entity context.")
        return str(entity_id)

    if token == "actor_id":
        entity_id = runtime_params.get("actor_entity_id")
        if not entity_id:
            raise KeyError("Token '$actor_id' requires an actor entity context.")
        return str(entity_id)

    if token == "caller_id":
        entity_id = runtime_params.get("caller_entity_id")
        if not entity_id:
            raise KeyError("Token '$caller_id' requires a caller entity context.")
        return str(entity_id)

    parts = [part for part in token.split(".") if part]
    if not parts:
        raise KeyError("Empty runtime token.")

    head, tail = parts[0], parts[1:]
    if head in runtime_params:
        return copy.deepcopy(_lookup_nested_value(runtime_params[head], tail))

    if head == "project":
        if context.project is None:
            raise KeyError("No active project context for $project lookup.")
        return copy.deepcopy(context.project.resolve_shared_variable(tail))

    if head == "camera":
        if context.camera is None:
            raise KeyError("No active camera context for $camera lookup.")
        camera_state = context.camera.to_state_dict()
        camera_state.setdefault("follow_mode", "none")
        camera_state.setdefault("follow_entity_id", None)
        camera_state.setdefault("follow_input_action", None)
        camera_state.setdefault("x", None)
        camera_state.setdefault("y", None)
        camera_state.setdefault("follow_offset_x", 0.0)
        camera_state.setdefault("follow_offset_y", 0.0)
        camera_state.setdefault("bounds", None)
        camera_state.setdefault("deadzone", None)
        camera_state["has_bounds"] = camera_state.get("bounds") is not None
        camera_state["has_deadzone"] = camera_state.get("deadzone") is not None
        camera_state["mode"] = camera_state.get("follow_mode")
        if not tail:
            return copy.deepcopy(camera_state)
        return copy.deepcopy(_lookup_nested_value(camera_state, tail))

    if head == "area":
        if context.area is None:
            raise KeyError("No active area context for $area lookup.")
        area_state = {
            "area_id": context.area.area_id,
            "name": context.area.name,
            "tile_size": context.area.tile_size,
            "width": context.area.width,
            "height": context.area.height,
            "pixel_width": context.area.pixel_width,
            "pixel_height": context.area.pixel_height,
            "camera": copy.deepcopy(context.area.camera_defaults),
        }
        if not tail:
            return copy.deepcopy(area_state)
        return copy.deepcopy(_lookup_nested_value(area_state, tail))

    if head == "world":
        return copy.deepcopy(_lookup_nested_value(context.world.variables, tail))

    if head == "entity":
        if len(parts) < 3:
            raise KeyError(f"Token '${token}' requires an entity id and variable path.")
        entity_id = parts[1]
        entity = context.world.get_entity(str(entity_id))
        if entity is None:
            raise KeyError(f"Token '${token}' references missing entity '{entity_id}'.")
        return copy.deepcopy(_lookup_nested_value(entity.variables, parts[2:]))

    if head == "self":
        entity_id = runtime_params.get("source_entity_id")
        if not entity_id:
            raise KeyError(f"Token '${token}' requires a source entity context.")
        entity = context.world.get_entity(str(entity_id))
        if entity is None:
            raise KeyError(f"Token '${token}' references missing source entity '{entity_id}'.")
        return copy.deepcopy(_lookup_nested_value(entity.variables, tail))

    if head == "actor":
        entity_id = runtime_params.get("actor_entity_id")
        if not entity_id:
            raise KeyError(f"Token '${token}' requires an actor entity context.")
        entity = context.world.get_entity(str(entity_id))
        if entity is None:
            raise KeyError(f"Token '${token}' references missing actor entity '{entity_id}'.")
        return copy.deepcopy(_lookup_nested_value(entity.variables, tail))

    if head == "caller":
        entity_id = runtime_params.get("caller_entity_id")
        if not entity_id:
            raise KeyError(f"Token '${token}' requires a caller entity context.")
        entity = context.world.get_entity(str(entity_id))
        if entity is None:
            raise KeyError(f"Token '${token}' references missing caller entity '{entity_id}'.")
        return copy.deepcopy(_lookup_nested_value(entity.variables, tail))

    raise KeyError(f"Unknown runtime token '${token}'.")


def _resolve_runtime_values(
    value: Any,
    context: CommandContext,
    runtime_params: dict[str, Any],
) -> Any:
    """Resolve $tokens recursively inside a command spec before execution."""
    if isinstance(value, dict):
        if len(value) == 1:
            source_name, source_value = next(iter(value.items()))
            if isinstance(source_name, str) and source_name in {
                "$json_file",
                "$wrapped_lines",
                "$text_window",
                "$entity_ref",
                "$cell_flags_at",
                "$entities_at",
                "$entity_at",
                "$entities_query",
                "$entity_query",
                "$collection_item",
                "$sum",
                "$product",
                "$join_text",
                "$slice_collection",
                "$wrap_index",
                "$and",
                "$or",
                "$not",
                "$random_int",
                "$random_choice",
                "$find_in_collection",
                "$any_in_collection",
            }:
                return _resolve_runtime_value_source(
                    source_name,
                    source_value,
                    context,
                    runtime_params,
                )
        return {
            key: _resolve_runtime_values(item, context, runtime_params)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            _resolve_runtime_values(item, context, runtime_params)
            for item in value
        ]

    if isinstance(value, str):
        token = None
        if value.startswith("${") and value.endswith("}"):
            token = value[2:-1]
        elif value.startswith("$"):
            token = value[1:]
        if token is not None:
            return _resolve_runtime_token(token, context, runtime_params)

    return value


def _resolve_deferred_runtime_value(
    value: Any,
    context: CommandContext,
    runtime_params: dict[str, Any],
) -> Any:
    """Resolve one top-level token while leaving nested command specs untouched."""
    if isinstance(value, str):
        token = None
        if value.startswith("${") and value.endswith("}"):
            token = value[2:-1]
        elif value.startswith("$"):
            token = value[1:]
        if token is not None:
            return _resolve_runtime_token(token, context, runtime_params)
    return copy.deepcopy(value)


def execute_registered_command(
    registry: Any,
    context: CommandContext,
    name: str,
    params: dict[str, Any],
) -> CommandHandle:
    """Execute a named command with one already-resolved parameter dictionary."""
    command_params = dict(params)
    disallowed_lifecycle_keys = {"on_complete", "on_start", "on_end"} & set(command_params)
    if disallowed_lifecycle_keys:
        forbidden = sorted(disallowed_lifecycle_keys)
        if forbidden == ["on_complete"]:
            message = (
                f"Command '{name}' must not use 'on_complete'; "
                "use explicit sequencing with 'run_sequence' instead."
            )
        else:
            formatted = ", ".join(f"'{key}'" for key in forbidden)
            message = (
                f"Command '{name}' must not use lifecycle wrapper field(s) {formatted}; "
                "use explicit sequencing with 'run_sequence', grouped overlap with "
                "'run_parallel', or fire-and-forget overlap with 'spawn_flow' instead."
            )
        raise ValueError(message)
    trace_entry = _describe_command(name, command_params)
    context.command_trace.append(trace_entry)
    try:
        handle = registry.execute(name, context, command_params) or ImmediateHandle()
    except CommandExecutionError:
        raise
    except Exception as exc:
        trace_snapshot = list(context.command_trace)
        raise CommandExecutionError(
            f"Command '{name}' failed.",
            command_name=name,
            params=command_params,
            trace=trace_snapshot,
        ) from exc
    finally:
        if context.command_trace and context.command_trace[-1] == trace_entry:
            context.command_trace.pop()
    return handle


def execute_command_spec(
    registry: Any,
    context: CommandContext,
    command_spec: dict[str, Any],
    *,
    base_params: dict[str, Any] | None = None,
) -> CommandHandle:
    """Execute a single command spec with optional inherited base parameters."""
    inherited_params = dict(base_params or {})
    raw_spec = dict(command_spec)
    command_name = str(raw_spec.get("type", ""))
    deferred_keys = set()
    if hasattr(registry, "get_deferred_params"):
        deferred_keys = registry.get_deferred_params(command_name)
    if deferred_keys:
        spec = {
            key: _resolve_deferred_runtime_value(value, context, inherited_params)
            if key in deferred_keys
            else _resolve_runtime_values(value, context, inherited_params)
            for key, value in raw_spec.items()
        }
    else:
        spec = _resolve_runtime_values(raw_spec, context, inherited_params)
    command_name = str(spec.pop("type"))
    params = dict(inherited_params)
    params.update(spec)
    return execute_registered_command(
        registry,
        context,
        command_name,
        params,
    )


class SequenceCommandHandle(CommandHandle):
    """Execute a list of command specs one after another, waiting for async steps."""

    def __init__(
        self,
        registry: Any,
        context: CommandContext,
        commands: list[dict[str, Any]],
        base_params: dict[str, Any] | None = None,
        *,
        auto_start: bool = True,
    ) -> None:
        super().__init__()
        self.registry = registry
        self.context = context
        self.commands = commands
        self.base_params = dict(base_params or {})
        self.current_index = 0
        self.current_handle: CommandHandle | None = None
        if auto_start:
            self.update(0.0)

    def update(self, dt: float) -> None:
        """Advance the current child command and start the next one when ready."""
        if self.complete:
            return

        if self.current_handle is not None:
            self.current_handle.update(dt)
            if self.current_handle.complete:
                self.current_handle = None

        while self.current_handle is None and self.current_index < len(self.commands):
            command_spec = dict(self.commands[self.current_index])
            self.current_index += 1
            self.current_handle = execute_command_spec(
                self.registry,
                self.context,
                command_spec,
                base_params=self.base_params,
            )
            if self.current_handle.complete:
                self.current_handle = None

        if self.current_handle is None and self.current_index >= len(self.commands):
            self.complete = True


class CommandRunner:
    """Execute pending commands as independent root flows."""

    def __init__(self, registry: Any, context: CommandContext) -> None:
        self.registry = registry
        self.context = context
        self.pending: deque[QueuedCommand] = deque()
        self.root_handles: list[CommandHandle] = []
        self._pending_spawned_root_handles: list[CommandHandle] = []
        self._updating_root_handles = False
        self.last_error_notice: str | None = None
        self.context.command_runner = self

    def enqueue(self, name: str, **params: Any) -> None:
        """Add a command request to the end of the queue."""
        self.pending.append(QueuedCommand(name=name, params=params))

    def dispatch_input_event(
        self,
        entity_id: str,
        event_id: str,
        *,
        actor_entity_id: str | None = None,
    ) -> bool:
        """Queue one routed input event as an ordinary root flow."""
        params: dict[str, Any] = {
            "entity_id": entity_id,
            "event_id": event_id,
        }
        if actor_entity_id is not None:
            params["actor_entity_id"] = actor_entity_id

        self.enqueue("run_event", **params)
        return True

    def has_pending_work(self) -> bool:
        """Return True when a command is queued or still running."""
        return bool(self.pending or self.root_handles or self._pending_spawned_root_handles)

    def spawn_root_handle(self, handle: CommandHandle) -> None:
        """Run one handle as an independent root flow."""
        if handle.complete:
            return
        if self._updating_root_handles:
            self._pending_spawned_root_handles.append(handle)
            return
        self.root_handles.append(handle)

    def update(self, dt: float) -> None:
        """Advance all root flows and materialize queued dispatches."""
        try:
            self._materialize_pending_commands()

            if self.root_handles:
                self._updating_root_handles = True
                try:
                    remaining_handles: list[CommandHandle] = []
                    for handle in self.root_handles:
                        handle.update(dt)
                        if not handle.complete:
                            remaining_handles.append(handle)
                    self.root_handles = remaining_handles
                finally:
                    self._updating_root_handles = False

            if self._pending_spawned_root_handles:
                self.root_handles.extend(self._pending_spawned_root_handles)
                self._pending_spawned_root_handles.clear()

            self._materialize_pending_commands()
        except CommandExecutionError as exc:
            self._handle_command_error(exc)
        except Exception as exc:
            wrapped = CommandExecutionError(
                "Command runner update failed.",
                command_name="<runner>",
                params={},
                trace=list(self.context.command_trace),
            )
            wrapped.__cause__ = exc
            self._handle_command_error(wrapped)

    def _handle_command_error(self, exc: CommandExecutionError) -> None:
        """Log a command error once and stop the current lane cleanly."""
        cause = exc.__cause__
        trace_text = " -> ".join(exc.trace) if exc.trace else "<no trace>"
        logger.exception(
            "Command execution error: %s | trace=%s | params=%s",
            exc,
            trace_text,
            exc.params,
            exc_info=(type(cause), cause, cause.__traceback__) if cause is not None else None,
        )
        self.root_handles.clear()
        self._pending_spawned_root_handles.clear()
        self._updating_root_handles = False
        self.pending.clear()
        self.context.command_trace.clear()
        self.last_error_notice = "Command error: see logs/error.log"

    def _materialize_pending_commands(self) -> None:
        """Turn queued requests into root flows or immediate effects."""
        while self.pending:
            queued_command = self.pending.popleft()
            handle = execute_registered_command(
                self.registry,
                self.context,
                queued_command.name,
                queued_command.params,
            )
            self.spawn_root_handle(handle)

