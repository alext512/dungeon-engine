"""JSON loading helpers for areas, reusable entity templates, and starter assets."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from puzzle_dungeon import config
from puzzle_dungeon.world.area import Area, TileLayer
from puzzle_dungeon.world.entity import Entity
from puzzle_dungeon.world.world import World


_TEMPLATE_CACHE: dict[str, dict[str, Any]] = {}


def load_area(area_path: Path) -> tuple[Area, World]:
    """Load an area JSON file and build a runtime world for it."""
    raw_data = json.loads(area_path.read_text(encoding="utf-8"))
    return load_area_from_data(raw_data, source_name=str(area_path))


def load_area_from_data(
    raw_data: dict[str, Any],
    *,
    source_name: str = "<memory>",
) -> tuple[Area, World]:
    """Build a runtime area and world from already-loaded JSON-like data."""
    tile_layers = _parse_tile_layers(raw_data)
    _validate_tile_layers(tile_layers, source_name)
    width = len(tile_layers[0].grid[0]) if tile_layers and tile_layers[0].grid else 0
    height = len(tile_layers[0].grid) if tile_layers else 0
    cell_flags = _parse_cell_flags(raw_data, width, height)

    area = Area(
        name=raw_data.get("name", "untitled_area"),
        tile_size=int(raw_data.get("tile_size", config.DEFAULT_TILE_SIZE)),
        tile_definitions=dict(raw_data.get("tile_definitions", {})),
        tile_layers=tile_layers,
        cell_flags=cell_flags,
    )

    world = World(player_id=raw_data.get("player_id", "player"))
    for entity_instance in raw_data.get("entities", []):
        entity = instantiate_entity(entity_instance, area.tile_size)
        world.add_entity(entity)

    return area, world


def instantiate_entity(entity_instance: dict[str, Any], tile_size: int) -> Entity:
    """Create a runtime entity from an instance definition or template reference."""
    entity_data = _resolve_entity_instance(entity_instance)
    sprite_data = dict(entity_data.get("sprite", {}))
    animation_frames = [int(frame) for frame in sprite_data.get("frames", [0])]
    entity = Entity(
        entity_id=entity_data["id"],
        kind=entity_data["kind"],
        grid_x=int(entity_data["x"]),
        grid_y=int(entity_data["y"]),
        pixel_x=float(int(entity_data["x"]) * tile_size),
        pixel_y=float(int(entity_data["y"]) * tile_size),
        facing=entity_data.get("facing", "down"),
        solid=bool(entity_data.get("solid", True)),
        pushable=bool(entity_data.get("pushable", False)),
        enabled=bool(entity_data.get("enabled", True)),
        visible=bool(entity_data.get("visible", True)),
        layer=int(entity_data.get("layer", 1)),
        stack_order=int(entity_data.get("stack_order", 0)),
        color=_parse_color(entity_data.get("color"), sprite_data),
        template_id=entity_instance.get("template"),
        template_parameters=dict(entity_instance.get("parameters", {})),
        sprite_path=str(sprite_data.get("path", "")),
        sprite_frame_width=int(sprite_data.get("frame_width", tile_size)),
        sprite_frame_height=int(sprite_data.get("frame_height", tile_size)),
        animation_frames=animation_frames,
        animation_fps=float(sprite_data.get("animation_fps", 0.0)),
        animate_when_moving=bool(sprite_data.get("animate_when_moving", False)),
        current_frame=int(animation_frames[0]),
        interact_commands=list(entity_data.get("interact_commands", [])),
        variables=dict(entity_data.get("variables", {})),
    )
    entity.sync_pixel_position(tile_size)
    return entity


def list_entity_template_ids() -> list[str]:
    """Return all available entity template ids in a stable order."""
    return sorted(path.stem for path in config.ENTITIES_DIR.glob("*.json"))


def load_entity_template(template_id: str) -> dict[str, Any]:
    """Load and cache a reusable entity template by its file name."""
    return _load_entity_template(template_id)


def _parse_tile_layers(raw_data: dict[str, Any]) -> list[TileLayer]:
    """Parse new layered tile data or convert the legacy single-grid format."""
    raw_layers = raw_data.get("tile_layers")
    if raw_layers is None:
        legacy_tiles = raw_data["tiles"]
        return [
            TileLayer(
                name="ground",
                grid=[[tile for tile in row] for row in legacy_tiles],
                draw_above_entities=False,
            )
        ]

    parsed_layers: list[TileLayer] = []
    for raw_layer in raw_layers:
        parsed_layers.append(
            TileLayer(
                name=str(raw_layer["name"]),
                grid=[
                    [tile if tile is None else str(tile) for tile in row]
                    for row in raw_layer["grid"]
                ],
                draw_above_entities=bool(raw_layer.get("draw_above_entities", False)),
            )
        )
    return parsed_layers


def _validate_tile_layers(tile_layers: list[TileLayer], source_name: str) -> None:
    """Ensure all tile layers share the same room dimensions."""
    if not tile_layers:
        raise ValueError(f"Area '{source_name}' does not define any tile layers.")

    expected_height = len(tile_layers[0].grid)
    expected_width = len(tile_layers[0].grid[0]) if tile_layers[0].grid else 0
    for layer in tile_layers:
        if len(layer.grid) != expected_height:
            raise ValueError(
                f"Area '{source_name}' layer '{layer.name}' has an unexpected height."
            )
        if any(len(row) != expected_width for row in layer.grid):
            raise ValueError(
                f"Area '{source_name}' layer '{layer.name}' has inconsistent row widths."
            )


def _parse_cell_flags(
    raw_data: dict[str, Any],
    width: int,
    height: int,
) -> list[list[dict[str, Any]]]:
    """Parse explicit cell flags or derive them from legacy single-character tiles."""
    raw_flags = raw_data.get("cell_flags")
    if raw_flags is not None:
        if len(raw_flags) != height or any(len(row) != width for row in raw_flags):
            raise ValueError("cell_flags dimensions must match the tile layers.")
        parsed_flags: list[list[dict[str, Any]]] = []
        for row in raw_flags:
            parsed_row: list[dict[str, Any]] = []
            for cell in row:
                if isinstance(cell, dict):
                    parsed_row.append(dict(cell))
                elif isinstance(cell, bool):
                    parsed_row.append({"walkable": cell})
                elif cell is None:
                    parsed_row.append({})
                else:
                    raise ValueError("cell_flags values must be booleans, objects, or null.")
            parsed_flags.append(parsed_row)
        return parsed_flags

    legacy_tiles = raw_data["tiles"]
    return [
        [{"walkable": tile != "#"} for tile in row]
        for row in legacy_tiles
    ]


def _resolve_entity_instance(instance_data: dict[str, Any]) -> dict[str, Any]:
    """Merge a reusable template with a level-specific instance definition."""
    template_id = instance_data.get("template")
    if template_id is None:
        resolved = copy.deepcopy(instance_data)
    else:
        template_data = _load_entity_template(str(template_id))
        resolved = _deep_merge(template_data, instance_data)

    parameters = dict(resolved.pop("parameters", {}))
    resolved.pop("template", None)
    return _substitute_parameters(resolved, parameters)


def _load_entity_template(template_id: str) -> dict[str, Any]:
    """Load and cache a reusable entity template by its file name."""
    cached = _TEMPLATE_CACHE.get(template_id)
    if cached is not None:
        return copy.deepcopy(cached)

    template_path = config.ENTITIES_DIR / f"{template_id}.json"
    if not template_path.exists():
        raise FileNotFoundError(f"Missing entity template '{template_id}' at '{template_path}'.")

    template_data = json.loads(template_path.read_text(encoding="utf-8"))
    _TEMPLATE_CACHE[template_id] = template_data
    return copy.deepcopy(template_data)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge dictionaries while letting instance data win."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _substitute_parameters(value: Any, parameters: dict[str, Any]) -> Any:
    """Replace '$name' or '${name}' strings with per-instance parameter values."""
    if isinstance(value, dict):
        return {key: _substitute_parameters(item, parameters) for key, item in value.items()}

    if isinstance(value, list):
        return [_substitute_parameters(item, parameters) for item in value]

    if isinstance(value, str):
        token = None
        if value.startswith("${") and value.endswith("}"):
            token = value[2:-1]
        elif value.startswith("$"):
            token = value[1:]

        if token is not None and token in parameters:
            return copy.deepcopy(parameters[token])

    return value


def _parse_color(
    raw_color: list[int] | tuple[int, int, int] | None,
    sprite_data: dict[str, Any],
) -> tuple[int, int, int]:
    """Return a tint color, defaulting to white when a sprite is present."""
    if raw_color is None:
        return (255, 255, 255)
    return (int(raw_color[0]), int(raw_color[1]), int(raw_color[2]))
