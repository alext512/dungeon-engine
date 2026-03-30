"""Project manifest loading and content discovery.

Replicates the runtime's path-resolution conventions from
``dungeon_engine/project.py`` without importing it.  The shared contract
is the ``project.json`` manifest and the filesystem layout it describes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


AREA_ID_PREFIX = "areas"
TEMPLATE_ID_PREFIX = "entity_templates"


@dataclass
class AreaEntry:
    area_id: str
    file_path: Path


@dataclass
class TemplateEntry:
    template_id: str
    file_path: Path


@dataclass
class ProjectManifest:
    project_root: Path
    area_paths: list[Path] = field(default_factory=list)
    entity_template_paths: list[Path] = field(default_factory=list)
    asset_paths: list[Path] = field(default_factory=list)
    command_paths: list[Path] = field(default_factory=list)
    dialogue_paths: list[Path] = field(default_factory=list)
    display_width: int = 320
    display_height: int = 240
    startup_area: str | None = None
    _raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_path_list(
    project_root: Path,
    raw: dict[str, Any],
    key: str,
    default_name: str,
) -> list[Path]:
    """Resolve a manifest path-array key, falling back to a conventional dir."""
    entries = raw.get(key, [])
    if not entries:
        fallback = project_root / default_name
        return [fallback] if fallback.is_dir() else []
    return [(project_root / p).resolve() for p in entries]


def _resolve_optional_path(
    project_root: Path,
    raw_value: Any,
    *,
    fallback_name: str | None = None,
) -> Path | None:
    """Resolve one optional manifest file path with an optional fallback file."""
    if raw_value not in (None, ""):
        return (project_root / str(raw_value)).resolve()
    if fallback_name is None:
        return None
    fallback = (project_root / fallback_name).resolve()
    return fallback if fallback.is_file() else None


def _load_shared_variables(variables_path: Path | None) -> dict[str, Any]:
    """Load project shared variables, or return an empty mapping when absent."""
    if variables_path is None or not variables_path.is_file():
        return {}
    raw = json.loads(variables_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Project variables file '{variables_path}' must contain a JSON object.")
    return raw


def _resolve_project_dimension(shared_variables: dict[str, Any], key: str, default: int) -> int:
    """Read one display dimension from shared variables with a sane fallback."""
    display = shared_variables.get("display", {})
    if not isinstance(display, dict):
        return int(default)
    raw_value = display.get(key, default)
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return int(default)


def _content_id(file_path: Path, root_dirs: list[Path]) -> str:
    """Derive a content id from a file path relative to its root directory."""
    resolved = file_path.resolve()
    for directory in root_dirs:
        try:
            relative = resolved.relative_to(directory.resolve())
            return str(relative.with_suffix("")).replace("\\", "/")
        except ValueError:
            continue
    return file_path.stem


def _prefixed_content_id(file_path: Path, root_dirs: list[Path], *, prefix: str) -> str:
    """Derive one canonical type-prefixed content id from a file path."""
    return f"{prefix}/{_content_id(file_path, root_dirs)}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_manifest(project_path: Path) -> ProjectManifest:
    """Load a ``project.json`` manifest and return a resolved context.

    *project_path* can point at the JSON file directly or at the folder
    that contains it.
    """
    if project_path.is_dir():
        project_file = project_path / "project.json"
    else:
        project_file = project_path

    if not project_file.is_file():
        raise FileNotFoundError(f"Project manifest not found: {project_file}")

    project_root = project_file.parent.resolve()
    raw: dict[str, Any] = json.loads(project_file.read_text(encoding="utf-8"))
    shared_variables_path = _resolve_optional_path(
        project_root,
        raw.get("shared_variables_path"),
        fallback_name="shared_variables.json",
    )
    shared_variables = _load_shared_variables(shared_variables_path)

    return ProjectManifest(
        project_root=project_root,
        area_paths=_resolve_path_list(project_root, raw, "area_paths", "areas"),
        entity_template_paths=_resolve_path_list(
            project_root, raw, "entity_template_paths", "entity_templates"
        ),
        asset_paths=_resolve_path_list(project_root, raw, "asset_paths", "assets"),
        command_paths=_resolve_path_list(
            project_root, raw, "command_paths", "commands"
        ),
        dialogue_paths=_resolve_path_list(
            project_root, raw, "dialogue_paths", "dialogues"
        ),
        display_width=_resolve_project_dimension(shared_variables, "internal_width", 320),
        display_height=_resolve_project_dimension(shared_variables, "internal_height", 240),
        startup_area=raw.get("startup_area"),
        _raw=raw,
    )


def discover_areas(manifest: ProjectManifest) -> list[AreaEntry]:
    """Scan all area paths and return discovered area entries."""
    entries: list[AreaEntry] = []
    seen: set[Path] = set()
    for directory in manifest.area_paths:
        if not directory.is_dir():
            continue
        for f in sorted(directory.rglob("*.json")):
            resolved = f.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            area_id = _prefixed_content_id(
                f,
                manifest.area_paths,
                prefix=AREA_ID_PREFIX,
            )
            entries.append(AreaEntry(area_id=area_id, file_path=f))
    return sorted(entries, key=lambda e: e.area_id)


def discover_entity_templates(manifest: ProjectManifest) -> list[TemplateEntry]:
    """Scan all template paths and return discovered template entries."""
    entries: list[TemplateEntry] = []
    seen: set[Path] = set()
    for directory in manifest.entity_template_paths:
        if not directory.is_dir():
            continue
        for f in sorted(directory.rglob("*.json")):
            resolved = f.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            template_id = _prefixed_content_id(
                f,
                manifest.entity_template_paths,
                prefix=TEMPLATE_ID_PREFIX,
            )
            entries.append(TemplateEntry(template_id=template_id, file_path=f))
    return sorted(entries, key=lambda e: e.template_id)
