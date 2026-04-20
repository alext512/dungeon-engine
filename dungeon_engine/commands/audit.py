"""Startup validation helpers for authored command surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.library import load_project_command_definition
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.json_io import iter_json_data_files, load_json_data


def audit_project_command_surfaces(project) -> list[str]:
    """Return command-authoring validation issues for one project's JSON surfaces."""
    registry = CommandRegistry()
    register_builtin_commands(registry)

    issues: list[str] = []
    for command_path in project.list_command_files():
        raw = _load_json_object(command_path)
        if raw is None:
            continue
        issues.extend(
            _audit_command_list(
                raw.get("commands"),
                registry,
                project=project,
                source_name=str(command_path),
                location="commands",
            )
        )

    for item_path in project.list_item_files():
        raw = _load_json_object(item_path)
        if raw is None:
            continue
        issues.extend(
            _audit_command_list(
                raw.get("use_commands"),
                registry,
                project=project,
                source_name=str(item_path),
                location="use_commands",
            )
        )

    for template_path in project.list_entity_template_files():
        raw = _load_json_object(template_path)
        if raw is None:
            continue
        issues.extend(
            _audit_entity_command_map(
                raw.get("entity_commands"),
                registry,
                project=project,
                source_name=str(template_path),
            )
        )
        issues.extend(
            _audit_entity_dialogue_map(
                raw.get("dialogues"),
                registry,
                project=project,
                source_name=str(template_path),
                location="dialogues",
            )
        )

    for area_path in project.list_area_files():
        raw = _load_json_object(area_path)
        if raw is None:
            continue
        issues.extend(
            _audit_command_list(
                raw.get("enter_commands"),
                registry,
                project=project,
                source_name=str(area_path),
                location="enter_commands",
            )
        )
        raw_entities = raw.get("entities")
        if isinstance(raw_entities, list):
            for index, entity_data in enumerate(raw_entities):
                if not isinstance(entity_data, dict):
                    continue
                issues.extend(
                    _audit_entity_command_map(
                        entity_data.get("entity_commands"),
                        registry,
                        project=project,
                        source_name=f"{area_path} entities[{index}]",
                    )
                )
                issues.extend(
                    _audit_entity_dialogue_map(
                        entity_data.get("dialogues"),
                        registry,
                        project=project,
                        source_name=f"{area_path} entities[{index}]",
                        location="dialogues",
                    )
                )

    for index, entity_data in enumerate(project.global_entities):
        if not isinstance(entity_data, dict):
            continue
        issues.extend(
            _audit_entity_command_map(
                entity_data.get("entity_commands"),
                registry,
                project=project,
                source_name=f"project.json global_entities[{index}]",
            )
        )
        issues.extend(
            _audit_entity_dialogue_map(
                entity_data.get("dialogues"),
                registry,
                project=project,
                source_name=f"project.json global_entities[{index}]",
                location="dialogues",
            )
        )

    dialogue_root = (project.project_root / "dialogues").resolve()
    if dialogue_root.is_dir():
        for dialogue_path in iter_json_data_files(dialogue_root):
            raw = _load_json_object(dialogue_path)
            if raw is None:
                continue
            issues.extend(
                _audit_dialogue_payload(
                    raw,
                    registry,
                    project=project,
                    source_name=str(dialogue_path),
                )
            )

    return list(dict.fromkeys(issues))


def _load_json_object(path: Path) -> dict[str, Any] | None:
    """Load one JSON file as an object when possible, otherwise skip it."""
    try:
        raw = load_json_data(path)
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def _audit_entity_command_map(
    raw_entity_commands: Any,
    registry: CommandRegistry,
    *,
    project: Any,
    source_name: str,
) -> list[str]:
    """Audit one entity_commands object and every contained command list."""
    if not isinstance(raw_entity_commands, dict):
        return []
    issues: list[str] = []
    for command_id, raw_command in raw_entity_commands.items():
        if isinstance(raw_command, list):
            issues.extend(
                _audit_command_list(
                    raw_command,
                    registry,
                    project=project,
                    source_name=source_name,
                    location=f"entity_commands.{command_id}",
                )
            )
            continue
        if isinstance(raw_command, dict):
            issues.extend(
                _audit_command_list(
                    raw_command.get("commands"),
                    registry,
                    project=project,
                    source_name=source_name,
                    location=f"entity_commands.{command_id}.commands",
                )
            )
    return issues


