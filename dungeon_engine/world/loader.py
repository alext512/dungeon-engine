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

from dungeon_engine import config
from dungeon_engine.logging_utils import get_logger
from dungeon_engine.world.area import Area, AreaEntryPoint, TileLayer, Tileset
from dungeon_engine.world.entity import Entity, EntityEvent, EntityVisual
from dungeon_engine.world.persistence import PersistentAreaState, apply_persistent_area_state
from dungeon_engine.world.world import World


from dungeon_engine.project import ProjectContext

logger = get_logger(__name__)

_TEMPLATE_CACHE: dict[tuple[Path, str], dict[str, Any]] = {}
_RESERVED_ENTITY_IDS = {"self", "actor", "caller"}
_STRICT_ENTITY_TARGET_COMMANDS = {
    "set_entity_var",
    "increment_entity_var",
    "set_entity_var_length",
    "append_entity_var",
    "pop_entity_var",
    "set_entity_var_from_collection_item",
    "check_entity_var",
    "set_event_enabled",
    "set_events_enabled",
    "set_input_target",
    "set_entity_field",
    "route_inputs_to_entity",
    "set_camera_follow_entity",
    "set_entity_var_from_camera",
    "set_facing",
    "move_entity_one_tile",
    "move_entity",
    "teleport_entity",
    "wait_for_move",
    "play_animation",
    "wait_for_animation",
    "stop_animation",
    "set_visual_frame",
    "set_visual_flip_x",
    "set_visible",
    "set_solid",
    "set_present",
    "set_color",
    "destroy_entity",
}


def load_area(
    area_path: Path,
    *,
    project: ProjectContext,
    asset_manager: Any = None,
    persistent_area_state: PersistentAreaState | None = None,
) -> tuple[Area, World]:
    """Load an area JSON file and build a runtime world for it.

    If ``asset_manager`` is provided, tileset tile_counts and columns are
    computed from the actual image dimensions. Otherwise they default to 0
    (the area will still work, but GID bounds won't be validated).
    """
    resolved_area_path = area_path.resolve()
    raw_data = json.loads(resolved_area_path.read_text(encoding="utf-8"))
    return load_area_from_data(
        raw_data,
        source_name=str(resolved_area_path),
        asset_manager=asset_manager,
        persistent_area_state=persistent_area_state,
        project=project,
    )


def load_area_from_data(
    raw_data: dict[str, Any],
    *,
    project: ProjectContext,
    source_name: str = "<memory>",
    asset_manager: Any = None,
    persistent_area_state: PersistentAreaState | None = None,
) -> tuple[Area, World]:
    """Build a runtime area and world from already-loaded JSON-like data."""
    if not isinstance(raw_data, dict):
        raise ValueError(f"Area '{source_name}' must be a JSON object.")
    if "area_id" in raw_data:
        raise ValueError(
            f"Area '{source_name}' must not declare 'area_id'; area ids are path-derived."
        )

    area_name = _optional_string(raw_data.get("name"), field_name="name", source_name=source_name)
    tile_size = _coerce_int(
        raw_data.get("tile_size", config.DEFAULT_TILE_SIZE),
        field_name="tile_size",
        source_name=source_name,
    )
    if tile_size <= 0:
        raise ValueError(f"Area '{source_name}' tile_size must be positive, got {tile_size}.")

    variables = raw_data.get("variables", {})
    if variables is None:
        variables = {}
    if not isinstance(variables, dict):
        raise ValueError(f"Area '{source_name}' field 'variables' must be a JSON object.")

    raw_entities = raw_data.get("entities", [])
    if raw_entities is None:
        raw_entities = []
    if not isinstance(raw_entities, list):
        raise ValueError(f"Area '{source_name}' field 'entities' must be a JSON array.")

    tilesets = _parse_tilesets(raw_data, asset_manager, source_name=source_name)
    tile_layers = _parse_tile_layers(raw_data)
    _validate_tile_layers(tile_layers, source_name)
    width = len(tile_layers[0].grid[0]) if tile_layers and tile_layers[0].grid else 0
    height = len(tile_layers[0].grid) if tile_layers else 0
    cell_flags = _parse_cell_flags(raw_data, width, height)
    enter_commands = _parse_command_list(
        raw_data.get("enter_commands"),
        field_name="enter_commands",
        source_name=source_name,
    )
    entry_points = _parse_entry_points(raw_data.get("entry_points"), source_name=source_name)
    camera_defaults = _parse_camera_defaults(raw_data.get("camera"), source_name=source_name)

    area = Area(
        area_id=_derive_area_id(source_name=source_name, project=project, area_name=area_name),
        name=area_name or "untitled_area",
        tile_size=tile_size,
        tilesets=tilesets,
        tile_layers=tile_layers,
        cell_flags=cell_flags,
        entry_points=entry_points,
        camera_defaults=camera_defaults,
        enter_commands=enter_commands,
    )
    area.build_gid_lookup()

    if "player_id" in raw_data:
        raise ValueError(
            f"Area '{source_name}' must not declare 'player_id'; use explicit "
            "'input_targets', transfer payloads, and camera defaults instead."
        )
    if "active_entity_id" in raw_data:
        raise ValueError(
            f"Area '{source_name}' must not declare 'active_entity_id'; use 'input_targets' instead."
        )
    resolved_input_targets = copy.deepcopy(project.input_targets)
    resolved_input_targets.update(
        _parse_input_targets(
            raw_data.get("input_targets"),
            source_name=source_name,
        )
    )
    world = World(default_input_targets=resolved_input_targets)
    world.variables = copy.deepcopy(variables)
    for index, entity_instance in enumerate(raw_entities):
        entity = instantiate_entity(
            entity_instance,
            area.tile_size,
            project=project,
            source_name=f"{source_name} entities[{index}]",
        )
        world.add_entity(entity)

    if persistent_area_state is not None:
        apply_persistent_area_state(area, world, persistent_area_state, project=project)

    return area, world


