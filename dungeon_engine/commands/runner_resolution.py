"""Runtime token and command-spec resolution helpers for the command runner."""

from __future__ import annotations

import copy
from typing import Any

from dungeon_engine import config
from dungeon_engine.commands.runner_query_values import (
    resolve_area_entity_ref_value,
    resolve_cell_flags_at_value,
    resolve_current_area_var_value,
    resolve_entities_at_value,
    resolve_entities_query_value,
    resolve_entity_at_value,
    resolve_entity_query_value,
    resolve_entity_ref_value,
    resolve_entity_var_value,
    resolve_inventory_has_item_value,
    resolve_inventory_item_count_value,
)
from dungeon_engine.commands.runner_value_utils import (
    build_text_window,
    extract_collection_item,
    load_json_file,
    lookup_nested_value,
    resolve_add_value,
    resolve_and_value,
    resolve_any_in_collection_value,
    resolve_divide_value,
    resolve_find_in_collection_value,
    resolve_boolean_not_value,
    resolve_join_text_value,
    resolve_length_value,
    resolve_json_file_path,
    resolve_multiply_value,
    resolve_not_value,
    resolve_or_value,
    resolve_random_choice_value,
    resolve_random_int_value,
    resolve_slice_collection_value,
    resolve_subtract_value,
    resolve_wrap_index_value,
)


_VALUE_SOURCE_NAMES = {
    "$json_file",
    "$wrapped_lines",
    "$text_window",
    "$entity_ref",
    "$area_entity_ref",
    "$entity_var",
    "$current_area_var",
    "$inventory_item_count",
    "$inventory_has_item",
    "$cell_flags_at",
    "$entities_at",
    "$entity_at",
    "$entities_query",
    "$entity_query",
    "$collection_item",
    "$add",
    "$subtract",
    "$multiply",
    "$divide",
    "$join_text",
    "$slice_collection",
    "$wrap_index",
    "$and",
    "$or",
    "$not",
    "$boolean_not",
    "$length",
    "$random_int",
    "$random_choice",
    "$find_in_collection",
    "$any_in_collection",
}


def _active_text_renderer(context: Any) -> Any:
    """Return the active text renderer for runtime value resolution."""
    services = getattr(context, "services", None)
    ui_services = None if services is None else getattr(services, "ui", None)
    return None if ui_services is None else ui_services.text_renderer


def _active_camera(context: Any) -> Any:
    """Return the active camera for runtime value resolution."""
    services = getattr(context, "services", None)
    ui_services = None if services is None else getattr(services, "ui", None)
    return None if ui_services is None else ui_services.camera


def _active_area(context: Any) -> Any:
    """Return the active area for runtime value resolution."""
    services = getattr(context, "services", None)
    world_services = None if services is None else getattr(services, "world", None)
    return None if world_services is None else world_services.area


def _active_world(context: Any) -> Any:
    """Return the active world for runtime value resolution."""
    services = getattr(context, "services", None)
    world_services = None if services is None else getattr(services, "world", None)
    return None if world_services is None else world_services.world


