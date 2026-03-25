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
        "dialogue_paths": ["dialogues/"],
        "variables_path": "variables.json",
        "startup_area": "test_room",
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
- ``dialogues/``
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
    save_dir: Path
    entity_paths: list[Path] = field(default_factory=list)
    asset_paths: list[Path] = field(default_factory=list)
    area_paths: list[Path] = field(default_factory=list)
    command_paths: list[Path] = field(default_factory=list)
    dialogue_paths: list[Path] = field(default_factory=list)
    variables_path: Path | None = None
    startup_area: str | None = None
    active_entity_id: str = "player"
    debug_inspection_enabled: bool = False
    shared_variables: dict[str, Any] = field(default_factory=dict)
    internal_width: int = 320
    internal_height: int = 240
    input_event_names: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_INPUT_EVENT_NAMES)
    )

    # ------------------------------------------------------------------
    # Entity template discovery
    # ------------------------------------------------------------------

    def entity_template_id(self, template_path: Path) -> str:
        """Return the canonical template id for an entity-template file.

        The id is derived from the file's path relative to its entity root
        directory, with the ``.json`` suffix stripped and backslashes
        normalized to forward slashes.
        """
        resolved = template_path.resolve()
        for directory in self.entity_paths:
            try:
                relative = resolved.relative_to(directory.resolve())
                return str(relative.with_suffix("")).replace("\\", "/")
            except ValueError:
                continue
        return template_path.stem

    def list_entity_template_files(self) -> list[Path]:
        """Return all entity-template JSON files across all entity paths."""
        files: list[Path] = []
        seen: set[Path] = set()
        for directory in self.entity_paths:
            if not directory.is_dir():
                continue
            for file_path in sorted(directory.rglob("*.json")):
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
        normalized_id = str(template_id).replace("\\", "/").strip()
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

        for directory in self.entity_paths:
            direct_candidate = directory / relative_id
            if direct_candidate.suffix.lower() != ".json":
                direct_candidate = direct_candidate.with_suffix(".json")
            if direct_candidate.exists():
                _record(direct_candidate)

            for candidate in directory.rglob("*.json"):
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
    # Dialogue definition discovery
    # ------------------------------------------------------------------

    def dialogue_definition_id(self, dialogue_path: Path) -> str:
        """Return the canonical dialogue id for a dialogue-definition file."""
        resolved = dialogue_path.resolve()
        for directory in self.dialogue_paths:
            try:
                relative = resolved.relative_to(directory.resolve())
                return str(relative.with_suffix("")).replace("\\", "/")
            except ValueError:
                continue
        return dialogue_path.stem

    def find_dialogue_definition_matches(self, dialogue_id: str) -> list[Path]:
        """Return all matching dialogue-definition JSON files for the requested id."""
        normalized_id = str(dialogue_id).replace("\\", "/").strip()
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

        for directory in self.dialogue_paths:
            direct_candidate = directory / relative_id
            if direct_candidate.suffix.lower() != ".json":
                direct_candidate = direct_candidate.with_suffix(".json")
            if direct_candidate.exists():
                _record(direct_candidate)

            for candidate in directory.rglob("*.json"):
                relative_candidate = self.dialogue_definition_id(candidate)
                if relative_candidate == normalized_id:
                    _record(candidate)
        return matches

    def list_dialogue_definition_files(self) -> list[Path]:
        """Return all dialogue-definition JSON files across all dialogue paths."""
        files: list[Path] = []
        seen: set[Path] = set()
        for directory in self.dialogue_paths:
            if not directory.is_dir():
                continue
            for file_path in sorted(directory.rglob("*.json")):
                resolved = file_path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                files.append(file_path)
        return files

    def list_dialogue_definition_ids(self) -> list[str]:
        """Return sorted unique dialogue ids from all dialogue paths."""
        ids: set[str] = set()
        for dialogue_path in self.list_dialogue_definition_files():
            ids.add(self.dialogue_definition_id(dialogue_path))
        return sorted(ids)

    def find_dialogue_definition(self, dialogue_id: str) -> Path | None:
        """Return the single matching dialogue-definition JSON file, or *None*."""
        matches = self.find_dialogue_definition_matches(dialogue_id)
        if not matches:
            return None
        if len(matches) > 1:
            match_list = ", ".join(str(path) for path in matches)
            raise ValueError(
                f"Duplicate dialogue definition lookup for '{dialogue_id}'. Matches: {match_list}"
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
        directory, with the ``.json`` suffix stripped and backslashes
        normalized to forward slashes.
        """
        resolved = area_path.resolve()
        for directory in self.area_paths:
            try:
                relative = resolved.relative_to(directory.resolve())
                return str(relative.with_suffix("")).replace("\\", "/")
            except ValueError:
                continue
        return area_path.stem

    def list_area_files(self) -> list[Path]:
        """Return all area JSON files across all area paths."""
        files: list[Path] = []
        seen: set[Path] = set()
        for directory in self.area_paths:
            if not directory.is_dir():
                continue
            for f in sorted(directory.rglob("*.json")):
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
        normalized_id = str(area_id_str).replace("\\", "/").strip()
        if not normalized_id:
            return None

        relative_id = Path(normalized_id)
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
            if direct_candidate.suffix.lower() != ".json":
                direct_candidate = direct_candidate.with_suffix(".json")
            if direct_candidate.exists():
                _record(direct_candidate)

            for candidate in directory.rglob("*.json"):
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
                return str(relative.with_suffix("")).replace("\\", "/")
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
        project_file = project_path / "project.json"
    else:
        project_file = project_path

    project_root = project_file.parent.resolve()

    if not project_file.is_file():
        raise FileNotFoundError(f"Project manifest '{project_file}' was not found.")

    raw: dict[str, Any] = json.loads(project_file.read_text(encoding="utf-8"))

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
    shared_variables = _load_shared_variables(variables_path)

    return ProjectContext(
        project_root=project_root,
        save_dir=(project_root / str(raw.get("save_dir", "saves"))).resolve(),
        entity_paths=_resolve_paths("entity_paths", "entities"),
        asset_paths=_resolve_paths("asset_paths", "assets"),
        area_paths=_resolve_paths("area_paths", "areas"),
        command_paths=_resolve_paths("command_paths", "commands"),
        dialogue_paths=_resolve_paths("dialogue_paths", "dialogues"),
        variables_path=variables_path,
        startup_area=_optional_manifest_str(raw.get("startup_area")),
        active_entity_id=str(raw.get("active_entity_id", "player")),
        debug_inspection_enabled=bool(raw.get("debug_inspection_enabled", False)),
        shared_variables=shared_variables,
        internal_width=_resolve_project_dimension(shared_variables, "internal_width", 320),
        internal_height=_resolve_project_dimension(shared_variables, "internal_height", 240),
        input_event_names=_resolve_input_events(raw.get("input_events")),
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