def instantiate_entity(
    entity_instance: dict[str, Any],
    tile_size: int,
    *,
    project: ProjectContext,
    source_name: str = "<entity>",
) -> Entity:
    """Create a runtime entity from an instance definition or template reference."""
    if not isinstance(entity_instance, dict):
        raise ValueError(f"{source_name} must be a JSON object.")

    template_id = _normalize_optional_id(entity_instance.get("template"))
    entity_data = _resolve_entity_instance(
        entity_instance,
        project=project,
        source_name=source_name,
    )
    entity_id = _require_non_empty_string(entity_data, "id", source_name=source_name)
    if entity_id in _RESERVED_ENTITY_IDS:
        reserved_names = ", ".join(sorted(_RESERVED_ENTITY_IDS))
        raise ValueError(
            f"{source_name} field 'id' must not use reserved runtime entity reference "
            f"'{entity_id}' ({reserved_names})."
        )
    kind = _require_non_empty_string(entity_data, "kind", source_name=source_name)
    space = _parse_entity_space(entity_data, source_name=source_name)
    scope = _parse_entity_scope(entity_data, source_name=source_name)
    if space == "world":
        grid_x = _coerce_required_int(entity_data, "x", source_name=source_name)
        grid_y = _coerce_required_int(entity_data, "y", source_name=source_name)
        default_pixel_x = float(grid_x * tile_size)
        default_pixel_y = float(grid_y * tile_size)
    else:
        if "x" in entity_data or "y" in entity_data:
            raise ValueError(
                f"{source_name} screen-space entities must not declare 'x'/'y'; use 'pixel_x'/'pixel_y' or visual offsets."
            )
        grid_x = 0
        grid_y = 0
        default_pixel_x = 0.0
        default_pixel_y = 0.0

    visuals = _parse_entity_visuals(entity_data, tile_size=tile_size, source_name=source_name)
    entity = Entity(
        entity_id=entity_id,
        kind=kind,
        grid_x=grid_x,
        grid_y=grid_y,
        pixel_x=float(entity_data.get("pixel_x", default_pixel_x)),
        pixel_y=float(entity_data.get("pixel_y", default_pixel_y)),
        facing=entity_data.get("facing", "down"),
        space=space,
        scope=scope,
        solid=bool(entity_data.get("solid", True)),
        pushable=bool(entity_data.get("pushable", False)),
        present=bool(entity_data.get("present", True)),
        visible=bool(entity_data.get("visible", True)),
        events_enabled=bool(entity_data.get("events_enabled", True)),
        layer=int(entity_data.get("layer", 1)),
        stack_order=int(entity_data.get("stack_order", 0)),
        color=_parse_color(entity_data.get("color")),
        template_id=template_id,
        template_parameters=copy.deepcopy(entity_instance.get("parameters", {})),
        tags=_coerce_string_list(entity_data.get("tags", []), field_name="tags", source_name=source_name),
        visuals=visuals,
        events=_parse_entity_events(entity_data),
        variables=copy.deepcopy(entity_data.get("variables", {})),
        input_map=_parse_input_map(entity_data.get("input_map")),
    )
    return entity


