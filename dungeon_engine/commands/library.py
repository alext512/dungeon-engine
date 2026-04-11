"""Project-level reusable JSON command definitions."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dungeon_engine.authored_command_validation import validate_authored_command_tree
from dungeon_engine.json_io import JsonDataDecodeError, iter_json_data_files, load_json_data
from dungeon_engine.logging_utils import get_logger

if TYPE_CHECKING:
    from dungeon_engine.project_context import ProjectContext


logger = get_logger(__name__)


@dataclass(slots=True)
class ProjectCommandDefinition:
    """A reusable JSON-authored command chain."""

    command_id: str
    params: list[str]
    deferred_params: list[str]
    commands: list[dict[str, Any]]
    source_path: Path


@dataclass(slots=True)
class ProjectCommandDatabase:
    """In-memory index of all project command definitions for one project."""

    project_root: Path
    definitions: dict[str, ProjectCommandDefinition]
    discovered_ids: set[str]


_COMMAND_CACHE: dict[Path, dict[str, Any]] = {}
_DATABASE_CACHE: dict[Path, ProjectCommandDatabase] = {}


class ProjectCommandValidationError(ValueError):
    """Raised when project command-library content fails startup validation."""

    def __init__(self, project_root: Path, issues: list[str]) -> None:
        self.project_root = project_root
        self.issues = list(issues)
        super().__init__(
            f"Project command validation failed for '{project_root}' with {len(self.issues)} issue(s)."
        )

    def format_user_message(self, *, max_issues: int = 8) -> str:
        """Return a short user-facing validation summary."""
        shown_issues = self.issues[:max_issues]
        lines = [
            f"Project command validation failed with {len(self.issues)} issue(s).",
            "See logs/error.log for full details.",
            "",
            "First issues:",
        ]
        lines.extend(f"- {issue}" for issue in shown_issues)
        hidden_count = len(self.issues) - len(shown_issues)
        if hidden_count > 0:
            lines.append(f"- ...and {hidden_count} more")
        return "\n".join(lines)


def load_project_command_definition(
    project: ProjectContext,
    command_id: str,
) -> ProjectCommandDefinition:
    """Load one project command definition from the prebuilt project database."""
    resolved_command_id = str(command_id).replace("\\", "/").strip()
    if not resolved_command_id:
        raise FileNotFoundError(
            f"Missing command definition '{command_id}' in project '{project.project_root}'."
        )

    database = build_project_command_database(project)
    definition = database.definitions.get(resolved_command_id)
    if definition is None:
        raise FileNotFoundError(
            f"Missing command definition '{resolved_command_id}' in project '{project.project_root}'."
        )
    return copy.deepcopy(definition)


def build_project_command_database(
    project: ProjectContext,
    *,
    force: bool = False,
) -> ProjectCommandDatabase:
    """Build and cache the full project command database for one project."""
    cache_key = project.project_root.resolve()
    if not force:
        cached_database = _DATABASE_CACHE.get(cache_key)
        if cached_database is not None:
            return cached_database

    database, issues = _scan_project_command_database(project)
    if issues:
        raise ProjectCommandValidationError(project.project_root, issues)
    _DATABASE_CACHE[cache_key] = database
    return database


def _scan_project_command_database(
    project: ProjectContext,
) -> tuple[ProjectCommandDatabase, list[str]]:
    """Scan project command files into an in-memory database plus any validation issues."""
    known_ids: dict[str, list[Path]] = {}
    for command_path in project.list_command_files():
        command_id = project.command_id(command_path)
        known_ids.setdefault(command_id, []).append(command_path)

    issues: list[str] = []
    definitions: dict[str, ProjectCommandDefinition] = {}
    discovered_ids = set(known_ids.keys())
    for command_id, paths in sorted(known_ids.items()):
        if len(paths) > 1:
            formatted_paths = ", ".join(str(path) for path in paths)
            issues.append(f"Duplicate command id '{command_id}' found in: {formatted_paths}")
            continue

        command_path = paths[0]
        try:
            definitions[command_id] = _load_project_command_definition_from_path(
                project,
                command_id,
                command_path,
            )
        except JsonDataDecodeError as exc:
            issues.append(
                f"{command_path}: invalid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})."
            )
        except Exception as exc:
            issues.append(f"{command_path}: {exc}")

    return (
        ProjectCommandDatabase(
            project_root=project.project_root.resolve(),
            definitions=definitions,
            discovered_ids=discovered_ids,
        ),
        issues,
    )


def _load_project_command_definition_from_path(
    project: ProjectContext,
    command_id: str,
    command_path: Path,
) -> ProjectCommandDefinition:
    """Parse and validate one command-definition file from a known path."""
    resolved_command_id = str(command_id).replace("\\", "/").strip()

    cached = _COMMAND_CACHE.get(command_path)
    if cached is None:
        cached = load_json_data(command_path)
        _COMMAND_CACHE[command_path] = cached
    raw = copy.deepcopy(cached)

    if not isinstance(raw, dict):
        raise ValueError(f"Command definition '{resolved_command_id}' must be a JSON object.")

    expected_id = project.command_id(command_path)
    if "id" in raw:
        raise ValueError(
            f"Command definition '{expected_id}' must not declare 'id'; command ids are path-derived."
        )
    resolved_id = expected_id

    raw_params = raw.get("params", [])
    if raw_params is None:
        raw_params = []
    if not isinstance(raw_params, list):
        raise ValueError(f"Command definition '{resolved_id}' must use a list for 'params'.")
    for param in raw_params:
        if not isinstance(param, str) or not param.strip():
            raise ValueError(
                f"Command definition '{resolved_id}' must use non-empty strings inside 'params'."
            )

    raw_deferred_params = raw.get("deferred_params", [])
    if raw_deferred_params is None:
        raw_deferred_params = []
    if not isinstance(raw_deferred_params, list):
        raise ValueError(f"Command definition '{resolved_id}' must use a list for 'deferred_params'.")
    for deferred_param in raw_deferred_params:
        if not isinstance(deferred_param, str) or not deferred_param.strip():
            raise ValueError(
                f"Command definition '{resolved_id}' must use non-empty strings inside 'deferred_params'."
            )
    unknown_deferred = sorted(
        str(name)
        for name in raw_deferred_params
        if str(name) not in {str(param) for param in raw_params}
    )
    if unknown_deferred:
        formatted = ", ".join(unknown_deferred)
        raise ValueError(
            f"Command definition '{resolved_id}' uses unknown deferred parameter(s): {formatted}."
        )

    raw_commands = raw.get("commands")
    if not isinstance(raw_commands, list):
        raise ValueError(f"Command definition '{resolved_id}' must use a list for 'commands'.")
    for index, command in enumerate(raw_commands):
        if not isinstance(command, dict):
            raise ValueError(
                f"Command definition '{resolved_id}' must use JSON objects inside 'commands'."
            )
        validate_authored_command_tree(
            command,
            source_name=f"Command definition '{resolved_id}'",
            location=f"commands[{index}]",
        )

    return ProjectCommandDefinition(
        command_id=resolved_id,
        params=[str(param) for param in raw_params],
        deferred_params=[str(param) for param in raw_deferred_params],
        commands=[dict(command) for command in raw_commands],
        source_path=command_path,
    )
def instantiate_project_command_commands(
    definition: ProjectCommandDefinition,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return a fully substituted command list for one project command invocation."""
    missing = [param for param in definition.params if param not in parameters]
    if missing:
        missing_list = ", ".join(missing)
        raise ValueError(
            f"Project command '{definition.command_id}' is missing required parameters: {missing_list}."
        )

    instantiated = _substitute_parameters(definition.commands, parameters)
    return [dict(command) for command in instantiated]


