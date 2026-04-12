"""Entity, area, and world-query value helpers for the command runner."""

from __future__ import annotations

import copy
from typing import Any

from dungeon_engine.commands.context_types import PersistenceRuntimeLike

from dungeon_engine.commands.runner_value_utils import (
    extract_collection_item,
    lookup_nested_value,
)
from dungeon_engine.inventory import inventory_has_item, inventory_item_count, serialize_inventory_state
from dungeon_engine.world.area import Area
from dungeon_engine.world.loader import load_area
from dungeon_engine.world.persistence_data import get_persistent_area_state
from dungeon_engine.world.world import World


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
    "facing",
    "solid",
    "pushable",
    "weight",
    "push_strength",
    "collision_push_strength",
    "interactable",
    "interaction_priority",
    "entity_commands_enabled",
    "inventory",
    "render_order",
    "y_sort",
    "sort_y_offset",
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
_ENTITY_QUERY_WHERE_BOOLEAN_FIELDS = (
    "present",
    "visible",
    "solid",
    "pushable",
    "interactable",
    "entity_commands_enabled",
)
_ENTITY_QUERY_WHERE_STRING_FIELDS = ("kind", "space", "scope")
_ENTITY_QUERY_WHERE_LIST_FIELDS = ("kinds", "tags_any", "tags_all")
_ENTITY_QUERY_ALLOWED_SPACES = ("world", "screen")
_ENTITY_QUERY_ALLOWED_SCOPES = ("area", "global")


def _active_world(context: Any) -> World:
    """Return the active runtime world for value-source resolution."""
    services = getattr(context, "services", None)
    world_services = None if services is None else getattr(services, "world", None)
    world = None if world_services is None else world_services.world
    if world is None:
        raise ValueError("Value-source resolution requires an active world service.")
    return world


def _active_area(context: Any) -> Area:
    """Return the active runtime area for value-source resolution."""
    services = getattr(context, "services", None)
    world_services = None if services is None else getattr(services, "world", None)
    area = None if world_services is None else world_services.area
    if area is None:
        raise ValueError("Value-source resolution requires an active area service.")
    return area


def _active_persistence_runtime(context: Any) -> PersistenceRuntimeLike | None:
    """Return the active persistence runtime when one is wired."""
    services = getattr(context, "services", None)
    persistence_services = None if services is None else getattr(services, "persistence", None)
    if persistence_services is None:
        return None
    return persistence_services.persistence_runtime


def _serialize_entity_fields(entity: Any, *, fields: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """Return a small plain-data object containing only the requested entity fields."""
    data: dict[str, Any] = {}
    for field_name in fields:
        if field_name == "tags":
            data[field_name] = list(entity.tags)
            continue
        if field_name == "inventory":
            data[field_name] = serialize_inventory_state(entity.inventory)
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
            "'scope', 'present', 'visible', 'solid', 'pushable', "
            "'interactable', 'entity_commands_enabled', 'push_strength', "
            "'collision_push_strength'."
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
    if "solid" in where and entity.is_effectively_solid() is not where["solid"]:
        return False
    if "pushable" in where and entity.is_effectively_pushable() is not where["pushable"]:
        return False
    if "interactable" in where and entity.is_effectively_interactable() is not where["interactable"]:
        return False
    if (
        "entity_commands_enabled" in where
        and entity.entity_commands_enabled is not where["entity_commands_enabled"]
    ):
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


def load_area_owned_snapshot(
    *,
    project: Any,
    area_id: str,
    persistence_runtime: PersistenceRuntimeLike | None = None,
    asset_manager: Any | None = None,
    include_persistent: bool = True,
) -> tuple[Area, World]:
    """Load one area-owned snapshot without layering globals or travelers on top."""
    if project is None:
        raise ValueError("Area-targeted queries require an active project context.")
    resolved_area_id = str(area_id).strip()
    if not resolved_area_id:
        raise ValueError("Area-targeted queries require a non-empty area_id.")
    area_path = project.resolve_area_reference(resolved_area_id)
    if area_path is None:
        raise KeyError(f"Unknown area '{resolved_area_id}'.")

    persistent_area_state = None
    if include_persistent and persistence_runtime is not None:
        persistent_area_state = get_persistent_area_state(
            persistence_runtime.save_data,
            resolved_area_id,
        )

    return load_area(
        area_path,
        project=project,
        asset_manager=asset_manager,
        persistent_area_state=copy.deepcopy(persistent_area_state)
        if persistent_area_state is not None
        else None,
    )


def resolve_entity_ref_value(context: Any, resolved_source: Any) -> dict[str, Any] | None:
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
    entity = _active_world(context).get_entity(entity_id)
    if entity is None:
        return default
    return _serialize_selected_entity(entity, select=select)


def resolve_area_entity_ref_value(context: Any, resolved_source: Any) -> dict[str, Any] | None:
    """Return one plain-data entity reference for an explicitly chosen area/entity pair."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$area_entity_ref value source requires a JSON object.")
    area_id = str(resolved_source.get("area_id", "")).strip()
    if not area_id:
        raise ValueError("$area_entity_ref value source requires a non-empty area_id.")
    entity_id = str(resolved_source.get("entity_id", "")).strip()
    if not entity_id:
        raise ValueError("$area_entity_ref value source requires a non-empty entity_id.")
    default = copy.deepcopy(resolved_source.get("default"))
    if "select" not in resolved_source:
        raise ValueError("$area_entity_ref value source requires a select object.")
    select = _resolve_entity_select_spec(
        resolved_source.get("select"),
        source_name="$area_entity_ref",
    )
    _, snapshot_world = load_area_owned_snapshot(
        project=context.project,
        area_id=area_id,
        persistence_runtime=_active_persistence_runtime(context),
        asset_manager=context.asset_manager,
        include_persistent=True,
    )
    entity = snapshot_world.area_entities.get(entity_id)
    if entity is None:
        return default
    return _serialize_selected_entity(entity, select=select)


def resolve_entity_var_value(context: Any, resolved_source: Any) -> Any:
    """Return one variable value from an explicitly chosen live entity."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$entity_var value source requires a JSON object.")
    entity_id = str(resolved_source.get("entity_id", "")).strip()
    if not entity_id:
        raise ValueError("$entity_var value source requires a non-empty entity_id.")
    name = str(resolved_source.get("name", "")).strip()
    if not name:
        raise ValueError("$entity_var value source requires a non-empty name.")
    entity = _active_world(context).get_entity(entity_id)
    if entity is None:
        return copy.deepcopy(resolved_source.get("default"))
    if "default" in resolved_source:
        return copy.deepcopy(entity.variables.get(name, resolved_source.get("default")))
    return copy.deepcopy(entity.variables.get(name))


