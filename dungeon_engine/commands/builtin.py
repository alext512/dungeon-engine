"""Builtin command registration entry point.

The public registration surface stays here even as command domains move into
smaller helper modules under ``dungeon_engine.commands.builtin_domains``.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any, Callable

from dungeon_engine.commands.context_types import PersistenceRuntimeLike

from dungeon_engine.commands.builtin_domains.camera import register_camera_commands
from dungeon_engine.commands.builtin_domains.entity_state import register_entity_state_commands
from dungeon_engine.commands.builtin_domains.flow import register_flow_commands
from dungeon_engine.commands.builtin_domains.inventory import register_inventory_commands
from dungeon_engine.commands.builtin_domains.movement import register_movement_commands
from dungeon_engine.commands.builtin_domains.persistence_state import register_persistence_state_commands
from dungeon_engine.commands.builtin_domains.presentation import register_presentation_commands
from dungeon_engine.commands.builtin_domains.runtime_controls import register_runtime_control_commands
from dungeon_engine.inventory import inventory_item_count
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import (
    CommandContext,
    CommandHandle,
    ImmediateHandle,
    SequenceCommandHandle,
    load_area_owned_snapshot,
)
from dungeon_engine.world.entity import DIRECTION_VECTORS
from dungeon_engine.world.loader_entities import instantiate_entity

logger = logging.getLogger(__name__)

class CompositeCommandHandle(CommandHandle):
    """Wait until every child handle finishes."""

    def __init__(self, handles: list[CommandHandle]) -> None:
        super().__init__()
        self.handles = [handle for handle in handles if not handle.complete]
        if not self.handles:
            self.complete = True

    def update(self, dt: float) -> None:
        """Advance all child handles until every one completes."""
        if self.complete:
            return
        remaining_handles: list[CommandHandle] = []
        for handle in self.handles:
            handle.update(dt)
            if not handle.complete:
                remaining_handles.append(handle)
        self.handles = remaining_handles
        if not self.handles:
            self.complete = True


class PostActionCommandHandle(CommandHandle):
    """Run one callback exactly once after an inner handle finishes."""

    def __init__(self, inner_handle: CommandHandle, on_complete: Callable[[], None]) -> None:
        super().__init__()
        self.inner_handle = inner_handle
        self.on_complete = on_complete
        self._action_ran = False
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Advance the inner handle, then run the completion callback once."""
        if self.complete:
            return
        self.inner_handle.update(dt)
        if not self.inner_handle.complete or self._action_ran:
            return
        self.on_complete()
        self._action_ran = True
        self.complete = True

