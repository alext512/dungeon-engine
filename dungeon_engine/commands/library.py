"""Project-level reusable JSON command definitions."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from dungeon_engine.authored_command_validation import validate_authored_command_tree
from dungeon_engine.json_io import JsonDataDecodeError, iter_json_data_files, load_json_data
from dungeon_engine.logging_utils import get_logger

if TYPE_CHECKING:
    from dungeon_engine.project_context import ProjectContext


logger = get_logger(__name__)

ProjectCommandDeferredPayloadShape = Literal[
    "raw_data",
    "command_payload",
    "dialogue_definition",
    "dialogue_segment_hooks",
]
_PROJECT_COMMAND_DEFERRED_PAYLOAD_SHAPES = frozenset(
    {
        "raw_data",
        "command_payload",
        "dialogue_definition",
        "dialogue_segment_hooks",
    }
)
_PROJECT_COMMAND_DEFINITION_KEYS = frozenset(
    {
        "inputs",
        "params",
        "deferred_param_shapes",
        "commands",
    }
)
_PROJECT_COMMAND_INPUT_TYPES = frozenset(
    {
        "string",
        "int",
        "float",
        "bool",
        "enum",
        "json",
        "area_id",
        "entity_id",
        "item_id",
        "dialogue_id",
        "project_command_id",
        "asset_path",
        "image_path",
        "sound_path",
        "visual_id",
        "animation_id",
        "entity_command_id",
        "entity_dialogue_id",
    }
)
_PROJECT_COMMAND_INPUT_PARENT_TYPES = {
    "visual_id": frozenset({"entity_id"}),
    "animation_id": frozenset({"visual_id"}),
    "entity_command_id": frozenset({"entity_id"}),
    "entity_dialogue_id": frozenset({"entity_id"}),
}


@dataclass(slots=True)
class ProjectCommandDefinition:
    """A reusable JSON-authored command chain."""

    command_id: str
    params: list[str]
    inputs: dict[str, dict[str, Any]]
    deferred_param_shapes: dict[str, ProjectCommandDeferredPayloadShape]
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
    unknown_top_level_keys = sorted(
        key for key in raw.keys() if key not in _PROJECT_COMMAND_DEFINITION_KEYS
    )
    if unknown_top_level_keys:
        formatted = ", ".join(unknown_top_level_keys)
        raise ValueError(
            f"Command definition '{expected_id}' contains unknown top-level field(s): {formatted}."
        )
    resolved_id = expected_id

    raw_inputs = raw.get("inputs")
    inputs: dict[str, dict[str, Any]] = {}
    input_param_names: list[str] | None = None
    if raw_inputs is not None:
        if not isinstance(raw_inputs, dict):
            raise ValueError(f"Command definition '{resolved_id}' must use an object for 'inputs'.")
        inputs = _validate_project_command_inputs(resolved_id, raw_inputs)
        input_param_names = list(inputs.keys())

    raw_params = raw.get("params")
    if raw_params is None:
        raw_params = [] if input_param_names is None else input_param_names
    if not isinstance(raw_params, list):
        raise ValueError(f"Command definition '{resolved_id}' must use a list for 'params'.")
    params: list[str] = []
    for param in raw_params:
        if not isinstance(param, str) or not param.strip():
            raise ValueError(
                f"Command definition '{resolved_id}' must use non-empty strings inside 'params'."
            )
        param_name = param.strip()
        if param_name in params:
            raise ValueError(
                f"Command definition '{resolved_id}' declares duplicate parameter '{param_name}'."
            )
        params.append(param_name)
    if input_param_names is not None and params != input_param_names:
        raise ValueError(
            f"Command definition '{resolved_id}' must keep 'params' in the same order as 'inputs' "
            "when both are declared."
        )

    param_names = set(params)
    raw_deferred_param_shapes = raw.get("deferred_param_shapes", {})
    if raw_deferred_param_shapes is None:
        raw_deferred_param_shapes = {}
    if not isinstance(raw_deferred_param_shapes, dict):
        raise ValueError(
            f"Command definition '{resolved_id}' must use an object for 'deferred_param_shapes'."
        )
    deferred_param_shapes: dict[str, ProjectCommandDeferredPayloadShape] = {}
    for raw_name, raw_shape in raw_deferred_param_shapes.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError(
                f"Command definition '{resolved_id}' must use non-empty strings as "
                "'deferred_param_shapes' keys."
        )
        name = raw_name.strip()
        if name not in param_names:
            deferred_param_shapes[name] = "raw_data"
            continue
        if not isinstance(raw_shape, str) or raw_shape not in _PROJECT_COMMAND_DEFERRED_PAYLOAD_SHAPES:
            raise ValueError(
                f"Command definition '{resolved_id}' uses unknown deferred payload shape "
                f"'{raw_shape}' for parameter '{name}'."
            )
        deferred_param_shapes[name] = raw_shape
    unknown_deferred = sorted(
        name for name in deferred_param_shapes if name not in param_names
    )
    if unknown_deferred:
        formatted = ", ".join(unknown_deferred)
        raise ValueError(
            f"Command definition '{resolved_id}' uses unknown deferred parameter shape(s): {formatted}."
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
        params=params,
        inputs=copy.deepcopy(inputs),
        deferred_param_shapes=dict(deferred_param_shapes),
        commands=[dict(command) for command in raw_commands],
        source_path=command_path,
    )


def _validate_project_command_inputs(
    command_id: str,
    raw_inputs: dict[Any, Any],
) -> dict[str, dict[str, Any]]:
    inputs: dict[str, dict[str, Any]] = {}
    input_types: dict[str, str] = {}
    for raw_name, raw_spec in raw_inputs.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError(
                f"Command definition '{command_id}' must use non-empty strings as 'inputs' keys."
            )
        name = raw_name.strip()
        if name in inputs:
            raise ValueError(f"Command definition '{command_id}' declares duplicate input '{name}'.")
        if not isinstance(raw_spec, dict):
            raise ValueError(
                f"Command definition '{command_id}' input '{name}' must be a JSON object."
            )
        spec = copy.deepcopy(raw_spec)
        raw_type = spec.get("type")
        if not isinstance(raw_type, str) or not raw_type.strip():
            raise ValueError(
                f"Command definition '{command_id}' input '{name}' must declare a non-empty type."
            )
        input_type = raw_type.strip()
        if input_type not in _PROJECT_COMMAND_INPUT_TYPES:
            raise ValueError(
                f"Command definition '{command_id}' input '{name}' uses unknown type '{input_type}'."
            )
        spec["type"] = input_type

        raw_of = spec.get("of")
        if raw_of not in (None, ""):
            if not isinstance(raw_of, str) or not raw_of.strip():
                raise ValueError(
                    f"Command definition '{command_id}' input '{name}' must use a non-empty string for 'of'."
                )
            parent_name = raw_of.strip()
            parent_type = input_types.get(parent_name)
            if parent_type is None:
                raise ValueError(
                    f"Command definition '{command_id}' input '{name}' uses unknown or later input "
                    f"'{parent_name}' for 'of'."
                )
            allowed_parent_types = _PROJECT_COMMAND_INPUT_PARENT_TYPES.get(input_type, frozenset())
            if parent_type not in allowed_parent_types:
                raise ValueError(
                    f"Command definition '{command_id}' input '{name}' of type '{input_type}' "
                    f"cannot be scoped by '{parent_name}' of type '{parent_type}'."
                )
            spec["of"] = parent_name
        else:
            spec.pop("of", None)

        if input_type == "enum":
            raw_values = spec.get("values")
            if not isinstance(raw_values, list) or not raw_values:
                raise ValueError(
                    f"Command definition '{command_id}' enum input '{name}' must declare a non-empty "
                    "'values' list."
                )
            values: list[str] = []
            for raw_value in raw_values:
                if not isinstance(raw_value, str) or not raw_value.strip():
                    raise ValueError(
                        f"Command definition '{command_id}' enum input '{name}' values must be "
                        "non-empty strings."
                    )
                value = raw_value.strip()
                if value not in values:
                    values.append(value)
            spec["values"] = values
            default = spec.get("default")
            if default is not None and default not in values:
                raise ValueError(
                    f"Command definition '{command_id}' enum input '{name}' default must be one of "
                    "its values."
                )
        else:
            spec.pop("values", None)

        inputs[name] = spec
        input_types[name] = input_type
    return inputs


def instantiate_project_command_commands(
    definition: ProjectCommandDefinition,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return a fully substituted command list for one project command invocation."""
    resolved_parameters = resolve_project_command_parameters(definition, parameters)
    instantiated = _substitute_parameters(definition.commands, resolved_parameters)
    return [dict(command) for command in instantiated]


def resolve_project_command_parameters(
    definition: ProjectCommandDefinition,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """Return invocation parameters with input defaults applied and required params checked."""
    resolved_parameters = dict(parameters)
    for param_name, spec in definition.inputs.items():
        if param_name not in resolved_parameters and "default" in spec:
            resolved_parameters[param_name] = copy.deepcopy(spec["default"])
    missing = [param for param in definition.params if param not in resolved_parameters]
    if missing:
        missing_list = ", ".join(missing)
        raise ValueError(
            f"Project command '{definition.command_id}' is missing required parameters: {missing_list}."
        )
    return resolved_parameters


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

