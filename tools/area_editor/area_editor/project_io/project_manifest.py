"""Project manifest loading and content discovery for the external editor.

The editor keeps its project-layout interpreter separate from the runtime. The
shared contract is the ``project.json`` manifest and the filesystem layout it
describes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from area_editor.json_io import (
    is_json_data_file,
    iter_json_data_files,
    json_data_path_candidates,
    load_json_data,
    resolve_json_data_file,
    strip_json_data_suffix,
)


AREA_ID_PREFIX = "areas"
TEMPLATE_ID_PREFIX = "entity_templates"
COMMAND_ID_PREFIX = "commands"
ITEM_ID_PREFIX = "items"


@dataclass
class AreaEntry:
    area_id: str
    file_path: Path


@dataclass
class TemplateEntry:
    template_id: str
    file_path: Path


@dataclass
class CommandEntry:
    command_id: str
    file_path: Path


@dataclass
class ItemEntry:
    item_id: str
    file_path: Path


@dataclass
class GlobalEntityEntry:
    entity_id: str
    template_id: str | None
    index: int


@dataclass
class ProjectManifest:
    project_file: Path
    project_root: Path
    area_paths: list[Path] = field(default_factory=list)
    entity_template_paths: list[Path] = field(default_factory=list)
    asset_paths: list[Path] = field(default_factory=list)
    command_paths: list[Path] = field(default_factory=list)
    dialogue_paths: list[Path] = field(default_factory=list)
    item_paths: list[Path] = field(default_factory=list)
    shared_variables_path: Path | None = None
    display_width: int = 320
    display_height: int = 240
    startup_area: str | None = None
    _raw: dict[str, Any] = field(default_factory=dict)


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
        configured = (project_root / str(raw_value)).resolve()
        if is_json_data_file(configured):
            return configured
        matches = [
            candidate.resolve()
            for candidate in json_data_path_candidates(configured)
            if candidate.is_file()
        ]
        if len(matches) > 1:
            formatted = ", ".join(str(path) for path in matches)
            raise ValueError(f"Ambiguous project variable file matches: {formatted}")
        if matches:
            return matches[0]
        return configured
    if fallback_name is None:
        return None
    fallback = strip_json_data_suffix(project_root / fallback_name)
    matches = [
        candidate.resolve()
        for candidate in json_data_path_candidates(fallback)
        if candidate.is_file()
    ]
    if len(matches) > 1:
        formatted = ", ".join(str(path) for path in matches)
        raise ValueError(f"Ambiguous fallback project variable file matches: {formatted}")
    return matches[0] if matches else None


def _load_shared_variables(variables_path: Path | None) -> dict[str, Any]:
    """Load project shared variables, or return an empty mapping when absent."""
    if variables_path is None or not variables_path.is_file():
        return {}
    raw = load_json_data(variables_path)
    if not isinstance(raw, dict):
        raise ValueError(f"Project variables file '{variables_path}' must contain a JSON object.")
    return raw


def _resolve_project_dimension(
    shared_variables: dict[str, Any],
    key: str,
    default: int,
) -> int:
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
            return str(strip_json_data_suffix(relative)).replace("\\", "/")
        except ValueError:
            continue
    return file_path.stem


def _prefixed_content_id(file_path: Path, root_dirs: list[Path], *, prefix: str) -> str:
    """Derive one canonical type-prefixed content id from a file path."""
    return f"{prefix}/{_content_id(file_path, root_dirs)}"


def load_manifest(project_path: Path) -> ProjectManifest:
    """Load a ``project.json`` manifest and return a resolved context.

    *project_path* can point at the JSON file directly or at the folder
    that contains it.
    """
    if project_path.is_dir():
        project_file = resolve_json_data_file(
            project_path,
            basename="project",
            description="Project manifest",
        )
    else:
        project_file = project_path

    if not project_file.is_file():
        raise FileNotFoundError(f"Project manifest not found: {project_file}")

    project_root = project_file.parent.resolve()
    raw: dict[str, Any] = load_json_data(project_file)
    shared_variables_path = _resolve_optional_path(
        project_root,
        raw.get("shared_variables_path"),
        fallback_name="shared_variables.json",
    )
    shared_variables = _load_shared_variables(shared_variables_path)

    return ProjectManifest(
        project_file=project_file.resolve(),
        project_root=project_root,
        area_paths=_resolve_path_list(project_root, raw, "area_paths", "areas"),
        entity_template_paths=_resolve_path_list(
            project_root, raw, "entity_template_paths", "entity_templates"
        ),
        asset_paths=_resolve_path_list(project_root, raw, "asset_paths", "assets"),
        command_paths=_resolve_path_list(project_root, raw, "command_paths", "commands"),
        dialogue_paths=_resolve_path_list(
            project_root, raw, "dialogue_paths", "dialogues"
        ),
        item_paths=_resolve_path_list(project_root, raw, "item_paths", "items"),
        shared_variables_path=shared_variables_path,
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
        for f in iter_json_data_files(directory):
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
        for f in iter_json_data_files(directory):
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


def discover_commands(manifest: ProjectManifest) -> list[CommandEntry]:
    """Scan all command paths and return discovered project-command entries."""
    entries: list[CommandEntry] = []
    seen: set[Path] = set()
    for directory in manifest.command_paths:
        if not directory.is_dir():
            continue
        for f in iter_json_data_files(directory):
            resolved = f.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            command_id = _prefixed_content_id(
                f,
                manifest.command_paths,
                prefix=COMMAND_ID_PREFIX,
            )
            entries.append(CommandEntry(command_id=command_id, file_path=f))
    return sorted(entries, key=lambda e: e.command_id)


def discover_items(manifest: ProjectManifest) -> list[ItemEntry]:
    """Scan all item paths and return discovered item-definition entries."""
    entries: list[ItemEntry] = []
    seen: set[Path] = set()
    for directory in manifest.item_paths:
        if not directory.is_dir():
            continue
        for f in iter_json_data_files(directory):
            resolved = f.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            item_id = _prefixed_content_id(
                f,
                manifest.item_paths,
                prefix=ITEM_ID_PREFIX,
            )
            entries.append(ItemEntry(item_id=item_id, file_path=f))
    return sorted(entries, key=lambda e: e.item_id)


def discover_global_entities(manifest: ProjectManifest) -> list[GlobalEntityEntry]:
    """Return authored global entities in the manifest's stored order."""
    raw_entries = manifest._raw.get("global_entities", [])
    if not isinstance(raw_entries, list):
        return []

    entries: list[GlobalEntityEntry] = []
    for index, raw_entry in enumerate(raw_entries):
        if not isinstance(raw_entry, dict):
            continue
        raw_id = raw_entry.get("id")
        entity_id = (
            str(raw_id).strip()
            if raw_id not in (None, "")
            else f"<unnamed #{index + 1}>"
        )
        raw_template = raw_entry.get("template")
        template_id = str(raw_template).strip() if raw_template not in (None, "") else None
        entries.append(
            GlobalEntityEntry(
                entity_id=entity_id,
                template_id=template_id,
                index=index,
            )
        )
    return entries
