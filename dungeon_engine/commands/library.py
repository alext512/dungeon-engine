"""Project-level reusable JSON command definitions."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dungeon_engine.logging_utils import get_logger

if TYPE_CHECKING:
    from dungeon_engine.project import ProjectContext


logger = get_logger(__name__)
_STRICT_ENTITY_TARGET_COMMANDS = {
    "set_entity_var",
    "increment_entity_var",
    "set_entity_var_length",
    "append_entity_var",
    "pop_entity_var",
    "set_entity_var_from_collection_item",
    "check_entity_var",
    "set_event_enabled",
    "set_events_enabled",
    "set_input_target",
    "set_entity_field",
    "route_inputs_to_entity",
    "set_camera_follow_entity",
    "set_entity_var_from_camera",
    "set_facing",
    "move_entity_one_tile",
    "move_entity",
    "teleport_entity",
    "wait_for_move",
    "play_animation",
    "wait_for_animation",
    "stop_animation",
    "set_visual_frame",
    "set_visual_flip_x",
    "set_visible",
    "set_solid",
    "set_present",
    "set_color",
    "destroy_entity",
}
_RESERVED_ENTITY_IDS = {"self", "actor", "caller"}


@dataclass(slots=True)
class NamedCommandDefinition:
    """A reusable JSON-authored command chain."""

    command_id: str
    params: list[str]
    commands: list[dict[str, Any]]
    source_path: Path


@dataclass(slots=True)
class NamedCommandDatabase:
    """In-memory index of all named command definitions for one project."""

    project_root: Path
    definitions: dict[str, NamedCommandDefinition]
    discovered_ids: set[str]


_COMMAND_CACHE: dict[Path, dict[str, Any]] = {}
_DATABASE_CACHE: dict[Path, NamedCommandDatabase] = {}


class NamedCommandValidationError(ValueError):
    """Raised when project command-library content fails startup validation."""

    def __init__(self, project_root: Path, issues: list[str]) -> None:
        self.project_root = project_root
        self.issues = list(issues)
        super().__init__(
            f"Named-command validation failed for '{project_root}' with {len(self.issues)} issue(s)."
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


def load_named_command_definition(
    project: ProjectContext,
    command_id: str,
) -> NamedCommandDefinition:
    """Load one named command definition from the prebuilt project database."""
    resolved_command_id = str(command_id).replace("\\", "/").strip()
    if not resolved_command_id:
        raise FileNotFoundError(
            f"Missing command definition '{command_id}' in project '{project.project_root}'."
        )

    database = build_named_command_database(project)
    definition = database.definitions.get(resolved_command_id)
    if definition is None:
        raise FileNotFoundError(
            f"Missing command definition '{resolved_command_id}' in project '{project.project_root}'."
        )
    return copy.deepcopy(definition)


def build_named_command_database(
    project: ProjectContext,
    *,
    force: bool = False,
) -> NamedCommandDatabase:
    """Build and cache the full named-command database for one project."""
    cache_key = project.project_root.resolve()
    if not force:
        cached_database = _DATABASE_CACHE.get(cache_key)
        if cached_database is not None:
            return cached_database

    database, issues = _scan_named_command_database(project)
    if issues:
        raise NamedCommandValidationError(project.project_root, issues)
    _DATABASE_CACHE[cache_key] = database
    return database


def _scan_named_command_database(
    project: ProjectContext,
) -> tuple[NamedCommandDatabase, list[str]]:
    """Scan named-command files into an in-memory database plus any validation issues."""
    known_ids: dict[str, list[Path]] = {}
    for command_path in project.list_named_command_files():
        command_id = project.named_command_id(command_path)
        known_ids.setdefault(command_id, []).append(command_path)

    issues: list[str] = []
    definitions: dict[str, NamedCommandDefinition] = {}
    discovered_ids = set(known_ids.keys())
    for command_id, paths in sorted(known_ids.items()):
        if len(paths) > 1:
            formatted_paths = ", ".join(str(path) for path in paths)
            issues.append(f"Duplicate command id '{command_id}' found in: {formatted_paths}")
            continue

        command_path = paths[0]
        try:
            definitions[command_id] = _load_named_command_definition_from_path(
                project,
                command_id,
                command_path,
            )
        except json.JSONDecodeError as exc:
            issues.append(
                f"{command_path}: invalid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})."
            )
        except Exception as exc:
            issues.append(f"{command_path}: {exc}")

    return (
        NamedCommandDatabase(
            project_root=project.project_root.resolve(),
            definitions=definitions,
            discovered_ids=discovered_ids,
        ),
        issues,
    )


def _load_named_command_definition_from_path(
    project: ProjectContext,
    command_id: str,
    command_path: Path,
) -> NamedCommandDefinition:
    """Parse and validate one command-definition file from a known path."""
    resolved_command_id = str(command_id).replace("\\", "/").strip()

    cached = _COMMAND_CACHE.get(command_path)
    if cached is None:
        cached = json.loads(command_path.read_text(encoding="utf-8"))
        _COMMAND_CACHE[command_path] = cached
    raw = copy.deepcopy(cached)

    if not isinstance(raw, dict):
        raise ValueError(f"Command definition '{resolved_command_id}' must be a JSON object.")

    expected_id = project.named_command_id(command_path)
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

    raw_commands = raw.get("commands")
    if not isinstance(raw_commands, list):
        raise ValueError(f"Command definition '{resolved_id}' must use a list for 'commands'.")
    for index, command in enumerate(raw_commands):
        if not isinstance(command, dict):
            raise ValueError(
                f"Command definition '{resolved_id}' must use JSON objects inside 'commands'."
            )
        _validate_command_tree(
            command,
            source_name=f"Command definition '{resolved_id}'",
            location=f"commands[{index}]",
        )

    return NamedCommandDefinition(
        command_id=resolved_id,
        params=[str(param) for param in raw_params],
        commands=[dict(command) for command in raw_commands],
        source_path=command_path,
    )


def _validate_command_tree(value: Any, *, source_name: str, location: str) -> None:
    """Reject removed command-shape fields anywhere inside named-command content."""
    if isinstance(value, dict):
        if "on_complete" in value:
            raise ValueError(
                f"{source_name} command '{location}' must not use 'on_complete'; "
                "use 'on_start' and 'on_end' instead."
            )
        command_type = value.get("type")
        if command_type == "run_dialogue":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'run_dialogue'; "
                "load dialogue JSON into controller variables and drive it with controller entity events instead."
            )
        if command_type == "start_dialogue_session":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'start_dialogue_session'; "
                "keep dialogue state on the controller entity and drive it with normal commands instead."
            )
        if command_type in {
            "dialogue_advance",
            "dialogue_move_selection",
            "dialogue_confirm_choice",
            "dialogue_cancel",
            "close_dialogue",
        }:
            raise ValueError(
                f"{source_name} command '{location}' uses removed command '{command_type}'; "
                "the controller entity should update and clear its own dialogue state through normal commands."
            )
        if command_type in {
            "prepare_text_session",
            "read_text_session",
            "advance_text_session",
            "reset_text_session",
        }:
            raise ValueError(
                f"{source_name} command '{location}' uses removed command '{command_type}'; "
                "store wrapped lines and visible text directly in entity variables instead."
            )
        if command_type == "set_sprite_frame":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_sprite_frame'; "
                "use 'set_visual_frame' instead."
            )
        if command_type == "set_sprite_flip_x":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_sprite_flip_x'; "
                "use 'set_visual_flip_x' instead."
            )
        if command_type == "set_active_entity":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_active_entity'; "
                "route inputs explicitly with 'set_input_target' or 'route_inputs_to_entity'."
            )
        if command_type == "push_active_entity":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'push_active_entity'; "
                "route inputs explicitly with 'set_input_target' or 'route_inputs_to_entity'."
            )
        if command_type == "pop_active_entity":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'pop_active_entity'; "
                "route inputs explicitly with 'set_input_target' or 'route_inputs_to_entity'."
            )
        if command_type == "set_camera_follow_active_entity":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_camera_follow_active_entity'; "
                "use 'set_camera_follow_input_target' or 'set_camera_follow_entity'."
            )
        if command_type == "set_camera_follow_player":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_camera_follow_player'; "
                "use 'set_camera_follow_input_target' or 'set_camera_follow_entity'."
            )
        if command_type == "set_var_from_camera":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_var_from_camera'; "
                "use explicit variable commands with runtime tokens like '$camera.x' instead."
            )
        if command_type == "set_input_event_name":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_input_event_name'; "
                "routed entities should define explicit 'input_map' entries instead."
            )
        if command_type in {"set_world_var_from_camera", "set_entity_var_from_camera"}:
            raise ValueError(
                f"{source_name} command '{location}' uses removed command '{command_type}'; "
                "use explicit variable commands with runtime tokens like '$camera.x' instead."
            )
        if command_type == "if_var":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'if_var'; "
                "use 'check_world_var' or 'check_entity_var' instead."
            )
        if command_type == "set_var":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_var'; "
                "use 'set_world_var' or 'set_entity_var' instead."
            )
        if command_type == "increment_var":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'increment_var'; "
                "use 'increment_world_var' or 'increment_entity_var' instead."
            )
        if command_type == "set_var_length":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_var_length'; "
                "use 'set_world_var_length' or 'set_entity_var_length' instead."
            )
        if command_type == "append_to_var":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'append_to_var'; "
                "use 'append_world_var' or 'append_entity_var' instead."
            )
        if command_type == "pop_var":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'pop_var'; "
                "use 'pop_world_var' or 'pop_entity_var' instead."
            )
        if command_type == "set_var_from_collection_item":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'set_var_from_collection_item'; "
                "use 'set_world_var_from_collection_item' or 'set_entity_var_from_collection_item' instead."
            )
        if command_type == "check_var":
            raise ValueError(
                f"{source_name} command '{location}' uses removed command 'check_var'; "
                "use 'check_world_var' or 'check_entity_var' instead."
            )
        if command_type in _STRICT_ENTITY_TARGET_COMMANDS and value.get("entity_id") in _RESERVED_ENTITY_IDS:
            symbolic_id = value["entity_id"]
            raise ValueError(
                f"{source_name} command '{location}' must not use symbolic entity id '{symbolic_id}' "
                f"with strict primitive '{command_type}'; use '${symbolic_id}_id' or resolve the id "
                "before invoking the primitive."
            )
        for key, item in value.items():
            _validate_command_tree(
                item,
                source_name=source_name,
                location=f"{location}.{key}",
            )
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_command_tree(
                item,
                source_name=source_name,
                location=f"{location}[{index}]",
            )


def instantiate_named_command_commands(
    definition: NamedCommandDefinition,
    parameters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return a fully substituted command list for one named-command invocation."""
    missing = [param for param in definition.params if param not in parameters]
    if missing:
        missing_list = ", ".join(missing)
        raise ValueError(
            f"Named command '{definition.command_id}' is missing required parameters: {missing_list}."
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


def validate_project_named_commands(project: ProjectContext) -> None:
    """Validate command-library files and literal named-command references for a project."""
    issues: list[str] = []
    database, database_issues = _scan_named_command_database(project)
    issues.extend(database_issues)
    _validate_literal_named_command_references(
        project,
        set(database.definitions.keys()),
        database.discovered_ids,
        issues,
    )
    if issues:
        raise NamedCommandValidationError(project.project_root, issues)
    _DATABASE_CACHE[project.project_root.resolve()] = database


def log_named_command_validation_error(error: NamedCommandValidationError) -> None:
    """Write a full startup-validation failure report to the persistent log."""
    logger.error(
        "Named-command validation failed for %s with %d issue(s):\n%s",
        error.project_root,
        len(error.issues),
        "\n".join(f"- {issue}" for issue in error.issues),
    )


def _validate_literal_named_command_references(
    project: ProjectContext,
    valid_command_ids: set[str],
    discovered_command_ids: set[str],
    issues: list[str],
) -> None:
    """Check literal run_named_command references that can be resolved statically."""
    seen_missing_refs: set[tuple[Path, str, str]] = set()
    for source_path in _iter_named_command_reference_files(project):
        try:
            raw = json.loads(source_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            if source_path.suffix.lower() == ".json" and not _path_is_under_roots(source_path, project.named_command_paths):
                issues.append(
                    f"{source_path}: invalid JSON while validating named-command references "
                    f"({exc.msg} at line {exc.lineno}, column {exc.colno})."
                )
            continue

        for command_id, location in _find_literal_named_command_references(raw):
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
                f"{source_path} ({location}): missing named command '{normalized_id}'."
            )


def _iter_named_command_reference_files(project: ProjectContext) -> list[Path]:
    """Return JSON files that may contain literal run_named_command references."""
    files: list[Path] = []
    seen: set[Path] = set()

    def _add_files(root: Path) -> None:
        if not root.is_dir():
            return
        for file_path in sorted(root.rglob("*.json")):
            resolved = file_path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(file_path)

    for root in project.named_command_paths:
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


def _find_literal_named_command_references(
    value: Any,
    *,
    location: str = "$",
) -> list[tuple[str, str]]:
    """Return literal run_named_command references with a human-readable JSON path."""
    references: list[tuple[str, str]] = []

    if isinstance(value, dict):
        command_type = value.get("type")
        command_id = value.get("command_id")
        if command_type == "run_named_command" and isinstance(command_id, str):
            references.append((command_id, location))

        for key, item in value.items():
            child_location = f"{location}.{key}" if location != "$" else f"$.{key}"
            references.extend(_find_literal_named_command_references(item, location=child_location))
        return references

    if isinstance(value, list):
        for index, item in enumerate(value):
            child_location = f"{location}[{index}]"
            references.extend(_find_literal_named_command_references(item, location=child_location))
        return references

    return references

