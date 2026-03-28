"""Serialization helpers for saving and cloning editable area data.

Writes areas back to the GID-based JSON format: tilesets array, integer grids,
cell flags, and entity instances.

Depends on: area, world
Used by: editor (save)
"""

from __future__ import annotations

import copy
import math
from typing import Any

from dungeon_engine.project import ProjectContext
from dungeon_engine.world.area import Area
from dungeon_engine.world.loader import instantiate_entity
from dungeon_engine.world.world import World


def serialize_area(
    area: Area,
    world: World,
    *,
    project: ProjectContext,
) -> dict[str, Any]:
    """Convert the editable area and world state into JSON-serializable data."""
    data = {
        "name": area.name,
        "tile_size": area.tile_size,
        "variables": copy.deepcopy(world.variables),
        "tilesets": [
            _serialize_tileset(ts)
            for ts in area.tilesets
        ],
        "tile_layers": [
            {
                "name": layer.name,
                "draw_above_entities": layer.draw_above_entities,
                "grid": layer.grid,
            }
            for layer in area.tile_layers
        ],
        "cell_flags": [
            [
                _serialize_cell_flags(cell_flags)
                for cell_flags in row
            ]
            for row in area.cell_flags
        ],
        "entities": [
            serialize_entity_instance(entity, area.tile_size, project=project)
            for entity in sorted(
                world.iter_area_entities(include_absent=True),
                key=world.entity_sort_key,
            )
        ],
    }
    if world.default_input_targets != project.input_targets:
        data["input_targets"] = copy.deepcopy(world.default_input_targets)
    if area.entry_points:
        data["entry_points"] = {
            entry_id: _serialize_entry_point(entry_point)
            for entry_id, entry_point in area.entry_points.items()
        }
    if area.camera_defaults:
        data["camera"] = copy.deepcopy(area.camera_defaults)
    if area.enter_commands:
        data["enter_commands"] = copy.deepcopy(area.enter_commands)
    return data


def _serialize_tileset(tileset: Any) -> dict[str, Any]:
    """Serialize a Tileset to its JSON representation.

    Only stores the fields needed to reconstruct the tileset; columns and
    tile_count are recomputed on load from the actual image.
    """
    return {
        "firstgid": tileset.firstgid,
        "path": tileset.path,
        "tile_width": tileset.tile_width,
        "tile_height": tileset.tile_height,
    }


def _serialize_entry_point(entry_point: Any) -> dict[str, Any]:
    """Serialize one authored area-entry marker."""
    data: dict[str, Any] = {
        "x": int(entry_point.grid_x),
        "y": int(entry_point.grid_y),
    }
    if entry_point.facing is not None:
        data["facing"] = str(entry_point.facing)
    if entry_point.pixel_x is not None:
        data["pixel_x"] = _serialize_number(entry_point.pixel_x)
    if entry_point.pixel_y is not None:
        data["pixel_y"] = _serialize_number(entry_point.pixel_y)
    return data


def _serialize_cell_flags(cell_flags: dict[str, Any]) -> bool | dict[str, Any]:
    """Keep simple walkability cells concise while preserving richer future metadata."""
    if set(cell_flags.keys()) <= {"walkable"}:
        return bool(cell_flags.get("walkable", True))
    return dict(cell_flags)


def serialize_entity_instance(
    entity: Any,
    tile_size: int,
    *,
    project: ProjectContext,
) -> dict[str, Any]:
    """Persist either a template instance or a fully inline entity definition."""
    data: dict[str, Any] = {
        "id": entity.entity_id,
    }
    if entity.space == "world":
        data["x"] = entity.grid_x
        data["y"] = entity.grid_y
    data.update(_serialize_pixel_position_fields(entity, tile_size))

    if entity.template_id:
        data["template"] = entity.template_id
        if entity.template_parameters:
            data["parameters"] = copy.deepcopy(entity.template_parameters)
        data.update(_serialize_template_entity_overrides(entity, tile_size, project=project))
        return data

    data.update(_serialize_runtime_entity_fields(entity, tile_size))

    visuals_data = _serialize_visuals(entity)
    if visuals_data:
        data["visuals"] = visuals_data
    return data