def _parse_entity_space(entity_data: dict[str, Any], *, source_name: str) -> str:
    """Parse one entity's spatial domain."""
    space = str(entity_data.get("space", "world")).strip().lower()
    if space not in {"world", "screen"}:
        raise ValueError(f"{source_name} field 'space' must be 'world' or 'screen'.")
    return space


def _parse_entity_scope(entity_data: dict[str, Any], *, source_name: str) -> str:
    """Parse one entity's lifetime scope."""
    scope = str(entity_data.get("scope", "area")).strip().lower()
    if scope not in {"area", "global"}:
        raise ValueError(f"{source_name} field 'scope' must be 'area' or 'global'.")
    return scope


def _parse_entity_visuals(
    entity_data: dict[str, Any],
    *,
    tile_size: int,
    source_name: str,
) -> list[EntityVisual]:
    """Parse and validate one entity's visuals list."""
    if "sprite" in entity_data:
        raise ValueError(
            f"{source_name} must not use 'sprite'; entities now define a 'visuals' array."
        )

    raw_visuals = entity_data.get("visuals", [])
    if raw_visuals is None:
        raw_visuals = []
    if not isinstance(raw_visuals, list):
        raise ValueError(f"{source_name} field 'visuals' must be a JSON array.")

    visuals: list[EntityVisual] = []
    seen_visual_ids: set[str] = set()
    for index, raw_visual in enumerate(raw_visuals):
        if not isinstance(raw_visual, dict):
            raise ValueError(f"{source_name} visuals[{index}] must be a JSON object.")
        visual_id = _require_non_empty_string(
            raw_visual,
            "id",
            source_name=f"{source_name} visuals[{index}]",
        )
        if visual_id in seen_visual_ids:
            raise ValueError(f"{source_name} uses duplicate visual id '{visual_id}'.")
        seen_visual_ids.add(visual_id)

        raw_frames = raw_visual.get("frames", [0])
        if not isinstance(raw_frames, list):
            raise ValueError(f"{source_name} visuals[{index}] field 'frames' must be a JSON array.")
        frames = [int(frame) for frame in raw_frames]
        if not frames:
            raise ValueError(f"{source_name} visuals[{index}] field 'frames' must not be empty.")

        frame_width = int(raw_visual.get("frame_width", tile_size))
        frame_height = int(raw_visual.get("frame_height", tile_size))
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError(f"{source_name} visuals[{index}] frame dimensions must be positive.")

        tint = _parse_color(raw_visual.get("tint"))
        visuals.append(
            EntityVisual(
                visual_id=visual_id,
                path=_require_non_empty_string(
                    raw_visual,
                    "path",
                    source_name=f"{source_name} visuals[{index}]",
                ),
                frame_width=frame_width,
                frame_height=frame_height,
                frames=frames,
                animation_fps=float(raw_visual.get("animation_fps", 0.0)),
                animate_when_moving=bool(raw_visual.get("animate_when_moving", False)),
                current_frame=int(frames[0]),
                flip_x=bool(raw_visual.get("flip_x", False)),
                visible=bool(raw_visual.get("visible", True)),
                tint=tint,
                offset_x=float(raw_visual.get("offset_x", 0.0)),
                offset_y=float(raw_visual.get("offset_y", 0.0)),
                draw_order=int(raw_visual.get("draw_order", index)),
            )
        )

    return visuals


def list_entity_template_ids(project: ProjectContext) -> list[str]:
    """Return all available entity template ids in a stable order."""
    return project.list_entity_template_ids()


def load_entity_template(template_id: str, *, project: ProjectContext) -> dict[str, Any]:
    """Load and cache a reusable entity template by its file name."""
    return _load_entity_template(template_id, project=project)


