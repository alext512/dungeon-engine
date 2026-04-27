"""Shared parsers for structured entity editor fields."""

from __future__ import annotations

import copy
from typing import Any

from area_editor.json_io import JsonDataDecodeError, loads_json_data

ENTITY_BOOL_DEFAULTS = {
    "solid": False,
    "pushable": False,
    "interactable": False,
    "present": True,
    "visible": True,
    "entity_commands_enabled": True,
}
ENTITY_INT_DEFAULTS = {
    "weight": 1,
    "push_strength": 0,
    "collision_push_strength": 0,
    "interaction_priority": 0,
}
ENTITY_FACING_VALUES = ("down", "up", "left", "right")
DEFAULT_ENTITY_COLOR = (255, 255, 255)


def parse_tag_list(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def parse_color(raw_color: object) -> tuple[int, int, int] | None:
    if raw_color is None:
        return None
    if not isinstance(raw_color, (list, tuple)):
        raise ValueError("Color must be a JSON array of three RGB integers.")
    if len(raw_color) != 3:
        raise ValueError("Color must have exactly three RGB values.")

    values: list[int] = []
    for index, value in enumerate(raw_color):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"Color value {index} must be an integer.")
        if value < 0 or value > 255:
            raise ValueError(f"Color value {index} must be between 0 and 255.")
        values.append(int(value))
    return values[0], values[1], values[2]


def default_entity_render_order(space: str) -> int:
    return 10 if str(space).strip().lower() == "world" else 0


def default_entity_y_sort(space: str) -> bool:
    return str(space).strip().lower() == "world"


def parse_persistence_policy(
    raw_persistence: object,
) -> tuple[bool, dict[str, bool]]:
    if raw_persistence is None:
        return False, {}
    if not isinstance(raw_persistence, dict):
        raise ValueError("Persistence must be a JSON object.")

    raw_entity_state = raw_persistence.get("entity_state", False)
    if not isinstance(raw_entity_state, bool):
        raise ValueError("Persistence 'entity_state' must be true or false.")

    raw_variables = raw_persistence.get("variables", {})
    if raw_variables is None:
        raw_variables = {}
    if not isinstance(raw_variables, dict):
        raise ValueError("Persistence 'variables' must be a JSON object.")

    variables: dict[str, bool] = {}
    for raw_name, raw_value in raw_variables.items():
        name = str(raw_name).strip()
        if not name:
            raise ValueError("Persistence variable overrides must not use blank names.")
        if not isinstance(raw_value, bool):
            raise ValueError(f"Persistence variable '{name}' must be true or false.")
        variables[name] = raw_value
    return bool(raw_entity_state), variables


def build_persistence_policy(
    *,
    entity_state: bool,
    variables_text: str,
) -> dict[str, Any] | None:
    raw_variables_text = variables_text.strip()
    variables: dict[str, bool] = {}
    if raw_variables_text:
        try:
            parsed = loads_json_data(
                raw_variables_text,
                source_name="Persistence variables",
            )
        except JsonDataDecodeError as exc:
            raise ValueError(f"Persistence variables must be valid JSON.\n{exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Persistence variables must be a JSON object.")
        for raw_name, raw_value in parsed.items():
            name = str(raw_name).strip()
            if not name:
                raise ValueError("Persistence variables must not use blank names.")
            if not isinstance(raw_value, bool):
                raise ValueError(f"Persistence variable '{name}' must be true or false.")
            variables[name] = raw_value

    if not entity_state and not variables:
        return None

    payload: dict[str, Any] = {"entity_state": bool(entity_state)}
    if variables:
        payload["variables"] = variables
    return payload


def parse_input_map(raw_input_map: object) -> dict[str, str]:
    if raw_input_map is None:
        return {}
    if not isinstance(raw_input_map, dict):
        raise ValueError("Input map must be a JSON object.")

    input_map: dict[str, str] = {}
    for raw_action, raw_command_name in raw_input_map.items():
        if not isinstance(raw_command_name, str):
            raise ValueError(
                f"Input map action '{raw_action}' must map to a string command name."
            )
        input_map[str(raw_action)] = raw_command_name
    return input_map


def build_input_map(
    input_map_text: str,
    *,
    source_name: str = "Input map",
) -> dict[str, str] | None:
    stripped = input_map_text.strip()
    if not stripped:
        return None
    try:
        parsed = loads_json_data(
            stripped,
            source_name=source_name,
        )
    except JsonDataDecodeError as exc:
        raise ValueError(f"Input map must be valid JSON.\n{exc}") from exc
    return parse_input_map(parsed) or None


def parse_entity_commands(raw_entity_commands: object) -> dict[str, Any]:
    if raw_entity_commands is None:
        return {}
    if not isinstance(raw_entity_commands, dict):
        raise ValueError("Entity commands must be a JSON object.")

    entity_commands = copy.deepcopy(raw_entity_commands)
    for raw_command_name, raw_command_definition in entity_commands.items():
        command_name = str(raw_command_name).strip()
        if not command_name:
            raise ValueError("Entity command names must not be blank.")
        if isinstance(raw_command_definition, list):
            continue
        if not isinstance(raw_command_definition, dict):
            raise ValueError(
                f"Entity command '{command_name}' must be an array or an object."
            )
        if "enabled" not in raw_command_definition or "commands" not in raw_command_definition:
            raise ValueError(
                f"Entity command '{command_name}' object form must define "
                "'enabled' and 'commands'."
            )
        if not isinstance(raw_command_definition["enabled"], bool):
            raise ValueError(
                f"Entity command '{command_name}' field 'enabled' must be true or false."
            )
        if not isinstance(raw_command_definition["commands"], list):
            raise ValueError(
                f"Entity command '{command_name}' field 'commands' must be a JSON array."
            )
    return entity_commands


