"""JSON loading helpers for areas, reusable entity templates, and starter assets.

Parses area JSON files into runtime Area + World objects. Handles:
- GID-based tileset resolution (computing tile_count and columns from images)
- Entity template loading and parameter substitution
- Cell flags parsing (booleans or rich metadata dicts)

Depends on: config, area, entity, world, asset_manager (for tileset image queries)
Used by: game, editor
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from puzzle_dungeon import config
from puzzle_dungeon.world.area import Area, TileLayer, Tileset
from puzzle_dungeon.world.entity import Entity, EntityEvent
from puzzle_dungeon.world.persistence import PersistentAreaState, apply_persistent_area_state
from puzzle_dungeon.world.world import World


from puzzle_dungeon.project import ProjectContext

_TEMPLATE_CACHE: dict[str, dict[str, Any]] = {}

# Module-level project context: set before loading so internal helpers
# (e.g. _load_entity_template) can resolve paths without threading the
# parameter through every call.
_active_project: ProjectContext | None = None


def set_active_project(project: ProjectContext | None) -> None:
    """Set the project context used for template and asset resolution."""
    global _active_project
    _active_project = project


def load_area(
    area_path: Path,
    asset_manager: Any = None,
    persistent_area_state: PersistentAreaState | None = None,
) -> tuple[Area, World]:
    """Load an area JSON file and build a runtime world for it.

    If ``asset_manager`` is provided, tileset tile_counts and columns are
    computed from the actual image dimensions. Otherwise they default to 0
    (the area will still work, but GID bounds won't be validated).
    """
    raw_data = json.loads(area_path.read_text(encoding="utf-8"))
    return load_area_from_data(
        raw_data,
        source_name=str(area_path),
        asset_manager=asset_manager,
        persistent_area_state=persistent_area_state,
    )


def load_area_from_data(
    raw_data: dict[str, Any],
    *,
    source_name: str = "<memory>",
    asset_manager: Any = None,
    persistent_area_state: PersistentAreaState | None = None,
) -> tuple[Area, World]:
    """Build a runtime area and world from already-loaded JSON-like data."""
    tilesets = _parse_tilesets(raw_data, asset_manager)
    tile_layers = _parse_tile_layers(raw_data)
    _validate_tile_layers(tile_layers, source_name)
    width = len(tile_layers[0].grid[0]) if tile_layers and tile_layers[0].grid else 0
    height = len(tile_layers[0].grid) if tile_layers else 0
    cell_flags = _parse_cell_flags(raw_data, width, height)

    area = Area(
        area_id=str(raw_data.get("area_id", _derive_area_id(raw_data, source_name))),
        name=raw_data.get("name", "untitled_area"),
        tile_size=int(raw_data.get("tile_size", config.DEFAULT_TILE_SIZE)),
        tilesets=tilesets,
        tile_layers=tile_layers,
        cell_flags=cell_flags,
    )
    area.build_gid_lookup()

    world = World(player_id=raw_data.get("player_id", "player"))
    world.variables = copy.deepcopy(raw_data.get("variables", {}))
    for entity_instance in raw_data.get("entities", []):
        entity = instantiate_entity(entity_instance, area.tile_size)
        world.add_entity(entity)

    if persistent_area_state is not None:
        apply_persistent_area_state(area, world, persistent_area_state)

    return area, world


def instantiate_entity(entity_instance: dict[str, Any], tile_size: int) -> Entity:
    """Create a runtime entity from an instance definition or template reference."""
    entity_data = _resolve_entity_instance(entity_instance)
    sprite_data = dict(entity_data.get("sprite", {}))
    animation_frames = [int(frame) for frame in sprite_data.get("frames", [0])]
    grid_x = int(entity_data["x"])
    grid_y = int(entity_data["y"])
    default_pixel_x = float(grid_x * tile_size)
    default_pixel_y = float(grid_y * tile_size)
    entity = Entity(
        entity_id=entity_data["id"],
        kind=entity_data["kind"],
        grid_x=grid_x,
        grid_y=grid_y,
        pixel_x=float(entity_data.get("pixel_x", default_pixel_x)),
        pixel_y=float(entity_data.get("pixel_y", default_pixel_y)),
        facing=entity_data.get("facing", "down"),
        solid=bool(entity_data.get("solid", True)),
        pushable=bool(entity_data.get("pushable", False)),
        present=bool(entity_data.get("present", True)),
        visible=bool(entity_data.get("visible", True)),
        events_enabled=bool(entity_data.get("events_enabled", True)),
        layer=int(entity_data.get("layer", 1)),
        stack_order=int(entity_data.get("stack_order", 0)),
        color=_parse_color(entity_data.get("color"), sprite_data),
        template_id=entity_instance.get("template"),
        template_parameters=copy.deepcopy(entity_instance.get("parameters", {})),
        tags=[str(tag) for tag in entity_data.get("tags", [])],
        sprite_path=str(sprite_data.get("path", "")),
        sprite_frame_width=int(sprite_data.get("frame_width", tile_size)),
        sprite_frame_height=int(sprite_data.get("frame_height", tile_size)),
        animation_frames=animation_frames,
        animation_fps=float(sprite_data.get("animation_fps", 0.0)),
        animate_when_moving=bool(sprite_data.get("animate_when_moving", False)),
        current_frame=int(animation_frames[0]),
        events=_parse_entity_events(entity_data),
        variables=copy.deepcopy(entity_data.get("variables", {})),
    )
    return entity


def list_entity_template_ids() -> list[str]:
    """Return all available entity template ids in a stable order."""
    if _active_project is not None:
        return _active_project.list_entity_template_ids()
    return sorted(path.stem for path in config.ENTITIES_DIR.glob("*.json"))


def load_entity_template(template_id: str) -> dict[str, Any]:
    """Load and cache a reusable entity template by its file name."""
    return _load_entity_template(template_id)


def _parse_tilesets(raw_data: dict[str, Any], asset_manager: Any) -> list[Tileset]:
    """Parse the tilesets array from area JSON.

    Computes columns and tile_count from the actual image if an asset_manager
    is available; otherwise leaves them at 0.
    """
    raw_tilesets = raw_data.get("tilesets", [])
    tilesets: list[Tileset] = []
    for raw_ts in raw_tilesets:
        ts = Tileset(
            firstgid=int(raw_ts["firstgid"]),
            path=str(raw_ts["path"]),
            tile_width=int(raw_ts.get("tile_width", raw_data.get("tile_size", config.DEFAULT_TILE_SIZE))),
            tile_height=int(raw_ts.get("tile_height", raw_data.get("tile_size", config.DEFAULT_TILE_SIZE))),
        )
        if asset_manager is not None:
            ts.columns = asset_manager.get_columns(ts.path, ts.tile_width)
            ts.tile_count = asset_manager.get_frame_count(ts.path, ts.tile_width, ts.tile_height)
        tilesets.append(ts)
    return tilesets


def _parse_tile_layers(raw_data: dict[str, Any]) -> list[TileLayer]:
    """Parse tile layers with integer GID grids."""
    raw_layers = raw_data.get("tile_layers")
    if raw_layers is None:
        # Legacy single-grid format (string tiles) — shouldn't occur with GID format
        # but kept for safety during migration
        legacy_tiles = raw_data.get("tiles", [])
        return [
            TileLayer(
                name="ground",
                grid=[[0 for _ in row] for row in legacy_tiles],
                draw_above_entities=False,
            )
        ]

    parsed_layers: list[TileLayer] = []
    for raw_layer in raw_layers:
        parsed_layers.append(
            TileLayer(
                name=str(raw_layer["name"]),
                grid=[
                    [int(tile) if tile is not None else 0 for tile in row]
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

    # Fallback: all walkable
    return [[{"walkable": True} for _ in range(width)] for _ in range(height)]


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

    template_path: Path | None = None
    if _active_project is not None:
        template_path = _active_project.find_entity_template(template_id)

    if template_path is None:
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


def extract_template_parameter_names(template_id: str) -> list[str]:
    """Return the parameter placeholder names used by a template.

    Scans the template JSON for ``$name`` and ``${name}`` tokens and returns
    a sorted list of unique parameter names.  Useful for seeding the editor
    property inspector with empty values.
    """
    try:
        data = _load_entity_template(template_id)
    except FileNotFoundError:
        return []
    found: set[str] = set()
    _collect_parameter_tokens(data, found)
    return sorted(found)


def _collect_parameter_tokens(value: Any, found: set[str]) -> None:
    """Recursively find ``$name`` / ``${name}`` tokens in a data tree."""
    if isinstance(value, dict):
        for item in value.values():
            _collect_parameter_tokens(item, found)
    elif isinstance(value, list):
        for item in value:
            _collect_parameter_tokens(item, found)
    elif isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            found.add(value[2:-1])
        elif value.startswith("$"):
            found.add(value[1:])


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


def _parse_entity_events(entity_data: dict[str, Any]) -> dict[str, EntityEvent]:
    """Parse named entity events, wrapping legacy interact_commands when needed."""
    parsed_events: dict[str, EntityEvent] = {}

    raw_events = entity_data.get("events", {})
    if isinstance(raw_events, dict):
        for event_id, raw_event in raw_events.items():
            if isinstance(raw_event, list):
                parsed_events[str(event_id)] = EntityEvent(
                    enabled=True,
                    commands=copy.deepcopy(raw_event),
                )
                continue

            if not isinstance(raw_event, dict):
                raise ValueError("Entity events must be objects or command lists.")

            parsed_events[str(event_id)] = EntityEvent(
                enabled=bool(raw_event.get("enabled", True)),
                commands=copy.deepcopy(raw_event.get("commands", [])),
            )

    legacy_interact_commands = entity_data.get("interact_commands", [])
    if legacy_interact_commands and "interact" not in parsed_events:
        parsed_events["interact"] = EntityEvent(
            enabled=True,
            commands=copy.deepcopy(legacy_interact_commands),
        )

    return parsed_events


def _derive_area_id(raw_data: dict[str, Any], source_name: str) -> str:
    """Return a stable area id from authored JSON or the source path."""
    if source_name not in {"", "<memory>"}:
        return Path(source_name).stem

    name = str(raw_data.get("name", "untitled_area")).strip().lower()
    slug_chars = [
        char if char.isalnum() else "_"
        for char in name
    ]
    slug = "".join(slug_chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "untitled_area"
