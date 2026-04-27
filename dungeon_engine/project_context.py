"""Runtime-facing project context and ``project.json`` loading helpers.

A project is a folder containing a ``project.json`` file that declares search
paths for game data. All paths inside the manifest are relative to the folder
that contains the ``project.json`` file.

Example ``project.json``::

    {
        "entity_template_paths": ["entity_templates/"],
        "asset_paths": ["assets/"],
        "area_paths": ["areas/"],
        "command_paths": ["commands/"],
        "item_paths": ["items/"],
        "shared_variables_path": "shared_variables.json",
        "startup_area": "areas/title_screen",
        "input_routes": {
            "menu": {
                "entity_id": "pause_controller",
                "command_id": "open_menu"
            }
        },
        "debug_inspection_enabled": true,
        "command_runtime": {
            "max_settle_passes": 128,
            "max_immediate_commands_per_settle": 8192
        }
    }

If any section is omitted the engine falls back to conventional folders inside
the selected project root:

- ``entity_templates/``
- ``assets/``
- ``areas/``
- ``commands/``
- ``items/``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dungeon_engine import config
from dungeon_engine.json_io import (
    dumps_for_clone,
    is_json_data_file,
    iter_json_data_files,
    json_data_path_candidates,
    load_json_data,
    resolve_json_data_file,
    strip_json_data_suffix,
)


AREA_ID_PREFIX = "areas"
ENTITY_TEMPLATE_ID_PREFIX = "entity_templates"
COMMAND_ID_PREFIX = "commands"
ITEM_ID_PREFIX = "items"


@dataclass(frozen=True, slots=True)
class CommandRuntimeConfig:
    """Runtime safety settings for eager command settling."""

    max_settle_passes: int = config.COMMAND_RUNTIME_MAX_SETTLE_PASSES
    max_immediate_commands_per_settle: int = (
        config.COMMAND_RUNTIME_MAX_IMMEDIATE_COMMANDS_PER_SETTLE
    )
    log_settle_usage_peaks: bool = config.COMMAND_RUNTIME_LOG_SETTLE_USAGE_PEAKS
    settle_warning_ratio: float = config.COMMAND_RUNTIME_SETTLE_WARNING_RATIO


def _normalize_content_id(value: str) -> str:
    """Return one normalized authored content id string."""
    return str(value).replace("\\", "/").strip().strip("/")


def _prefix_relative_id(relative_id: str, *, prefix: str) -> str:
    """Return one canonical type-prefixed id from a relative id."""
    normalized_relative = _normalize_content_id(relative_id)
    if not normalized_relative:
        raise ValueError(f"Cannot build a canonical content id for empty relative path under '{prefix}'.")
    return f"{prefix}/{normalized_relative}"


def _relative_id_from_canonical(value: str, *, prefix: str) -> Path | None:
    """Return one relative path from a canonical type-prefixed id.

    Canonical authored ids are logical ids, not literal file paths, so they
    must not include the backing ``.json`` extension.
    """
    normalized = _normalize_content_id(value)
    prefix_with_sep = f"{prefix}/"
    if not normalized.startswith(prefix_with_sep):
        return None
    relative = normalized[len(prefix_with_sep):].strip("/")
    if not relative:
        return None
    if Path(relative).suffix.lower() in (".json", ".json5"):
        return None
    return Path(relative)


@dataclass
class ProjectContext:
    """Resolved search paths for a single project."""

    project_root: Path
    save_dir: Path
    entity_template_paths: list[Path] = field(default_factory=list)
    asset_paths: list[Path] = field(default_factory=list)
    area_paths: list[Path] = field(default_factory=list)
    command_paths: list[Path] = field(default_factory=list)
    item_paths: list[Path] = field(default_factory=list)
    shared_variables_path: Path | None = None
    global_entities: list[dict[str, Any]] = field(default_factory=list)
    startup_area: str | None = None
    input_routes: dict[str, dict[str, str]] = field(default_factory=dict)
    debug_inspection_enabled: bool = False
    shared_variables: dict[str, Any] = field(default_factory=dict)
    internal_width: int = 320
    internal_height: int = 240
    command_runtime: CommandRuntimeConfig = field(default_factory=CommandRuntimeConfig)

    # ------------------------------------------------------------------
    # Entity template discovery
    # ------------------------------------------------------------------

    def entity_template_id(self, template_path: Path) -> str:
        """Return the canonical template id for an entity-template file.

        The id is derived from the file's path relative to its entity root
        directory, with the JSON data suffix stripped, the
        ``entity_templates/`` type prefix added, and backslashes
        normalized to forward slashes.
        """
        resolved = template_path.resolve()
        for directory in self.entity_template_paths:
            try:
                relative = resolved.relative_to(directory.resolve())
                return _prefix_relative_id(
                    str(strip_json_data_suffix(relative)).replace("\\", "/"),
                    prefix=ENTITY_TEMPLATE_ID_PREFIX,
                )
            except ValueError:
                continue
        return _prefix_relative_id(template_path.stem, prefix=ENTITY_TEMPLATE_ID_PREFIX)

    def list_entity_template_files(self) -> list[Path]:
        """Return all entity-template JSON files across all entity paths."""
        files: list[Path] = []
        seen: set[Path] = set()
        for directory in self.entity_template_paths:
            if not directory.is_dir():
                continue
            for file_path in iter_json_data_files(directory):
                resolved = file_path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(file_path)
        return files

    def list_entity_template_ids(self) -> list[str]:
        """Return sorted unique template ids from all entity paths."""
        ids: set[str] = set()
        for template_path in self.list_entity_template_files():
            ids.add(self.entity_template_id(template_path))
        return sorted(ids)

    def find_entity_template_matches(self, template_id: str) -> list[Path]:
        """Return all matching entity-template JSON files for the requested id."""
        normalized_id = _normalize_content_id(template_id)
        if not normalized_id:
            return []

        relative_id = _relative_id_from_canonical(
            normalized_id,
            prefix=ENTITY_TEMPLATE_ID_PREFIX,
        )
        if relative_id is None:
            return []
        matches: list[Path] = []
        seen: set[Path] = set()

        def _record(candidate: Path) -> None:
            resolved = candidate.resolve()
            if resolved in seen:
                return
            seen.add(resolved)
            matches.append(candidate)

        for directory in self.entity_template_paths:
            direct_candidate = directory / relative_id
            for candidate in json_data_path_candidates(direct_candidate):
                if candidate.exists():
                    _record(candidate)

            for candidate in iter_json_data_files(directory):
                relative_candidate = self.entity_template_id(candidate)
                if relative_candidate == normalized_id:
                    _record(candidate)
        return matches

    def find_entity_template(self, template_id: str) -> Path | None:
        """Return the single matching entity-template JSON file, or *None*."""
        matches = self.find_entity_template_matches(template_id)
        if not matches:
            return None
        if len(matches) > 1:
            match_list = ", ".join(str(path) for path in matches)
            raise ValueError(
                f"Duplicate entity template lookup for '{template_id}'. Matches: {match_list}"
            )
        return matches[0]

    # ------------------------------------------------------------------
    # Project command discovery
    # ------------------------------------------------------------------

    def command_id(self, command_path: Path) -> str:
        """Return the canonical id for a project command file."""
        resolved = command_path.resolve()
        for directory in self.command_paths:
            try:
                relative = resolved.relative_to(directory.resolve())
                return _prefix_relative_id(
                    str(strip_json_data_suffix(relative)).replace("\\", "/"),
                    prefix=COMMAND_ID_PREFIX,
                )
            except ValueError:
                continue
        return _prefix_relative_id(command_path.stem, prefix=COMMAND_ID_PREFIX)

    def list_command_files(self) -> list[Path]:
        """Return all project command JSON files across all command paths."""
        files: list[Path] = []
        seen: set[Path] = set()
        for directory in self.command_paths:
            if not directory.is_dir():
                continue
            for file_path in iter_json_data_files(directory):
                resolved = file_path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(file_path)
        return files

    def find_command_matches(self, command_id: str) -> list[Path]:
        """Return all matching project command JSON files for the requested id."""
        normalized_id = _normalize_content_id(command_id)
        if not normalized_id:
            return []

        relative_id = _relative_id_from_canonical(
            normalized_id,
            prefix=COMMAND_ID_PREFIX,
        )
        if relative_id is None:
            return []
        matches: list[Path] = []
        seen: set[Path] = set()

        def _record(candidate: Path) -> None:
            resolved = candidate.resolve()
            if resolved in seen:
                return
            seen.add(resolved)
            matches.append(candidate)

        for directory in self.command_paths:
            direct_candidate = directory / relative_id
            for candidate in json_data_path_candidates(direct_candidate):
                if candidate.exists():
                    _record(candidate)

            for candidate in iter_json_data_files(directory):
                relative_candidate = self.command_id(candidate)
                if relative_candidate == normalized_id:
                    _record(candidate)
        return matches

    def find_command(self, command_id: str) -> Path | None:
        """Return the single matching project command JSON file, or *None*."""
        matches = self.find_command_matches(command_id)
        if not matches:
            return None
        if len(matches) > 1:
            match_list = ", ".join(str(path) for path in matches)
            raise ValueError(
                f"Duplicate command definition lookup for '{command_id}'. Matches: {match_list}"
            )
        return matches[0]

    # ------------------------------------------------------------------
    # Item discovery
    # ------------------------------------------------------------------

    def item_id(self, item_path: Path) -> str:
        """Return the canonical id for one item-definition file."""
        resolved = item_path.resolve()
        for directory in self.item_paths:
            try:
                relative = resolved.relative_to(directory.resolve())
                return _prefix_relative_id(
                    str(strip_json_data_suffix(relative)).replace("\\", "/"),
                    prefix=ITEM_ID_PREFIX,
                )
            except ValueError:
                continue
        return _prefix_relative_id(item_path.stem, prefix=ITEM_ID_PREFIX)

    def list_item_files(self) -> list[Path]:
        """Return all project item JSON files across all item paths."""
        files: list[Path] = []
        seen: set[Path] = set()
        for directory in self.item_paths:
            if not directory.is_dir():
                continue
            for file_path in iter_json_data_files(directory):
                resolved = file_path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(file_path)
        return files

    def list_item_ids(self) -> list[str]:
        """Return sorted unique item ids from all item roots."""
        ids: set[str] = set()
        for item_path in self.list_item_files():
            ids.add(self.item_id(item_path))
        return sorted(ids)

    def find_item_matches(self, item_id: str) -> list[Path]:
        """Return all matching item-definition JSON files for the requested id."""
        normalized_id = _normalize_content_id(item_id)
        if not normalized_id:
            return []

        relative_id = _relative_id_from_canonical(
            normalized_id,
            prefix=ITEM_ID_PREFIX,
        )
        if relative_id is None:
            return []
        matches: list[Path] = []
        seen: set[Path] = set()

        def _record(candidate: Path) -> None:
            resolved = candidate.resolve()
            if resolved in seen:
                return
            seen.add(resolved)
            matches.append(candidate)

        for directory in self.item_paths:
            direct_candidate = directory / relative_id
            for candidate in json_data_path_candidates(direct_candidate):
                if candidate.exists():
                    _record(candidate)

            for candidate in iter_json_data_files(directory):
                relative_candidate = self.item_id(candidate)
                if relative_candidate == normalized_id:
                    _record(candidate)
        return matches

    def find_item(self, item_id: str) -> Path | None:
        """Return the single matching item-definition JSON file, or *None*."""
        matches = self.find_item_matches(item_id)
        if not matches:
            return None
        if len(matches) > 1:
            match_list = ", ".join(str(path) for path in matches)
            raise ValueError(
                f"Duplicate item definition lookup for '{item_id}'. Matches: {match_list}"
            )
        return matches[0]

    # ------------------------------------------------------------------
    # Asset resolution
    # ------------------------------------------------------------------

    def resolve_asset(self, relative_path: str) -> Path | None:
        """Find an asset file across all asset search paths.

        ``relative_path`` is the path stored in area/entity JSON
        (e.g. ``"assets/tiles/basic_tiles.png"``).
        """
        rel_path = Path(relative_path)
        for directory in self.asset_paths:
            # Preferred layout: asset_paths entries point at the asset root
            # itself (for example ".../test_project/assets"), while authored
            # content stores paths like "assets/tiles/foo.png".
            rooted_candidate = directory.parent / rel_path
            if rooted_candidate.exists():
                return rooted_candidate

            direct_candidate = directory / rel_path
            if direct_candidate.exists():
                return direct_candidate
        return None

    # ------------------------------------------------------------------
    # Tileset discovery
    # ------------------------------------------------------------------

    def list_tileset_paths(self) -> list[str]:
        """Scan asset search paths recursively for PNGs.

        Returns paths relative to the asset root they were found in, using
        the same ``"assets/tiles/foo.png"`` convention the engine expects.
        """
        result: dict[str, Path] = {}
        for asset_dir in self.asset_paths:
            if not asset_dir.is_dir():
                continue
            for png in asset_dir.rglob("*.png"):
                # Key = relative from the asset_dir parent so existing JSON
                # paths like "assets/tiles/basic.png" keep working.
                rel = str(png.relative_to(asset_dir.parent)).replace("\\", "/")
                if rel not in result:
                    result[rel] = png
        return sorted(result.keys())

    # ------------------------------------------------------------------
    # Area discovery
    # ------------------------------------------------------------------

    def area_id(self, area_path: Path) -> str:
        """Return the canonical area id for an area JSON file.

        The id is derived from the file's path relative to its area root
        directory, with the JSON data suffix stripped, the ``areas/``
        type prefix added, and backslashes normalized to forward slashes.
        """
        resolved = area_path.resolve()
        for directory in self.area_paths:
            try:
                relative = resolved.relative_to(directory.resolve())
                return _prefix_relative_id(
                    str(strip_json_data_suffix(relative)).replace("\\", "/"),
                    prefix=AREA_ID_PREFIX,
                )
            except ValueError:
                continue
        return _prefix_relative_id(area_path.stem, prefix=AREA_ID_PREFIX)

    def list_area_files(self) -> list[Path]:
        """Return all area JSON files across all area paths."""
        files: list[Path] = []
        seen: set[Path] = set()
        for directory in self.area_paths:
            if not directory.is_dir():
                continue
            for f in iter_json_data_files(directory):
                resolved = f.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    files.append(f)
        return files

    def list_area_ids(self) -> list[str]:
        """Return sorted unique area ids from all area paths."""
        ids: set[str] = set()
        for area_path in self.list_area_files():
            ids.add(self.area_id(area_path))
        return sorted(ids)

    def find_area_by_id(self, area_id_str: str) -> Path | None:
        """Resolve an area id to a single file path, or *None*.

        Raises ``ValueError`` if the id matches multiple files.
        """
        normalized_id = _normalize_content_id(area_id_str)
        if not normalized_id:
            return None

        relative_id = _relative_id_from_canonical(
            normalized_id,
            prefix=AREA_ID_PREFIX,
        )
        if relative_id is None:
            return None
        matches: list[Path] = []
        seen: set[Path] = set()

        def _record(candidate: Path) -> None:
            resolved = candidate.resolve()
            if resolved in seen:
                return
            seen.add(resolved)
            matches.append(candidate)

        for directory in self.area_paths:
            direct_candidate = directory / relative_id
            for candidate in json_data_path_candidates(direct_candidate):
                if candidate.exists():
                    _record(candidate)

            for candidate in iter_json_data_files(directory):
                relative_candidate = self.area_id(candidate)
                if relative_candidate == normalized_id:
                    _record(candidate)

        if not matches:
            return None
        if len(matches) > 1:
            match_list = ", ".join(str(path) for path in matches)
            raise ValueError(
                f"Duplicate area lookup for '{normalized_id}'. Matches: {match_list}"
            )
        return matches[0]

    def resolve_area_reference(self, area_reference: str) -> Path | None:
        """Resolve one strict authored area reference by path-derived area id."""
        reference = str(area_reference).strip()
        if not reference:
            return None
        return self.find_area_by_id(reference)

    def area_path_to_reference(self, area_path: str | Path) -> str:
        """Return a stable area reference suitable for save data.

        Area references are strict path-derived ids, so the area file must live
        under one of the configured area roots.
        """
        resolved = Path(area_path).resolve()
        for directory in self.area_paths:
            try:
                relative = resolved.relative_to(directory.resolve())
                return _prefix_relative_id(
                    str(strip_json_data_suffix(relative)).replace("\\", "/"),
                    prefix=AREA_ID_PREFIX,
                )
            except ValueError:
                continue
        raise ValueError(
            f"Area path '{resolved}' is outside the configured area roots for project '{self.project_root}'."
        )

    def resolve_shared_variable(self, path: str | list[str]) -> Any:
        """Return a nested project-shared variable by dotted path or path-parts list."""
        if isinstance(path, str):
            parts = [part for part in path.split(".") if part]
        else:
            parts = [str(part) for part in path if str(part)]

        value: Any = self.shared_variables
        for part in parts:
            if isinstance(value, dict):
                if part not in value:
                    raise KeyError(f"Unknown project variable path segment '{part}'.")
                value = value[part]
                continue
            if isinstance(value, list):
                try:
                    index = int(part)
                except ValueError as exc:
                    raise KeyError(f"Expected list index at project variable segment '{part}'.") from exc
                try:
                    value = value[index]
                except IndexError as exc:
                    raise KeyError(f"List index '{index}' is out of range for project variable lookup.") from exc
                continue
            raise KeyError(f"Cannot descend into project variable segment '{part}'.")
        return value


def load_project(project_path: Path) -> ProjectContext:
    """Load a project manifest and return a resolved context.

    ``project_path`` can be:
    - A path to ``project.json`` directly
    - A path to a folder that contains ``project.json``
    """
    if project_path.is_dir():
        project_file = resolve_json_data_file(
            project_path,
            basename="project",
            description="Project manifest",
        )
    else:
        project_file = project_path

    project_root = project_file.parent.resolve()

    if not project_file.is_file():
        raise FileNotFoundError(f"Project manifest '{project_file}' was not found.")

    raw: dict[str, Any] = load_json_data(project_file)

    def _resolve_paths(key: str, default_name: str) -> list[Path]:
        entries = raw.get(key, [])
        if not entries:
            fallback = project_root / default_name
            return [fallback] if fallback.is_dir() else []
        return [(project_root / p).resolve() for p in entries]

    shared_variables_path = _resolve_optional_path(
        project_root,
        raw.get("shared_variables_path"),
        fallback_name="shared_variables.json",
    )
    shared_variables = _load_shared_variables(shared_variables_path)

    return ProjectContext(
        project_root=project_root,
        save_dir=(project_root / str(raw.get("save_dir", "saves"))).resolve(),
        entity_template_paths=_resolve_paths("entity_template_paths", "entity_templates"),
        asset_paths=_resolve_paths("asset_paths", "assets"),
        area_paths=_resolve_paths("area_paths", "areas"),
        command_paths=_resolve_paths("command_paths", "commands"),
        item_paths=_resolve_paths("item_paths", "items"),
        shared_variables_path=shared_variables_path,
        global_entities=_resolve_global_entities(raw.get("global_entities")),
        startup_area=_optional_manifest_str(raw.get("startup_area")),
        input_routes=_resolve_input_routes(raw.get("input_routes")),
        debug_inspection_enabled=bool(raw.get("debug_inspection_enabled", False)),
        shared_variables=shared_variables,
        internal_width=_resolve_project_dimension(shared_variables, "internal_width", 320),
        internal_height=_resolve_project_dimension(shared_variables, "internal_height", 240),
        command_runtime=_resolve_command_runtime_config(raw.get("command_runtime")),
    )


def _resolve_optional_path(project_root: Path, raw_value: Any, *, fallback_name: str | None = None) -> Path | None:
    """Resolve an optional manifest file path, falling back to a conventional file if present."""
    if raw_value not in (None, ""):
        configured = (project_root / str(raw_value)).resolve()
        if is_json_data_file(configured):
            return configured
        matches = [candidate.resolve() for candidate in json_data_path_candidates(configured) if candidate.is_file()]
        if len(matches) > 1:
            formatted = ", ".join(str(path) for path in matches)
            raise ValueError(f"Ambiguous project variable file matches: {formatted}")
        if matches:
            return matches[0]
        return configured
    if fallback_name is None:
        return None
    fallback = strip_json_data_suffix(project_root / fallback_name)
    matches = [candidate.resolve() for candidate in json_data_path_candidates(fallback) if candidate.is_file()]
    if len(matches) > 1:
        formatted = ", ".join(str(path) for path in matches)
        raise ValueError(f"Ambiguous fallback project variable file matches: {formatted}")
    return matches[0] if matches else None


def _load_shared_variables(variables_path: Path | None) -> dict[str, Any]:
    """Load project-shared variables from JSON, or return an empty mapping."""
    if variables_path is None or not variables_path.is_file():
        return {}
    raw = load_json_data(variables_path)
    if not isinstance(raw, dict):
        raise ValueError(f"Project variables file '{variables_path}' must contain a JSON object.")
    return raw


def _resolve_project_dimension(shared_variables: dict[str, Any], key: str, default: int) -> int:
    """Read a display dimension from shared project variables with a sane fallback."""
    display = shared_variables.get("display", {})
    if not isinstance(display, dict):
        return int(default)
    raw_value = display.get(key, default)
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return int(default)


def _resolve_command_runtime_config(raw_value: Any) -> CommandRuntimeConfig:
    """Normalize optional command-runtime safety settings from project.json."""
    if raw_value in (None, ""):
        return CommandRuntimeConfig()
    if not isinstance(raw_value, dict):
        raise ValueError("project.json field 'command_runtime' must be a JSON object.")

    def _positive_int(key: str, default: int) -> int:
        raw_setting = raw_value.get(key, default)
        try:
            return max(1, int(raw_setting))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"project.json field 'command_runtime.{key}' must be a positive integer."
            ) from exc

    def _ratio(key: str, default: float) -> float:
        raw_setting = raw_value.get(key, default)
        try:
            return max(0.0, min(1.0, float(raw_setting)))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"project.json field 'command_runtime.{key}' must be a number between 0 and 1."
            ) from exc

    return CommandRuntimeConfig(
        max_settle_passes=_positive_int(
            "max_settle_passes",
            config.COMMAND_RUNTIME_MAX_SETTLE_PASSES,
        ),
        max_immediate_commands_per_settle=_positive_int(
            "max_immediate_commands_per_settle",
            config.COMMAND_RUNTIME_MAX_IMMEDIATE_COMMANDS_PER_SETTLE,
        ),
        log_settle_usage_peaks=bool(
            raw_value.get(
                "log_settle_usage_peaks",
                config.COMMAND_RUNTIME_LOG_SETTLE_USAGE_PEAKS,
            )
        ),
        settle_warning_ratio=_ratio(
            "settle_warning_ratio",
            config.COMMAND_RUNTIME_SETTLE_WARNING_RATIO,
        ),
    )


def _resolve_input_routes(raw_input_routes: Any) -> dict[str, dict[str, str]]:
    """Normalize authored project-level input-route overrides."""
    resolved: dict[str, dict[str, str]] = {}
    if not isinstance(raw_input_routes, dict):
        return resolved
    for raw_action, raw_route in raw_input_routes.items():
        action = str(raw_action).strip()
        if not action:
            continue
        if raw_route in (None, ""):
            resolved[action] = {"entity_id": "", "command_id": ""}
            continue
        if not isinstance(raw_route, dict):
            continue
        entity_id = str(raw_route.get("entity_id", "")).strip()
        command_id = str(raw_route.get("command_id", "")).strip()
        if bool(entity_id) != bool(command_id):
            continue
        resolved[action] = {"entity_id": entity_id, "command_id": command_id}
    return resolved


def _optional_manifest_str(value: Any) -> str | None:
    """Normalize an optional manifest string field."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _resolve_global_entities(raw_global_entities: Any) -> list[dict[str, Any]]:
    """Return a normalized list of project-level global entity instances."""
    if raw_global_entities is None:
        return []
    if not isinstance(raw_global_entities, list):
        raise ValueError("project.json field 'global_entities' must be a JSON array.")
    normalized: list[dict[str, Any]] = []
    for index, entity_data in enumerate(raw_global_entities):
        if not isinstance(entity_data, dict):
            raise ValueError(
                f"project.json field 'global_entities' must contain JSON objects (invalid entry at index {index})."
            )
        normalized.append(dumps_for_clone(entity_data))
    return normalized