def resolve_current_area_var_value(context: Any, resolved_source: Any) -> Any:
    """Return one current-area variable value with optional defaulting."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$current_area_var value source requires a JSON object.")
    name = str(resolved_source.get("name", "")).strip()
    if not name:
        raise ValueError("$current_area_var value source requires a non-empty name.")
    if "default" in resolved_source:
        return copy.deepcopy(_active_world(context).variables.get(name, resolved_source.get("default")))
    return copy.deepcopy(_active_world(context).variables.get(name))


def resolve_inventory_item_count_value(context: Any, resolved_source: Any) -> int:
    """Return one item-count lookup from an explicitly chosen live entity inventory."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$inventory_item_count value source requires a JSON object.")
    entity_id = str(resolved_source.get("entity_id", "")).strip()
    if not entity_id:
        raise ValueError("$inventory_item_count value source requires a non-empty entity_id.")
    item_id = str(resolved_source.get("item_id", "")).strip()
    if not item_id:
        raise ValueError("$inventory_item_count value source requires a non-empty item_id.")
    entity = _active_world(context).get_entity(entity_id)
    if entity is None:
        return 0
    return int(inventory_item_count(entity.inventory, item_id))


def resolve_inventory_has_item_value(context: Any, resolved_source: Any) -> bool:
    """Return True when an explicitly chosen live entity inventory has enough of one item."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$inventory_has_item value source requires a JSON object.")
    entity_id = str(resolved_source.get("entity_id", "")).strip()
    if not entity_id:
        raise ValueError("$inventory_has_item value source requires a non-empty entity_id.")
    item_id = str(resolved_source.get("item_id", "")).strip()
    if not item_id:
        raise ValueError("$inventory_has_item value source requires a non-empty item_id.")
    quantity = int(resolved_source.get("quantity", 1))
    if quantity <= 0:
        raise ValueError("$inventory_has_item value source quantity must be positive.")
    entity = _active_world(context).get_entity(entity_id)
    if entity is None:
        return False
    return bool(inventory_has_item(entity.inventory, item_id, quantity=quantity))


def resolve_entities_at_value(context: Any, resolved_source: Any) -> list[dict[str, Any]]:
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
    entities = _active_world(context).get_entities_at(
        int(raw_x),
        int(raw_y),
        exclude_entity_id=None if exclude_entity_id in (None, "") else str(exclude_entity_id),
        include_hidden=include_hidden,
        include_absent=include_absent,
    )
    entities = [entity for entity in entities if _entity_matches_where(entity, where)]
    return [_serialize_selected_entity(entity, select=select) for entity in entities]


def resolve_entity_at_value(context: Any, resolved_source: Any) -> Any:
    """Return one plain-data entity ref selected from a tile query."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$entity_at value source requires a JSON object.")
    entities = resolve_entities_at_value(context, resolved_source)
    return extract_collection_item(
        entities,
        index=resolved_source.get("index", 0),
        default=resolved_source.get("default"),
    )


def resolve_entities_query_value(context: Any, resolved_source: Any) -> list[dict[str, Any]]:
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
    world = _active_world(context)
    entities = sorted(
        [
            entity
            for entity in world.iter_entities(include_absent=include_absent)
            if include_hidden or entity.visible
            if _entity_matches_where(entity, where)
        ],
        key=world.entity_sort_key,
    )
    return [_serialize_selected_entity(entity, select=select) for entity in entities]


def resolve_entity_query_value(context: Any, resolved_source: Any) -> Any:
    """Return one selected plain-data ref chosen from a filtered world/entity scan."""
    if not isinstance(resolved_source, dict):
        raise TypeError("$entity_query value source requires a JSON object.")
    entities = resolve_entities_query_value(context, resolved_source)
    return extract_collection_item(
        entities,
        index=resolved_source.get("index", 0),
        default=resolved_source.get("default"),
    )


def resolve_cell_flags_at_value(context: Any, resolved_source: Any) -> dict[str, Any] | Any:
    """Return plain per-cell flag data for one explicit tile coordinate."""
    area = _active_area(context)
    if not isinstance(resolved_source, dict):
        raise TypeError("$cell_flags_at value source requires a JSON object.")
    raw_x = resolved_source.get("x")
    raw_y = resolved_source.get("y")
    if raw_x is None or raw_y is None:
        raise ValueError("$cell_flags_at value source requires both x and y.")
    grid_x = int(raw_x)
    grid_y = int(raw_y)
    if area.in_bounds(grid_x, grid_y):
        return copy.deepcopy(area.cell_flags_at(grid_x, grid_y))
    if "default" in resolved_source:
        return copy.deepcopy(resolved_source.get("default"))
    raise KeyError(f"Cell flag lookup ({grid_x}, {grid_y}) is out of bounds.")