def _parse_tilesets(raw_data: dict[str, Any], asset_manager: Any, *, source_name: str) -> list[Tileset]:
    """Parse the tilesets array from area JSON.

    Computes columns and tile_count from the actual image if an asset_manager
    is available; otherwise leaves them at 0.
    """
    raw_tilesets = raw_data.get("tilesets", [])
    if not isinstance(raw_tilesets, list):
        raise ValueError(f"Area '{source_name}' field 'tilesets' must be a JSON array.")
    tilesets: list[Tileset] = []
    for index, raw_ts in enumerate(raw_tilesets):
        if not isinstance(raw_ts, dict):
            raise ValueError(f"Area '{source_name}' tilesets[{index}] must be a JSON object.")
        ts = Tileset(
            firstgid=_coerce_required_int(
                raw_ts,
                "firstgid",
                source_name=f"Area '{source_name}' tilesets[{index}]",
            ),
            path=_require_non_empty_string(
                raw_ts,
                "path",
                source_name=f"Area '{source_name}' tilesets[{index}]",
            ),
            tile_width=_coerce_int(
                raw_ts.get("tile_width", raw_data.get("tile_size", config.DEFAULT_TILE_SIZE)),
                field_name="tile_width",
                source_name=f"Area '{source_name}' tilesets[{index}]",
            ),
            tile_height=_coerce_int(
                raw_ts.get("tile_height", raw_data.get("tile_size", config.DEFAULT_TILE_SIZE)),
                field_name="tile_height",
                source_name=f"Area '{source_name}' tilesets[{index}]",
            ),
        )
        if ts.tile_width <= 0 or ts.tile_height <= 0:
            raise ValueError(
                f"Area '{source_name}' tilesets[{index}] tile dimensions must be positive."
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
        raise ValueError("Area data must define 'tile_layers'.")
    if not isinstance(raw_layers, list):
        raise ValueError("Area field 'tile_layers' must be a JSON array.")

    parsed_layers: list[TileLayer] = []
    for index, raw_layer in enumerate(raw_layers):
        if not isinstance(raw_layer, dict):
            raise ValueError(f"Area tile_layers[{index}] must be a JSON object.")
        raw_grid = raw_layer.get("grid")
        if not isinstance(raw_grid, list):
            raise ValueError(f"Area tile_layers[{index}] field 'grid' must be a JSON array.")
        parsed_layers.append(
            TileLayer(
                name=_require_non_empty_string(
                    raw_layer,
                    "name",
                    source_name=f"Area tile_layers[{index}]",
                ),
                grid=[
                    [int(tile) if tile is not None else 0 for tile in row]
                    for row in raw_grid
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
    """Parse explicit cell flags or fall back to all-walkable cells."""
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


def _parse_command_list(
    raw_commands: Any,
    *,
    field_name: str,
    source_name: str,
) -> list[dict[str, Any]]:
    """Parse one optional command-list field with descriptive validation."""
    if raw_commands is None:
        return []
    if not isinstance(raw_commands, list):
        raise ValueError(f"{source_name} field '{field_name}' must be a JSON array.")

    parsed: list[dict[str, Any]] = []
    for index, command in enumerate(raw_commands):
        if not isinstance(command, dict):
            raise ValueError(
                f"{source_name} field '{field_name}' must contain JSON objects "
                f"(invalid entry at index {index})."
            )
        _validate_command_tree(
            command,
            source_name=source_name,
            location=f"{field_name}[{index}]",
        )
        parsed.append(copy.deepcopy(command))
    return parsed


def _parse_entry_points(
    raw_entry_points: Any,
    *,
    source_name: str,
) -> dict[str, AreaEntryPoint]:
    """Parse one optional mapping of authored area-entry markers."""
    if raw_entry_points is None:
        return {}
    if not isinstance(raw_entry_points, dict):
        raise ValueError(f"Area '{source_name}' field 'entry_points' must be a JSON object.")

    parsed: dict[str, AreaEntryPoint] = {}
    for raw_entry_id, raw_entry_data in raw_entry_points.items():
        entry_id = str(raw_entry_id).strip()
        if not entry_id:
            raise ValueError(
                f"Area '{source_name}' field 'entry_points' cannot use a blank entry id."
            )
        if not isinstance(raw_entry_data, dict):
            raise ValueError(
                f"Area '{source_name}' entry_points.{entry_id} must be a JSON object."
            )
        if entry_id in parsed:
            raise ValueError(f"Area '{source_name}' uses duplicate entry point id '{entry_id}'.")

        grid_x = _coerce_required_int(
            raw_entry_data,
            "x",
            source_name=f"Area '{source_name}' entry_points.{entry_id}",
        )
        grid_y = _coerce_required_int(
            raw_entry_data,
            "y",
            source_name=f"Area '{source_name}' entry_points.{entry_id}",
        )
        facing = _optional_string(
            raw_entry_data.get("facing"),
            field_name="facing",
            source_name=f"Area '{source_name}' entry_points.{entry_id}",
        )
        pixel_x = raw_entry_data.get("pixel_x")
        pixel_y = raw_entry_data.get("pixel_y")
        parsed[entry_id] = AreaEntryPoint(
            entry_id=entry_id,
            grid_x=grid_x,
            grid_y=grid_y,
            facing=facing,
            pixel_x=None if pixel_x is None else float(pixel_x),
            pixel_y=None if pixel_y is None else float(pixel_y),
        )
    return parsed


def _parse_camera_defaults(raw_camera_defaults: Any, *, source_name: str) -> dict[str, Any]:
    """Parse one optional authored area-camera defaults object."""
    if raw_camera_defaults is None:
        return {}
    if not isinstance(raw_camera_defaults, dict):
        raise ValueError(f"Area '{source_name}' field 'camera' must be a JSON object.")
    return copy.deepcopy(raw_camera_defaults)


def _validate_command_tree(value: Any, *, source_name: str, location: str) -> None:
    """Reject removed command-shape fields anywhere inside authored command data."""
    if isinstance(value, dict):
        if "on_complete" in value:
            raise ValueError(
                f"{source_name} command '{location}' must not use 'on_complete'; "
                "use 'on_start' and 'on_end' instead."
            )
        command_type = value.get("type")
        if command_type == "run_dialogue":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'run_dialogue'; "
                "load dialogue JSON into controller variables and drive it with controller entity events instead."
            )
        if command_type == "start_dialogue_session":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'start_dialogue_session'; "
                "keep dialogue state on the controller entity and drive it with normal commands instead."
            )
        if command_type in {
            "dialogue_advance",
            "dialogue_move_selection",
            "dialogue_confirm_choice",
            "dialogue_cancel",
            "close_dialogue",
        }:
            raise ValueError(
                f"{source_name} command '{location}' uses removed command '{command_type}'; "
                "the controller entity should update and clear its own dialogue state through normal commands."
            )
        if command_type in {
            "prepare_text_session",
            "read_text_session",
            "advance_text_session",
            "reset_text_session",
        }:
            raise ValueError(
                f"{source_name} command '{location}' uses removed command '{command_type}'; "
                "store wrapped lines and visible text directly in entity variables instead."
            )
        if command_type == "set_sprite_frame":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_sprite_frame'; "
                "use 'set_visual_frame' instead."
            )
        if command_type == "set_sprite_flip_x":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_sprite_flip_x'; "
                "use 'set_visual_flip_x' instead."
            )
        if command_type == "set_camera_follow_player":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_camera_follow_player'; "
                "use 'set_camera_follow_input_target' or 'set_camera_follow_entity' instead."
            )
        if command_type == "set_var_from_camera":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_var_from_camera'; "
                "use 'set_world_var_from_camera' or 'set_entity_var_from_camera' instead."
            )
        if command_type == "if_var":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'if_var'; "
                "use 'check_world_var' or 'check_entity_var' instead."
            )
        if command_type == "set_var":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_var'; "
                "use 'set_world_var' or 'set_entity_var' instead."
            )
        if command_type == "increment_var":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'increment_var'; "
                "use 'increment_world_var' or 'increment_entity_var' instead."
            )
        if command_type == "set_var_length":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_var_length'; "
                "use 'set_world_var_length' or 'set_entity_var_length' instead."
            )
        if command_type == "append_to_var":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'append_to_var'; "
                "use 'append_world_var' or 'append_entity_var' instead."
            )
        if command_type == "pop_var":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'pop_var'; "
                "use 'pop_world_var' or 'pop_entity_var' instead."
            )
        if command_type == "set_var_from_collection_item":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_var_from_collection_item'; "
                "use 'set_world_var_from_collection_item' or 'set_entity_var_from_collection_item' instead."
            )
        if command_type == "check_var":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'check_var'; "
                "use 'check_world_var' or 'check_entity_var' instead."
            )
        if command_type in _STRICT_ENTITY_TARGET_COMMANDS and value.get("entity_id") in _RESERVED_ENTITY_IDS:
            symbolic_id = value["entity_id"]
            raise ValueError(
                f"{source_name} command '{location}' must not use symbolic entity id '{symbolic_id}' "
                f"with strict primitive '{command_type}'; use '${symbolic_id}_id' or resolve the id "
                "before invoking the primitive."
            )
        for key, item in value.items():
            child_location = f"{location}.{key}"
            _validate_command_tree(item, source_name=source_name, location=child_location)
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_command_tree(
                item,
                source_name=source_name,
                location=f"{location}[{index}]",
            )


