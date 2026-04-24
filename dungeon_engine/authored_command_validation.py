"""Shared validation rules for authored command trees.

These checks are used by multiple content-loading surfaces such as project
command files and entity template/instance command lists. Keeping the rules in
one module reduces drift between startup validation paths.
"""

from __future__ import annotations

from typing import Any


STRICT_ENTITY_TARGET_COMMANDS = frozenset(
    {
        "set_entity_var",
        "add_entity_var",
        "toggle_entity_var",
        "set_entity_var_length",
        "append_entity_var",
        "pop_entity_var",
        "set_entity_command_enabled",
        "set_entity_commands_enabled",
        "set_input_target",
        "set_entity_field",
        "set_entity_fields",
        "route_inputs_to_entity",
        "set_camera_follow_entity",
        "set_entity_grid_position",
        "set_entity_world_position",
        "set_entity_screen_position",
        "move_entity_world_position",
        "move_entity_screen_position",
        "wait_for_move",
        "play_animation",
        "wait_for_animation",
        "stop_animation",
        "set_visual_frame",
        "set_visual_flip_x",
        "set_visible",
        "set_present",
        "set_color",
        "destroy_entity",
    }
)
RESERVED_ENTITY_IDS = frozenset({"self"})


def validate_authored_command_tree(value: Any, *, source_name: str, location: str) -> None:
    """Enforce shared command-tree invariants for authored JSON content."""
    if isinstance(value, dict):
        _validate_authored_command_spec(value, source_name=source_name, location=location)
        for key, item in value.items():
            validate_authored_command_tree(
                item,
                source_name=source_name,
                location=f"{location}.{key}",
            )
        return

    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_authored_command_tree(
                item,
                source_name=source_name,
                location=f"{location}[{index}]",
            )


def _validate_authored_command_spec(
    value: dict[str, Any],
    *,
    source_name: str,
    location: str,
) -> None:
    """Apply one-level authored-command invariants to a possible command spec."""
    command_type = value.get("type")
    if (
        command_type in STRICT_ENTITY_TARGET_COMMANDS
        and value.get("entity_id") in RESERVED_ENTITY_IDS
    ):
        symbolic_id = value["entity_id"]
        raise ValueError(
            f"{source_name} command '{location}' must not use symbolic entity id '{symbolic_id}' "
            f"with strict primitive '{command_type}'; use '${symbolic_id}_id' or resolve the id "
            "before invoking the primitive."
        )
    _validate_strict_camera_follow(value, source_name=source_name, location=location)


def _validate_strict_camera_follow(
    value: dict[str, Any],
    *,
    source_name: str,
    location: str,
) -> None:
    """Reject symbolic follow.entity_id values on strict camera primitives."""
    command_type = value.get("type")
    if command_type != "set_camera_policy":
        return
    raw_follow = value.get("follow")
    if not isinstance(raw_follow, dict):
        return
    symbolic_id = raw_follow.get("entity_id")
    if symbolic_id not in RESERVED_ENTITY_IDS:
        return
    raise ValueError(
        f"{source_name} command '{location}' must not use symbolic entity id '{symbolic_id}' "
        f"inside '{command_type}.follow.entity_id'; use '${symbolic_id}_id' or resolve the id "
        "before invoking the primitive."
    )
