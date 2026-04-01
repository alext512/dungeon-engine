"""Starter command implementations used by the first prototype slice."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Any, Callable

from dungeon_engine import config
from dungeon_engine.commands.library import (
    instantiate_project_command_commands,
    load_project_command_definition,
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
    execute_command_spec,
    load_area_owned_snapshot,
)
from dungeon_engine.world.entity import DIRECTION_VECTORS
from dungeon_engine.world.loader import instantiate_entity

logger = logging.getLogger(__name__)


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


class AnimationCommandHandle(CommandHandle):
    """Wait until all entities started by an animation command finish playback."""

    def __init__(
        self,
        animation_system: Any,
        entity_ids: list[str],
        *,
        visual_id: str | None = None,
    ) -> None:
        super().__init__()
        self.animation_system = animation_system
        self.entity_ids = entity_ids
        self.visual_id = visual_id
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when every animated entity has finished."""
        self.complete = not any(
            self.animation_system.is_entity_animating(entity_id, visual_id=self.visual_id)
            for entity_id in self.entity_ids
        )


class CameraCommandHandle(CommandHandle):
    """Wait until an interpolated camera move finishes."""

    def __init__(self, camera: Any) -> None:
        super().__init__()
        self.camera = camera
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when the camera stops moving."""
        self.complete = self.camera is None or not self.camera.is_moving()


class ScreenAnimationCommandHandle(CommandHandle):
    """Wait until a screen-space animation finishes playback."""

    def __init__(self, screen_manager: Any, element_id: str) -> None:
        super().__init__()
        self.screen_manager = screen_manager
        self.element_id = element_id
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when the screen element stops animating."""
        self.complete = self.screen_manager is None or not self.screen_manager.is_animating(
            self.element_id
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
            if not self.current_handle.complete:
                return
            self.current_handle = None

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
            return

        if self.current_handle is None and self.current_index >= len(self.items):
            self.complete = True


class ProjectCommandHandle(CommandHandle):
    """Run a reusable project command definition while tracking recursion."""

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
        """Record entry into one project command invocation."""
        if self._stack_pushed:
            return
        self.context.project_command_stack.append(self.command_id)
        self._stack_pushed = True

    def _pop_stack(self) -> None:
        """Remove this invocation from the project command call stack."""
        if not self._stack_pushed:
            return
        if self.context.project_command_stack and self.context.project_command_stack[-1] == self.command_id:
            self.context.project_command_stack.pop()
        self._stack_pushed = False


class ParallelCommandHandle(CommandHandle):
    """Run several command branches together with explicit completion rules."""

    def __init__(
        self,
        registry: CommandRegistry,
        context: CommandContext,
        *,
        command_specs: list[dict[str, Any]],
        completion: dict[str, Any] | None = None,
        base_params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.registry = registry
        self.context = context
        self.base_params = dict(base_params or {})
        self.children: list[dict[str, Any]] = []
        self.completion_mode = "all"
        self.completion_child_id: str | None = None
        self.remaining_policy = "keep_running"
        self._completion_triggered = False
        self._configure_completion(completion)
        self._build_children(command_specs)
        self.update(0.0)

    def _configure_completion(self, completion: dict[str, Any] | None) -> None:
        """Validate and store one explicit parallel completion policy."""
        if completion is None:
            return
        if not isinstance(completion, dict):
            raise TypeError("run_parallel completion must be a JSON object or null.")
        self.completion_mode = str(completion.get("mode", "all")).strip() or "all"
        if self.completion_mode not in {"all", "any", "child"}:
            raise ValueError(
                "run_parallel completion.mode must be 'all', 'any', or 'child'."
            )
        if self.completion_mode == "child":
            child_id = str(completion.get("child_id", "")).strip()
            if not child_id:
                raise ValueError(
                    "run_parallel completion.mode 'child' requires a non-empty child_id."
                )
            self.completion_child_id = child_id
        remaining_policy = str(completion.get("remaining", "keep_running")).strip() or "keep_running"
        if remaining_policy != "keep_running":
            raise ValueError(
                "run_parallel currently only supports completion.remaining = 'keep_running'."
            )
        self.remaining_policy = remaining_policy

    def _build_children(self, command_specs: list[dict[str, Any]]) -> None:
        """Create child handles from authored command specs."""
        seen_ids: set[str] = set()
        for raw_command in command_specs:
            child_spec = dict(raw_command)
            child_id = str(child_spec.pop("id", "")).strip() or None
            if child_id is not None:
                if child_id in seen_ids:
                    raise ValueError(f"run_parallel child id '{child_id}' is duplicated.")
                seen_ids.add(child_id)
            handle = execute_command_spec(
                self.registry,
                self.context,
                child_spec,
                base_params=self.base_params,
            )
            self.children.append(
                {
                    "id": child_id,
                    "handle": handle,
                    "promoted": False,
                }
            )
        if self.completion_mode == "child" and self.completion_child_id not in seen_ids:
            raise ValueError(
                f"run_parallel completion child_id '{self.completion_child_id}' does not match any child id."
            )

    def update(self, dt: float) -> None:
        """Advance child handles and complete according to the configured policy."""
        if self.complete:
            return

        for child in self.children:
            handle = child["handle"]
            if not handle.complete:
                handle.update(dt)

        if self._completion_triggered:
            return

        should_complete = False
        if self.completion_mode == "all":
            should_complete = all(child["handle"].complete for child in self.children)
        elif self.completion_mode == "any":
            should_complete = any(child["handle"].complete for child in self.children)
        elif self.completion_mode == "child":
            should_complete = any(
                child["id"] == self.completion_child_id and child["handle"].complete
                for child in self.children
            )

        if not should_complete:
            return

        self._completion_triggered = True
        if self.completion_mode != "all":
            self._promote_remaining_children()
        self.complete = True

    def _promote_remaining_children(self) -> None:
        """Let unfinished non-waited children continue as independent root flows."""
        if self.context.command_runner is None:
            raise ValueError("Cannot keep parallel children running without an active command runner.")
        for child in self.children:
            handle = child["handle"]
            if child["promoted"] or handle.complete:
                continue
            child["promoted"] = True
            self.context.command_runner.spawn_root_handle(handle)


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
    persistence_runtime: Any | None,
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
    persistence_runtime: Any | None,
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
    persistence_runtime: Any | None,
    *,
    command_name: str,
) -> Any:
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
    persistence_runtime: Any | None,
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
    persistence_runtime: Any | None,
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
    mode = str(follow.get("mode", "")).strip() or "none"
    if mode not in {"none", "entity", "input_target"}:
        raise ValueError(
            f"{command_name} follow.mode must be 'none', 'entity', or 'input_target'."
        )

    offset_x = float(follow.get("offset_x", 0.0))
    offset_y = float(follow.get("offset_y", 0.0))
    normalized: dict[str, Any] = {
        "mode": mode,
        "offset_x": offset_x,
        "offset_y": offset_y,
    }

    if mode == "none":
        if "entity_id" in follow or "action" in follow or "offset_x" in follow or "offset_y" in follow:
            raise ValueError(
                f"{command_name} follow.mode 'none' must not provide entity_id, action, or offsets."
            )
        return normalized

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
        *,
        context: CommandContext | None,
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        entity_id: str,
        field_name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Apply one generic entity field mutation through the shared helper."""
        entity = _require_exact_entity(world, entity_id)
        previous_cell = _occupancy_cell_for(entity)
        persisted_field_name, persisted_value = _apply_entity_field_value(
            entity,
            str(field_name),
            value,
        )
        if persistent:
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
        persistence_runtime: Any | None,
        entity_id: str,
        set_payload: dict[str, Any],
        persistent: bool = False,
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
                if persistent:
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
            if persistent:
                _persist_exact_entity_variable_value(
                    world=world,
                    area=area,
                    persistence_runtime=persistence_runtime,
                    entity_id=entity.entity_id,
                    name=operation_name,
                    value=operation_value,
                )

        if persistent and visuals_changed:
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

    def _step_entity(
        *,
        world: Any,
        movement_system: Any,
        entity_id: str,
        direction: str,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str = "immediate",
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        resolved_id = _require_exact_entity(world, entity_id).entity_id
        moved_entity_ids = movement_system.request_grid_step(
            resolved_id,
            direction,  # type: ignore[arg-type]
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync=grid_sync,  # type: ignore[arg-type]
        )
        if not moved_entity_ids:
            return ImmediateHandle()
        if not wait:
            return ImmediateHandle()
        return MovementCommandHandle(movement_system, moved_entity_ids)

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
        entity = context.world.get_entity(str(entity_id).strip())
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
        context: CommandContext,
        actor: Any,
        runtime_params: dict[str, Any] | None = None,
    ) -> CommandHandle:
        """Dispatch the actor's generic on_blocked hook when it exists."""
        return _dispatch_named_entity_command(
            context=context,
            entity_id=actor.entity_id,
            command_id="on_blocked",
            runtime_params=runtime_params,
            entity_refs={"instigator": actor.entity_id},
            refs_mode="merge",
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
        handles: list[CommandHandle] = []

        if previous_cell is not None:
            for receiver in context.world.get_entities_at(
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
                    entity_refs={"instigator": instigator.entity_id},
                    refs_mode="merge",
                )
                if not handle.complete:
                    handles.append(handle)

        if next_cell is not None:
            for receiver in context.world.get_entities_at(
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
                    entity_refs={"instigator": instigator.entity_id},
                    refs_mode="merge",
                )
                if not handle.complete:
                    handles.append(handle)

        if not handles:
            return ImmediateHandle()
        if len(handles) == 1:
            return handles[0]
        return CompositeCommandHandle(handles)

    def _launch_side_effect_handle(
        context: CommandContext,
        handle: CommandHandle,
    ) -> CommandHandle:
        """Run a side-effect handle in the background when a runner exists."""
        if handle.complete:
            return ImmediateHandle()
        if context.command_runner is None:
            return handle
        context.command_runner.spawn_root_handle(handle)
        return ImmediateHandle()

    def _attempt_standard_push(
        *,
        actor: Any,
        direction: str,
        area: Any,
        collision_system: Any,
        movement_system: Any,
        push_strength: int,
        duration: float | None,
        frames_needed: int | None,
        speed_px_per_second: float | None,
        wait: bool,
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

        moved_entity_ids = movement_system.request_grid_step(
            blocker.entity_id,
            direction,  # type: ignore[arg-type]
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync="immediate",
        )
        if not moved_entity_ids:
            return False, []
        if not wait:
            return True, moved_entity_ids
        return True, moved_entity_ids

    def _move_entity_to_position(
        *,
        world: Any,
        movement_system: Any,
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
        resolved_id = _require_exact_entity(world, entity_id).entity_id
        moved_entity_ids = movement_system.request_move_to_position(
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
        return MovementCommandHandle(movement_system, moved_entity_ids)

    def _move_entity(
        *,
        world: Any,
        movement_system: Any,
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
        resolved_id = _require_exact_entity(world, entity_id).entity_id
        if space not in {"pixel", "grid"}:
            raise ValueError(f"Unknown movement space '{space}'.")
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown movement mode '{mode}'.")

        effective_grid_sync = grid_sync
        if effective_grid_sync is None:
            effective_grid_sync = "on_complete" if space == "grid" else "none"

        if space == "pixel" and mode == "absolute":
            return _move_entity_to_position(
                world=world,
                movement_system=movement_system,
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
            moved_entity_ids = movement_system.request_move_by_offset(
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
            return MovementCommandHandle(movement_system, moved_entity_ids)

        if space == "grid" and mode == "absolute":
            moved_entity_ids = movement_system.request_move_to_grid_position(
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
            return MovementCommandHandle(movement_system, moved_entity_ids)

        moved_entity_ids = movement_system.request_move_by_grid_offset(
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
        return MovementCommandHandle(movement_system, moved_entity_ids)

    def _teleport_entity(
        *,
        world: Any,
        movement_system: Any,
        entity_id: str,
        x: int | float,
        y: int | float,
        space: str = "pixel",
        mode: str = "absolute",
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
        **_: Any,
    ) -> CommandHandle:
        entity = _require_exact_entity(world, entity_id)
        resolved_id = entity.entity_id
        if space not in {"pixel", "grid"}:
            raise ValueError(f"Unknown teleport space '{space}'.")
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown teleport mode '{mode}'.")

        if space == "grid":
            grid_x = int(x) if mode == "absolute" else entity.grid_x + int(x)
            grid_y = int(y) if mode == "absolute" else entity.grid_y + int(y)
            movement_system.teleport_to_grid_position(resolved_id, grid_x, grid_y)
            return ImmediateHandle()

        pixel_x = float(x) if mode == "absolute" else entity.pixel_x + float(x)
        pixel_y = float(y) if mode == "absolute" else entity.pixel_y + float(y)
        movement_system.teleport_to_position(
            resolved_id,
            pixel_x,
            pixel_y,
            target_grid_x=target_grid_x,
            target_grid_y=target_grid_y,
        )
        return ImmediateHandle()

    def _play_exact_animation(
        *,
        world: Any,
        animation_system: Any,
        entity_id: str,
        visual_id: str | None = None,
        frame_sequence: list[int],
        frames_per_sprite_change: int = 1,
        hold_last_frame: bool = True,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        resolved_id = _require_exact_entity(world, entity_id).entity_id
        animation_system.start_frame_animation(
            resolved_id,
            frame_sequence,
            visual_id=visual_id,
            frames_per_sprite_change=frames_per_sprite_change,
            hold_last_frame=hold_last_frame,
        )
        if not wait:
            return ImmediateHandle()
        return AnimationCommandHandle(animation_system, [resolved_id], visual_id=visual_id)

    def _require_entity_space(
        world: Any,
        entity_id: str,
        *,
        expected_space: str,
        command_name: str,
    ) -> Any:
        entity = _require_exact_entity(world, entity_id)
        if entity.space != expected_space:
            raise ValueError(
                f"{command_name} requires entity '{entity.entity_id}' to use space "
                f"'{expected_space}', but it uses '{entity.space}'."
            )
        return entity

    def _set_entity_grid_position(
        *,
        world: Any,
        movement_system: Any,
        entity_id: str,
        x: int,
        y: int,
        mode: str = "absolute",
        **_: Any,
    ) -> CommandHandle:
        entity = _require_entity_space(
            world,
            entity_id,
            expected_space="world",
            command_name="set_entity_grid_position",
        )
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown grid-position mode '{mode}'.")
        target_x = int(x) if mode == "absolute" else entity.grid_x + int(x)
        target_y = int(y) if mode == "absolute" else entity.grid_y + int(y)
        movement_system.set_grid_position(entity.entity_id, target_x, target_y)
        return ImmediateHandle()

    def _set_entity_pixel_position(
        *,
        world: Any,
        movement_system: Any,
        entity_id: str,
        x: int | float,
        y: int | float,
        mode: str = "absolute",
        expected_space: str,
        command_name: str,
        **_: Any,
    ) -> CommandHandle:
        entity = _require_entity_space(
            world,
            entity_id,
            expected_space=expected_space,
            command_name=command_name,
        )
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown {expected_space}-position mode '{mode}'.")
        target_x = float(x) if mode == "absolute" else entity.pixel_x + float(x)
        target_y = float(y) if mode == "absolute" else entity.pixel_y + float(y)
        movement_system.set_pixel_position(entity.entity_id, target_x, target_y)
        return ImmediateHandle()

    def _move_entity_pixel_position(
        *,
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
        **_: Any,
    ) -> CommandHandle:
        entity = _require_entity_space(
            world,
            entity_id,
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
            )
        if not moved_entity_ids or not wait:
            return ImmediateHandle()
        return MovementCommandHandle(movement_system, moved_entity_ids)

    @registry.register("set_entity_grid_position")
    def set_entity_grid_position(
        world: Any,
        movement_system: Any,
        *,
        entity_id: str,
        x: int,
        y: int,
        mode: str = "absolute",
        **_: Any,
    ) -> CommandHandle:
        """Instantly update a world-space entity's logical grid position."""
        return _set_entity_grid_position(
            world=world,
            movement_system=movement_system,
            entity_id=entity_id,
            x=x,
            y=y,
            mode=mode,
        )

    @registry.register("set_entity_world_position")
    def set_entity_world_position(
        world: Any,
        movement_system: Any,
        *,
        entity_id: str,
        x: int | float,
        y: int | float,
        mode: str = "absolute",
        **_: Any,
    ) -> CommandHandle:
        """Instantly update a world-space entity's pixel position."""
        return _set_entity_pixel_position(
            world=world,
            movement_system=movement_system,
            entity_id=entity_id,
            x=x,
            y=y,
            mode=mode,
            expected_space="world",
            command_name="set_entity_world_position",
        )

    @registry.register("set_entity_screen_position")
    def set_entity_screen_position(
        world: Any,
        movement_system: Any,
        *,
        entity_id: str,
        x: int | float,
        y: int | float,
        mode: str = "absolute",
        **_: Any,
    ) -> CommandHandle:
        """Instantly update a screen-space entity's pixel position."""
        return _set_entity_pixel_position(
            world=world,
            movement_system=movement_system,
            entity_id=entity_id,
            x=x,
            y=y,
            mode=mode,
            expected_space="screen",
            command_name="set_entity_screen_position",
        )

    @registry.register("move_entity_world_position")
    def move_entity_world_position(
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
        **_: Any,
    ) -> CommandHandle:
        """Interpolate a world-space entity's pixel position."""
        return _move_entity_pixel_position(
            world=world,
            movement_system=movement_system,
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
        )

    @registry.register("move_entity_screen_position")
    def move_entity_screen_position(
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
        **_: Any,
    ) -> CommandHandle:
        """Interpolate a screen-space entity's pixel position."""
        return _move_entity_pixel_position(
            world=world,
            movement_system=movement_system,
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
        )

    @registry.register("move_in_direction")
    def move_in_direction(
        context: CommandContext,
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
        source_entity_id: str | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Resolve one standard grid step using blocked cells and solid/pushable entities."""
        if movement_system is None:
            raise ValueError("move_in_direction requires an active movement system.")
        if collision_system is None:
            raise ValueError("move_in_direction requires an active collision system.")

        resolved_id = _resolve_entity_id(entity_id, source_entity_id=source_entity_id)
        if not resolved_id:
            logger.warning("move_in_direction: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        actor = context.world.get_entity(resolved_id)
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

        if collision_system.can_move_to(
            target_x,
            target_y,
            ignore_entity_id=actor.entity_id,
        ):
            moved_entity_ids = movement_system.request_grid_step(
                actor.entity_id,
                resolved_direction,  # type: ignore[arg-type]
                duration=duration,
                frames_needed=frames_needed,
                speed_px_per_second=speed_px_per_second,
                grid_sync="immediate",
            )
            if not moved_entity_ids or not wait:
                return ImmediateHandle()
            return MovementCommandHandle(movement_system, moved_entity_ids)

        resolved_push_strength = int(actor.push_strength if push_strength is None else push_strength)
        if resolved_push_strength < 0:
            raise ValueError("move_in_direction push_strength must be zero or positive.")

        if resolved_push_strength > 0 and not area.is_blocked(target_x, target_y):
            pushed, pushed_entity_ids = _attempt_standard_push(
                actor=actor,
                direction=resolved_direction,
                area=area,
                collision_system=collision_system,
                movement_system=movement_system,
                push_strength=resolved_push_strength,
                duration=duration,
                frames_needed=frames_needed,
                speed_px_per_second=speed_px_per_second,
                wait=wait,
            )
            if pushed:
                moved_entity_ids = movement_system.request_grid_step(
                    actor.entity_id,
                    resolved_direction,  # type: ignore[arg-type]
                    duration=duration,
                    frames_needed=frames_needed,
                    speed_px_per_second=speed_px_per_second,
                    grid_sync="immediate",
                )
                combined_entity_ids = list(dict.fromkeys([*pushed_entity_ids, *moved_entity_ids]))
                if not combined_entity_ids or not wait:
                    return ImmediateHandle()
                return MovementCommandHandle(movement_system, combined_entity_ids)

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
        blockers = collision_system.get_blocking_entities(
            target_x,
            target_y,
            ignore_entity_id=actor.entity_id,
        )
        if len(blockers) == 1:
            blocked_runtime_params["blocking_entity_id"] = blockers[0].entity_id
        return _run_on_blocked_if_present(
            context=context,
            actor=actor,
            runtime_params=blocked_runtime_params,
        )

    @registry.register("push_facing")
    def push_facing(
        context: CommandContext,
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
        source_entity_id: str | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Try to push exactly one blocker in the actor's facing direction without moving the actor."""
        if movement_system is None:
            raise ValueError("push_facing requires an active movement system.")
        if collision_system is None:
            raise ValueError("push_facing requires an active collision system.")

        resolved_id = _resolve_entity_id(entity_id, source_entity_id=source_entity_id)
        if not resolved_id:
            logger.warning("push_facing: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        actor = context.world.get_entity(resolved_id)
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
            area=area,
            collision_system=collision_system,
            movement_system=movement_system,
            push_strength=resolved_push_strength,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            wait=wait,
        )
        if pushed:
            if not moved_entity_ids or not wait:
                return ImmediateHandle()
            return MovementCommandHandle(movement_system, moved_entity_ids)

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
        blockers = collision_system.get_blocking_entities(
            actor.grid_x + delta_x,
            actor.grid_y + delta_y,
            ignore_entity_id=actor.entity_id,
        )
        if len(blockers) == 1:
            blocked_runtime_params["blocking_entity_id"] = blockers[0].entity_id
        return _run_on_blocked_if_present(
            context=context,
            actor=actor,
            runtime_params=blocked_runtime_params,
        )

    @registry.register("interact_facing")
    def interact_facing(
        context: CommandContext,
        interaction_system: Any,
        *,
        entity_id: str,
        direction: str | None = None,
        source_entity_id: str | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Resolve the standard facing target and dispatch its normal interact command."""
        if interaction_system is None:
            raise ValueError("interact_facing requires an active interaction system.")

        resolved_id = _resolve_entity_id(entity_id, source_entity_id=source_entity_id)
        if not resolved_id:
            logger.warning("interact_facing: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        actor = context.world.get_entity(resolved_id)
        if actor is None:
            raise KeyError(f"Cannot interact with missing entity '{resolved_id}'.")
        if not actor.present:
            return ImmediateHandle()
        if actor.space != "world":
            raise ValueError("interact_facing only supports world-space entities.")

        resolved_direction = _resolve_standard_direction(actor, direction)
        actor.set_facing_value(resolved_direction)
        target = interaction_system.get_facing_target(actor.entity_id)
        if target is None:
            return ImmediateHandle()
        return _dispatch_named_entity_command(
            context=context,
            entity_id=target.entity_id,
            command_id="interact",
            runtime_params=runtime_params,
            entity_refs={"instigator": actor.entity_id},
            refs_mode="merge",
        )

    @registry.register(
        "open_dialogue_session",
        deferred_params={"dialogue_on_start", "dialogue_on_end", "segment_hooks"},
    )
    def open_dialogue_session(
        context: CommandContext,
        *,
        dialogue_path: str,
        dialogue_on_start: list[dict[str, Any]] | dict[str, Any] | None = None,
        dialogue_on_end: list[dict[str, Any]] | dict[str, Any] | None = None,
        segment_hooks: list[Any] | None = None,
        allow_cancel: bool = False,
        actor_id: str | None = None,
        caller_id: str | None = None,
        ui_preset: str | None = None,
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Open one engine-owned dialogue session using the canonical modal runtime."""
        from dungeon_engine.engine.dialogue_runtime import DialogueSessionWaitHandle

        dialogue_runtime = context.dialogue_runtime
        if dialogue_runtime is None:
            raise ValueError("open_dialogue_session requires an active dialogue runtime.")

        resolved_actor_id = None if actor_id in (None, "") else str(actor_id).strip()
        resolved_caller_id = None if caller_id in (None, "") else str(caller_id).strip()
        if isinstance(entity_refs, dict):
            if resolved_actor_id in (None, ""):
                instigator_id = entity_refs.get("instigator")
                if instigator_id not in (None, ""):
                    resolved_actor_id = str(instigator_id).strip()
            if resolved_caller_id in (None, ""):
                caller_ref_id = entity_refs.get("caller")
                if caller_ref_id not in (None, ""):
                    resolved_caller_id = str(caller_ref_id).strip()
        if resolved_caller_id in (None, "") and source_entity_id not in (None, ""):
            resolved_caller_id = str(source_entity_id).strip()

        session = dialogue_runtime.open_session(
            dialogue_path=str(dialogue_path),
            dialogue_on_start=dialogue_on_start,
            dialogue_on_end=dialogue_on_end,
            segment_hooks=segment_hooks,
            allow_cancel=bool(allow_cancel),
            actor_id=resolved_actor_id,
            caller_id=resolved_caller_id,
            ui_preset_name=None if ui_preset in (None, "") else str(ui_preset).strip(),
        )
        return DialogueSessionWaitHandle(dialogue_runtime, session)

    @registry.register("close_dialogue_session")
    def close_dialogue_session(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Close the currently active engine-owned dialogue session when one exists."""
        dialogue_runtime = context.dialogue_runtime
        if dialogue_runtime is None:
            raise ValueError("close_dialogue_session requires an active dialogue runtime.")
        dialogue_runtime.close_current_session()
        return ImmediateHandle()

    @registry.register("wait_for_move")
    def wait_for_move(
        world: Any,
        movement_system: Any,
        *,
        entity_id: str,
        **_: Any,
    ) -> CommandHandle:
        """Block the command lane until the requested entity stops moving."""
        resolved_id = _require_exact_entity(world, entity_id).entity_id
        if not movement_system.is_entity_moving(resolved_id):
            return ImmediateHandle()
        return MovementCommandHandle(movement_system, [resolved_id])

    @registry.register("play_animation")
    def play_animation(
        world: Any,
        animation_system: Any,
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
            world=world,
            animation_system=animation_system,
            entity_id=entity_id,
            visual_id=visual_id,
            frame_sequence=frame_sequence,
            frames_per_sprite_change=frames_per_sprite_change,
            hold_last_frame=hold_last_frame,
            wait=wait,
        )

    @registry.register("wait_for_animation")
    def wait_for_animation(
        world: Any,
        animation_system: Any,
        *,
        entity_id: str,
        visual_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Block the command lane until the requested entity stops animating."""
        resolved_id = _require_exact_entity(world, entity_id).entity_id
        if not animation_system.is_entity_animating(resolved_id, visual_id=visual_id):
            return ImmediateHandle()
        return AnimationCommandHandle(animation_system, [resolved_id], visual_id=visual_id)

    @registry.register("stop_animation")
    def stop_animation(
        world: Any,
        animation_system: Any,
        *,
        entity_id: str,
        visual_id: str | None = None,
        reset_to_default: bool = False,
        **_: Any,
    ) -> CommandHandle:
        """Stop command-driven animation playback on an entity."""
        resolved_id = _require_exact_entity(world, entity_id).entity_id
        animation_system.stop_animation(
            resolved_id,
            visual_id=visual_id,
            reset_to_default=reset_to_default,
        )
        return ImmediateHandle()

    @registry.register("set_visual_frame")
    def set_visual_frame(
        world: Any,
        *,
        entity_id: str,
        visual_id: str | None = None,
        frame: int,
        **_: Any,
    ) -> CommandHandle:
        """Set the currently displayed visual frame directly."""
        entity = _require_exact_entity(world, entity_id)
        visual = entity.require_visual(visual_id) if visual_id is not None else entity.get_primary_visual()
        if visual is None:
            raise KeyError(f"Entity '{entity.entity_id}' has no visual to set a frame on.")
        visual.current_frame = int(frame)
        return ImmediateHandle()

    @registry.register("set_visual_flip_x")
    def set_visual_flip_x(
        world: Any,
        *,
        entity_id: str,
        visual_id: str | None = None,
        flip_x: bool,
        **_: Any,
    ) -> CommandHandle:
        """Set whether an entity's visual should be mirrored horizontally."""
        entity = _require_exact_entity(world, entity_id)
        visual = entity.require_visual(visual_id) if visual_id is not None else entity.get_primary_visual()
        if visual is None:
            raise KeyError(f"Entity '{entity.entity_id}' has no visual to set flip_x on.")
        visual.flip_x = bool(flip_x)
        return ImmediateHandle()

    @registry.register("play_audio")
    def play_audio(
        audio_player: Any | None,
        *,
        path: str,
        volume: int | float | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Play a one-shot audio asset from the active project's assets."""
        if audio_player is None:
            return ImmediateHandle()
        audio_player.play_audio(str(path), volume=volume)
        return ImmediateHandle()

    @registry.register("set_sound_volume")
    def set_sound_volume(
        audio_player: Any | None,
        *,
        volume: int | float,
        **_: Any,
    ) -> CommandHandle:
        """Set the default sound-effect volume for future one-shot playback."""
        if audio_player is None:
            return ImmediateHandle()
        audio_player.set_sound_volume(float(volume))
        return ImmediateHandle()

    @registry.register("play_music")
    def play_music(
        audio_player: Any | None,
        *,
        path: str,
        loop: bool = True,
        volume: int | float | None = None,
        restart_if_same: bool = False,
        **_: Any,
    ) -> CommandHandle:
        """Start or resume one dedicated background music track."""
        if audio_player is None:
            return ImmediateHandle()
        audio_player.play_music(
            str(path),
            loop=bool(loop),
            volume=None if volume is None else float(volume),
            restart_if_same=bool(restart_if_same),
        )
        return ImmediateHandle()

    @registry.register("stop_music")
    def stop_music(
        audio_player: Any | None,
        *,
        fade_seconds: int | float = 0.0,
        **_: Any,
    ) -> CommandHandle:
        """Stop the current background music track."""
        if audio_player is None:
            return ImmediateHandle()
        audio_player.stop_music(fade_seconds=float(fade_seconds))
        return ImmediateHandle()

    @registry.register("pause_music")
    def pause_music(
        audio_player: Any | None,
        **_: Any,
    ) -> CommandHandle:
        """Pause the current background music track."""
        if audio_player is None:
            return ImmediateHandle()
        audio_player.pause_music()
        return ImmediateHandle()

    @registry.register("resume_music")
    def resume_music(
        audio_player: Any | None,
        **_: Any,
    ) -> CommandHandle:
        """Resume the paused background music track."""
        if audio_player is None:
            return ImmediateHandle()
        audio_player.resume_music()
        return ImmediateHandle()

    @registry.register("set_music_volume")
    def set_music_volume(
        audio_player: Any | None,
        *,
        volume: int | float,
        **_: Any,
    ) -> CommandHandle:
        """Set the dedicated music-channel volume."""
        if audio_player is None:
            return ImmediateHandle()
        audio_player.set_music_volume(float(volume))
        return ImmediateHandle()

    @registry.register("show_screen_image")
    def show_screen_image(
        screen_manager: Any | None,
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
        if screen_manager is None:
            raise ValueError("Cannot show a screen image without a screen manager.")
        screen_manager.show_image(
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
        screen_manager: Any | None,
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
        if screen_manager is None:
            raise ValueError("Cannot show screen text without a screen manager.")
        screen_manager.show_text(
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
        screen_manager: Any | None,
        *,
        element_id: str,
        text: str,
        **_: Any,
    ) -> CommandHandle:
        """Replace the text content of an existing screen-space text element."""
        if screen_manager is None:
            raise ValueError("Cannot set screen text without a screen manager.")
        screen_manager.set_text(str(element_id), str(text))
        return ImmediateHandle()

    @registry.register("remove_screen_element")
    def remove_screen_element(
        screen_manager: Any | None,
        *,
        element_id: str,
        **_: Any,
    ) -> CommandHandle:
        """Remove one screen-space element."""
        if screen_manager is None:
            raise ValueError("Cannot remove a screen element without a screen manager.")
        screen_manager.remove(str(element_id))
        return ImmediateHandle()

    @registry.register("clear_screen_elements")
    def clear_screen_elements(
        screen_manager: Any | None,
        *,
        layer: int | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Clear all screen-space elements, optionally only one layer."""
        if screen_manager is None:
            raise ValueError("Cannot clear screen elements without a screen manager.")
        screen_manager.clear(layer=layer)
        return ImmediateHandle()

    @registry.register("play_screen_animation")
    def play_screen_animation(
        screen_manager: Any | None,
        *,
        element_id: str,
        frame_sequence: list[int],
        ticks_per_frame: int = 1,
        hold_last_frame: bool = True,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Start a one-shot frame animation on an existing screen image."""
        if screen_manager is None:
            raise ValueError("Cannot play a screen animation without a screen manager.")
        screen_manager.start_animation(
            element_id=str(element_id),
            frame_sequence=[int(frame) for frame in frame_sequence],
            ticks_per_frame=int(ticks_per_frame),
            hold_last_frame=bool(hold_last_frame),
        )
        if not wait:
            return ImmediateHandle()
        return ScreenAnimationCommandHandle(screen_manager, str(element_id))

    @registry.register("wait_for_screen_animation")
    def wait_for_screen_animation(
        screen_manager: Any | None,
        *,
        element_id: str,
        **_: Any,
    ) -> CommandHandle:
        """Block until the requested screen-space animation finishes."""
        if screen_manager is None:
            raise ValueError("Cannot wait for a screen animation without a screen manager.")
        if not screen_manager.is_animating(str(element_id)):
            return ImmediateHandle()
        return ScreenAnimationCommandHandle(screen_manager, str(element_id))

    @registry.register("wait_frames")
    def wait_frames(
        *,
        frames: int,
        **_: Any,
    ) -> CommandHandle:
        """Pause the current command lane for a fixed number of simulation ticks."""
        return WaitFramesHandle(int(frames))

    @registry.register("wait_seconds")
    def wait_seconds(
        *,
        seconds: int | float,
        **_: Any,
    ) -> CommandHandle:
        """Pause the current command lane for a fixed amount of elapsed time."""
        return WaitSecondsHandle(float(seconds))

    @registry.register("spawn_flow", deferred_params={"commands"})
    def spawn_flow(
        context: CommandContext,
        *,
        commands: list[dict[str, Any]] | dict[str, Any] | None = None,
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        refs_mode: str | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Start one independent flow and return immediately."""
        if context.command_runner is None:
            raise ValueError("Cannot spawn a flow without an active command runner.")
        normalized_commands = _normalize_command_specs(commands)
        if not normalized_commands:
            return ImmediateHandle()
        handle = SequenceCommandHandle(
            registry,
            context,
            normalized_commands,
            base_params=_build_child_runtime_params(
                runtime_params,
                source_entity_id=source_entity_id,
                entity_refs=entity_refs,
                refs_mode=refs_mode,
            ),
        )
        context.command_runner.spawn_root_handle(handle)
        return ImmediateHandle()

    @registry.register("run_commands", deferred_params={"commands"})
    def run_commands(
        context: CommandContext,
        *,
        commands: list[dict[str, Any]] | dict[str, Any] | None = None,
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        refs_mode: str | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Execute one explicit command-list value in order, waiting for each child."""
        normalized_commands = _normalize_command_specs(commands)
        if not normalized_commands:
            return ImmediateHandle()
        return SequenceCommandHandle(
            registry,
            context,
            normalized_commands,
            base_params=_build_child_runtime_params(
                runtime_params,
                source_entity_id=source_entity_id,
                entity_refs=entity_refs,
                refs_mode=refs_mode,
            ),
        )

    @registry.register("run_parallel", deferred_params={"commands"})
    def run_parallel(
        context: CommandContext,
        *,
        commands: list[dict[str, Any]] | dict[str, Any] | None = None,
        completion: dict[str, Any] | None = None,
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        refs_mode: str | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Start several child commands together with explicit completion semantics."""
        normalized_commands = _normalize_command_specs(commands)
        if not normalized_commands:
            return ImmediateHandle()
        return ParallelCommandHandle(
            registry,
            context,
            command_specs=normalized_commands,
            completion=copy.deepcopy(completion),
            base_params=_build_child_runtime_params(
                runtime_params,
                source_entity_id=source_entity_id,
                entity_refs=entity_refs,
                refs_mode=refs_mode,
            ),
        )

    @registry.register("run_commands_for_collection", deferred_params={"commands"})
    def run_commands_for_collection(
        context: CommandContext,
        *,
        value: Any = None,
        commands: list[dict[str, Any]] | dict[str, Any] | None = None,
        item_param: str = "item",
        index_param: str = "index",
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        refs_mode: str | None = None,
        **runtime_params: Any,
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
            base_params=_build_child_runtime_params(
                runtime_params,
                source_entity_id=source_entity_id,
                entity_refs=entity_refs,
                refs_mode=refs_mode,
            ),
        )

    @registry.register(
        "run_entity_command",
        deferred_params={"dialogue_on_start", "dialogue_on_end", "segment_hooks"},
    )
    def run_entity_command(
        context: CommandContext,
        *,
        entity_id: str,
        command_id: str,
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        refs_mode: str | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Execute a named entity command on a target entity when it is enabled."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
        )
        if not resolved_id:
            logger.warning("run_entity_command: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot run entity command on missing entity '{resolved_id}'.")
        if not entity.present:
            return ImmediateHandle()
        entity_command = entity.get_entity_command(command_id)
        if (
            not entity.has_enabled_entity_command(command_id)
            or entity_command is None
            or not entity_command.commands
        ):
            return ImmediateHandle()

        base_params = _build_child_runtime_params(
            runtime_params,
            source_entity_id=resolved_id,
            entity_refs=entity_refs,
            refs_mode=refs_mode,
        )
        return SequenceCommandHandle(
            registry,
            context,
            entity_command.commands,
            base_params=base_params,
        )

    @registry.register("run_project_command")
    def run_project_command(
        context: CommandContext,
        *,
        command_id: str,
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        refs_mode: str | None = None,
        **command_parameters: Any,
    ) -> CommandHandle:
        """Execute a reusable project-level command definition from the command library."""
        if context.project is None:
            raise ValueError("Cannot run a project command without an active project context.")

        resolved_command_id = str(command_id).strip()
        if not resolved_command_id:
            logger.warning("run_project_command: skipping because command_id resolved to blank.")
            return ImmediateHandle()

        if resolved_command_id in context.project_command_stack:
            stack_preview = " -> ".join([*context.project_command_stack, resolved_command_id])
            raise ValueError(f"Detected recursive project command cycle: {stack_preview}")

        definition = load_project_command_definition(context.project, resolved_command_id)
        instantiated_commands = instantiate_project_command_commands(definition, command_parameters)
        if not instantiated_commands:
            return ImmediateHandle()

        base_params = _build_child_runtime_params(
            command_parameters,
            source_entity_id=source_entity_id,
            entity_refs=entity_refs,
            refs_mode=refs_mode,
        )

        sequence_handle = SequenceCommandHandle(
            registry,
            context,
            instantiated_commands,
            base_params=base_params,
            auto_start=False,
        )
        if sequence_handle.complete:
            return ImmediateHandle()
        return ProjectCommandHandle(context, resolved_command_id, sequence_handle)

    @registry.register("set_entity_command_enabled")
    def set_entity_command_enabled(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        command_id: str,
        enabled: bool,
        persistent: bool = False,
    ) -> CommandHandle:
        """Enable or disable a named entity command on an entity."""
        entity = _require_exact_entity(world, entity_id)
        entity.set_entity_command_enabled(command_id, enabled)
        if persistent:
            _persist_entity_command_enabled(
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity.entity_id,
                command_id=command_id,
                enabled=enabled,
                entity=entity,
            )
        return ImmediateHandle()

    @registry.register("set_entity_commands_enabled")
    def set_entity_commands_enabled(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        enabled: bool,
        persistent: bool = False,
    ) -> CommandHandle:
        """Enable or disable all named entity commands on an entity at once."""
        return _set_exact_entity_field_handle(
            context=None,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
            entity_id=entity_id,
            field_name="entity_commands_enabled",
            value=enabled,
            persistent=persistent,
        )

    @registry.register("set_input_target")
    def set_input_target(
        world: Any,
        *,
        action: str,
        entity_id: str | None = None,
    ) -> CommandHandle:
        """Route one logical input action to a specific entity or clear it."""
        resolved_entity_id = None if entity_id in (None, "") else _require_exact_entity(world, entity_id).entity_id
        world.set_input_target(str(action), resolved_entity_id)
        return ImmediateHandle()

    @registry.register("set_entity_field")
    def set_entity_field(
        context: CommandContext,
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        field_name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Change one supported runtime field on an entity."""
        return _set_exact_entity_field_handle(
            context=context,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
            entity_id=entity_id,
            field_name=field_name,
            value=value,
            persistent=persistent,
        )

    @registry.register("set_entity_fields")
    def set_entity_fields(
        context: CommandContext,
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        set: dict[str, Any],
        persistent: bool = False,
    ) -> CommandHandle:
        """Change several supported runtime fields, variables, and visuals on one entity at once."""
        return _set_exact_entity_fields_handle(
            context=context,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
            entity_id=entity_id,
            set_payload=set,
            persistent=persistent,
        )

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
            _require_exact_entity(world, entity_id).entity_id,
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
        transfer_entity_id: str | None = None,
        transfer_entity_ids: list[str] | None = None,
        camera_follow: dict[str, Any] | None = None,
        source_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Queue a transition into another authored area once the command lane is idle."""
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
            resolved_entity_id = _resolve_entity_id(
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
            follow_spec = _normalize_camera_follow_spec(
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
            follow_spec = _normalize_camera_follow_spec(
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
        follow_spec = _normalize_camera_follow_spec(
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

    @registry.register("set_camera_state")
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
                next_state["follow"] = _normalize_camera_follow_spec(
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
                next_state["bounds"] = _normalize_camera_rect_spec(
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
                next_state["deadzone"] = _normalize_camera_rect_spec(
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
        """Clamp camera movement/follow to one world-space rectangle."""
        if camera is None:
            raise ValueError("Cannot set camera bounds without an active camera.")
        rect = _normalize_camera_rect_spec(
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
        rect = _normalize_camera_rect_spec(
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
            raise ValueError(
                "move_camera space must be 'world_pixel' or 'world_grid'."
            )
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
            raise ValueError(
                "teleport_camera space must be 'world_pixel' or 'world_grid'."
            )
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

    @registry.register("set_visible")
    def set_visible(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        visible: bool,
        persistent: bool = False,
    ) -> CommandHandle:
        """Change whether an entity is rendered and targetable."""
        return _set_exact_entity_field_handle(
            context=None,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
            entity_id=entity_id,
            field_name="visible",
            value=visible,
            persistent=persistent,
        )

    @registry.register("set_present")
    def set_present(
        context: CommandContext,
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        present: bool,
        persistent: bool = False,
    ) -> CommandHandle:
        """Change whether an entity participates in the current scene."""
        return _set_exact_entity_field_handle(
            context=context,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
            entity_id=entity_id,
            field_name="present",
            value=present,
            persistent=persistent,
        )

    @registry.register("set_color")
    def set_color(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        color: list[int],
        persistent: bool = False,
    ) -> CommandHandle:
        """Change an entity's debug-render color."""
        return _set_exact_entity_field_handle(
            context=None,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
            entity_id=entity_id,
            field_name="color",
            value=color,
            persistent=persistent,
        )

    @registry.register("destroy_entity")
    def destroy_entity(
        context: CommandContext,
        world: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        persistent: bool = False,
    ) -> CommandHandle:
        """Destroy an entity instance completely."""
        entity = _require_exact_entity(world, entity_id)
        previous_cell = _occupancy_cell_for(entity)
        if previous_cell is None:
            world.remove_entity(entity.entity_id)
            if persistent and persistence_runtime is not None:
                persistence_runtime.remove_entity(entity.entity_id, entity=entity)
            return ImmediateHandle()

        entity.set_present(False)
        leave_handle = _build_occupancy_transition_handle(
            context=context,
            instigator=entity,
            previous_cell=previous_cell,
            next_cell=None,
        )

        def _finalize_destroy() -> None:
            world.remove_entity(entity.entity_id)
            if persistent and persistence_runtime is not None:
                persistence_runtime.remove_entity(entity.entity_id, entity=entity)

        if leave_handle.complete:
            _finalize_destroy()
            return ImmediateHandle()
        return PostActionCommandHandle(leave_handle, _finalize_destroy)

    @registry.register("spawn_entity")
    def spawn_entity(
        world: Any,
        area: Any,
        project: Any | None,
        persistence_runtime: Any | None,
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
        if world.get_entity(new_entity_id) is not None:
            raise KeyError(f"Cannot spawn duplicate entity '{new_entity_id}'.")

        new_entity = instantiate_entity(
            entity_data,
            area.tile_size,
            project=project,
            source_name=f"spawned entity '{new_entity_id}'",
        )
        world.add_entity(new_entity)
        if persistent and persistence_runtime is not None:
            persistence_runtime.record_spawned_entity(
                new_entity,
                tile_size=area.tile_size,
            )
        return ImmediateHandle()

    @registry.register("set_current_area_var")
    def set_current_area_var(
        world: Any,
        persistence_runtime: Any | None,
        *,
        name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Set one explicit current-area variable to a value."""
        persisted_value = copy.deepcopy(value)
        world.variables[name] = persisted_value
        if persistent:
            _persist_current_area_variable_value(persistence_runtime, name=name, value=persisted_value)
        return ImmediateHandle()

    @registry.register("set_entity_var")
    def set_entity_var(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Set one explicit entity variable to a value."""
        persisted_value = copy.deepcopy(value)
        variables = _require_exact_entity_variables(world, entity_id)
        variables[name] = persisted_value
        if persistent:
            _persist_exact_entity_variable_value(
                world=world,
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity_id,
                name=name,
                value=persisted_value,
            )
        return ImmediateHandle()

    @registry.register("add_current_area_var")
    def add_current_area_var(
        world: Any,
        persistence_runtime: Any | None,
        *,
        name: str,
        amount: int | float = 1,
        persistent: bool = False,
    ) -> CommandHandle:
        """Add an amount to one explicit current-area variable."""
        current_value = world.variables.get(name, 0) + amount
        world.variables[name] = current_value
        if persistent:
            _persist_current_area_variable_value(persistence_runtime, name=name, value=current_value)
        return ImmediateHandle()

    @registry.register("add_entity_var")
    def add_entity_var(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        name: str,
        amount: int | float = 1,
        persistent: bool = False,
    ) -> CommandHandle:
        """Add an amount to one explicit entity variable."""
        variables = _require_exact_entity_variables(world, entity_id)
        current_value = variables.get(name, 0) + amount
        variables[name] = current_value
        if persistent:
            _persist_exact_entity_variable_value(
                world=world,
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity_id,
                name=name,
                value=current_value,
            )
        return ImmediateHandle()

    @registry.register("toggle_current_area_var")
    def toggle_current_area_var(
        world: Any,
        persistence_runtime: Any | None,
        *,
        name: str,
        persistent: bool = False,
    ) -> CommandHandle:
        """Flip one explicit current-area variable between True and False."""
        current_value = world.variables.get(name, False)
        if current_value is None:
            current_value = False
        if not isinstance(current_value, bool):
            raise TypeError(
                "toggle_current_area_var requires boolean state "
                f"for '{name}', got {type(current_value).__name__}."
            )
        next_value = not current_value
        world.variables[name] = next_value
        if persistent:
            _persist_current_area_variable_value(persistence_runtime, name=name, value=next_value)
        return ImmediateHandle()

    @registry.register("toggle_entity_var")
    def toggle_entity_var(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        name: str,
        persistent: bool = False,
    ) -> CommandHandle:
        """Flip one explicit entity variable between True and False."""
        variables = _require_exact_entity_variables(world, entity_id)
        current_value = variables.get(name, False)
        if current_value is None:
            current_value = False
        if not isinstance(current_value, bool):
            raise TypeError(
                f"toggle_entity_var requires boolean state for '{name}', got {type(current_value).__name__}."
            )
        next_value = not current_value
        variables[name] = next_value
        if persistent:
            _persist_exact_entity_variable_value(
                world=world,
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity_id,
                name=name,
                value=next_value,
            )
        return ImmediateHandle()

    @registry.register("set_current_area_var_length")
    def set_current_area_var_length(
        world: Any,
        persistence_runtime: Any | None,
        *,
        name: str,
        value: Any = None,
        persistent: bool = False,
    ) -> CommandHandle:
        """Store the length of a value into one explicit current-area variable."""
        if value is None:
            length_value = 0
        else:
            try:
                length_value = len(value)
            except TypeError as exc:
                raise TypeError("set_current_area_var_length requires a sized value or null.") from exc
        world.variables[name] = length_value
        if persistent:
            _persist_current_area_variable_value(persistence_runtime, name=name, value=length_value)
        return ImmediateHandle()

    @registry.register("set_entity_var_length")
    def set_entity_var_length(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
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
        variables = _require_exact_entity_variables(world, entity_id)
        variables[name] = length_value
        if persistent:
            _persist_exact_entity_variable_value(
                world=world,
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity_id,
                name=name,
                value=length_value,
            )
        return ImmediateHandle()

    @registry.register("append_current_area_var")
    def append_current_area_var(
        world: Any,
        persistence_runtime: Any | None,
        *,
        name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Append one item to one explicit current-area list variable."""
        current_value = world.variables.get(name)
        if current_value is None:
            current_items: list[Any] = []
        elif isinstance(current_value, list):
            current_items = [copy.deepcopy(item) for item in current_value]
        else:
            raise TypeError(
                "append_current_area_var requires the target variable to be a list or null."
            )
        current_items.append(copy.deepcopy(value))
        world.variables[name] = current_items
        if persistent:
            _persist_current_area_variable_value(persistence_runtime, name=name, value=current_items)
        return ImmediateHandle()

    @registry.register("append_entity_var")
    def append_entity_var(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Append one item to one explicit entity list variable."""
        variables = _require_exact_entity_variables(world, entity_id)
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
                world=world,
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity_id,
                name=name,
                value=current_items,
            )
        return ImmediateHandle()

    @registry.register("pop_current_area_var")
    def pop_current_area_var(
        world: Any,
        persistence_runtime: Any | None,
        *,
        name: str,
        store_var: str | None = None,
        default: Any = None,
        persistent: bool = False,
    ) -> CommandHandle:
        """Pop the last item from one explicit current-area list variable."""
        current_value = world.variables.get(name)
        if current_value is None:
            current_items: list[Any] = []
        elif isinstance(current_value, list):
            current_items = [copy.deepcopy(item) for item in current_value]
        else:
            raise TypeError("pop_current_area_var requires the target variable to be a list or null.")

        popped_value = copy.deepcopy(default)
        if current_items:
            popped_value = current_items.pop()
        world.variables[name] = current_items
        if store_var:
            world.variables[store_var] = copy.deepcopy(popped_value)

        if persistent:
            _persist_current_area_variable_value(persistence_runtime, name=name, value=current_items)
            if store_var:
                _persist_current_area_variable_value(persistence_runtime, name=store_var, value=popped_value)
        return ImmediateHandle()

    @registry.register("pop_entity_var")
    def pop_entity_var(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        name: str,
        store_var: str | None = None,
        default: Any = None,
        persistent: bool = False,
    ) -> CommandHandle:
        """Pop the last item from one explicit entity list variable."""
        variables = _require_exact_entity_variables(world, entity_id)
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
                world=world,
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity_id,
                name=name,
                value=current_items,
            )
            if store_var:
                _persist_exact_entity_variable_value(
                    world=world,
                    area=area,
                    persistence_runtime=persistence_runtime,
                    entity_id=entity_id,
                    name=store_var,
                    value=popped_value,
                )
        return ImmediateHandle()

    @registry.register("if", deferred_params={"then", "else"})
    def if_command(
        context: CommandContext,
        *,
        left: Any = None,
        op: str = "eq",
        right: Any = None,
        then: list[dict[str, Any]] | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Branch using one small structured comparison between two resolved values."""
        comparator = _COMPARE_OPS.get(op)
        if comparator is None:
            raise ValueError(f"Unknown comparison operator '{op}'.")
        return _branch_with_runtime_context(
            registry,
            context,
            condition_met=comparator(left, right),
            then=then,
            else_branch=runtime_params.get("else"),
            runtime_params=runtime_params,
            excluded_param_names={"left", "op", "right", "then", "else"},
        )

    @registry.register("set_area_var")
    def set_area_var(
        context: CommandContext,
        world: Any,
        persistence_runtime: Any | None,
        *,
        area_id: str,
        name: str,
        value: Any,
    ) -> CommandHandle:
        """Persist one area-level variable override for an explicitly chosen area."""
        runtime = _require_cross_area_persistence_runtime(
            persistence_runtime,
            command_name="set_area_var",
        )
        resolved_area_id = _require_area_reference(
            context.project,
            area_id,
            command_name="set_area_var",
        )
        persisted_value = copy.deepcopy(value)
        runtime.set_area_variable(resolved_area_id, name, persisted_value)
        if context.area is not None and context.area.area_id == resolved_area_id:
            world.variables[name] = copy.deepcopy(persisted_value)
        return ImmediateHandle()

    @registry.register("set_area_entity_var")
    def set_area_entity_var(
        context: CommandContext,
        world: Any,
        persistence_runtime: Any | None,
        *,
        area_id: str,
        entity_id: str,
        name: str,
        value: Any,
    ) -> CommandHandle:
        """Persist one variable override for an authored area entity in an explicit area."""
        runtime = _require_cross_area_persistence_runtime(
            persistence_runtime,
            command_name="set_area_entity_var",
        )
        resolved_area_id = _require_area_reference(
            context.project,
            area_id,
            command_name="set_area_entity_var",
        )
        resolved_entity_id = str(entity_id).strip()
        if not resolved_entity_id:
            raise ValueError("set_area_entity_var requires a non-empty entity_id.")
        live_entity = None
        if context.area is not None and context.area.area_id == resolved_area_id:
            live_entity = world.area_entities.get(resolved_entity_id)
        if live_entity is None:
            _resolve_authored_area_entity_snapshot(
                project=context.project,
                area_id=resolved_area_id,
                entity_id=resolved_entity_id,
                asset_manager=context.asset_manager,
            )
        persisted_value = copy.deepcopy(value)
        runtime.set_area_entity_variable(
            resolved_area_id,
            resolved_entity_id,
            name,
            persisted_value,
        )
        if live_entity is not None:
            live_entity.variables[name] = copy.deepcopy(persisted_value)
        return ImmediateHandle()

    @registry.register("set_area_entity_field")
    def set_area_entity_field(
        context: CommandContext,
        world: Any,
        persistence_runtime: Any | None,
        *,
        area_id: str,
        entity_id: str,
        field_name: str,
        value: Any,
    ) -> CommandHandle:
        """Persist one field override for an authored area entity in an explicit area."""
        runtime = _require_cross_area_persistence_runtime(
            persistence_runtime,
            command_name="set_area_entity_field",
        )
        resolved_area_id = _require_area_reference(
            context.project,
            area_id,
            command_name="set_area_entity_field",
        )
        resolved_entity_id = str(entity_id).strip()
        if not resolved_entity_id:
            raise ValueError("set_area_entity_field requires a non-empty entity_id.")

        live_entity = None
        if context.area is not None and context.area.area_id == resolved_area_id:
            live_entity = world.area_entities.get(resolved_entity_id)

        validation_entity = live_entity
        if validation_entity is None:
            validation_entity = _resolve_authored_area_entity_snapshot(
                project=context.project,
                area_id=resolved_area_id,
                entity_id=resolved_entity_id,
                asset_manager=context.asset_manager,
            )

        mutation = _normalize_entity_field_mutation(validation_entity, field_name, value)
        if live_entity is not None:
            persisted_field_name, persisted_value = _apply_normalized_entity_field_mutation(
                live_entity,
                mutation,
            )
        else:
            persisted_field_name, persisted_value = _apply_normalized_entity_field_mutation(
                copy.deepcopy(validation_entity),
                mutation,
            )

        runtime.set_area_entity_field(
            resolved_area_id,
            resolved_entity_id,
            persisted_field_name,
            persisted_value,
        )
        return ImmediateHandle()

    @registry.register("reset_transient_state")
    def reset_transient_state(
        persistence_runtime: Any | None,
        *,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        apply: str = "immediate",
        **_: Any,
    ) -> CommandHandle:
        """Reset the current room against authored data plus persistent overrides."""
        if persistence_runtime is None:
            return ImmediateHandle()
        persistence_runtime.request_reset(
            kind="transient",
            apply=apply,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
        )
        return ImmediateHandle()

    @registry.register("reset_persistent_state")
    def reset_persistent_state(
        persistence_runtime: Any | None,
        *,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        apply: str = "immediate",
        **_: Any,
    ) -> CommandHandle:
        """Clear persistent overrides for the current room or matching tagged entities."""
        if persistence_runtime is None:
            return ImmediateHandle()
        persistence_runtime.request_reset(
            kind="persistent",
            apply=apply,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
        )
        return ImmediateHandle()
