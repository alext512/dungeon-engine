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
from dungeon_engine.world.area import Area, TileLayer, Tileset
from dungeon_engine.world.entity import Entity, EntityEvent
from dungeon_engine.world.persistence import PersistentAreaState, apply_persistent_area_state
from dungeon_engine.world.world import World


from dungeon_engine.project import ProjectContext

logger = get_logger(__name__)

_TEMPLATE_CACHE: dict[tuple[Path, str], dict[str, Any]] = {}


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

    area = Area(
        area_id=_derive_area_id(source_name=source_name, project=project, area_name=area_name),
        name=area_name or "untitled_area",
        tile_size=tile_size,
        tilesets=tilesets,
        tile_layers=tile_layers,
        cell_flags=cell_flags,
    )
    area.build_gid_lookup()

    configured_player_id = _optional_string(
        raw_data.get("player_id"),
        field_name="player_id",
        source_name=source_name,
    ) or "player"
    default_active_entity_id = str(project.active_entity_id or configured_player_id)
    configured_active_entity_id = _optional_string(
        raw_data.get("active_entity_id"),
        field_name="active_entity_id",
        source_name=source_name,
    )
    world = World(
        player_id=configured_player_id,
        active_entity_id=configured_active_entity_id or default_active_entity_id,
    )
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
    kind = _require_non_empty_string(entity_data, "kind", source_name=source_name)
    grid_x = _coerce_required_int(entity_data, "x", source_name=source_name)
    grid_y = _coerce_required_int(entity_data, "y", source_name=source_name)

    sprite_raw = entity_data.get("sprite", {})
    if sprite_raw is None:
        sprite_raw = {}
    if not isinstance(sprite_raw, dict):
        raise ValueError(f"{source_name} field 'sprite' must be a JSON object when present.")
    sprite_data = dict(sprite_raw)
    raw_frames = sprite_data.get("frames", [0])
    if not isinstance(raw_frames, list):
        raise ValueError(f"{source_name} sprite field 'frames' must be a JSON array.")
    animation_frames = [int(frame) for frame in raw_frames]
    if not animation_frames:
        raise ValueError(f"{source_name} sprite field 'frames' must not be empty.")
    default_pixel_x = float(grid_x * tile_size)
    default_pixel_y = float(grid_y * tile_size)
    entity = Entity(
        entity_id=entity_id,
        kind=kind,
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
        template_id=template_id,
        template_parameters=copy.deepcopy(entity_instance.get("parameters", {})),
        tags=_coerce_string_list(entity_data.get("tags", []), field_name="tags", source_name=source_name),
        sprite_path=str(sprite_data.get("path", "")),
        sprite_frame_width=int(sprite_data.get("frame_width", tile_size)),
        sprite_frame_height=int(sprite_data.get("frame_height", tile_size)),
        animation_frames=animation_frames,
        animation_fps=float(sprite_data.get("animation_fps", 0.0)),
        animate_when_moving=bool(sprite_data.get("animate_when_moving", False)),
        current_frame=int(animation_frames[0]),
        events=_parse_entity_events(entity_data),
        variables=copy.deepcopy(entity_data.get("variables", {})),
        input_map=_parse_input_map(entity_data.get("input_map")),
    )
    return entity


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
    sprite_data: dict[str, Any],
) -> tuple[int, int, int]:
    """Return a tint color, defaulting to white when a sprite is present."""
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

    return parsed_events


def _parse_input_map(raw_input_map: Any) -> dict[str, str]:
    """Parse an optional entity-owned logical-input map."""
    if not isinstance(raw_input_map, dict):
        return {}
    return {
        str(action): str(event_name)
        for action, event_name in raw_input_map.items()
    }


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
        except json.JSONDecodeError as exc:
            issues.append(
                f"{template_path}: invalid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})."
            )

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
            load_area_from_data(raw, source_name=str(area_path), asset_manager=None, project=project)
        except json.JSONDecodeError as exc:
            issues.append(
                f"{area_path}: invalid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})."
            )
        except Exception as exc:
            issues.append(f"{area_path}: {exc}")

    if issues:
        raise AreaValidationError(project.project_root, issues)


def log_area_validation_error(error: AreaValidationError) -> None:
    """Write a full area validation failure report to the persistent log."""
    logger.error(
        "Area validation failed for %s with %d issue(s):\n%s",
        error.project_root,
        len(error.issues),
        "\n".join(f"- {issue}" for issue in error.issues),
    )
