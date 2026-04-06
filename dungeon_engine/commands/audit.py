"""Warning-only audit helpers for authored command surfaces."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.registry import CommandRegistry


def audit_project_command_surfaces(project) -> list[str]:
    """Return non-blocking command-authoring warnings for one project's JSON surfaces."""
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
                source_name=str(template_path),
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
                        source_name=f"{area_path} entities[{index}]",
                    )
                )

    for index, entity_data in enumerate(project.global_entities):
        if not isinstance(entity_data, dict):
            continue
        issues.extend(
            _audit_entity_command_map(
                entity_data.get("entity_commands"),
                registry,
                source_name=f"project.json global_entities[{index}]",
            )
        )

    dialogue_root = (project.project_root / "dialogues").resolve()
    if dialogue_root.is_dir():
        for dialogue_path in sorted(dialogue_root.rglob("*.json")):
            raw = _load_json_object(dialogue_path)
            if raw is None:
                continue
            issues.extend(
                _audit_dialogue_payload(
                    raw,
                    registry,
                    source_name=str(dialogue_path),
                )
            )

    return list(dict.fromkeys(issues))


def _load_json_object(path: Path) -> dict[str, Any] | None:
    """Load one JSON file as an object when possible, otherwise skip it."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def _audit_entity_command_map(
    raw_entity_commands: Any,
    registry: CommandRegistry,
    *,
    source_name: str,
) -> list[str]:
    """Audit one entity_commands object and every contained command list."""
    if not isinstance(raw_entity_commands, dict):
        return []
    issues: list[str] = []
    for command_id, raw_command in raw_entity_commands.items():
        if not isinstance(raw_command, dict):
            continue
        issues.extend(
            _audit_command_list(
                raw_command.get("commands"),
                registry,
                source_name=source_name,
                location=f"entity_commands.{command_id}.commands",
            )
        )
    return issues


def _audit_dialogue_payload(
    raw_dialogue: dict[str, Any],
    registry: CommandRegistry,
    *,
    source_name: str,
) -> list[str]:
    """Audit known inline command surfaces inside one dialogue JSON payload."""
    raw_segments = raw_dialogue.get("segments")
    if not isinstance(raw_segments, list):
        return []

    issues: list[str] = []
    for segment_index, raw_segment in enumerate(raw_segments):
        if not isinstance(raw_segment, dict):
            continue
        segment_location = f"segments[{segment_index}]"
        issues.extend(
            _audit_command_list(
                raw_segment.get("on_start"),
                registry,
                source_name=source_name,
                location=f"{segment_location}.on_start",
            )
        )
        issues.extend(
            _audit_command_list(
                raw_segment.get("on_end"),
                registry,
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
            issues.extend(
                _audit_command_list(
                    raw_option.get("commands"),
                    registry,
                    source_name=source_name,
                    location=f"{segment_location}.options[{option_index}].commands",
                )
            )
    return issues


def _audit_command_list(
    raw_commands: Any,
    registry: CommandRegistry,
    *,
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
                source_name=source_name,
                location=command_location,
            )
        )
    return issues


def _audit_command_spec(
    raw_command: dict[str, Any],
    registry: CommandRegistry,
    *,
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

    for deferred_param in registry.get_deferred_params(command_name):
        if deferred_param not in raw_command:
            continue
        deferred_value = raw_command.get(deferred_param)
        deferred_location = f"{location}.{deferred_param}"
        if deferred_param == "segment_hooks":
            issues.extend(
                _audit_segment_hooks(
                    deferred_value,
                    registry,
                    source_name=source_name,
                    location=deferred_location,
                )
            )
            continue
        issues.extend(
            _audit_command_payload(
                deferred_value,
                registry,
                source_name=source_name,
                location=deferred_location,
            )
        )
    return issues


def _audit_command_payload(
    payload: Any,
    registry: CommandRegistry,
    *,
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
            source_name=source_name,
            location=location,
        )
    if isinstance(payload, list):
        return _audit_command_list(
            payload,
            registry,
            source_name=source_name,
            location=location,
        )
    return []


def _audit_segment_hooks(
    raw_hooks: Any,
    registry: CommandRegistry,
    *,
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
                source_name=source_name,
                location=f"{hook_location}.on_start",
            )
        )
        issues.extend(
            _audit_command_list(
                raw_hook.get("on_end"),
                registry,
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
                        source_name=source_name,
                        location=f"{hook_location}.option_commands_by_id.{option_id}",
                    )
                )
    return issues