def _substitute_parameters(value: Any, parameters: dict[str, Any]) -> Any:
    """Replace '$name' or '${name}' strings with provided invocation parameters."""
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


def validate_project_commands(project: ProjectContext) -> None:
    """Validate command-library files and literal run_project_command references for a project."""
    issues: list[str] = []
    database, database_issues = _scan_project_command_database(project)
    issues.extend(database_issues)
    _validate_literal_command_references(
        project,
        set(database.definitions.keys()),
        database.discovered_ids,
        issues,
    )
    if issues:
        raise ProjectCommandValidationError(project.project_root, issues)
    _DATABASE_CACHE[project.project_root.resolve()] = database


def log_project_command_validation_error(error: ProjectCommandValidationError) -> None:
    """Write a full startup-validation failure report to the persistent log."""
    logger.error(
        "Project command validation failed for %s with %d issue(s):\n%s",
        error.project_root,
        len(error.issues),
        "\n".join(f"- {issue}" for issue in error.issues),
    )


def _validate_literal_command_references(
    project: ProjectContext,
    valid_command_ids: set[str],
    discovered_command_ids: set[str],
    issues: list[str],
) -> None:
    """Check literal run_project_command references that can be resolved statically."""
    seen_missing_refs: set[tuple[Path, str, str]] = set()
    for source_path in _iter_command_reference_files(project):
        try:
            raw = load_json_data(source_path)
        except JsonDataDecodeError as exc:
            if not _path_is_under_roots(source_path, project.command_paths):
                issues.append(
                    f"{source_path}: invalid JSON while validating project command references "
                    f"({exc.msg} at line {exc.lineno}, column {exc.colno})."
                )
            continue

        for command_id, location in _find_literal_command_references(raw):
            normalized_id = str(command_id).replace("\\", "/").strip()
            if not normalized_id or normalized_id.startswith("$"):
                continue
            if normalized_id in valid_command_ids or normalized_id in discovered_command_ids:
                continue
            key = (source_path.resolve(), location, normalized_id)
            if key in seen_missing_refs:
                continue
            seen_missing_refs.add(key)
            issues.append(
                f"{source_path} ({location}): missing project command '{normalized_id}'."
            )


def _iter_command_reference_files(project: ProjectContext) -> list[Path]:
    """Return JSON files that may contain literal run_project_command references."""
    files: list[Path] = []
    seen: set[Path] = set()

    def _add_files(root: Path) -> None:
        if not root.is_dir():
            return
        for file_path in iter_json_data_files(root):
            resolved = file_path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(file_path)

    for root in project.command_paths:
        _add_files(root)
    for root in project.entity_template_paths:
        _add_files(root)
    for root in project.area_paths:
        _add_files(root)
    return files


def _path_is_under_roots(path: Path, roots: list[Path]) -> bool:
    """Return True when *path* is inside one of the given roots."""
    resolved = path.resolve()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def _find_literal_command_references(
    value: Any,
    *,
    location: str = "$",
) -> list[tuple[str, str]]:
    """Return literal run_project_command references with a human-readable JSON path."""
    references: list[tuple[str, str]] = []

    if isinstance(value, dict):
        command_type = value.get("type")
        command_id = value.get("command_id")
        if command_type == "run_project_command" and isinstance(command_id, str):
            references.append((command_id, location))

        for key, item in value.items():
            child_location = f"{location}.{key}" if location != "$" else f"$.{key}"
            references.extend(_find_literal_command_references(item, location=child_location))
        return references

    if isinstance(value, list):
        for index, item in enumerate(value):
            child_location = f"{location}[{index}]"
            references.extend(_find_literal_command_references(item, location=child_location))
        return references

    return references