def resolve_runtime_value_source(
    source_name: str,
    source_value: Any,
    context: Any,
    runtime_params: dict[str, Any],
) -> Any:
    """Resolve one structured value source before primitive execution."""
    resolved_source = resolve_runtime_values(source_value, context, runtime_params)

    if source_name == "$json_file":
        if resolved_source in (None, ""):
            raise ValueError("JSON file value source requires a non-empty path.")
        return load_json_file(
            context,
            resolve_json_file_path(context, str(resolved_source)),
        )

    if source_name == "$wrapped_lines":
        text_renderer = _active_text_renderer(context)
        if text_renderer is None:
            raise ValueError("Cannot wrap text without an active text renderer.")
        if not isinstance(resolved_source, dict):
            raise TypeError("$wrapped_lines value source requires a JSON object.")
        return text_renderer.wrap_lines(
            "" if resolved_source.get("text") is None else str(resolved_source.get("text")),
            int(resolved_source.get("max_width", 0)),
            font_id=str(resolved_source.get("font_id", config.DEFAULT_UI_FONT_ID)),
        )

    if source_name == "$text_window":
        if not isinstance(resolved_source, dict):
            raise TypeError("$text_window value source requires a JSON object.")
        return build_text_window(
            resolved_source.get("lines"),
            start=int(resolved_source.get("start", 0)),
            max_lines=int(resolved_source.get("max_lines", 1)),
            separator=str(resolved_source.get("separator", "\n")),
        )

    if source_name == "$entity_ref":
        return resolve_entity_ref_value(context, resolved_source)

    if source_name == "$area_entity_ref":
        return resolve_area_entity_ref_value(context, resolved_source)

    if source_name == "$entity_var":
        return resolve_entity_var_value(context, resolved_source)

    if source_name == "$current_area_var":
        return resolve_current_area_var_value(context, resolved_source)

    if source_name == "$inventory_item_count":
        return resolve_inventory_item_count_value(context, resolved_source)

    if source_name == "$inventory_has_item":
        return resolve_inventory_has_item_value(context, resolved_source)

    if source_name == "$add":
        return resolve_add_value(resolved_source)

    if source_name == "$subtract":
        return resolve_subtract_value(resolved_source)

    if source_name == "$multiply":
        return resolve_multiply_value(resolved_source)

    if source_name == "$divide":
        return resolve_divide_value(resolved_source)

    if source_name == "$join_text":
        return resolve_join_text_value(resolved_source)

    if source_name == "$slice_collection":
        return resolve_slice_collection_value(resolved_source)

    if source_name == "$wrap_index":
        return resolve_wrap_index_value(resolved_source)

    if source_name == "$and":
        return resolve_and_value(resolved_source)

    if source_name == "$or":
        return resolve_or_value(resolved_source)

    if source_name == "$not":
        return resolve_not_value(resolved_source)

    if source_name == "$boolean_not":
        return resolve_boolean_not_value(resolved_source)

    if source_name == "$length":
        return resolve_length_value(resolved_source)

    if source_name == "$random_int":
        return resolve_random_int_value(context, resolved_source)

    if source_name == "$random_choice":
        return resolve_random_choice_value(context, resolved_source)

    if source_name == "$entities_at":
        return resolve_entities_at_value(context, resolved_source)

    if source_name == "$entity_at":
        return resolve_entity_at_value(context, resolved_source)

    if source_name == "$entities_query":
        return resolve_entities_query_value(context, resolved_source)

    if source_name == "$entity_query":
        return resolve_entity_query_value(context, resolved_source)

    if source_name == "$cell_flags_at":
        return resolve_cell_flags_at_value(context, resolved_source)

    if source_name == "$collection_item":
        if not isinstance(resolved_source, dict):
            raise TypeError("$collection_item value source requires a JSON object.")
        return extract_collection_item(
            resolved_source.get("value"),
            index=resolved_source.get("index"),
            key=resolved_source.get("key"),
            default=resolved_source.get("default"),
        )

    if source_name == "$find_in_collection":
        return resolve_find_in_collection_value(resolved_source)

    if source_name == "$any_in_collection":
        return resolve_any_in_collection_value(resolved_source)

    raise KeyError(f"Unknown value source '{source_name}'.")


def resolve_runtime_token(
    token: str,
    context: Any,
    runtime_params: dict[str, Any],
) -> Any:
    """Resolve a $token against runtime params, engine state, or entity variables."""
    if token.startswith("half:"):
        base_value = resolve_runtime_token(token[5:], context, runtime_params)
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

    parts = [part for part in token.split(".") if part]
    if not parts:
        raise KeyError("Empty runtime token.")

    head, tail = parts[0], parts[1:]
    if head in runtime_params:
        return copy.deepcopy(lookup_nested_value(runtime_params[head], tail))

    if head == "project":
        if context.project is None:
            raise KeyError("No active project context for $project lookup.")
        return copy.deepcopy(context.project.resolve_shared_variable(tail))

    if head == "camera":
        camera = _active_camera(context)
        if camera is None:
            raise KeyError("No active camera context for $camera lookup.")
        camera_state = camera.to_state_dict()
        camera_state.setdefault("x", None)
        camera_state.setdefault("y", None)
        camera_state.setdefault(
            "follow",
            {
                "mode": "none",
                "offset_x": 0.0,
                "offset_y": 0.0,
            },
        )
        camera_state.setdefault("bounds", None)
        camera_state.setdefault("deadzone", None)
        camera_state["has_bounds"] = camera_state.get("bounds") is not None
        camera_state["has_deadzone"] = camera_state.get("deadzone") is not None
        if not tail:
            return copy.deepcopy(camera_state)
        return copy.deepcopy(lookup_nested_value(camera_state, tail))

    if head == "area":
        area = _active_area(context)
        if area is None:
            raise KeyError("No active area context for $area lookup.")
        area_state = {
            "area_id": area.area_id,
            "tile_size": area.tile_size,
            "width": area.width,
            "height": area.height,
            "pixel_width": area.pixel_width,
            "pixel_height": area.pixel_height,
            "camera": copy.deepcopy(area.camera_defaults),
        }
        if not tail:
            return copy.deepcopy(area_state)
        return copy.deepcopy(lookup_nested_value(area_state, tail))

    if head == "current_area":
        world = _active_world(context)
        if world is None:
            raise KeyError("No active world context for $current_area lookup.")
        return copy.deepcopy(lookup_nested_value(world.variables, tail))

    if head == "self":
        entity_id = runtime_params.get("source_entity_id")
        if not entity_id:
            raise KeyError(f"Token '${token}' requires a source entity context.")
        world = _active_world(context)
        if world is None:
            raise KeyError(f"Token '${token}' requires an active world context.")
        entity = world.get_entity(str(entity_id))
        if entity is None:
            raise KeyError(f"Token '${token}' references missing source entity '{entity_id}'.")
        return copy.deepcopy(lookup_nested_value(entity.variables, tail))

    if head == "ref_ids":
        if len(parts) != 2:
            raise KeyError(f"Token '${token}' only supports the form '$ref_ids.<name>'.")
        entity_refs = runtime_params.get("entity_refs")
        if not isinstance(entity_refs, dict):
            raise KeyError(f"Token '${token}' requires an entity_refs context.")
        ref_name = parts[1]
        entity_id = entity_refs.get(ref_name)
        if not entity_id:
            raise KeyError(f"Token '${token}' references missing entity ref '{ref_name}'.")
        return str(entity_id)

    if head == "refs":
        if len(parts) < 2:
            raise KeyError(f"Token '${token}' requires a ref name after '$refs'.")
        entity_refs = runtime_params.get("entity_refs")
        if not isinstance(entity_refs, dict):
            raise KeyError(f"Token '${token}' requires an entity_refs context.")
        ref_name = parts[1]
        entity_id = entity_refs.get(ref_name)
        if not entity_id:
            raise KeyError(f"Token '${token}' references missing entity ref '{ref_name}'.")
        world = _active_world(context)
        if world is None:
            raise KeyError(f"Token '${token}' requires an active world context.")
        entity = world.get_entity(str(entity_id))
        if entity is None:
            raise KeyError(f"Token '${token}' references missing entity '{entity_id}'.")
        return copy.deepcopy(lookup_nested_value(entity.variables, parts[2:]))

    raise KeyError(f"Unknown runtime token '${token}'.")