def _resolve_entity_id(
    entity_id: str,
    *,
    source_entity_id: str | None,
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
    return entity_id


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


def _require_exact_entity(world: Any, entity_id: str) -> Any:
    """Return one explicitly addressed entity or raise a clear error."""
    resolved_id = str(entity_id).strip()
    if not resolved_id:
        raise ValueError("Entity-targeted primitive commands require a non-blank entity_id.")
    if resolved_id == "self":
        raise ValueError(
            "Entity-targeted primitive commands require an explicit entity_id; "
            "use '$self_id' or '$ref_ids.<name>' in a higher-level command first."
        )
    entity = world.get_entity(resolved_id)
    if entity is None:
        raise KeyError(f"Entity '{resolved_id}' not found.")
    return entity


def _require_exact_entity_variables(world: Any, entity_id: str) -> dict[str, Any]:
    """Return the variables dict for one explicitly addressed entity."""
    return _require_exact_entity(world, entity_id).variables


def _persist_current_area_variable_value(
    persistence_runtime: PersistenceRuntimeLike | None,
    *,
    name: str,
    value: Any,
) -> None:
    """Mirror one explicit current-area variable write into persistence when available."""
    if persistence_runtime is None:
        return
    persistence_runtime.set_current_area_variable(name, copy.deepcopy(value))


def _persist_exact_entity_variable_value(
    *,
    world: Any,
    area: Any,
    persistence_runtime: PersistenceRuntimeLike | None,
    entity_id: str,
    name: str,
    value: Any,
) -> None:
    """Mirror one explicit entity-variable write into persistence when available."""
    if persistence_runtime is None:
        return
    entity = _require_exact_entity(world, entity_id)
    persistence_runtime.set_entity_variable(
        str(entity_id).strip(),
        name,
        copy.deepcopy(value),
        entity=entity,
        tile_size=area.tile_size,
    )


def _require_cross_area_persistence_runtime(
    persistence_runtime: PersistenceRuntimeLike | None,
    *,
    command_name: str,
) -> PersistenceRuntimeLike:
    """Return the active persistence runtime or raise a clear error for cross-area state APIs."""
    if persistence_runtime is None:
        raise ValueError(f"{command_name} requires an active persistence runtime.")
    return persistence_runtime


def _require_area_reference(
    project: Any | None,
    area_id: str,
    *,
    command_name: str,
) -> str:
    """Return one resolved authored area id or raise a clear cross-area API error."""
    if project is None:
        raise ValueError(f"{command_name} requires an active project context.")
    resolved_area_id = str(area_id).strip()
    if not resolved_area_id:
        raise ValueError(f"{command_name} requires a non-empty area_id.")
    if project.resolve_area_reference(resolved_area_id) is None:
        raise KeyError(f"Unknown area '{resolved_area_id}'.")
    return resolved_area_id


def _resolve_authored_area_entity_snapshot(
    *,
    project: Any | None,
    area_id: str,
    entity_id: str,
    asset_manager: Any | None = None,
) -> Any:
    """Return one authored area-owned entity for validation in cross-area state APIs."""
    _, snapshot_world = load_area_owned_snapshot(
        project=project,
        area_id=area_id,
        asset_manager=asset_manager,
        include_persistent=False,
    )
    resolved_entity_id = str(entity_id).strip()
    entity = snapshot_world.area_entities.get(resolved_entity_id)
    if entity is None:
        raise KeyError(
            f"Area '{str(area_id).strip()}' does not define authored entity '{resolved_entity_id}'."
        )
    return entity


def _persist_entity_field(
    *,
    area: Any,
    persistence_runtime: PersistenceRuntimeLike | None,
    entity_id: str,
    field_name: str,
    value: Any,
    entity: Any,
) -> None:
    """Persist a single entity field when runtime persistence is available."""
    if persistence_runtime is None:
        return
    persistence_runtime.set_entity_field(
        entity_id,
        field_name,
        value,
        entity=entity,
        tile_size=area.tile_size,
    )


def _persist_entity_command_enabled(
    *,
    area: Any,
    persistence_runtime: PersistenceRuntimeLike | None,
    entity_id: str,
    command_id: str,
    enabled: bool,
    entity: Any,
) -> None:
    """Persist an entity-command enabled-state change when runtime persistence is available."""
    if persistence_runtime is None:
        return
    persistence_runtime.set_entity_command_enabled(
        entity_id,
        command_id,
        enabled,
        entity=entity,
        tile_size=area.tile_size,
    )


def _normalize_camera_follow_spec(
    follow: Any,
    *,
    command_name: str,
    world: Any | None = None,
    source_entity_id: str | None = None,
    require_exact_entity: bool,
) -> dict[str, Any]:
    """Validate one public camera follow spec and return normalized runtime data."""
    if not isinstance(follow, dict):
        raise TypeError(f"{command_name} follow must be a JSON object.")

    allowed_keys = {"mode", "entity_id", "action", "offset_x", "offset_y"}
    unknown_keys = set(follow) - allowed_keys
    if unknown_keys:
        unknown_list = ", ".join(sorted(unknown_keys))
        raise ValueError(f"{command_name} follow contains unknown field(s): {unknown_list}.")

    if "mode" not in follow:
        raise ValueError(f"{command_name} follow requires an explicit mode.")
    mode = str(follow.get("mode", "")).strip()
    if mode not in {"entity", "input_target"}:
        raise ValueError(
            f"{command_name} follow.mode must be 'entity' or 'input_target'."
        )

    offset_x = float(follow.get("offset_x", 0.0))
    offset_y = float(follow.get("offset_y", 0.0))
    normalized: dict[str, Any] = {
        "mode": mode,
        "offset_x": offset_x,
        "offset_y": offset_y,
    }

    if mode == "entity":
        if "action" in follow:
            raise ValueError(f"{command_name} follow.mode 'entity' must not provide action.")
        raw_entity_id = str(follow.get("entity_id", "")).strip()
        if not raw_entity_id:
            raise ValueError(f"{command_name} follow.mode 'entity' requires a non-empty entity_id.")
        if require_exact_entity:
            if world is None:
                raise ValueError(f"{command_name} requires an active world for entity follow.")
            normalized["entity_id"] = _require_exact_entity(world, raw_entity_id).entity_id
            return normalized
        normalized["entity_id"] = _resolve_entity_id(
            raw_entity_id,
            source_entity_id=source_entity_id,
        )
        if not normalized["entity_id"]:
            raise ValueError(f"{command_name} resolved a blank entity_id for follow.mode 'entity'.")
        return normalized

    if "entity_id" in follow:
        raise ValueError(f"{command_name} follow.mode 'input_target' must not provide entity_id.")
    action = str(follow.get("action", "")).strip()
    if not action:
        raise ValueError(f"{command_name} follow.mode 'input_target' requires a non-empty action.")
    normalized["action"] = action
    return normalized


def _normalize_camera_rect_spec(
    area: Any,
    rect: Any,
    *,
    command_name: str,
    rect_name: str,
    pixel_space_name: str,
    grid_space_name: str,
) -> dict[str, float]:
    """Validate and normalize one camera rect spec into pixel-space data."""
    if not isinstance(rect, dict):
        raise TypeError(f"{command_name} {rect_name} must be a JSON object.")

    allowed_keys = {"x", "y", "width", "height", "space"}
    unknown_keys = set(rect) - allowed_keys
    if unknown_keys:
        unknown_list = ", ".join(sorted(unknown_keys))
        raise ValueError(f"{command_name} {rect_name} contains unknown field(s): {unknown_list}.")

    try:
        x = float(rect.get("x", 0.0))
        y = float(rect.get("y", 0.0))
        width = float(rect.get("width", 0.0))
        height = float(rect.get("height", 0.0))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{command_name} {rect_name} x/y/width/height must be numeric."
        ) from exc

    if width <= 0 or height <= 0:
        raise ValueError(f"{command_name} {rect_name} width and height must be positive.")

    space = str(rect.get("space", pixel_space_name)).strip() or pixel_space_name
    if space not in {pixel_space_name, grid_space_name}:
        raise ValueError(
            f"{command_name} {rect_name}.space must be '{pixel_space_name}' or '{grid_space_name}'."
        )

    scale = area.tile_size if space == grid_space_name else 1
    return {
        "x": x * scale,
        "y": y * scale,
        "width": width * scale,
        "height": height * scale,
    }


