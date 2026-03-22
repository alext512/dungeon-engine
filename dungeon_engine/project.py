"""Project manifest: tells the engine where to find areas, entities, and assets.

A project is a folder containing a ``project.json`` file that declares search
paths for game data. All paths inside the manifest are relative to the folder
that contains the ``project.json`` file.

Example ``project.json``::

    {
        "entity_paths": ["entities/"],
        "asset_paths": ["assets/"],
        "area_paths": ["areas/"],
        "command_paths": ["commands/"],
        "startup_area": "areas/test_room.json",
        "active_entity_id": "player",
        "debug_inspection_enabled": true,
        "input_events": {
            "move_up": "move_up",
            "move_down": "move_down",
            "move_left": "move_left",
            "move_right": "move_right",
            "interact": "interact"
        }
    }

If any section is omitted the engine falls back to conventional folders inside
the selected project root:

- ``entities/``
- ``assets/``
- ``areas/``
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_INPUT_EVENT_NAMES: dict[str, str] = {
    "move_up": "move_up",
    "move_down": "move_down",
    "move_left": "move_left",
    "move_right": "move_right",
    "interact": "interact",
}

@dataclass
class ProjectContext:
    """Resolved search paths for a single project."""

    project_root: Path
    entity_paths: list[Path] = field(default_factory=list)
    asset_paths: list[Path] = field(default_factory=list)
    area_paths: list[Path] = field(default_factory=list)
    command_paths: list[Path] = field(default_factory=list)
    variables_path: Path | None = None
    startup_area: str | None = None
    active_entity_id: str = "player"
    debug_inspection_enabled: bool = False
    shared_variables: dict[str, Any] = field(default_factory=dict)
    input_event_names: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_INPUT_EVENT_NAMES)
    )

    # ------------------------------------------------------------------
    # Entity template discovery
    # ------------------------------------------------------------------

    def list_entity_template_ids(self) -> list[str]:
        """Return sorted unique template ids from all entity paths."""
        ids: set[str] = set()
        for directory in self.entity_paths:
            if directory.is_dir():
                ids.update(p.stem for p in directory.glob("*.json"))
        return sorted(ids)

    def find_entity_template(self, template_id: str) -> Path | None:
        """Return the first matching template path, or *None*."""
        for directory in self.entity_paths:
            candidate = directory / f"{template_id}.json"
            if candidate.exists():
                return candidate
        return None

    # ------------------------------------------------------------------
    # Command definition discovery
    # ------------------------------------------------------------------

    def command_definition_id(self, command_path: Path) -> str:
        """Return the canonical command id for a command-definition file."""
        resolved = command_path.resolve()
        for directory in self.command_paths:
            try:
                relative = resolved.relative_to(directory.resolve())
                return str(relative.with_suffix("")).replace("\\", "/")
            except ValueError:
                continue
        return command_path.stem

    def list_command_definition_files(self) -> list[Path]:
        """Return all command-definition JSON files across all command paths."""
        files: list[Path] = []
        seen: set[Path] = set()
        for directory in self.command_paths:
            if not directory.is_dir():
                continue
            for file_path in sorted(directory.rglob("*.json")):
                resolved = file_path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(file_path)
        return files

    def find_command_definition_matches(self, command_id: str) -> list[Path]:
        """Return all matching command-definition JSON files for the requested id."""
        normalized_id = str(command_id).replace("\\", "/").strip()
        if not normalized_id:
            return []

        relative_id = Path(normalized_id)
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
            if direct_candidate.suffix.lower() != ".json":
                direct_candidate = direct_candidate.with_suffix(".json")
            if direct_candidate.exists():
                _record(direct_candidate)

            for candidate in directory.rglob("*.json"):
                relative_candidate = self.command_definition_id(candidate)
                if relative_candidate == normalized_id:
                    _record(candidate)
        return matches

    def find_command_definition(self, command_id: str) -> Path | None:
        """Return the single matching command-definition JSON file, or *None*."""
        matches = self.find_command_definition_matches(command_id)
        if not matches:
            return None
        if len(matches) > 1:
            match_list = ", ".join(str(path) for path in matches)
            raise ValueError(
                f"Duplicate command definition lookup for '{command_id}'. Matches: {match_list}"
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

    def list_area_files(self) -> list[Path]:
        """Return all area JSON files across all area paths."""
        files: list[Path] = []
        seen: set[Path] = set()
        for directory in self.area_paths:
            if not directory.is_dir():
                continue
            for f in sorted(directory.glob("*.json")):
                resolved = f.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    files.append(f)
        return files

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
        project_file = project_path / "project.json"
    else:
        project_file = project_path

    project_root = project_file.parent.resolve()

    if project_file.exists():
        raw: dict[str, Any] = json.loads(project_file.read_text(encoding="utf-8"))
    else:
        raw = {}

    def _resolve_paths(key: str, default_name: str) -> list[Path]:
        entries = raw.get(key, [])
        if not entries:
            fallback = project_root / default_name
            return [fallback] if fallback.is_dir() else []
        return [(project_root / p).resolve() for p in entries]

    variables_path = _resolve_optional_path(
        project_root,
        raw.get("variables_path"),
        fallback_name="variables.json",
    )

    return ProjectContext(
        project_root=project_root,
        entity_paths=_resolve_paths("entity_paths", "entities"),
        asset_paths=_resolve_paths("asset_paths", "assets"),
        area_paths=_resolve_paths("area_paths", "areas"),
        command_paths=_resolve_paths("command_paths", "commands"),
        variables_path=variables_path,
        startup_area=_optional_manifest_str(raw.get("startup_area")),
        active_entity_id=str(raw.get("active_entity_id", "player")),
        debug_inspection_enabled=bool(raw.get("debug_inspection_enabled", False)),
        shared_variables=_load_shared_variables(variables_path),
        input_event_names=_resolve_input_events(raw.get("input_events")),
    )


def default_project(project_root: Path | None = None) -> ProjectContext:
    """Return a project context using standard folders under the chosen root."""
    root = (project_root or Path.cwd()).resolve()

    def _optional_dir(path: Path) -> list[Path]:
        return [path] if path.is_dir() else []

    return ProjectContext(
        project_root=root,
        entity_paths=_optional_dir(root / "entities"),
        asset_paths=_optional_dir(root / "assets"),
        area_paths=_optional_dir(root / "areas"),
        command_paths=_optional_dir(root / "commands"),
        variables_path=(root / "variables.json") if (root / "variables.json").is_file() else None,
        startup_area=None,
        active_entity_id="player",
        debug_inspection_enabled=False,
        shared_variables=_load_shared_variables((root / "variables.json") if (root / "variables.json").is_file() else None),
        input_event_names=dict(DEFAULT_INPUT_EVENT_NAMES),
    )


def _resolve_optional_path(project_root: Path, raw_value: Any, *, fallback_name: str | None = None) -> Path | None:
    """Resolve an optional manifest file path, falling back to a conventional file if present."""
    if raw_value not in (None, ""):
        return (project_root / str(raw_value)).resolve()
    if fallback_name is None:
        return None
    fallback = (project_root / fallback_name).resolve()
    return fallback if fallback.is_file() else None


def _load_shared_variables(variables_path: Path | None) -> dict[str, Any]:
    """Load project-shared variables from JSON, or return an empty mapping."""
    if variables_path is None or not variables_path.is_file():
        return {}
    raw = json.loads(variables_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Project variables file '{variables_path}' must contain a JSON object.")
    return raw


def _resolve_input_events(raw_input_events: Any) -> dict[str, str]:
    """Merge authored input-event names with engine defaults."""
    resolved = dict(DEFAULT_INPUT_EVENT_NAMES)
    if not isinstance(raw_input_events, dict):
        return resolved
    for action, event_name in raw_input_events.items():
        resolved[str(action)] = str(event_name)
    return resolved


def _optional_manifest_str(value: Any) -> str | None:
    """Normalize an optional manifest string field."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
