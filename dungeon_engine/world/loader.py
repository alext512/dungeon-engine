"""Area loading and validation helpers.

Area parsing stays here, while entity/template loading lives in
``loader_entities.py``.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from dungeon_engine import config
from dungeon_engine.authored_command_validation import validate_authored_command_tree
from dungeon_engine.json_io import JsonDataDecodeError, load_json_data
from dungeon_engine.logging_utils import get_logger
from dungeon_engine.project_context import ProjectContext
from dungeon_engine.world.area import Area, AreaEntryPoint, TileLayer, Tileset
from dungeon_engine.world.loader_entities import (
    _coerce_int,
    _coerce_required_int,
    _require_non_empty_string,
    instantiate_entity as _instantiate_entity,
)
from dungeon_engine.world.persistence_data import PersistentAreaState
from dungeon_engine.world.persistence_snapshots import apply_persistent_area_state
from dungeon_engine.world.world import World

logger = get_logger(__name__)


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
    raw_data = load_json_data(resolved_area_path)
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
    if "name" in raw_data:
        raise ValueError(
            f"Area '{source_name}' must not declare 'name'; areas no longer support a separate display-name field."
        )

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
        area_id=_derive_area_id(source_name=source_name, project=project),
        tile_size=tile_size,
        tilesets=tilesets,
        tile_layers=tile_layers,
        cell_flags=cell_flags,
        entry_points=entry_points,
        camera_defaults=camera_defaults,
        enter_commands=enter_commands,
    )
    area.build_gid_lookup()

    resolved_input_routes = copy.deepcopy(project.input_routes)
    resolved_input_routes.update(
        _parse_input_routes(
            raw_data.get("input_routes"),
            source_name=source_name,
        )
    )
    world = World(default_input_routes=resolved_input_routes)
    world.variables = copy.deepcopy(variables)
    for index, entity_instance in enumerate(raw_entities):
        entity = _instantiate_entity(
            entity_instance,
            area.tile_size,
            project=project,
            source_name=f"{source_name} entities[{index}]",
        )
        world.add_entity(entity)

    if persistent_area_state is not None:
        apply_persistent_area_state(area, world, persistent_area_state, project=project)

    return area, world


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
                render_order=_parse_tile_layer_render_order(raw_layer),
                y_sort=bool(raw_layer.get("y_sort", False)),
                sort_y_offset=float(raw_layer.get("sort_y_offset", 0.0)),
                stack_order=int(raw_layer.get("stack_order", index)),
            )
        )
    return parsed_layers


def _parse_tile_layer_render_order(raw_layer: dict[str, Any]) -> int:
    """Parse one tile layer's unified render band."""
    if "render_order" in raw_layer:
        return int(raw_layer.get("render_order", 0))
    return 0


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
    """Parse explicit cell flags or fall back to cells with no flags."""
    raw_flags = raw_data.get("cell_flags")
    if raw_flags is not None:
        if len(raw_flags) != height or any(len(row) != width for row in raw_flags):
            raise ValueError("cell_flags dimensions must match the tile layers.")
        parsed_flags: list[list[dict[str, Any]]] = []
        for row in raw_flags:
            parsed_row: list[dict[str, Any]] = []
            for cell in row:
                if isinstance(cell, dict):
                    parsed_row.append(_normalize_cell_flags_dict(cell))
                elif cell is None:
                    parsed_row.append({"blocked": False})
                else:
                    raise ValueError("cell_flags values must be objects or null.")
            parsed_flags.append(parsed_row)
        return parsed_flags

    return [[{"blocked": False} for _ in range(width)] for _ in range(height)]


def _normalize_cell_flags_dict(raw_cell: dict[str, Any]) -> dict[str, Any]:
    """Normalize one authored cell-flags object with engine-known defaults."""
    normalized = dict(raw_cell)
    if "blocked" not in normalized:
        normalized["blocked"] = False
    return normalized


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
        validate_authored_command_tree(
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
            "grid_x",
            source_name=f"Area '{source_name}' entry_points.{entry_id}",
        )
        grid_y = _coerce_required_int(
            raw_entry_data,
            "grid_y",
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


def _parse_input_routes(raw_input_routes: Any, *, source_name: str) -> dict[str, dict[str, str]]:
    """Parse an optional area-owned logical-input route mapping."""
    if raw_input_routes is None:
        return {}
    if not isinstance(raw_input_routes, dict):
        raise ValueError(f"Area '{source_name}' field 'input_routes' must be a JSON object.")
    parsed: dict[str, dict[str, str]] = {}
    for raw_action, raw_route in raw_input_routes.items():
        action = str(raw_action).strip()
        if not action:
            raise ValueError(
                f"Area '{source_name}' field 'input_routes' cannot use a blank action key."
            )
        if raw_route in (None, ""):
            parsed[action] = {"entity_id": "", "command_id": ""}
            continue
        if not isinstance(raw_route, dict):
            raise ValueError(
                f"Area '{source_name}' field 'input_routes.{action}' must be a JSON object."
            )
        entity_id = str(raw_route.get("entity_id", "")).strip()
        command_id = str(raw_route.get("command_id", "")).strip()
        if bool(entity_id) != bool(command_id):
            raise ValueError(
                f"Area '{source_name}' field 'input_routes.{action}' must set both "
                "'entity_id' and 'command_id', or leave both blank."
            )
        parsed[action] = {"entity_id": entity_id, "command_id": command_id}
    return parsed


def _derive_area_id(
    *,
    source_name: str,
    project: ProjectContext,
) -> str:
    """Return a stable area id from the source path when available."""
    if source_name not in {"", "<memory>"}:
        source_path = Path(source_name)
        return project.area_id(source_path)
    return "areas/untitled_area"


def _optional_string(value: Any, *, field_name: str, source_name: str) -> str | None:
    """Normalize an optional string field and reject non-string values."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{source_name} field '{field_name}' must be a string when present.")
    text = value.strip()
    return text or None


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
    area_entity_ids: dict[str, list[Path]] = {}
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
            raw = load_json_data(area_path)
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
            for entity_id in world.area_entities:
                area_entity_ids.setdefault(entity_id, []).append(area_path)
        except JsonDataDecodeError as exc:
            issues.append(
                f"{area_path}: invalid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})."
            )
        except Exception as exc:
            issues.append(f"{area_path}: {exc}")

    for entity_id, area_paths in sorted(area_entity_ids.items()):
        if len(area_paths) <= 1:
            continue
        formatted_paths = ", ".join(str(path) for path in area_paths)
        issues.append(f"Duplicate area entity id '{entity_id}' found in: {formatted_paths}")

    if issues:
        raise AreaValidationError(project.project_root, issues)


def _validate_project_global_entities(project: ProjectContext) -> tuple[set[str], list[str]]:
    """Validate project-level global entity instances before runtime installation."""
    global_entity_ids: set[str] = set()
    issues: list[str] = []
    for index, entity_data in enumerate(project.global_entities):
        source_name = f"project.json global_entities[{index}]"
        try:
            entity = _instantiate_entity(
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
