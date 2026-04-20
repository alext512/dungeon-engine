"""Serialization helpers for saving and cloning editable area data.

Writes areas back to the GID-based JSON format: tilesets array, integer grids,
cell flags, and entity instances.

Depends on: area, world
Used by: save/export tooling
"""

from __future__ import annotations

import copy
import math
from typing import Any

from dungeon_engine.inventory import serialize_inventory_state
from dungeon_engine.project_context import ProjectContext
from dungeon_engine.world.area import Area
from dungeon_engine.world.loader_entities import instantiate_entity
from dungeon_engine.world.world import World


def serialize_area(
    area: Area,
    world: World,
    *,
    project: ProjectContext,
) -> dict[str, Any]:
    """Convert the editable area and world state into JSON-serializable data."""
    data = {
        "tile_size": area.tile_size,
        "variables": copy.deepcopy(world.variables),
        "tilesets": [
            _serialize_tileset(ts)
            for ts in area.tilesets
        ],
        "tile_layers": [
            _serialize_tile_layer(layer)
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
            serialize_entity_instance(
                entity,
                area.tile_size,
                project=project,
                omit_default_render_fields=True,
            )
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


def _serialize_tile_layer(layer: Any) -> dict[str, Any]:
    """Serialize one tile layer using the unified render-order schema."""
    data: dict[str, Any] = {
        "name": layer.name,
        "render_order": int(layer.render_order),
        "y_sort": bool(layer.y_sort),
        "stack_order": int(layer.stack_order),
        "grid": layer.grid,
    }
    if not math.isclose(float(layer.sort_y_offset), 0.0, abs_tol=0.001):
        data["sort_y_offset"] = _serialize_number(float(layer.sort_y_offset))
    return data


def _serialize_entry_point(entry_point: Any) -> dict[str, Any]:
    """Serialize one authored area-entry marker."""
    data: dict[str, Any] = {
        "grid_x": int(entry_point.grid_x),
        "grid_y": int(entry_point.grid_y),
    }
    if entry_point.facing is not None:
        data["facing"] = str(entry_point.facing)
    if entry_point.pixel_x is not None:
        data["pixel_x"] = _serialize_number(entry_point.pixel_x)
    if entry_point.pixel_y is not None:
        data["pixel_y"] = _serialize_number(entry_point.pixel_y)
    return data


def _serialize_cell_flags(cell_flags: dict[str, Any]) -> dict[str, Any]:
    """Keep simple cells concise while preferring the new blocked terminology."""
    if set(cell_flags.keys()) <= {"blocked"}:
        return {"blocked": bool(cell_flags.get("blocked", False))}
    return dict(cell_flags)


def serialize_entity_instance(
    entity: Any,
    tile_size: int,
    *,
    project: ProjectContext,
    omit_default_render_fields: bool = False,
) -> dict[str, Any]:
    """Persist either a template instance or a fully inline entity definition."""
    data: dict[str, Any] = {
        "id": entity.entity_id,
    }
    if entity.space == "world":
        data["grid_x"] = entity.grid_x
        data["grid_y"] = entity.grid_y
    data.update(_serialize_pixel_position_fields(entity, tile_size))

    if entity.template_id:
        data["template"] = entity.template_id
        if entity.template_parameters:
            data["parameters"] = copy.deepcopy(entity.template_parameters)
        data.update(_serialize_template_entity_overrides(entity, tile_size, project=project))
        return data

    data.update(
        _serialize_runtime_entity_fields(
            entity,
            tile_size,
            omit_default_render_fields=omit_default_render_fields,
        )
    )

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
    JSON during normal saves. Those belong to the template plus
    parameters, not the authored room instance.
    """
    reference_entity = instantiate_entity(
        (
            {
                "id": entity.entity_id,
                "template": entity.template_id,
                "grid_x": entity.grid_x,
                "grid_y": entity.grid_y,
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
        "solid": entity.is_effectively_solid(),
        "pushable": entity.is_effectively_pushable(),
        "weight": int(entity.weight),
        "push_strength": int(entity.push_strength),
        "collision_push_strength": int(entity.collision_push_strength),
        "interactable": entity.is_effectively_interactable(),
        "interaction_priority": int(entity.interaction_priority),
        "entity_commands_enabled": entity.entity_commands_enabled,
        "inventory": serialize_inventory_state(entity.inventory),
        "render_order": entity.render_order,
        "y_sort": entity.y_sort,
        "sort_y_offset": _serialize_number(entity.sort_y_offset),
        "stack_order": entity.stack_order,
        "color": list(entity.color),
        "tags": copy.deepcopy(entity.tags),
    }
    persistence = _serialize_entity_persistence(entity)
    if persistence is not None:
        data["persistence"] = persistence
    if entity.input_map:
        data["input_map"] = copy.deepcopy(entity.input_map)
    if data["inventory"] is None:
        data.pop("inventory", None)
    if entity.authored_facing is not None or entity.get_effective_facing() != "down":
        data["facing"] = entity.get_effective_facing()
    data.update(_serialize_pixel_position_fields(entity, tile_size))
    dialogues = _serialize_entity_dialogues(entity)
    if dialogues:
        data["dialogues"] = dialogues
    entity_commands = _serialize_entity_commands(entity)
    if entity_commands:
        data["entity_commands"] = entity_commands
    return data


def _serialize_runtime_entity_fields(
    entity: Any,
    tile_size: int,
    *,
    omit_default_render_fields: bool,
) -> dict[str, Any]:
    """Return the stable authored/runtime fields that should round-trip through JSON."""
    data = {
        "kind": entity.kind,
        "space": entity.space,
        "scope": entity.scope,
        "present": entity.present,
        "visible": entity.visible,
        "solid": entity.is_effectively_solid(),
        "pushable": entity.is_effectively_pushable(),
        "weight": int(entity.weight),
        "push_strength": int(entity.push_strength),
        "collision_push_strength": int(entity.collision_push_strength),
        "interactable": entity.is_effectively_interactable(),
        "interaction_priority": int(entity.interaction_priority),
        "entity_commands_enabled": entity.entity_commands_enabled,
        "inventory": serialize_inventory_state(entity.inventory),
        "color": list(entity.color),
        "tags": copy.deepcopy(entity.tags),
        "variables": copy.deepcopy(entity.variables),
    }
    if entity.authored_facing is not None or entity.get_effective_facing() != "down":
        data["facing"] = entity.get_effective_facing()
    data.update(
        _serialize_entity_render_fields(
            entity,
            omit_defaults=omit_default_render_fields,
        )
    )
    persistence = _serialize_entity_persistence(entity)
    if persistence is not None:
        data["persistence"] = persistence
    if entity.input_map:
        data["input_map"] = copy.deepcopy(entity.input_map)
    if data["inventory"] is None:
        data.pop("inventory", None)
    data.update(_serialize_pixel_position_fields(entity, tile_size))
    dialogues = _serialize_entity_dialogues(entity)
    if dialogues:
        data["dialogues"] = dialogues
    entity_commands = _serialize_entity_commands(entity)
    if entity_commands:
        data["entity_commands"] = entity_commands
    return data


def _default_entity_render_order(space: str) -> int:
    return 10 if str(space).strip().lower() == "world" else 0


def _default_entity_y_sort(space: str) -> bool:
    return str(space).strip().lower() == "world"


def _serialize_entity_render_fields(entity: Any, *, omit_defaults: bool) -> dict[str, Any]:
    data: dict[str, Any] = {}
    render_order = int(entity.render_order)
    y_sort = bool(entity.y_sort)
    sort_y_offset = float(entity.sort_y_offset)
    stack_order = int(entity.stack_order)
    if not omit_defaults or render_order != _default_entity_render_order(entity.space):
        data["render_order"] = render_order
    if not omit_defaults or y_sort != _default_entity_y_sort(entity.space):
        data["y_sort"] = y_sort
    if not omit_defaults or not math.isclose(sort_y_offset, 0.0, abs_tol=0.001):
        data["sort_y_offset"] = _serialize_number(sort_y_offset)
    if not omit_defaults or stack_order != 0:
        data["stack_order"] = stack_order
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


def _serialize_entity_persistence(entity: Any) -> dict[str, Any] | None:
    """Serialize an entity's authored persistence policy when it is non-default."""
    policy = getattr(entity, "persistence", None)
    if policy is None or policy.is_default():
        return None

    data: dict[str, Any] = {
        "entity_state": bool(policy.entity_state),
    }
    if policy.variables:
        data["variables"] = {
            str(name): bool(value)
            for name, value in sorted(policy.variables.items())
        }
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
        serialized_visual = {
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
        if visual.default_animation is not None:
            serialized_visual["default_animation"] = visual.default_animation
        if visual.default_animation_by_facing:
            serialized_visual["default_animation_by_facing"] = {
                str(facing): str(animation_id)
                for facing, animation_id in sorted(visual.default_animation_by_facing.items())
            }
        if visual.animations:
            serialized_visual["animations"] = _serialize_visual_animations(visual)
        serialized.append(serialized_visual)
    return serialized


def _serialize_entity_dialogues(entity: Any) -> dict[str, dict[str, Any]]:
    """Serialize an entity's named dialogue map."""
    return copy.deepcopy(entity.dialogues)


def _serialize_visual_animations(visual: Any) -> dict[str, dict[str, Any]]:
    """Serialize named visual animation clips."""
    serialized: dict[str, dict[str, Any]] = {}
    for animation_id, clip in visual.animations.items():
        serialized_clip: dict[str, Any] = {
            "frames": list(clip.frames),
        }
        if clip.flip_x is not None:
            serialized_clip["flip_x"] = bool(clip.flip_x)
        if bool(clip.preserve_phase):
            serialized_clip["preserve_phase"] = True
        serialized[str(animation_id)] = serialized_clip
    return serialized


def _serialize_entity_commands(entity: Any) -> dict[str, Any]:
    """Serialize named entity commands in a stable JSON-friendly form."""
    serialized: dict[str, Any] = {}
    for command_id, entity_command in entity.entity_commands.items():
        if bool(entity_command.enabled):
            serialized[str(command_id)] = copy.deepcopy(entity_command.commands)
        else:
            serialized[str(command_id)] = {
                "enabled": False,
                "commands": copy.deepcopy(entity_command.commands),
            }
    return serialized