def _audit_entity_dialogue_map(
    raw_dialogues: Any,
    registry: CommandRegistry,
    *,
    project: Any,
    source_name: str,
    location: str,
) -> list[str]:
    """Audit one entity-owned dialogue map and any inline dialogue definitions."""
    if not isinstance(raw_dialogues, dict):
        return []
    issues: list[str] = []
    for raw_dialogue_id, raw_dialogue_entry in raw_dialogues.items():
        dialogue_id = str(raw_dialogue_id).strip()
        if not dialogue_id or not isinstance(raw_dialogue_entry, dict):
            continue
        raw_definition = raw_dialogue_entry.get("dialogue_definition")
        if not isinstance(raw_definition, dict):
            continue
        issues.extend(
            _audit_dialogue_payload(
                raw_definition,
                registry,
                project=project,
                source_name=source_name,
                location=f"{location}.{dialogue_id}.dialogue_definition",
            )
        )
    return issues


def _audit_dialogue_payload(
    raw_dialogue: dict[str, Any],
    registry: CommandRegistry,
    *,
    project: Any,
    source_name: str,
    location: str = "",
) -> list[str]:
    """Audit known inline command surfaces inside one dialogue JSON payload."""
    if not isinstance(raw_dialogue, dict):
        return []
    raw_segments = raw_dialogue.get("segments")
    if not isinstance(raw_segments, list):
        return []

    issues: list[str] = []
    for segment_index, raw_segment in enumerate(raw_segments):
        if not isinstance(raw_segment, dict):
            continue
        segment_location = f"segments[{segment_index}]"
        if location:
            segment_location = f"{location}.{segment_location}"
        issues.extend(
            _audit_dialogue_end_flag(
                raw_segment.get("end_dialogue"),
                source_name=source_name,
                location=f"{segment_location}.end_dialogue",
                subject_name="dialogue segment",
            )
        )
        issues.extend(
            _audit_command_list(
                raw_segment.get("on_start"),
                registry,
                project=project,
                source_name=source_name,
                location=f"{segment_location}.on_start",
            )
        )
        issues.extend(
            _audit_command_list(
                raw_segment.get("on_end"),
                registry,
                project=project,
                source_name=source_name,
                location=f"{segment_location}.on_end",
            )
        )
        raw_options = raw_segment.get("options")
        if not isinstance(raw_options, list):
            continue
        for option_index, raw_option in enumerate(raw_options):
            if not isinstance(raw_option, dict):
                continue
            option_location = f"{segment_location}.options[{option_index}]"
            issues.extend(
                _audit_dialogue_end_flag(
                    raw_option.get("end_dialogue"),
                    source_name=source_name,
                    location=f"{option_location}.end_dialogue",
                    subject_name="dialogue choice option",
                )
            )
            issues.extend(
                _audit_command_list(
                    raw_option.get("commands"),
                    registry,
                    project=project,
                    source_name=source_name,
                    location=f"{option_location}.commands",
                )
            )
            issues.extend(
                _audit_dialogue_option_branch(
                    raw_option,
                    registry,
                    project=project,
                    source_name=source_name,
                    location=option_location,
                )
            )
    return issues


def _audit_dialogue_option_branch(
    raw_option: dict[str, Any],
    registry: CommandRegistry,
    *,
    project: Any,
    source_name: str,
    location: str,
) -> list[str]:
    """Audit first-class child dialogue branches authored on one choice option."""
    issues: list[str] = []
    has_next_path = bool(str(raw_option.get("next_dialogue_path", "")).strip())
    has_next_definition = raw_option.get("next_dialogue_definition") is not None
    if has_next_path and has_next_definition:
        issues.append(
            f"{source_name} ({location}): dialogue choice option must not define both "
            f"'next_dialogue_path' and 'next_dialogue_definition'."
        )
    if has_next_definition:
        issues.extend(
            _audit_dialogue_payload(
                raw_option.get("next_dialogue_definition"),
                registry,
                project=project,
                source_name=source_name,
                location=f"{location}.next_dialogue_definition",
            )
        )
    if (has_next_path or has_next_definition) and _command_list_contains_type(
        raw_option.get("commands"),
        "open_dialogue_session",
    ):
        issues.append(
            f"{source_name} ({location}.commands): dialogue choice option must not combine "
            f"'next_dialogue_path' or 'next_dialogue_definition' with "
            f"'open_dialogue_session' in its commands."
        )
    return issues