def resolve_runtime_values(
    value: Any,
    context: Any,
    runtime_params: dict[str, Any],
) -> Any:
    """Resolve $tokens recursively inside a command spec before execution."""
    if isinstance(value, dict):
        if len(value) == 1:
            source_name, source_value = next(iter(value.items()))
            if isinstance(source_name, str):
                if source_name in _VALUE_SOURCE_NAMES:
                    return resolve_runtime_value_source(
                        source_name,
                        source_value,
                        context,
                        runtime_params,
                    )
                if source_name.startswith("$"):
                    raise KeyError(f"Unknown value source '{source_name}'.")
        return {
            key: resolve_runtime_values(item, context, runtime_params)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            resolve_runtime_values(item, context, runtime_params)
            for item in value
        ]

    if isinstance(value, str):
        token = None
        if value.startswith("${") and value.endswith("}"):
            token = value[2:-1]
        elif value.startswith("$"):
            token = value[1:]
        if token is not None:
            return resolve_runtime_token(token, context, runtime_params)

    return value


def resolve_deferred_runtime_value(
    value: Any,
    context: Any,
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
            return resolve_runtime_token(token, context, runtime_params)
    return copy.deepcopy(value)


def resolve_run_project_command_spec(
    raw_spec: dict[str, Any],
    context: Any,
    inherited_params: dict[str, Any],
) -> dict[str, Any]:
    """Resolve one run_project_command spec while honoring project-level deferred params."""
    resolved_command_id = resolve_runtime_values(raw_spec.get("command_id"), context, inherited_params)
    deferred_keys: set[str] = set()
    if context.project is not None and isinstance(resolved_command_id, str) and resolved_command_id.strip():
        try:
            from dungeon_engine.commands.library import load_project_command_definition

            definition = load_project_command_definition(context.project, resolved_command_id)
            deferred_keys = set(definition.deferred_param_shapes)
        except Exception:
            deferred_keys = set()

    resolved_spec: dict[str, Any] = {}
    for key, value in raw_spec.items():
        if key == "command_id":
            resolved_spec[key] = resolved_command_id
        elif key in deferred_keys:
            resolved_spec[key] = resolve_deferred_runtime_value(value, context, inherited_params)
        else:
            resolved_spec[key] = resolve_runtime_values(value, context, inherited_params)
    return resolved_spec


def dynamic_deferred_keys_for_spec(command_name: str, raw_spec: dict[str, Any]) -> set[str]:
    """Return spec-local deferred params for commands that opt into raw payload storage."""
    value_mode = str(raw_spec.get("value_mode", "")).strip().lower()
    if value_mode != "raw":
        return set()
    if command_name in {
        "set_entity_var",
        "append_entity_var",
        "set_current_area_var",
        "append_current_area_var",
    }:
        return {"value"}
    return set()