def _resolve_entity_instance(
    instance_data: dict[str, Any],
    *,
    project: ProjectContext,
    source_name: str,
) -> dict[str, Any]:
    """Merge a reusable template with a level-specific instance definition."""
    template_id = _normalize_optional_id(instance_data.get("template"))
    if template_id is None:
        resolved = copy.deepcopy(instance_data)
    else:
        template_data = _load_entity_template(template_id, project=project)
        resolved = _deep_merge(template_data, instance_data)

    parameters = resolved.pop("parameters", {})
    if parameters is None:
        parameters = {}
    if not isinstance(parameters, dict):
        raise ValueError(f"{source_name} field 'parameters' must be a JSON object.")
    resolved.pop("template", None)
    substituted = _substitute_parameters(resolved, dict(parameters))
    if not isinstance(substituted, dict):
        raise ValueError(f"{source_name} must resolve to a JSON object after template expansion.")
    return substituted


def _load_entity_template(template_id: str, *, project: ProjectContext) -> dict[str, Any]:
    """Load and cache a reusable entity template by its path-derived id.

    Template ids support subdirectories (e.g. ``"npcs/village_guard"``).
    """
    normalized_id = str(template_id).replace("\\", "/").strip()
    cache_key = (project.project_root.resolve(), normalized_id)
    cached = _TEMPLATE_CACHE.get(cache_key)
    if cached is not None:
        return copy.deepcopy(cached)

    template_path = project.find_entity_template(normalized_id)
    if template_path is None or not template_path.exists():
        raise FileNotFoundError(f"Missing entity template '{normalized_id}'.")

    template_data = json.loads(template_path.read_text(encoding="utf-8"))
    _TEMPLATE_CACHE[cache_key] = template_data
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