def _audit_dialogue_end_flag(
    raw_value: Any,
    *,
    source_name: str,
    location: str,
    subject_name: str,
) -> list[str]:
    """Validate one optional authored end_dialogue flag."""
    if raw_value is None or isinstance(raw_value, bool):
        return []
    return [f"{source_name} ({location}): {subject_name} 'end_dialogue' must be a boolean."]


def _audit_command_list(
    raw_commands: Any,
    registry: CommandRegistry,
    *,
    project: Any,
    source_name: str,
    location: str,
) -> list[str]:
    """Audit one known command-list payload and any nested deferred command data."""
    if not isinstance(raw_commands, list):
        return []

    issues: list[str] = []
    for index, raw_command in enumerate(raw_commands):
        command_location = f"{location}[{index}]"
        if not isinstance(raw_command, dict):
            continue
        issues.extend(
            _audit_command_spec(
                raw_command,
                registry,
                project=project,
                source_name=source_name,
                location=command_location,
            )
        )
    return issues


def _audit_command_spec(
    raw_command: dict[str, Any],
    registry: CommandRegistry,
    *,
    project: Any,
    source_name: str,
    location: str,
) -> list[str]:
    """Audit one command object plus its known deferred child payloads."""
    issues: list[str] = []
    raw_command_type = raw_command.get("type")
    if not isinstance(raw_command_type, str) or not raw_command_type.strip():
        issues.append(f"{source_name} ({location}): command is missing a non-empty 'type'.")
        return issues

    command_name = raw_command_type.strip()
    if not registry.has_command(command_name):
        issues.append(f"{source_name} ({location}): unknown command type '{command_name}'.")
        return issues

    authored_param_names = {str(key) for key in raw_command.keys() if key != "type"}
    unknown_fields = registry.get_unknown_authored_params(command_name, authored_param_names)
    if unknown_fields:
        unknown_list = ", ".join(sorted(unknown_fields))
        issues.append(
            f"{source_name} ({location}): command '{command_name}' contains unknown field(s): "
            f"{unknown_list}."
        )

    if command_name == "run_project_command":
        issues.extend(
            _audit_run_project_command_payloads(
                raw_command,
                registry,
                project=project,
                source_name=source_name,
                location=location,
            )
        )

    for deferred_param, payload_shape in registry.get_deferred_param_shapes(command_name).items():
        if deferred_param not in raw_command:
            continue
        deferred_value = raw_command.get(deferred_param)
        deferred_location = f"{location}.{deferred_param}"
        if payload_shape == "dialogue_definition":
            issues.extend(
                _audit_dialogue_payload(
                    deferred_value,
                    registry,
                    project=project,
                    source_name=source_name,
                    location=deferred_location,
                )
            )
            continue
        if payload_shape == "dialogue_segment_hooks":
            issues.extend(
                _audit_segment_hooks(
                    deferred_value,
                    registry,
                    project=project,
                    source_name=source_name,
                    location=deferred_location,
                )
            )
            continue
        if payload_shape != "command_payload":
            raise ValueError(
                f"Command '{command_name}' declares unsupported deferred payload shape "
                f"'{payload_shape}' for '{deferred_param}'."
            )
        issues.extend(
            _audit_command_payload(
                deferred_value,
                registry,
                project=project,
                source_name=source_name,
                location=deferred_location,
            )
        )
    return issues