def summarize_entity_commands(entity_commands: dict[str, Any]) -> str:
    count = len(entity_commands)
    if count == 0:
        return "No entity commands"
    if count == 1:
        return "1 entity command"
    return f"{count} entity commands"


def entity_command_command_list(entity_command_definition: object) -> list[dict[str, Any]]:
    if isinstance(entity_command_definition, list):
        return copy.deepcopy(entity_command_definition)
    if isinstance(entity_command_definition, dict):
        raw_commands = entity_command_definition.get("commands", [])
        return copy.deepcopy(raw_commands) if isinstance(raw_commands, list) else []
    return []


def replace_entity_command_command_list(
    entity_command_definition: object,
    commands: list[dict[str, Any]],
) -> object:
    if isinstance(entity_command_definition, dict):
        updated = copy.deepcopy(entity_command_definition)
        updated["commands"] = copy.deepcopy(commands)
        return updated
    return copy.deepcopy(commands)


def suggested_entity_command_copy_name(
    command_name: str,
    existing_names: set[str],
) -> str:
    base = str(command_name).strip() or "command"
    prefix = f"{base}_copy"
    if prefix not in existing_names:
        return prefix
    index = 2
    while f"{prefix}_{index}" in existing_names:
        index += 1
    return f"{prefix}_{index}"


def build_entity_commands(
    entity_commands_text: str,
    *,
    source_name: str = "Entity commands",
) -> dict[str, Any] | None:
    stripped = entity_commands_text.strip()
    if not stripped:
        return None
    try:
        parsed = loads_json_data(
            stripped,
            source_name=source_name,
        )
    except JsonDataDecodeError as exc:
        raise ValueError(f"Entity commands must be valid JSON.\n{exc}") from exc
    return parse_entity_commands(parsed) or None


def parse_inventory(raw_inventory: object) -> dict[str, Any] | None:
    if raw_inventory is None:
        return None
    if not isinstance(raw_inventory, dict):
        raise ValueError("Inventory must be a JSON object.")
    if "max_stacks" not in raw_inventory:
        raise ValueError("Inventory must define 'max_stacks'.")

    max_stacks = _parse_non_negative_int(
        raw_inventory["max_stacks"],
        field_name="inventory.max_stacks",
    )
    raw_stacks = raw_inventory.get("stacks", [])
    if raw_stacks is None:
        raw_stacks = []
    stacks = parse_inventory_stacks(raw_stacks)
    if len(stacks) > max_stacks:
        raise ValueError(
            f"Inventory uses {len(stacks)} stack(s) but max_stacks is {max_stacks}."
        )

    inventory = copy.deepcopy(raw_inventory)
    inventory["max_stacks"] = max_stacks
    inventory["stacks"] = stacks
    return inventory


def parse_inventory_stacks(raw_stacks: object) -> list[dict[str, Any]]:
    if not isinstance(raw_stacks, list):
        raise ValueError("Inventory 'stacks' must be a JSON array.")

    stacks: list[dict[str, Any]] = []
    for index, raw_stack in enumerate(raw_stacks):
        if not isinstance(raw_stack, dict):
            raise ValueError(f"Inventory stacks[{index}] must be a JSON object.")
        raw_item_id = raw_stack.get("item_id")
        if not isinstance(raw_item_id, str) or not raw_item_id.strip():
            raise ValueError(
                f"Inventory stacks[{index}] field 'item_id' must be a non-empty string."
            )
        quantity = _parse_positive_int(
            raw_stack.get("quantity"),
            field_name=f"inventory.stacks[{index}].quantity",
        )
        stack = copy.deepcopy(raw_stack)
        stack["item_id"] = raw_item_id.strip()
        stack["quantity"] = quantity
        stacks.append(stack)
    return stacks


def build_inventory(
    *,
    enabled: bool,
    max_stacks: int,
    stacks_text: str,
    base_inventory: object | None = None,
    source_name: str = "Inventory stacks",
) -> dict[str, Any] | None:
    if not enabled:
        return None

    stripped = stacks_text.strip()
    if stripped:
        try:
            parsed_stacks = loads_json_data(
                stripped,
                source_name=source_name,
            )
        except JsonDataDecodeError as exc:
            raise ValueError(f"Inventory stacks must be valid JSON.\n{exc}") from exc
        stacks = parse_inventory_stacks(parsed_stacks)
    else:
        stacks = []

    inventory: dict[str, Any]
    if isinstance(base_inventory, dict):
        inventory = copy.deepcopy(base_inventory)
    else:
        inventory = {}
    inventory["max_stacks"] = int(max_stacks)
    inventory["stacks"] = stacks
    return parse_inventory(inventory)


def _parse_non_negative_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")
    if value < 0:
        raise ValueError(f"{field_name} must be zero or positive.")
    return int(value)


def _parse_positive_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive.")
    return int(value)