def extract_template_parameter_names(
    template_id: str,
    *,
    project: ProjectContext,
) -> list[str]:
    """Return the parameter placeholder names used by a template.

    Scans the template JSON for ``$name`` and ``${name}`` tokens and returns
    a sorted list of unique parameter names.  Useful for seeding the editor
    property inspector with empty values.
    """
    try:
        data = _load_entity_template(template_id, project=project)
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
) -> tuple[int, int, int]:
    """Return one RGB color tuple."""
    if raw_color is None:
        return (255, 255, 255)
    return (int(raw_color[0]), int(raw_color[1]), int(raw_color[2]))


def _parse_entity_events(entity_data: dict[str, Any]) -> dict[str, EntityEvent]:
    """Parse named entity events from the authored ``events`` object."""
    parsed_events: dict[str, EntityEvent] = {}

    if "interact_commands" in entity_data:
        raise ValueError(
            "Entity data must not use 'interact_commands'; define an 'events.interact' entry instead."
        )

    raw_events = entity_data.get("events", {})
    if isinstance(raw_events, dict):
        for event_id, raw_event in raw_events.items():
            if isinstance(raw_event, list):
                _validate_command_tree(
                    raw_event,
                    source_name="Entity events",
                    location=f"events.{event_id}",
                )
                parsed_events[str(event_id)] = EntityEvent(
                    enabled=True,
                    commands=copy.deepcopy(raw_event),
                )
                continue

            if not isinstance(raw_event, dict):
                raise ValueError("Entity events must be objects or command lists.")

            _validate_command_tree(
                raw_event.get("commands", []),
                source_name="Entity events",
                location=f"events.{event_id}.commands",
            )
            parsed_events[str(event_id)] = EntityEvent(
                enabled=bool(raw_event.get("enabled", True)),
                commands=copy.deepcopy(raw_event.get("commands", [])),
            )

    return parsed_events


def _parse_input_map(raw_input_map: Any) -> dict[str, str]:
    """Parse an optional entity-owned logical-input map."""
    if not isinstance(raw_input_map, dict):
        return {}
    return {
        str(action): str(event_name)
        for action, event_name in raw_input_map.items()
    }


def _parse_input_targets(raw_input_targets: Any, *, source_name: str) -> dict[str, str]:
    """Parse an optional area-owned logical-input target mapping."""
    if raw_input_targets is None:
        return {}
    if not isinstance(raw_input_targets, dict):
        raise ValueError(f"Area '{source_name}' field 'input_targets' must be a JSON object.")
    parsed: dict[str, str] = {}
    for raw_action, raw_entity_id in raw_input_targets.items():
        action = str(raw_action).strip()
        if not action:
            raise ValueError(
                f"Area '{source_name}' field 'input_targets' cannot use a blank action key."
            )
        if raw_entity_id in (None, ""):
            parsed[action] = ""
            continue
        parsed[action] = str(raw_entity_id).strip()
    return parsed


def _derive_area_id(
    *,
    source_name: str,
    project: ProjectContext,
    area_name: str | None,
) -> str:
    """Return a stable area id from the source path when available."""
    if source_name not in {"", "<memory>"}:
        source_path = Path(source_name)
        return project.area_id(source_path)

    name = (area_name or "untitled_area").strip().lower()
    slug_chars = [
        char if char.isalnum() else "_"
        for char in name
    ]
    slug = "".join(slug_chars).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug or "untitled_area"