def _normalize_entity_refs(entity_refs: Any) -> dict[str, str] | None:
    """Validate one authored entity-ref mapping and normalize it to string ids."""
    if entity_refs is None:
        return None
    if not isinstance(entity_refs, dict):
        raise TypeError("entity_refs must be a JSON object when provided.")
    normalized: dict[str, str] = {}
    for raw_name, raw_entity_id in entity_refs.items():
        ref_name = str(raw_name).strip()
        if not ref_name:
            raise ValueError("entity_refs cannot use blank names.")
        entity_id = str(raw_entity_id).strip()
        if not entity_id:
            raise ValueError(f"entity_refs.{ref_name} must resolve to a non-empty entity id.")
        normalized[ref_name] = entity_id
    return normalized


def _build_child_runtime_params(
    runtime_params: dict[str, Any] | None,
    *,
    source_entity_id: str | None = None,
    entity_refs: Any = None,
    refs_mode: str | None = None,
    excluded_param_names: set[str] | None = None,
) -> dict[str, Any]:
    """Return inherited runtime params with optional ref and source overrides applied."""
    inherited_params = {
        key: copy.deepcopy(value)
        for key, value in dict(runtime_params or {}).items()
        if key not in (excluded_param_names or set())
    }
    if source_entity_id is not None:
        inherited_params["source_entity_id"] = source_entity_id

    normalized_refs = _normalize_entity_refs(entity_refs)
    resolved_refs_mode = refs_mode
    if resolved_refs_mode is None:
        resolved_refs_mode = "merge" if normalized_refs is not None else "inherit"
    resolved_refs_mode = str(resolved_refs_mode).strip().lower()
    if resolved_refs_mode not in {"inherit", "merge", "replace"}:
        raise ValueError("refs_mode must be 'inherit', 'merge', or 'replace'.")
    if resolved_refs_mode == "inherit" and normalized_refs is not None:
        raise ValueError("refs_mode 'inherit' cannot be combined with explicit entity_refs.")

    existing_refs = inherited_params.get("entity_refs", {})
    if existing_refs is None:
        inherited_ref_map: dict[str, str] = {}
    elif isinstance(existing_refs, dict):
        inherited_ref_map = {
            str(name): str(entity_id)
            for name, entity_id in existing_refs.items()
        }
    else:
        raise TypeError("Inherited entity_refs must be a JSON object.")

    if resolved_refs_mode == "inherit":
        next_refs = inherited_ref_map
    elif resolved_refs_mode == "merge":
        next_refs = dict(inherited_ref_map)
        next_refs.update(normalized_refs or {})
    else:
        next_refs = dict(normalized_refs or {})

    if next_refs:
        inherited_params["entity_refs"] = next_refs
    else:
        inherited_params.pop("entity_refs", None)

    return inherited_params

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
                "default_animation": visual.default_animation,
                "default_animation_by_facing": dict(visual.default_animation_by_facing),
                "animations": {
                    str(animation_id): {
                        "frames": list(clip.frames),
                        **({"flip_x": bool(clip.flip_x)} if clip.flip_x is not None else {}),
                        **({"preserve_phase": True} if bool(clip.preserve_phase) else {}),
                    }
                    for animation_id, clip in visual.animations.items()
                },
            }
        )
    return serialized


@dataclass(frozen=True, slots=True)
class _EntityFieldMutation:
    """One validated runtime entity-field mutation."""

    path: tuple[str, ...]
    normalized_value: Any


def _normalize_rgb_triplet(value: Any, *, label: str) -> tuple[int, int, int]:
    """Validate a color/tint value and return a normalized RGB triplet."""
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        raise ValueError(f"{label} must be a list or tuple with at least 3 channels.")
    return (int(value[0]), int(value[1]), int(value[2]))