def _serialize_template_entity_overrides(
    entity: Any,
    tile_size: int,
    *,
    project: ProjectContext,
) -> dict[str, Any]:
    """Persist only explicit authored overrides for a template instance.

    Generated data like resolved command chains should not leak back into room
    JSON during normal editor saves. Those belong to the template plus
    parameters, not the authored room instance.
    """
    reference_entity = instantiate_entity(
        (
            {
                "id": entity.entity_id,
                "template": entity.template_id,
                "x": entity.grid_x,
                "y": entity.grid_y,
                "parameters": copy.deepcopy(entity.template_parameters),
            }
            if entity.space == "world"
            else {
                "id": entity.entity_id,
                "template": entity.template_id,
                "pixel_x": _serialize_number(entity.pixel_x),
                "pixel_y": _serialize_number(entity.pixel_y),
                "space": entity.space,
                "scope": entity.scope,
                "parameters": copy.deepcopy(entity.template_parameters),
            }
        ),
        tile_size,
        project=project,
        source_name=f"template reference '{entity.entity_id}'",
    )

    overrides: dict[str, Any] = {}
    runtime_fields = _serialize_template_override_fields(entity, tile_size)
    reference_fields = _serialize_template_override_fields(reference_entity, tile_size)
    for key, value in runtime_fields.items():
        if value != reference_fields.get(key):
            overrides[key] = value

    visuals_data = _serialize_visuals(entity)
    reference_visuals_data = _serialize_visuals(reference_entity)
    if visuals_data != reference_visuals_data:
        overrides["visuals"] = visuals_data

    return overrides


def _serialize_template_override_fields(entity: Any, tile_size: int) -> dict[str, Any]:
    """Return only the safe authored override fields for template instances."""
    data = {
        "space": entity.space,
        "scope": entity.scope,
        "present": entity.present,
        "visible": entity.visible,
        "events_enabled": entity.events_enabled,
        "layer": entity.layer,
        "stack_order": entity.stack_order,
        "color": list(entity.color),
        "tags": copy.deepcopy(entity.tags),
    }
    if entity.input_map:
        data["input_map"] = copy.deepcopy(entity.input_map)
    data.update(_serialize_pixel_position_fields(entity, tile_size))
    events = _serialize_events(entity)
    if events:
        data["events"] = events
    return data


def _serialize_runtime_entity_fields(entity: Any, tile_size: int) -> dict[str, Any]:
    """Return the stable authored/runtime fields that should round-trip through JSON."""
    data = {
        "kind": entity.kind,
        "space": entity.space,
        "scope": entity.scope,
        "present": entity.present,
        "visible": entity.visible,
        "events_enabled": entity.events_enabled,
        "layer": entity.layer,
        "stack_order": entity.stack_order,
        "color": list(entity.color),
        "tags": copy.deepcopy(entity.tags),
        "variables": copy.deepcopy(entity.variables),
    }
    if entity.input_map:
        data["input_map"] = copy.deepcopy(entity.input_map)
    data.update(_serialize_pixel_position_fields(entity, tile_size))
    events = _serialize_events(entity)
    if events:
        data["events"] = events
    return data


def _serialize_pixel_position_fields(entity: Any, tile_size: int) -> dict[str, Any]:
    """Serialize pixel position only when it differs from the tile-derived default."""
    default_pixel_x = float(entity.grid_x * tile_size) if entity.space == "world" else 0.0
    default_pixel_y = float(entity.grid_y * tile_size) if entity.space == "world" else 0.0
    data: dict[str, Any] = {}
    if not math.isclose(entity.pixel_x, default_pixel_x, abs_tol=0.001):
        data["pixel_x"] = _serialize_number(entity.pixel_x)
    if not math.isclose(entity.pixel_y, default_pixel_y, abs_tol=0.001):
        data["pixel_y"] = _serialize_number(entity.pixel_y)
    return data


def _serialize_number(value: float) -> int | float:
    """Preserve integer-looking values while allowing fractional positions."""
    if math.isclose(value, round(value), abs_tol=0.001):
        return int(round(value))
    return float(value)


def _serialize_visuals(entity: Any) -> list[dict[str, Any]]:
    """Serialize an entity's visuals list."""
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
                "flip_x": visual.flip_x,
                "visible": visual.visible,
                "tint": list(visual.tint),
                "offset_x": _serialize_number(visual.offset_x),
                "offset_y": _serialize_number(visual.offset_y),
                "draw_order": visual.draw_order,
            }
        )
    return serialized


def _serialize_events(entity: Any) -> dict[str, Any]:
    """Serialize named entity events in a stable JSON-friendly form."""
    serialized: dict[str, Any] = {}
    for event_id, event in entity.events.items():
        serialized[str(event_id)] = {
            "enabled": bool(event.enabled),
            "commands": copy.deepcopy(event.commands),
        }
    return serialized