def _optional_string(value: Any, *, field_name: str, source_name: str) -> str | None:
    """Normalize an optional string field and reject non-string values."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{source_name} field '{field_name}' must be a string when present.")
    text = value.strip()
    return text or None


def _normalize_optional_id(value: Any) -> str | None:
    """Return a stripped optional id string."""
    if value is None:
        return None
    text = str(value).replace("\\", "/").strip()
    return text or None


def _require_non_empty_string(data: dict[str, Any], key: str, *, source_name: str) -> str:
    """Read one required non-empty string field from a mapping."""
    if key not in data:
        raise ValueError(f"{source_name} is missing required field '{key}'.")
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source_name} field '{key}' must be a non-empty string.")
    return value.strip()


def _coerce_int(value: Any, *, field_name: str, source_name: str) -> int:
    """Coerce one integer field with a descriptive error."""
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source_name} field '{field_name}' must be an integer.") from exc


def _coerce_required_int(data: dict[str, Any], key: str, *, source_name: str) -> int:
    """Read one required integer field from a mapping."""
    if key not in data:
        raise ValueError(f"{source_name} is missing required field '{key}'.")
    return _coerce_int(data[key], field_name=key, source_name=source_name)


def _coerce_string_list(value: Any, *, field_name: str, source_name: str) -> list[str]:
    """Return a list[str] or raise a descriptive validation error."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{source_name} field '{field_name}' must be a JSON array.")
    return [str(item) for item in value]


# ------------------------------------------------------------------
# Entity template validation
# ------------------------------------------------------------------


class EntityTemplateValidationError(ValueError):
    """Raised when entity template files fail startup validation."""

    def __init__(self, project_root: Path, issues: list[str]) -> None:
        self.project_root = project_root
        self.issues = list(issues)
        super().__init__(
            f"Entity template validation failed for '{project_root}' with {len(self.issues)} issue(s)."
        )

    def format_user_message(self, *, max_issues: int = 8) -> str:
        """Return a short user-facing validation summary."""
        shown_issues = self.issues[:max_issues]
        lines = [
            f"Entity template validation failed with {len(self.issues)} issue(s).",
            "See logs/error.log for full details.",
            "",
            "First issues:",
        ]
        lines.extend(f"- {issue}" for issue in shown_issues)
        hidden_count = len(self.issues) - len(shown_issues)
        if hidden_count > 0:
            lines.append(f"- ...and {hidden_count} more")
        return "\n".join(lines)


