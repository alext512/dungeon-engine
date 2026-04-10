"""Project-level reusable JSON item definitions."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dungeon_engine.authored_command_validation import validate_authored_command_tree
from dungeon_engine.logging_utils import get_logger

if TYPE_CHECKING:
    from dungeon_engine.project_context import ProjectContext


logger = get_logger(__name__)
_ITEM_CACHE: dict[Path, dict[str, Any]] = {}
_DATABASE_CACHE: dict[Path, "ProjectItemDatabase"] = {}


@dataclass(slots=True)
class ItemDefinition:
    """One path-derived reusable project item definition."""

    item_id: str
    name: str
    description: str
    icon: dict[str, Any] | None
    portrait: dict[str, Any] | None
    max_stack: int
    consume_quantity_on_use: int
    use_commands: list[dict[str, Any]]
    source_path: Path


@dataclass(slots=True)
class ProjectItemDatabase:
    """In-memory index of all item definitions for one project."""

    project_root: Path
    definitions: dict[str, ItemDefinition]
    discovered_ids: set[str]


class ItemDefinitionValidationError(ValueError):
    """Raised when project item-definition content fails startup validation."""

    def __init__(self, project_root: Path, issues: list[str]) -> None:
        self.project_root = project_root
        self.issues = list(issues)
        super().__init__(
            f"Item definition validation failed for '{project_root}' with {len(self.issues)} issue(s)."
        )

    def format_user_message(self, *, max_issues: int = 8) -> str:
        """Return a short user-facing validation summary."""
        shown_issues = self.issues[:max_issues]
        lines = [
            f"Item definition validation failed with {len(self.issues)} issue(s).",
            "See logs/error.log for full details.",
            "",
            "First issues:",
        ]
        lines.extend(f"- {issue}" for issue in shown_issues)
        hidden_count = len(self.issues) - len(shown_issues)
        if hidden_count > 0:
            lines.append(f"- ...and {hidden_count} more")
        return "\n".join(lines)


def load_item_definition(
    project: ProjectContext,
    item_id: str,
) -> ItemDefinition:
    """Load one project item definition from the prebuilt project database."""
    resolved_item_id = str(item_id).replace("\\", "/").strip()
    if not resolved_item_id:
        raise FileNotFoundError(
            f"Missing item definition '{item_id}' in project '{project.project_root}'."
        )
    database = build_project_item_database(project)
    definition = database.definitions.get(resolved_item_id)
    if definition is None:
        raise FileNotFoundError(
            f"Missing item definition '{resolved_item_id}' in project '{project.project_root}'."
        )
    return copy.deepcopy(definition)


def build_project_item_database(
    project: ProjectContext,
    *,
    force: bool = False,
) -> ProjectItemDatabase:
    """Build and cache the full item-definition database for one project."""
    cache_key = project.project_root.resolve()
    if not force:
        cached_database = _DATABASE_CACHE.get(cache_key)
        if cached_database is not None:
            return cached_database

    database, issues = _scan_project_item_database(project)
    if issues:
        raise ItemDefinitionValidationError(project.project_root, issues)
    _DATABASE_CACHE[cache_key] = database
    return database


def validate_project_items(project: ProjectContext) -> None:
    """Validate item-definition files for a project."""
    database, issues = _scan_project_item_database(project)
    if issues:
        raise ItemDefinitionValidationError(project.project_root, issues)
    _DATABASE_CACHE[project.project_root.resolve()] = database


def log_item_definition_validation_error(error: ItemDefinitionValidationError) -> None:
    """Write a full startup-validation failure report to the persistent log."""
    logger.error(
        "Item definition validation failed for %s with %d issue(s):\n%s",
        error.project_root,
        len(error.issues),
        "\n".join(f"- {issue}" for issue in error.issues),
    )


def _scan_project_item_database(
    project: ProjectContext,
) -> tuple[ProjectItemDatabase, list[str]]:
    """Scan project item files into one in-memory database plus validation issues."""
    known_ids: dict[str, list[Path]] = {}
    for item_path in project.list_item_files():
        item_id = project.item_id(item_path)
        known_ids.setdefault(item_id, []).append(item_path)

    issues: list[str] = []
    definitions: dict[str, ItemDefinition] = {}
    discovered_ids = set(known_ids.keys())
    for item_id, paths in sorted(known_ids.items()):
        if len(paths) > 1:
            formatted_paths = ", ".join(str(path) for path in paths)
            issues.append(f"Duplicate item id '{item_id}' found in: {formatted_paths}")
            continue

        item_path = paths[0]
        try:
            definitions[item_id] = _load_item_definition_from_path(project, item_id, item_path)
        except json.JSONDecodeError as exc:
            issues.append(
                f"{item_path}: invalid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})."
            )
        except Exception as exc:
            issues.append(f"{item_path}: {exc}")

    return (
        ProjectItemDatabase(
            project_root=project.project_root.resolve(),
            definitions=definitions,
            discovered_ids=discovered_ids,
        ),
        issues,
    )


def _load_item_definition_from_path(
    project: ProjectContext,
    item_id: str,
    item_path: Path,
) -> ItemDefinition:
    """Parse and validate one item-definition file from a known path."""
    resolved_item_id = str(item_id).replace("\\", "/").strip()

    cached = _ITEM_CACHE.get(item_path)
    if cached is None:
        cached = json.loads(item_path.read_text(encoding="utf-8"))
        _ITEM_CACHE[item_path] = cached
    raw = copy.deepcopy(cached)

    if not isinstance(raw, dict):
        raise ValueError(f"Item definition '{resolved_item_id}' must be a JSON object.")

    expected_id = project.item_id(item_path)
    if "id" in raw:
        raise ValueError(
            f"Item definition '{expected_id}' must not declare 'id'; item ids are path-derived."
        )

    name = _require_non_empty_string(
        raw,
        "name",
        source_name=f"Item definition '{resolved_item_id}'",
    )
    description = _optional_string(raw.get("description"))
    icon = _parse_visual_payload(
        raw.get("icon"),
        source_name=f"Item definition '{resolved_item_id}'",
        field_name="icon",
        default_size=16,
    )
    portrait = _parse_visual_payload(
        raw.get("portrait"),
        source_name=f"Item definition '{resolved_item_id}'",
        field_name="portrait",
        default_size=38,
    )
    max_stack = _coerce_positive_int(
        raw.get("max_stack", 1),
        field_name="max_stack",
        source_name=f"Item definition '{resolved_item_id}'",
    )
    consume_quantity_on_use = _coerce_non_negative_int(
        raw.get("consume_quantity_on_use", 0),
        field_name="consume_quantity_on_use",
        source_name=f"Item definition '{resolved_item_id}'",
    )
    use_commands = _parse_use_commands(
        raw.get("use_commands"),
        source_name=f"Item definition '{resolved_item_id}'",
    )
    return ItemDefinition(
        item_id=resolved_item_id,
        name=name,
        description=description,
        icon=icon,
        portrait=portrait,
        max_stack=max_stack,
        consume_quantity_on_use=consume_quantity_on_use,
        use_commands=use_commands,
        source_path=item_path,
    )


def _parse_visual_payload(
    raw_visual: Any,
    *,
    source_name: str,
    field_name: str,
    default_size: int,
) -> dict[str, Any] | None:
    """Validate one optional item image payload used by icon and portrait fields."""
    if raw_visual is None:
        return None
    if not isinstance(raw_visual, dict):
        raise ValueError(f"{source_name} field '{field_name}' must be a JSON object when present.")
    visual = copy.deepcopy(raw_visual)
    path = visual.get("path")
    if not isinstance(path, str) or not path.strip():
        raise ValueError(f"{source_name} field '{field_name}.path' must be a non-empty string.")
    visual["path"] = path.strip()
    visual["frame_width"] = _coerce_positive_int(
        visual.get("frame_width", default_size),
        field_name=f"{field_name}.frame_width",
        source_name=source_name,
    )
    visual["frame_height"] = _coerce_positive_int(
        visual.get("frame_height", default_size),
        field_name=f"{field_name}.frame_height",
        source_name=source_name,
    )
    visual["frame"] = _coerce_non_negative_int(
        visual.get("frame", 0),
        field_name=f"{field_name}.frame",
        source_name=source_name,
    )
    return visual


def _parse_use_commands(raw_commands: Any, *, source_name: str) -> list[dict[str, Any]]:
    """Validate one optional item use-command list."""
    if raw_commands is None:
        return []
    if not isinstance(raw_commands, list):
        raise ValueError(f"{source_name} field 'use_commands' must be a JSON array.")
    parsed_commands: list[dict[str, Any]] = []
    for index, raw_command in enumerate(raw_commands):
        if not isinstance(raw_command, dict):
            raise ValueError(f"{source_name} use_commands[{index}] must be a JSON object.")
        validate_authored_command_tree(
            raw_command,
            source_name=source_name,
            location=f"use_commands[{index}]",
        )
        parsed_commands.append(copy.deepcopy(raw_command))
    return parsed_commands


def _require_non_empty_string(data: dict[str, Any], key: str, *, source_name: str) -> str:
    """Read one required non-empty string field from a mapping."""
    if key not in data:
        raise ValueError(f"{source_name} is missing required field '{key}'.")
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source_name} field '{key}' must be a non-empty string.")
    return value.strip()


def _optional_string(value: Any) -> str:
    """Normalize one optional string field to a safe string default."""
    if value is None:
        return ""
    return str(value)


def _coerce_positive_int(value: Any, *, field_name: str, source_name: str) -> int:
    """Coerce one positive integer field with a descriptive error."""
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source_name} field '{field_name}' must be an integer.") from exc
    if resolved <= 0:
        raise ValueError(f"{source_name} field '{field_name}' must be positive.")
    return resolved


def _coerce_non_negative_int(value: Any, *, field_name: str, source_name: str) -> int:
    """Coerce one non-negative integer field with a descriptive error."""
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source_name} field '{field_name}' must be an integer.") from exc
    if resolved < 0:
        raise ValueError(f"{source_name} field '{field_name}' must be zero or positive.")
    return resolved