def _normalize_entity_field_mutation(
    entity: Any,
    field_name: str,
    value: Any,
) -> _EntityFieldMutation:
    """Validate one supported runtime entity-field mutation without applying it yet."""
    path = tuple(segment for segment in str(field_name).split(".") if segment)
    if not path:
        raise ValueError("set_entity_field requires a non-empty field name.")

    root = path[0]
    if root == "present":
        if len(path) != 1:
            raise ValueError("present does not support nested field paths.")
        return _EntityFieldMutation(path=path, normalized_value=bool(value))

    if root == "visible":
        if len(path) != 1:
            raise ValueError("visible does not support nested field paths.")
        return _EntityFieldMutation(path=path, normalized_value=bool(value))

    if root == "facing":
        if len(path) != 1:
            raise ValueError("facing does not support nested field paths.")
        normalized_value = str(value).strip().lower()
        if normalized_value not in DIRECTION_VECTORS:
            raise ValueError("facing must be 'up', 'down', 'left', or 'right'.")
        return _EntityFieldMutation(path=path, normalized_value=normalized_value)

    if root == "solid":
        if len(path) != 1:
            raise ValueError("solid does not support nested field paths.")
        return _EntityFieldMutation(path=path, normalized_value=bool(value))

    if root == "pushable":
        if len(path) != 1:
            raise ValueError("pushable does not support nested field paths.")
        return _EntityFieldMutation(path=path, normalized_value=bool(value))

    if root == "weight":
        if len(path) != 1:
            raise ValueError("weight does not support nested field paths.")
        normalized_value = int(value)
        if normalized_value <= 0:
            raise ValueError("weight must be positive.")
        return _EntityFieldMutation(path=path, normalized_value=normalized_value)

    if root == "push_strength":
        if len(path) != 1:
            raise ValueError("push_strength does not support nested field paths.")
        normalized_value = int(value)
        if normalized_value < 0:
            raise ValueError("push_strength must be zero or positive.")
        return _EntityFieldMutation(path=path, normalized_value=normalized_value)

    if root == "collision_push_strength":
        if len(path) != 1:
            raise ValueError("collision_push_strength does not support nested field paths.")
        normalized_value = int(value)
        if normalized_value < 0:
            raise ValueError("collision_push_strength must be zero or positive.")
        return _EntityFieldMutation(path=path, normalized_value=normalized_value)

    if root == "interactable":
        if len(path) != 1:
            raise ValueError("interactable does not support nested field paths.")
        return _EntityFieldMutation(path=path, normalized_value=bool(value))

    if root == "interaction_priority":
        if len(path) != 1:
            raise ValueError("interaction_priority does not support nested field paths.")
        return _EntityFieldMutation(path=path, normalized_value=int(value))

    if root == "entity_commands_enabled":
        if len(path) != 1:
            raise ValueError("entity_commands_enabled does not support nested field paths.")
        return _EntityFieldMutation(path=path, normalized_value=bool(value))

    if root == "render_order":
        if len(path) != 1:
            raise ValueError(f"{root} does not support nested field paths.")
        return _EntityFieldMutation(path=path, normalized_value=int(value))

    if root == "y_sort":
        if len(path) != 1:
            raise ValueError("y_sort does not support nested field paths.")
        return _EntityFieldMutation(path=path, normalized_value=bool(value))

    if root == "sort_y_offset":
        if len(path) != 1:
            raise ValueError("sort_y_offset does not support nested field paths.")
        return _EntityFieldMutation(path=path, normalized_value=float(value))

    if root == "stack_order":
        if len(path) != 1:
            raise ValueError("stack_order does not support nested field paths.")
        return _EntityFieldMutation(path=path, normalized_value=int(value))

    if root == "color":
        if len(path) != 1:
            raise ValueError("color does not support nested field paths.")
        return _EntityFieldMutation(
            path=path,
            normalized_value=_normalize_rgb_triplet(value, label="color"),
        )

    if root == "visuals":
        if len(path) < 3:
            raise ValueError("visuals field mutations must use visuals.<visual_id>.<field>.")
        entity.require_visual(str(path[1]))
        visual_field = str(path[2])
        if visual_field == "flip_x":
            normalized_value = bool(value)
        elif visual_field == "visible":
            normalized_value = bool(value)
        elif visual_field == "current_frame":
            normalized_value = int(value)
        elif visual_field == "tint":
            normalized_value = _normalize_rgb_triplet(value, label="visual tint")
        elif visual_field == "offset_x":
            normalized_value = float(value)
        elif visual_field == "offset_y":
            normalized_value = float(value)
        elif visual_field == "animation_fps":
            normalized_value = float(value)
            if normalized_value < 0:
                raise ValueError("visual animation_fps must be non-negative.")
        else:
            raise ValueError(f"Unsupported visuals field '{visual_field}'.")
        return _EntityFieldMutation(path=path, normalized_value=normalized_value)

    if root == "input_map":
        if len(path) == 1:
            normalized_value = _normalize_input_map(value)
        elif len(path) == 2:
            normalized_value = str(value)
        else:
            raise ValueError("input_map only supports one nested key level.")
        return _EntityFieldMutation(path=path, normalized_value=normalized_value)

    raise ValueError(
        f"Unsupported entity field '{field_name}'. "
        "Use set_current_area_var/set_entity_var for variables and dedicated commands for entity commands/template rebuilds."
    )