def validate_project_entity_templates(project: ProjectContext) -> None:
    """Validate entity template files for a project at startup.

    Checks for duplicate IDs, invalid JSON, and basic structure issues.
    """
    known_ids: dict[str, list[Path]] = {}
    for template_path in project.list_entity_template_files():
        template_id = project.entity_template_id(template_path)
        known_ids.setdefault(template_id, []).append(template_path)

    issues: list[str] = []
    for template_id, paths in sorted(known_ids.items()):
        if len(paths) > 1:
            formatted_paths = ", ".join(str(path) for path in paths)
            issues.append(f"Duplicate entity template id '{template_id}' found in: {formatted_paths}")
            continue

        template_path = paths[0]
        try:
            raw = json.loads(template_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                issues.append(f"{template_path}: entity template must be a JSON object.")
                continue
            _validate_entity_template_raw(
                raw,
                source_name=str(template_path),
            )
        except json.JSONDecodeError as exc:
            issues.append(
                f"{template_path}: invalid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})."
            )
        except Exception as exc:
            issues.append(f"{template_path}: {exc}")

    if issues:
        raise EntityTemplateValidationError(project.project_root, issues)


def log_entity_template_validation_error(error: EntityTemplateValidationError) -> None:
    """Write a full entity template validation failure report to the persistent log."""
    logger.error(
        "Entity template validation failed for %s with %d issue(s):\n%s",
        error.project_root,
        len(error.issues),
        "\n".join(f"- {issue}" for issue in error.issues),
    )


def _validate_entity_template_raw(raw_template: dict[str, Any], *, source_name: str) -> None:
    """Reject removed entity-template fields and command shapes before instantiation."""
    if "sprite" in raw_template:
        raise ValueError(
            f"{source_name} must not use 'sprite'; entities now define a 'visuals' array."
        )
    if "interact_commands" in raw_template:
        raise ValueError(
            f"{source_name} must not use 'interact_commands'; define an 'events.interact' entry instead."
        )

    raw_events = raw_template.get("events", {})
    if raw_events is None:
        return
    if not isinstance(raw_events, dict):
        raise ValueError(f"{source_name} field 'events' must be a JSON object.")

    for event_id, raw_event in raw_events.items():
        if isinstance(raw_event, list):
            _validate_command_tree(
                raw_event,
                source_name=source_name,
                location=f"events.{event_id}",
            )
            continue
        if not isinstance(raw_event, dict):
            raise ValueError(f"{source_name} event '{event_id}' must be an object or command list.")
        raw_commands = raw_event.get("commands", [])
        if not isinstance(raw_commands, list):
            raise ValueError(f"{source_name} event '{event_id}' field 'commands' must be a JSON array.")
        _validate_command_tree(
            raw_commands,
            source_name=source_name,
            location=f"events.{event_id}.commands",
        )


class AreaValidationError(ValueError):
    """Raised when project area files fail startup validation."""

    def __init__(self, project_root: Path, issues: list[str]) -> None:
        self.project_root = project_root
        self.issues = list(issues)
        super().__init__(
            f"Area validation failed for '{project_root}' with {len(self.issues)} issue(s)."
        )

    def format_user_message(self, *, max_issues: int = 8) -> str:
        """Return a short user-facing validation summary."""
        shown_issues = self.issues[:max_issues]
        lines = [
            f"Project area validation failed with {len(self.issues)} issue(s).",
            "See logs/error.log for full details.",
            "",
            "First issues:",
        ]
        lines.extend(f"- {issue}" for issue in shown_issues)
        hidden_count = len(self.issues) - len(shown_issues)
        if hidden_count > 0:
            lines.append(f"- ...and {hidden_count} more")
        return "\n".join(lines)


def validate_project_areas(project: ProjectContext) -> None:
    """Validate area files for a project at startup."""
    known_ids: dict[str, list[Path]] = {}
    for area_path in project.list_area_files():
        area_id = project.area_id(area_path)
        known_ids.setdefault(area_id, []).append(area_path)

    issues: list[str] = []
    global_entity_ids, global_entity_issues = _validate_project_global_entities(project)
    issues.extend(global_entity_issues)
    startup_area = getattr(project, "startup_area", None)
    if startup_area:
        resolved_startup_area = project.resolve_area_reference(startup_area)
        if resolved_startup_area is None:
            issues.append(
                f"project.json: startup_area '{startup_area}' does not match any authored area id."
            )

    for area_id, paths in sorted(known_ids.items()):
        if len(paths) > 1:
            formatted_paths = ", ".join(str(path) for path in paths)
            issues.append(f"Duplicate area id '{area_id}' found in: {formatted_paths}")
            continue

        area_path = paths[0]
        try:
            raw = json.loads(area_path.read_text(encoding="utf-8"))
            _, world = load_area_from_data(
                raw,
                source_name=str(area_path),
                asset_manager=None,
                project=project,
            )
            conflicting_global_ids = sorted(
                entity_id
                for entity_id in world.area_entities
                if entity_id in global_entity_ids
            )
            for entity_id in conflicting_global_ids:
                issues.append(
                    f"{area_path}: area entity id '{entity_id}' conflicts with project.json global entity id '{entity_id}'."
                )
        except json.JSONDecodeError as exc:
            issues.append(
                f"{area_path}: invalid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})."
            )
        except Exception as exc:
            issues.append(f"{area_path}: {exc}")

    if issues:
        raise AreaValidationError(project.project_root, issues)


def _validate_project_global_entities(project: ProjectContext) -> tuple[set[str], list[str]]:
    """Validate project-level global entity instances before runtime installation."""
    global_entity_ids: set[str] = set()
    issues: list[str] = []
    for index, entity_data in enumerate(project.global_entities):
        source_name = f"project.json global_entities[{index}]"
        try:
            entity = instantiate_entity(
                {
                    **copy.deepcopy(entity_data),
                    "scope": "global",
                },
                config.DEFAULT_TILE_SIZE,
                project=project,
                source_name=source_name,
            )
        except Exception as exc:
            issues.append(f"{source_name}: {exc}")
            continue

        if entity.entity_id in global_entity_ids:
            issues.append(f"{source_name} uses duplicate entity id '{entity.entity_id}'.")
            continue
        global_entity_ids.add(entity.entity_id)
    return global_entity_ids, issues


def log_area_validation_error(error: AreaValidationError) -> None:
    """Write a full area validation failure report to the persistent log."""
    logger.error(
        "Area validation failed for %s with %d issue(s):\n%s",
        error.project_root,
        len(error.issues),
        "\n".join(f"- {issue}" for issue in error.issues),
    )
