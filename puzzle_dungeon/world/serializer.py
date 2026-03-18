"""Serialization helpers for saving and cloning editable area data.

Writes areas back to the GID-based JSON format: tilesets array, integer grids,
cell flags, and entity instances.

Depends on: area, world
Used by: editor (save)
"""

from __future__ import annotations

from typing import Any

from puzzle_dungeon.world.area import Area
from puzzle_dungeon.world.world import World


def serialize_area(area: Area, world: World) -> dict[str, Any]:
    """Convert the editable area and world state into JSON-serializable data."""
    return {
        "name": area.name,
        "tile_size": area.tile_size,
        "player_id": world.player_id,
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
            _serialize_entity(entity)
            for entity in sorted(
                world.iter_entities(),
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


def _serialize_entity(entity: Any) -> dict[str, Any]:
    """Persist either a template instance or a fully inline entity definition."""
    data: dict[str, Any] = {
        "id": entity.entity_id,
        "x": entity.grid_x,
        "y": entity.grid_y,
    }

    if entity.template_id:
        data["template"] = entity.template_id
        if entity.template_parameters:
            data["parameters"] = dict(entity.template_parameters)
        if entity.facing != "down":
            data["facing"] = entity.facing
        if entity.stack_order != 0:
            data["stack_order"] = entity.stack_order
        return data

    data.update(
        {
            "kind": entity.kind,
            "facing": entity.facing,
            "solid": entity.solid,
            "pushable": entity.pushable,
            "enabled": entity.enabled,
            "visible": entity.visible,
            "layer": entity.layer,
            "stack_order": entity.stack_order,
            "color": list(entity.color),
            "interact_commands": list(entity.interact_commands),
            "variables": dict(entity.variables),
        }
    )

    if entity.sprite_path:
        data["sprite"] = {
            "path": entity.sprite_path,
            "frame_width": entity.sprite_frame_width,
            "frame_height": entity.sprite_frame_height,
            "frames": list(entity.animation_frames),
            "animation_fps": entity.animation_fps,
            "animate_when_moving": entity.animate_when_moving,
        }
    return data