def _audit_command_payload(
    payload: Any,
    registry: CommandRegistry,
    *,
    project: Any,
    source_name: str,
    location: str,
) -> list[str]:
    """Audit a deferred command payload stored as one object or one list."""
    if payload is None:
        return []
    if isinstance(payload, dict):
        return _audit_command_spec(
            payload,
            registry,
            project=project,
            source_name=source_name,
            location=location,
        )
    if isinstance(payload, list):
        return _audit_command_list(
            payload,
            registry,
            project=project,
            source_name=source_name,
            location=location,
        )
    return []


def _audit_run_project_command_payloads(
    raw_command: dict[str, Any],
    registry: CommandRegistry,
    *,
    project: Any,
    source_name: str,
    location: str,
) -> list[str]:
    """Audit shaped deferred payload params on one literal project-command call."""
    raw_command_id = raw_command.get("command_id")
    if not isinstance(raw_command_id, str):
        return []
    command_id = raw_command_id.replace("\\", "/").strip()
    if not command_id or command_id.startswith("$"):
        return []

    try:
        definition = load_project_command_definition(project, command_id)
    except Exception:
        return []

    issues: list[str] = []
    for param_name, payload_shape in definition.deferred_param_shapes.items():
        if param_name not in raw_command:
            continue
        payload = raw_command.get(param_name)
        payload_location = f"{location}.{param_name}"
        if payload_shape == "raw_data":
            continue
        if payload_shape == "dialogue_definition":
            issues.extend(
                _audit_dialogue_payload(
                    payload,
                    registry,
                    project=project,
                    source_name=source_name,
                    location=payload_location,
                )
            )
            continue
        if payload_shape == "dialogue_segment_hooks":
            issues.extend(
                _audit_segment_hooks(
                    payload,
                    registry,
                    project=project,
                    source_name=source_name,
                    location=payload_location,
                )
            )
            continue
        if payload_shape == "command_payload":
            issues.extend(
                _audit_command_payload(
                    payload,
                    registry,
                    project=project,
                    source_name=source_name,
                    location=payload_location,
                )
            )
            continue
        raise ValueError(
            f"Project command '{definition.command_id}' declares unsupported deferred payload "
            f"shape '{payload_shape}' for '{param_name}'."
        )
    return issues


def _audit_segment_hooks(
    raw_hooks: Any,
    registry: CommandRegistry,
    *,
    project: Any,
    source_name: str,
    location: str,
) -> list[str]:
    """Audit the known command-bearing surfaces inside dialogue segment hooks."""
    if not isinstance(raw_hooks, list):
        return []

    issues: list[str] = []
    for hook_index, raw_hook in enumerate(raw_hooks):
        if not isinstance(raw_hook, dict):
            continue
        hook_location = f"{location}[{hook_index}]"
        issues.extend(
            _audit_command_list(
                raw_hook.get("on_start"),
                registry,
                project=project,
                source_name=source_name,
                location=f"{hook_location}.on_start",
            )
        )
        issues.extend(
            _audit_command_list(
                raw_hook.get("on_end"),
                registry,
                project=project,
                source_name=source_name,
                location=f"{hook_location}.on_end",
            )
        )
        raw_option_commands = raw_hook.get("option_commands")
        if isinstance(raw_option_commands, list):
            for option_index, option_commands in enumerate(raw_option_commands):
                issues.extend(
                    _audit_command_payload(
                        option_commands,
                        registry,
                        project=project,
                        source_name=source_name,
                        location=f"{hook_location}.option_commands[{option_index}]",
                    )
                )
        raw_by_id = raw_hook.get("option_commands_by_id")
        if isinstance(raw_by_id, dict):
            for option_id, option_commands in raw_by_id.items():
                issues.extend(
                    _audit_command_payload(
                        option_commands,
                        registry,
                        project=project,
                        source_name=source_name,
                        location=f"{hook_location}.option_commands_by_id.{option_id}",
                    )
                )
    return issues


def _command_list_contains_type(raw_commands: Any, command_type: str) -> bool:
    """Return whether one authored command list contains the provided command type."""
    if not isinstance(raw_commands, list):
        return False
    for raw_command in raw_commands:
        if not isinstance(raw_command, dict):
            continue
        if str(raw_command.get("type", "")).strip() == command_type:
            return True
    return False