def _apply_normalized_entity_field_mutation(
    entity: Any,
    mutation: _EntityFieldMutation,
) -> tuple[str, Any]:
    """Apply one already-validated entity-field mutation and return its persistent form."""
    path = mutation.path
    value = mutation.normalized_value
    root = path[0]

    if root == "present":
        entity.set_present(bool(value))
        return "present", entity.present

    if root == "visible":
        entity.visible = bool(value)
        return "visible", entity.visible

    if root == "facing":
        entity.set_facing_value(str(value))  # type: ignore[arg-type]
        return "facing", entity.facing

    if root == "solid":
        entity.set_solid_value(bool(value))
        return "solid", entity.solid

    if root == "pushable":
        entity.set_pushable_value(bool(value))
        return "pushable", entity.pushable

    if root == "weight":
        entity.weight = int(value)
        return "weight", entity.weight

    if root == "push_strength":
        entity.push_strength = int(value)
        return "push_strength", entity.push_strength

    if root == "collision_push_strength":
        entity.collision_push_strength = int(value)
        return "collision_push_strength", entity.collision_push_strength

    if root == "interactable":
        entity.interactable = bool(value)
        return "interactable", entity.interactable

    if root == "interaction_priority":
        entity.interaction_priority = int(value)
        return "interaction_priority", entity.interaction_priority

    if root == "entity_commands_enabled":
        entity.set_entity_commands_enabled(bool(value))
        return "entity_commands_enabled", entity.entity_commands_enabled

    if root == "render_order":
        entity.render_order = int(value)
        return "render_order", entity.render_order

    if root == "y_sort":
        entity.y_sort = bool(value)
        return "y_sort", entity.y_sort

    if root == "sort_y_offset":
        entity.sort_y_offset = float(value)
        return "sort_y_offset", entity.sort_y_offset

    if root == "stack_order":
        entity.stack_order = int(value)
        return "stack_order", entity.stack_order

    if root == "color":
        entity.color = tuple(value)
        return "color", list(entity.color)

    if root == "visuals":
        visual = entity.require_visual(str(path[1]))
        visual_field = str(path[2])
        if visual_field == "flip_x":
            visual.flip_x = bool(value)
        elif visual_field == "visible":
            visual.visible = bool(value)
        elif visual_field == "current_frame":
            visual.current_frame = int(value)
        elif visual_field == "tint":
            visual.tint = tuple(value)
        elif visual_field == "offset_x":
            visual.offset_x = float(value)
        elif visual_field == "offset_y":
            visual.offset_y = float(value)
        elif visual_field == "animation_fps":
            visual.animation_fps = float(value)
        else:
            raise ValueError(f"Unsupported visuals field '{visual_field}'.")
        return "visuals", _serialize_entity_visuals(entity)

    if root == "input_map":
        if len(path) == 1:
            entity.input_map = copy.deepcopy(value)
        else:
            entity.input_map[str(path[1])] = str(value)
        return "input_map", copy.deepcopy(entity.input_map)

    raise ValueError(
        f"Unsupported entity field path '{'.'.join(path)}'. "
        "Use set_current_area_var/set_entity_var for variables and dedicated commands for entity commands/template rebuilds."
    )


def _apply_entity_field_value(
    entity: Any,
    field_name: str,
    value: Any,
) -> tuple[str, Any]:
    """Apply one supported runtime entity field mutation and return its persistent form."""
    mutation = _normalize_entity_field_mutation(entity, field_name, value)
    return _apply_normalized_entity_field_mutation(entity, mutation)

