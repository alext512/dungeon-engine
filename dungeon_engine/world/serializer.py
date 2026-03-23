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

from dungeon_engine.world.area import Area
from dungeon_engine.world.loader import instantiate_entity
from dungeon_engine.world.world import World


def serialize_area(area: Area, world: World) -> dict[str, Any]:
    """Convert the editable area and world state into JSON-serializable data."""
    return {
        "area_id": area.area_id,
        "name": area.name,
        "tile_size": area.tile_size,
        "player_id": world.player_id,
        "active_entity_id": world.active_entity_id,
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
            _serialize_entity(entity, area.tile_size)
            for entity in sorted(
                world.iter_entities(include_absent=True),
                key=world.entity_sort_key,
            )
        ],
    }


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


def _serialize_cell_flags(cell_flags: dict[str, Any]) -> bool | dict[str, Any]:
    """Keep simple walkability cells concise while preserving richer future metadata."""
    if set(cell_flags.keys()) <= {"walkable"}:
        return bool(cell_flags.get("walkable", True))
    return dict(cell_flags)


def _serialize_entity(entity: Any, tile_size: int) -> dict[str, Any]:
    """Persist either a template instance or a fully inline entity definition."""
    data: dict[str, Any] = {
        "id": entity.entity_id,
        "x": entity.grid_x,
        "y": entity.grid_y,
    }
    data.update(_serialize_pixel_position_fields(entity, tile_size))

    if entity.template_id:
        data["template"] = entity.template_id
        if entity.template_parameters:
            data["parameters"] = copy.deepcopy(entity.template_parameters)
        data.update(_serialize_template_entity_overrides(entity, tile_size))
        return data

    data.update(_serialize_runtime_entity_fields(entity, tile_size))

    sprite_data = _serialize_sprite_data(entity)
    if sprite_data is not None:
        data["sprite"] = sprite_data
    return data


def _serialize_template_entity_overrides(entity: Any, tile_size: int) -> dict[str, Any]:
    """Persist only explicit authored overrides for a template instance.

    Generated data like resolved command chains should not leak back into room
    JSON during normal editor saves. Those belong to the template plus
    parameters, not the authored room instance.
    """
    reference_entity = instantiate_entity(
        {
            "id": entity.entity_id,
            "template": entity.template_id,
            "x": entity.grid_x,
            "y": entity.grid_y,
            "parameters": copy.deepcopy(entity.template_parameters),
        },
        tile_size,
    )

    overrides: dict[str, Any] = {}
    runtime_fields = _serialize_template_override_fields(entity, tile_size)
    reference_fields = _serialize_template_override_fields(reference_entity, tile_size)
    for key, value in runtime_fields.items():
        if value != reference_fields.get(key):
            overrides[key] = value

    sprite_data = _serialize_sprite_data(entity)
    reference_sprite_data = _serialize_sprite_data(reference_entity)
    if sprite_data != reference_sprite_data:
        overrides["sprite"] = sprite_data or {
            "path": "",
            "frame_width": entity.sprite_frame_width,
            "frame_height": entity.sprite_frame_height,
            "frames": list(entity.animation_frames),
            "animation_fps": entity.animation_fps,
            "animate_when_moving": entity.animate_when_moving,
        }

    return overrides


def _serialize_template_override_fields(entity: Any, tile_size: int) -> dict[str, Any]:
    """Return only the safe authored override fields for template instances."""
    data = {
        "facing": entity.facing,
        "solid": entity.solid,
        "pushable": entity.pushable,
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
        "facing": entity.facing,
        "solid": entity.solid,
        "pushable": entity.pushable,
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
    default_pixel_x = float(entity.grid_x * tile_size)
    default_pixel_y = float(entity.grid_y * tile_size)
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


def _serialize_sprite_data(entity: Any) -> dict[str, Any] | None:
    """Serialize sprite data when an entity uses sprite rendering."""
    if not entity.sprite_path:
        return None
    return {
        "path": entity.sprite_path,
        "frame_width": entity.sprite_frame_width,
        "frame_height": entity.sprite_frame_height,
        "frames": list(entity.animation_frames),
        "animation_fps": entity.animation_fps,
        "animate_when_moving": entity.animate_when_moving,
    }


def _serialize_events(entity: Any) -> dict[str, Any]:
    """Serialize named entity events in a stable JSON-friendly form."""
    serialized: dict[str, Any] = {}
    for event_id, event in entity.events.items():
        serialized[str(event_id)] = {
            "enabled": bool(event.enabled),
            "commands": copy.deepcopy(event.commands),
        }
    return serialized