def register_builtin_commands(registry: CommandRegistry) -> None:
    """Register the minimal command set needed for the first movement slice."""

    def _should_persist_entity_field(entity: Any, *, persistent: bool | None) -> bool:
        """Resolve effective persistence for one entity-state mutation."""
        return entity.persistence.resolve_field(explicit=persistent)

    def _should_persist_entity_variable(
        entity: Any,
        *,
        name: str,
        persistent: bool | None,
    ) -> bool:
        """Resolve effective persistence for one entity-variable mutation."""
        return entity.persistence.resolve_variable(str(name), explicit=persistent)

    def _should_persist_entity_inventory(entity: Any, *, persistent: bool | None) -> bool:
        """Resolve effective persistence for one inventory mutation."""
        return entity.persistence.resolve_field(explicit=persistent)

    def _set_exact_entity_field_handle(
        *,
        context: CommandContext | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        entity_id: str,
        field_name: str,
        value: Any,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Apply one generic entity field mutation through the shared helper."""
        entity = _require_exact_entity(world, entity_id)
        previous_cell = _occupancy_cell_for(entity)
        persisted_field_name, persisted_value = _apply_entity_field_value(
            entity,
            str(field_name),
            value,
        )
        if _should_persist_entity_field(entity, persistent=persistent):
            _persist_entity_field(
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity.entity_id,
                field_name=persisted_field_name,
                value=persisted_value,
                entity=entity,
            )
        if context is None or persisted_field_name != "present":
            return ImmediateHandle()
        return _build_occupancy_transition_handle(
            context=context,
            instigator=entity,
            previous_cell=previous_cell,
            next_cell=_occupancy_cell_for(entity),
        )

    def _set_exact_entity_fields_handle(
        *,
        context: CommandContext | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        entity_id: str,
        set_payload: dict[str, Any],
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Apply one validated batch of entity field, variable, and visual mutations."""
        entity = _require_exact_entity(world, entity_id)
        previous_cell = _occupancy_cell_for(entity)
        if not isinstance(set_payload, dict):
            raise ValueError("set_entity_fields requires 'set' to be a JSON object.")

        prepared_operations: list[tuple[str, Any, Any]] = []
        for section_name, section_value in set_payload.items():
            if section_name == "fields":
                if not isinstance(section_value, dict):
                    raise ValueError("set_entity_fields.set.fields must be a JSON object.")
                for field_name, raw_value in section_value.items():
                    mutation = _normalize_entity_field_mutation(entity, str(field_name), raw_value)
                    if mutation.path[0] == "visuals":
                        raise ValueError(
                            "set_entity_fields.set.fields only supports top-level entity fields; "
                            "use set.visuals for visual mutations."
                        )
                    prepared_operations.append(("field", mutation, None))
            elif section_name == "variables":
                if not isinstance(section_value, dict):
                    raise ValueError("set_entity_fields.set.variables must be a JSON object.")
                for name, raw_value in section_value.items():
                    prepared_operations.append(("variable", str(name), copy.deepcopy(raw_value)))
            elif section_name == "visuals":
                if not isinstance(section_value, dict):
                    raise ValueError("set_entity_fields.set.visuals must be a JSON object.")
                for visual_id, visual_fields in section_value.items():
                    resolved_visual_id = str(visual_id).strip()
                    if not resolved_visual_id:
                        raise ValueError("set_entity_fields.set.visuals keys must be non-empty visual ids.")
                    if not isinstance(visual_fields, dict):
                        raise ValueError(
                            f"set_entity_fields.set.visuals.{resolved_visual_id} must be a JSON object."
                        )
                    for visual_field, raw_value in visual_fields.items():
                        mutation = _normalize_entity_field_mutation(
                            entity,
                            f"visuals.{resolved_visual_id}.{visual_field}",
                            raw_value,
                        )
                        prepared_operations.append(("field", mutation, None))
            else:
                raise ValueError(
                    f"Unsupported set_entity_fields section '{section_name}'. "
                    "Supported sections are: fields, variables, visuals."
                )

        visuals_changed = False
        for operation_kind, operation_name, operation_value in prepared_operations:
            if operation_kind == "field":
                persisted_field_name, persisted_value = _apply_normalized_entity_field_mutation(
                    entity,
                    operation_name,
                )
                if _should_persist_entity_field(entity, persistent=persistent):
                    if persisted_field_name == "visuals":
                        visuals_changed = True
                    else:
                        _persist_entity_field(
                            area=area,
                            persistence_runtime=persistence_runtime,
                            entity_id=entity.entity_id,
                            field_name=persisted_field_name,
                            value=persisted_value,
                            entity=entity,
                        )
                continue

            variables = _require_exact_entity_variables(world, entity.entity_id)
            variables[operation_name] = copy.deepcopy(operation_value)
            if _should_persist_entity_variable(
                entity,
                name=str(operation_name),
                persistent=persistent,
            ):
                _persist_exact_entity_variable_value(
                    world=world,
                    area=area,
                    persistence_runtime=persistence_runtime,
                    entity_id=entity.entity_id,
                    name=operation_name,
                    value=operation_value,
                )

        if visuals_changed and _should_persist_entity_field(entity, persistent=persistent):
            _persist_entity_field(
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity.entity_id,
                field_name="visuals",
                value=_serialize_entity_visuals(entity),
                entity=entity,
            )
        if context is None:
            return ImmediateHandle()
        return _build_occupancy_transition_handle(
            context=context,
            instigator=entity,
            previous_cell=previous_cell,
            next_cell=_occupancy_cell_for(entity),
        )

    def _dispatch_named_entity_command(
        *,
        context: CommandContext,
        entity_id: str,
        command_id: str,
        runtime_params: dict[str, Any] | None = None,
        entity_refs: dict[str, str] | None = None,
        refs_mode: str | None = None,
    ) -> CommandHandle:
        """Execute one named entity command through the normal runtime pipeline."""
        world_services = context.services.world
        if world_services is None or world_services.world is None:
            raise ValueError("Entity command dispatch requires an active world service.")
        entity = world_services.world.get_entity(str(entity_id).strip())
        if entity is None or not entity.present:
            return ImmediateHandle()
        entity_command = entity.get_entity_command(command_id)
        if (
            not entity.has_enabled_entity_command(command_id)
            or entity_command is None
            or not entity_command.commands
        ):
            return ImmediateHandle()
        base_params = _build_child_runtime_params(
            runtime_params or {},
            source_entity_id=entity.entity_id,
            entity_refs=entity_refs,
            refs_mode=refs_mode,
        )
        return SequenceCommandHandle(
            registry,
            context,
            entity_command.commands,
            base_params=base_params,
        )

    def _occupancy_cell_for(entity: Any) -> tuple[int, int] | None:
        """Return the occupied cell for one present world-space entity."""
        if entity.space != "world" or not entity.present:
            return None
        return (int(entity.grid_x), int(entity.grid_y))

    def _build_occupancy_runtime_params(
        previous_cell: tuple[int, int] | None,
        next_cell: tuple[int, int] | None,
    ) -> dict[str, Any]:
        """Return the shared runtime parameters for occupancy hooks."""
        runtime_params: dict[str, Any] = {}
        if previous_cell is not None:
            runtime_params["from_x"] = int(previous_cell[0])
            runtime_params["from_y"] = int(previous_cell[1])
        if next_cell is not None:
            runtime_params["to_x"] = int(next_cell[0])
            runtime_params["to_y"] = int(next_cell[1])
        return runtime_params

    def _build_occupancy_transition_handle(
        *,
        context: CommandContext,
        instigator: Any,
        previous_cell: tuple[int, int] | None,
        next_cell: tuple[int, int] | None,
    ) -> CommandHandle:
        """Dispatch stationary-entity occupancy hooks for one logical tile transition."""
        if previous_cell == next_cell:
            return ImmediateHandle()

        runtime_params = _build_occupancy_runtime_params(previous_cell, next_cell)
        runtime_params["instigator_id"] = instigator.entity_id
        handles: list[CommandHandle] = []
        world_services = context.services.world
        if world_services is None or world_services.world is None:
            raise ValueError("Occupancy transition hooks require an active world service.")
        world = world_services.world

        if previous_cell is not None:
            for receiver in world.get_entities_at(
                previous_cell[0],
                previous_cell[1],
                exclude_entity_id=instigator.entity_id,
                include_hidden=True,
            ):
                handle = _dispatch_named_entity_command(
                    context=context,
                    entity_id=receiver.entity_id,
                    command_id="on_occupant_leave",
                    runtime_params=runtime_params,
                )
                if not handle.complete:
                    handles.append(handle)

        if next_cell is not None:
            for receiver in world.get_entities_at(
                next_cell[0],
                next_cell[1],
                exclude_entity_id=instigator.entity_id,
                include_hidden=True,
            ):
                handle = _dispatch_named_entity_command(
                    context=context,
                    entity_id=receiver.entity_id,
                    command_id="on_occupant_enter",
                    runtime_params=runtime_params,
                )
                if not handle.complete:
                    handles.append(handle)

        if not handles:
            return ImmediateHandle()
        if len(handles) == 1:
            return handles[0]
        return CompositeCommandHandle(handles)

    def _open_dialogue_session_handle(
        context: CommandContext,
        *,
        dialogue_path: str | None = None,
        dialogue_definition: dict[str, Any] | None = None,
        dialogue_on_start: list[dict[str, Any]] | dict[str, Any] | None = None,
        dialogue_on_end: list[dict[str, Any]] | dict[str, Any] | None = None,
        segment_hooks: list[Any] | None = None,
        allow_cancel: bool = False,
        actor_id: str | None = None,
        caller_id: str | None = None,
        instigator_id: str | None = None,
        ui_preset: str | None = None,
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
    ) -> CommandHandle:
        """Open one engine-owned dialogue session using the canonical modal runtime."""
        from dungeon_engine.engine.dialogue_runtime import DialogueSessionWaitHandle

        ui_services = context.services.ui
        dialogue_runtime = None if ui_services is None else ui_services.dialogue_runtime
        if dialogue_runtime is None:
            raise ValueError("open_dialogue_session requires an active dialogue runtime.")

        resolved_actor_id = None if actor_id in (None, "") else str(actor_id).strip()
        if resolved_actor_id in (None, "") and instigator_id not in (None, ""):
            resolved_actor_id = str(instigator_id).strip()
        resolved_caller_id = None if caller_id in (None, "") else str(caller_id).strip()
        if resolved_caller_id in (None, "") and source_entity_id not in (None, ""):
            resolved_caller_id = str(source_entity_id).strip()

        session = dialogue_runtime.open_session(
            dialogue_path=dialogue_path,
            dialogue_definition=dialogue_definition,
            dialogue_on_start=dialogue_on_start,
            dialogue_on_end=dialogue_on_end,
            segment_hooks=segment_hooks,
            allow_cancel=bool(allow_cancel),
            actor_id=resolved_actor_id,
            caller_id=resolved_caller_id,
            entity_refs=_normalize_entity_refs(entity_refs) or None,
            ui_preset_name=None if ui_preset in (None, "") else str(ui_preset).strip(),
        )
        return DialogueSessionWaitHandle(dialogue_runtime, session)

    @registry.register(
        "open_dialogue_session",
        deferred_param_shapes={
            "dialogue_definition": "dialogue_definition",
            "dialogue_on_start": "command_payload",
            "dialogue_on_end": "command_payload",
            "segment_hooks": "dialogue_segment_hooks",
        },
    )
    def open_dialogue_session(
        context: CommandContext,
        *,
        dialogue_path: str | None = None,
        dialogue_definition: dict[str, Any] | None = None,
        dialogue_on_start: list[dict[str, Any]] | dict[str, Any] | None = None,
        dialogue_on_end: list[dict[str, Any]] | dict[str, Any] | None = None,
        segment_hooks: list[Any] | None = None,
        allow_cancel: bool = False,
        actor_id: str | None = None,
        caller_id: str | None = None,
        ui_preset: str | None = None,
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Open one engine-owned dialogue session using the canonical modal runtime."""
        return _open_dialogue_session_handle(
            context,
            dialogue_path=dialogue_path,
            dialogue_definition=dialogue_definition,
            dialogue_on_start=dialogue_on_start,
            dialogue_on_end=dialogue_on_end,
            segment_hooks=segment_hooks,
            allow_cancel=allow_cancel,
            actor_id=actor_id,
            caller_id=caller_id,
            instigator_id=runtime_params.get("instigator_id"),
            ui_preset=ui_preset,
            source_entity_id=source_entity_id,
            entity_refs=entity_refs,
        )

    @registry.register(
        "open_entity_dialogue",
        deferred_param_shapes={
            "dialogue_on_start": "command_payload",
            "dialogue_on_end": "command_payload",
            "segment_hooks": "dialogue_segment_hooks",
        },
    )
    def open_entity_dialogue(
        context: CommandContext,
        world: Any,
        *,
        entity_id: str,
        dialogue_id: str | None = None,
        dialogue_on_start: list[dict[str, Any]] | dict[str, Any] | None = None,
        dialogue_on_end: list[dict[str, Any]] | dict[str, Any] | None = None,
        segment_hooks: list[Any] | None = None,
        allow_cancel: bool = False,
        actor_id: str | None = None,
        caller_id: str | None = None,
        ui_preset: str | None = None,
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Open one named entity-owned dialogue or the entity's current active dialogue."""
        entity = _require_exact_entity(world, entity_id)
        if not entity.dialogues:
            raise ValueError(
                f"open_entity_dialogue requires entity '{entity.entity_id}' to define a non-empty 'dialogues' map."
            )

        resolved_dialogue_id: str
        if dialogue_id in (None, ""):
            current_dialogue_id = entity.variables.get("active_dialogue")
            if not isinstance(current_dialogue_id, str) or not current_dialogue_id.strip():
                raise ValueError(
                    f"open_entity_dialogue requires entity '{entity.entity_id}' to have a non-empty "
                    "'active_dialogue' variable when dialogue_id is omitted."
                )
            resolved_dialogue_id = current_dialogue_id.strip()
        else:
            resolved_dialogue_id = str(dialogue_id).strip()

        dialogue_entry = entity.dialogues.get(resolved_dialogue_id)
        if dialogue_entry is None:
            raise KeyError(
                f"Entity '{entity.entity_id}' has no dialogue '{resolved_dialogue_id}'."
            )

        resolved_dialogue_path = dialogue_entry.get("dialogue_path")
        resolved_dialogue_definition = dialogue_entry.get("dialogue_definition")
        if (resolved_dialogue_path is None) == (resolved_dialogue_definition is None):
            raise ValueError(
                f"Entity '{entity.entity_id}' dialogue '{resolved_dialogue_id}' must define exactly one "
                "of 'dialogue_path' or 'dialogue_definition'."
            )

        return _open_dialogue_session_handle(
            context,
            dialogue_path=None if resolved_dialogue_path is None else str(resolved_dialogue_path).strip(),
            dialogue_definition=(
                None
                if resolved_dialogue_definition is None
                else copy.deepcopy(resolved_dialogue_definition)
            ),
            dialogue_on_start=dialogue_on_start,
            dialogue_on_end=dialogue_on_end,
            segment_hooks=segment_hooks,
            allow_cancel=allow_cancel,
            actor_id=actor_id,
            caller_id=entity.entity_id if caller_id in (None, "") else caller_id,
            instigator_id=runtime_params.get("instigator_id"),
            ui_preset=ui_preset,
            source_entity_id=source_entity_id,
            entity_refs=entity_refs,
        )

    @registry.register("close_dialogue_session")
    def close_dialogue_session(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Close the currently active engine-owned dialogue session when one exists."""
        ui_services = context.services.ui
        dialogue_runtime = None if ui_services is None else ui_services.dialogue_runtime
        if dialogue_runtime is None:
            raise ValueError("close_dialogue_session requires an active dialogue runtime.")
        dialogue_runtime.close_current_session()
        return ImmediateHandle()

    register_presentation_commands(
        registry,
        require_exact_entity=_require_exact_entity,
    )

    register_movement_commands(
        registry,
        logger=logger,
        require_exact_entity=_require_exact_entity,
        resolve_entity_id=_resolve_entity_id,
        dispatch_named_entity_command=_dispatch_named_entity_command,
    )

    register_flow_commands(
        registry,
        logger=logger,
        build_child_runtime_params=_build_child_runtime_params,
        resolve_entity_id=_resolve_entity_id,
    )

    register_entity_state_commands(
        registry,
        instantiate_entity=instantiate_entity,
        require_exact_entity=_require_exact_entity,
        should_persist_entity_field=_should_persist_entity_field,
        should_persist_entity_variable=_should_persist_entity_variable,
        persist_current_area_variable_value=_persist_current_area_variable_value,
        persist_exact_entity_variable_value=_persist_exact_entity_variable_value,
        persist_entity_command_enabled=_persist_entity_command_enabled,
        set_exact_entity_field_handle=_set_exact_entity_field_handle,
        set_exact_entity_fields_handle=_set_exact_entity_fields_handle,
        occupancy_cell_for=_occupancy_cell_for,
        build_occupancy_transition_handle=_build_occupancy_transition_handle,
        post_action_handle_factory=PostActionCommandHandle,
    )

    register_inventory_commands(
        registry,
        logger=logger,
        require_exact_entity=_require_exact_entity,
        persist_entity_field=_persist_entity_field,
        build_child_runtime_params=_build_child_runtime_params,
        post_action_handle_factory=PostActionCommandHandle,
    )

    register_runtime_control_commands(
        registry,
        logger=logger,
        require_exact_entity=_require_exact_entity,
        resolve_entity_id=_resolve_entity_id,
        normalize_camera_follow_spec=_normalize_camera_follow_spec,
    )

    register_camera_commands(
        registry,
        require_exact_entity=_require_exact_entity,
        normalize_camera_follow_spec=_normalize_camera_follow_spec,
        normalize_camera_rect_spec=_normalize_camera_rect_spec,
    )

    register_persistence_state_commands(
        registry,
        require_cross_area_persistence_runtime=_require_cross_area_persistence_runtime,
        require_area_reference=_require_area_reference,
        resolve_authored_area_entity_snapshot=_resolve_authored_area_entity_snapshot,
        normalize_entity_field_mutation=_normalize_entity_field_mutation,
        apply_normalized_entity_field_mutation=_apply_normalized_entity_field_mutation,
    )
