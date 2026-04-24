"""Popup editors for authored command lists and individual commands."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
import sys
from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    from dungeon_engine.commands.builtin import register_builtin_commands
    from dungeon_engine.commands.registry import CommandRegistry
except ModuleNotFoundError:
    repo_root = Path(__file__).resolve().parents[4]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from dungeon_engine.commands.builtin import register_builtin_commands
    from dungeon_engine.commands.registry import CommandRegistry

from area_editor.json_io import JsonDataDecodeError, loads_json_data
from area_editor.widgets.reference_picker_support import (
    EntityReferencePickerRequest,
    call_reference_picker_callback,
)

_KNOWN_COMMAND_NAMES: tuple[str, ...] | None = None
_ADVANCED_COMMAND_TYPES = {
    "set_current_area_var_length",
    "set_entity_var_length",
    "append_current_area_var",
    "append_entity_var",
    "pop_current_area_var",
    "pop_entity_var",
    "run_commands_for_collection",
    "if",
}
_SUPPORTED_COMMAND_TYPES = {
    "open_dialogue_session",
    "run_project_command",
    "run_entity_command",
    "run_sequence",
    "spawn_flow",
    "run_parallel",
    "run_commands_for_collection",
    "if",
    "change_area",
    "new_game",
    "load_game",
    "save_game",
    "quit_game",
    "set_simulation_paused",
    "toggle_simulation_paused",
    "step_simulation_tick",
    "adjust_output_scale",
    "open_entity_dialogue",
    "step_in_direction",
    "set_entity_grid_position",
    "set_entity_world_position",
    "set_entity_screen_position",
    "move_entity_world_position",
    "move_entity_screen_position",
    "push_facing",
    "wait_for_move",
    "set_camera_follow_entity",
    "set_camera_follow_input_target",
    "clear_camera_follow",
    "set_camera_policy",
    "push_camera_state",
    "pop_camera_state",
    "set_camera_bounds",
    "clear_camera_bounds",
    "set_camera_deadzone",
    "clear_camera_deadzone",
    "move_camera",
    "teleport_camera",
    "play_audio",
    "set_sound_volume",
    "play_music",
    "stop_music",
    "pause_music",
    "resume_music",
    "set_music_volume",
    "show_screen_image",
    "show_screen_text",
    "set_screen_text",
    "remove_screen_element",
    "clear_screen_elements",
    "play_screen_animation",
    "wait_for_screen_animation",
    "play_animation",
    "wait_for_animation",
    "stop_animation",
    "add_inventory_item",
    "remove_inventory_item",
    "use_inventory_item",
    "set_inventory_max_stacks",
    "open_inventory_session",
    "close_inventory_session",
    "set_current_area_var",
    "add_current_area_var",
    "add_entity_var",
    "toggle_current_area_var",
    "toggle_entity_var",
    "set_current_area_var_length",
    "set_entity_var_length",
    "append_current_area_var",
    "append_entity_var",
    "pop_current_area_var",
    "pop_entity_var",
    "set_entity_field",
    "set_entity_fields",
    "spawn_entity",
    "set_area_var",
    "set_area_entity_var",
    "set_area_entity_field",
    "reset_transient_state",
    "reset_persistent_state",
    "set_entity_var",
    "set_visible",
    "set_present",
    "set_color",
    "destroy_entity",
    "set_visual_frame",
    "set_visual_flip_x",
    "set_entity_command_enabled",
    "set_entity_commands_enabled",
    "set_input_target",
    "route_inputs_to_entity",
    "push_input_routes",
    "pop_input_routes",
    "wait_frames",
    "wait_seconds",
    "close_dialogue_session",
    "interact_facing",
    "set_entity_active_dialogue",
    "step_entity_active_dialogue",
    "set_entity_active_dialogue_by_order",
}
_OWNED_FIELDS_BY_COMMAND_TYPE: dict[str, set[str]] = {
    "open_dialogue_session": {
        "dialogue_path",
        "dialogue_definition",
        "allow_cancel",
        "ui_preset",
        "actor_id",
        "caller_id",
        "entity_refs",
    },
    "run_project_command": {
        "command_id",
        "source_entity_id",
        "refs_mode",
        "entity_refs",
    },
    "run_entity_command": {
        "entity_id",
        "command_id",
        "source_entity_id",
        "refs_mode",
        "entity_refs",
    },
    "run_sequence": {
        "commands",
        "source_entity_id",
        "refs_mode",
        "entity_refs",
    },
    "spawn_flow": {
        "commands",
        "source_entity_id",
        "refs_mode",
        "entity_refs",
    },
    "run_parallel": {
        "commands",
        "completion",
        "source_entity_id",
        "refs_mode",
        "entity_refs",
    },
    "run_commands_for_collection": {
        "value",
        "commands",
        "item_param",
        "index_param",
        "source_entity_id",
        "refs_mode",
        "entity_refs",
    },
    "if": {
        "left",
        "op",
        "right",
        "then",
        "else",
    },
    "change_area": {
        "area_id",
        "entry_id",
        "destination_entity_id",
        "transfer_entity_id",
        "transfer_entity_ids",
        "camera_follow",
        "allowed_instigator_kinds",
        "source_entity_id",
        "entity_refs",
    },
    "new_game": {
        "area_id",
        "entry_id",
        "destination_entity_id",
        "camera_follow",
        "source_entity_id",
    },
    "load_game": {
        "save_path",
    },
    "save_game": {
        "save_path",
    },
    "quit_game": set(),
    "set_simulation_paused": {
        "paused",
    },
    "toggle_simulation_paused": set(),
    "step_simulation_tick": set(),
    "adjust_output_scale": {
        "delta",
    },
    "open_entity_dialogue": {
        "entity_id",
        "dialogue_id",
        "allow_cancel",
        "ui_preset",
        "actor_id",
        "caller_id",
        "entity_refs",
    },
    "step_in_direction": {
        "entity_id",
        "direction",
        "push_strength",
        "frames_needed",
        "wait",
        "persistent",
    },
    "set_entity_grid_position": {
        "entity_id",
        "x",
        "y",
        "mode",
        "persistent",
    },
    "set_entity_world_position": {
        "entity_id",
        "x",
        "y",
        "mode",
        "persistent",
    },
    "set_entity_screen_position": {
        "entity_id",
        "x",
        "y",
        "mode",
        "persistent",
    },
    "move_entity_world_position": {
        "entity_id",
        "x",
        "y",
        "mode",
        "duration",
        "frames_needed",
        "speed_px_per_second",
        "wait",
        "persistent",
    },
    "move_entity_screen_position": {
        "entity_id",
        "x",
        "y",
        "mode",
        "duration",
        "frames_needed",
        "speed_px_per_second",
        "wait",
        "persistent",
    },
    "push_facing": {
        "entity_id",
        "direction",
        "push_strength",
        "duration",
        "frames_needed",
        "speed_px_per_second",
        "wait",
        "persistent",
    },
    "wait_for_move": {
        "entity_id",
    },
    "set_camera_follow_entity": {
        "entity_id",
        "offset_x",
        "offset_y",
    },
    "set_camera_follow_input_target": {
        "action",
        "offset_x",
        "offset_y",
    },
    "clear_camera_follow": set(),
    "set_camera_policy": {
        "follow",
        "bounds",
        "deadzone",
    },
    "push_camera_state": set(),
    "pop_camera_state": set(),
    "set_camera_bounds": {
        "x",
        "y",
        "width",
        "height",
        "space",
    },
    "clear_camera_bounds": set(),
    "set_camera_deadzone": {
        "x",
        "y",
        "width",
        "height",
        "space",
    },
    "clear_camera_deadzone": set(),
    "move_camera": {
        "x",
        "y",
        "space",
        "mode",
        "duration",
        "frames_needed",
        "speed_px_per_second",
    },
    "teleport_camera": {
        "x",
        "y",
        "space",
        "mode",
    },
    "play_audio": {
        "path",
        "volume",
    },
    "set_sound_volume": {
        "volume",
    },
    "play_music": {
        "path",
        "loop",
        "volume",
        "restart_if_same",
    },
    "stop_music": {
        "fade_seconds",
    },
    "pause_music": set(),
    "resume_music": set(),
    "set_music_volume": {
        "volume",
    },
    "show_screen_image": {
        "element_id",
        "path",
        "x",
        "y",
        "frame_width",
        "frame_height",
        "frame",
        "layer",
        "anchor",
        "flip_x",
        "tint",
        "visible",
    },
    "show_screen_text": {
        "element_id",
        "text",
        "x",
        "y",
        "layer",
        "anchor",
        "color",
        "font_id",
        "max_width",
        "visible",
    },
    "set_screen_text": {
        "element_id",
        "text",
    },
    "remove_screen_element": {
        "element_id",
    },
    "clear_screen_elements": {
        "layer",
    },
    "play_screen_animation": {
        "element_id",
        "frame_sequence",
        "ticks_per_frame",
        "hold_last_frame",
        "wait",
    },
    "wait_for_screen_animation": {
        "element_id",
    },
    "play_animation": {
        "entity_id",
        "visual_id",
        "animation",
        "frame_count",
        "duration_ticks",
        "wait",
    },
    "wait_for_animation": {
        "entity_id",
        "visual_id",
    },
    "stop_animation": {
        "entity_id",
        "visual_id",
        "reset_to_default",
    },
    "add_inventory_item": {
        "entity_id",
        "item_id",
        "quantity",
        "quantity_mode",
        "result_var_name",
        "persistent",
    },
    "remove_inventory_item": {
        "entity_id",
        "item_id",
        "quantity",
        "quantity_mode",
        "result_var_name",
        "persistent",
    },
    "use_inventory_item": {
        "entity_id",
        "item_id",
        "quantity",
        "result_var_name",
        "persistent",
    },
    "set_inventory_max_stacks": {
        "entity_id",
        "max_stacks",
        "persistent",
    },
    "open_inventory_session": {
        "entity_id",
        "ui_preset",
        "wait",
    },
    "close_inventory_session": set(),
    "set_current_area_var": {
        "name",
        "value",
        "persistent",
        "value_mode",
    },
    "add_current_area_var": {
        "name",
        "amount",
        "persistent",
    },
    "add_entity_var": {
        "entity_id",
        "name",
        "amount",
        "persistent",
    },
    "toggle_current_area_var": {
        "name",
        "persistent",
    },
    "toggle_entity_var": {
        "entity_id",
        "name",
        "persistent",
    },
    "set_current_area_var_length": {
        "name",
        "value",
        "persistent",
    },
    "set_entity_var_length": {
        "entity_id",
        "name",
        "value",
        "persistent",
    },
    "append_current_area_var": {
        "name",
        "value",
        "persistent",
        "value_mode",
    },
    "append_entity_var": {
        "entity_id",
        "name",
        "value",
        "persistent",
        "value_mode",
    },
    "pop_current_area_var": {
        "name",
        "store_var",
        "default",
        "persistent",
    },
    "pop_entity_var": {
        "entity_id",
        "name",
        "store_var",
        "default",
        "persistent",
    },
    "set_entity_field": {
        "entity_id",
        "field_name",
        "value",
        "persistent",
    },
    "set_entity_fields": {
        "entity_id",
        "set",
        "persistent",
    },
    "spawn_entity": {
        "entity",
        "entity_id",
        "template",
        "kind",
        "x",
        "y",
        "parameters",
        "present",
        "persistent",
    },
    "set_area_var": {
        "area_id",
        "name",
        "value",
    },
    "set_area_entity_var": {
        "area_id",
        "entity_id",
        "name",
        "value",
    },
    "set_area_entity_field": {
        "area_id",
        "entity_id",
        "field_name",
        "value",
    },
    "reset_transient_state": {
        "entity_id",
        "entity_ids",
        "include_tags",
        "exclude_tags",
        "apply",
    },
    "reset_persistent_state": {
        "include_tags",
        "exclude_tags",
        "apply",
    },
    "set_entity_var": {
        "entity_id",
        "name",
        "value",
        "persistent",
        "value_mode",
    },
    "set_visible": {
        "entity_id",
        "visible",
        "persistent",
    },
    "set_present": {
        "entity_id",
        "present",
        "persistent",
    },
    "set_color": {
        "entity_id",
        "color",
        "persistent",
    },
    "destroy_entity": {
        "entity_id",
        "persistent",
    },
    "set_visual_frame": {
        "entity_id",
        "visual_id",
        "frame",
    },
    "set_visual_flip_x": {
        "entity_id",
        "visual_id",
        "flip_x",
    },
    "set_entity_command_enabled": {
        "entity_id",
        "command_id",
        "enabled",
        "persistent",
    },
    "set_entity_commands_enabled": {
        "entity_id",
        "enabled",
        "persistent",
    },
    "set_input_target": {
        "action",
        "entity_id",
    },
    "route_inputs_to_entity": {
        "entity_id",
        "actions",
    },
    "push_input_routes": {
        "actions",
    },
    "pop_input_routes": set(),
    "wait_frames": {
        "frames",
    },
    "wait_seconds": {
        "seconds",
    },
    "close_dialogue_session": set(),
    "interact_facing": {
        "entity_id",
        "direction",
    },
    "set_entity_active_dialogue": {
        "entity_id",
        "dialogue_id",
        "persistent",
    },
    "step_entity_active_dialogue": {
        "entity_id",
        "delta",
        "wrap",
        "persistent",
    },
    "set_entity_active_dialogue_by_order": {
        "entity_id",
        "order",
        "wrap",
        "persistent",
    },
}

_COMMON_ENTITY_REFERENCE_TOKENS: tuple[tuple[str, str], ...] = (
    ("$self_id", "Self"),
    ("$instigator_id", "Instigator"),
    ("$ref_ids.<name>", "Explicit Ref"),
)

_SCREEN_ANCHOR_CHOICES: tuple[tuple[str, str], ...] = (
    ("topleft", "topleft"),
    ("top", "top"),
    ("topright", "topright"),
    ("left", "left"),
    ("center", "center"),
    ("right", "right"),
    ("bottomleft", "bottomleft"),
    ("bottom", "bottom"),
    ("bottomright", "bottomright"),
)

_CAMERA_WORLD_SPACE_CHOICES: tuple[tuple[str, str], ...] = (
    ("world_pixel", "world_pixel"),
    ("world_grid", "world_grid"),
)

_CAMERA_VIEWPORT_SPACE_CHOICES: tuple[tuple[str, str], ...] = (
    ("viewport_pixel", "viewport_pixel"),
    ("viewport_grid", "viewport_grid"),
)

_CAMERA_MOVE_MODE_CHOICES: tuple[tuple[str, str], ...] = (
    ("absolute", "absolute"),
    ("relative", "relative"),
)

_STANDARD_DIRECTION_CHOICES: tuple[tuple[str, str], ...] = (
    ("up", "up"),
    ("down", "down"),
    ("left", "left"),
    ("right", "right"),
)

_INVENTORY_QUANTITY_MODE_CHOICES: tuple[tuple[str, str], ...] = (
    ("atomic", "atomic"),
    ("partial", "partial"),
)

_RESET_APPLY_CHOICES: tuple[tuple[str, str], ...] = (
    ("immediate", "immediate"),
    ("on_reentry", "on_reentry"),
)

_ENTITY_FIELD_NAME_CHOICES: tuple[tuple[str, str], ...] = (
    ("present", "present"),
    ("visible", "visible"),
    ("facing", "facing"),
    ("solid", "solid"),
    ("pushable", "pushable"),
    ("weight", "weight"),
    ("push_strength", "push_strength"),
    ("collision_push_strength", "collision_push_strength"),
    ("interactable", "interactable"),
    ("interaction_priority", "interaction_priority"),
    ("entity_commands_enabled", "entity_commands_enabled"),
    ("render_order", "render_order"),
    ("y_sort", "y_sort"),
    ("sort_y_offset", "sort_y_offset"),
    ("stack_order", "stack_order"),
    ("color", "color"),
    ("input_map", "input_map"),
    ("input_map.interact", "input_map.interact"),
    ("visuals.main.flip_x", "visuals.main.flip_x"),
    ("visuals.main.visible", "visuals.main.visible"),
    ("visuals.main.current_frame", "visuals.main.current_frame"),
    ("visuals.main.tint", "visuals.main.tint"),
    ("visuals.main.offset_x", "visuals.main.offset_x"),
    ("visuals.main.offset_y", "visuals.main.offset_y"),
    ("visuals.main.animation_fps", "visuals.main.animation_fps"),
)


def summarize_command_list(commands: object) -> str:
    """Return a short human-readable summary for one command list."""
    normalized = _normalize_command_list(commands)
    count = len(normalized)
    if count <= 0:
        return "none"
    first_type = str(normalized[0].get("type", "")).strip()
    if count == 1:
        if first_type:
            return f"1 command: {first_type}"
        return "1 command"
    if first_type:
        return f"{count} commands: {first_type}..."
    return f"{count} commands"


def _normalize_command_list(commands: object) -> list[dict[str, Any]]:
    if commands in (None, ""):
        return []
    if isinstance(commands, dict):
        return [copy.deepcopy(commands)]
    if not isinstance(commands, list):
        return []
    normalized: list[dict[str, Any]] = []
    for command in commands:
        if isinstance(command, dict):
            normalized.append(copy.deepcopy(command))
    return normalized


def _command_summary(command: object, index: int) -> str:
    if not isinstance(command, dict):
        return f"{index + 1}. invalid command"
    command_type = str(command.get("type", "")).strip() or "(no type)"
    if command_type == "open_dialogue_session":
        dialogue_path = str(command.get("dialogue_path", "")).strip()
        if dialogue_path:
            return f"{index + 1}. {command_type}: {dialogue_path}"
        if isinstance(command.get("dialogue_definition"), dict):
            return (
                f"{index + 1}. {command_type}: "
                f"{_summarize_dialogue_definition(command.get('dialogue_definition'))}"
            )
    if command_type == "run_project_command":
        command_id = str(command.get("command_id", "")).strip()
        if command_id:
            return f"{index + 1}. {command_type}: {command_id}"
    if command_type == "run_entity_command":
        entity_id = str(command.get("entity_id", "")).strip()
        command_id = str(command.get("command_id", "")).strip()
        parts = [part for part in (entity_id, command_id) if part]
        if parts:
            return f"{index + 1}. {command_type}: {' -> '.join(parts)}"
    if command_type in {"run_sequence", "spawn_flow"}:
        commands_summary = summarize_command_list(command.get("commands"))
        if commands_summary != "none":
            return f"{index + 1}. {command_type}: {commands_summary}"
    if command_type == "run_parallel":
        branch_count = len(_normalize_command_list(command.get("commands")))
        details = f"{branch_count} branches" if branch_count else "no branches"
        completion = command.get("completion")
        if isinstance(completion, dict):
            mode = str(completion.get("mode", "")).strip()
            if mode:
                details = f"{details}, {mode}"
                child_id = str(completion.get("child_id", "")).strip()
                if mode == "child" and child_id:
                    details = f"{details}={child_id}"
        return f"{index + 1}. {command_type}: {details}"
    if command_type == "run_commands_for_collection":
        item_param = str(command.get("item_param", "item")).strip() or "item"
        commands_summary = summarize_command_list(command.get("commands"))
        return (
            f"{index + 1}. {command_type}: "
            f"${item_param}, {commands_summary}"
        )
    if command_type == "if":
        op = str(command.get("op", "eq")).strip() or "eq"
        details = [op]
        then_summary = summarize_command_list(command.get("then"))
        if then_summary != "none":
            details.append(f"then {then_summary}")
        else_summary = summarize_command_list(command.get("else"))
        if else_summary != "none":
            details.append(f"else {else_summary}")
        return f"{index + 1}. {command_type}: {', '.join(details)}"
    if command_type in {"change_area", "new_game"}:
        area_id = str(command.get("area_id", "")).strip()
        entry_id = str(command.get("entry_id", "")).strip()
        details = area_id or entry_id
        if area_id and entry_id:
            details = f"{area_id} ({entry_id})"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type in {"load_game", "save_game"}:
        save_path = str(command.get("save_path", "")).strip()
        if save_path:
            return f"{index + 1}. {command_type}: {save_path}"
    if command_type == "set_simulation_paused":
        paused = command.get("paused")
        if paused not in (None, ""):
            return f"{index + 1}. {command_type}: {paused}"
    if command_type == "adjust_output_scale":
        delta = command.get("delta")
        if delta not in (None, ""):
            return f"{index + 1}. {command_type}: {delta}"
    if command_type in {"open_entity_dialogue", "set_entity_active_dialogue"}:
        entity_id = str(command.get("entity_id", "")).strip()
        dialogue_id = str(command.get("dialogue_id", "")).strip()
        parts = [part for part in (entity_id, dialogue_id) if part]
        if parts:
            return f"{index + 1}. {command_type}: {' -> '.join(parts)}"
    if command_type == "interact_facing":
        entity_id = str(command.get("entity_id", "")).strip()
        direction = str(command.get("direction", "")).strip()
        details = entity_id or direction
        if entity_id and direction:
            details = f"{entity_id} ({direction})"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type == "step_in_direction":
        entity_id = str(command.get("entity_id", "")).strip()
        direction = str(command.get("direction", "")).strip()
        details = entity_id or direction
        if entity_id and direction:
            details = f"{entity_id} ({direction})"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type in {
        "set_entity_grid_position",
        "set_entity_world_position",
        "set_entity_screen_position",
        "move_entity_world_position",
        "move_entity_screen_position",
    }:
        entity_id = str(command.get("entity_id", "")).strip()
        x = command.get("x")
        y = command.get("y")
        details = entity_id
        if x not in (None, "") and y not in (None, ""):
            coordinate_text = f"({x}, {y})"
            details = f"{entity_id} -> {coordinate_text}" if entity_id else coordinate_text
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type == "push_facing":
        entity_id = str(command.get("entity_id", "")).strip()
        direction = str(command.get("direction", "")).strip()
        details = entity_id or direction
        if entity_id and direction:
            details = f"{entity_id} ({direction})"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type == "wait_for_move":
        entity_id = str(command.get("entity_id", "")).strip()
        if entity_id:
            return f"{index + 1}. {command_type}: {entity_id}"
    if command_type == "set_camera_follow_entity":
        target = str(command.get("entity_id", "")).strip()
        details = target or "entity"
        return f"{index + 1}. {command_type}: {details}"
    if command_type == "set_camera_follow_input_target":
        action = str(command.get("action", "")).strip()
        details = action or "input_target"
        return f"{index + 1}. {command_type}: {details}"
    if command_type in {"clear_camera_follow", "clear_camera_bounds", "clear_camera_deadzone"}:
        return f"{index + 1}. {command_type}"
    if command_type == "set_camera_policy":
        section_summaries: list[str] = []
        for section_name in ("follow", "bounds", "deadzone"):
            if section_name not in command:
                continue
            raw_value = command.get(section_name)
            if raw_value is None:
                section_summaries.append(f"{section_name}=clear")
            else:
                section_summaries.append(section_name)
        if section_summaries:
            return f"{index + 1}. {command_type}: {', '.join(section_summaries)}"
    if command_type in {"set_camera_bounds", "set_camera_deadzone"}:
        width = command.get("width")
        height = command.get("height")
        if width not in (None, "") and height not in (None, ""):
            return f"{index + 1}. {command_type}: {width}x{height}"
    if command_type in {"move_camera", "teleport_camera"}:
        x = command.get("x")
        y = command.get("y")
        if x not in (None, "") and y not in (None, ""):
            return f"{index + 1}. {command_type}: ({x}, {y})"
    if command_type in {"play_audio", "play_music"}:
        path = str(command.get("path", "")).strip()
        if path:
            return f"{index + 1}. {command_type}: {path}"
    if command_type in {
        "show_screen_image",
        "show_screen_text",
        "set_screen_text",
        "remove_screen_element",
        "wait_for_screen_animation",
    }:
        element_id = str(command.get("element_id", "")).strip()
        if element_id:
            return f"{index + 1}. {command_type}: {element_id}"
    if command_type == "clear_screen_elements":
        layer = command.get("layer")
        if layer not in (None, ""):
            return f"{index + 1}. {command_type}: layer {layer}"
    if command_type == "play_screen_animation":
        element_id = str(command.get("element_id", "")).strip()
        frame_sequence = command.get("frame_sequence")
        frame_count = len(frame_sequence) if isinstance(frame_sequence, list) else 0
        details = element_id or f"{frame_count} frames"
        if element_id and frame_count:
            details = f"{element_id} ({frame_count} frames)"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type in {"play_animation", "wait_for_animation", "stop_animation"}:
        entity_id = str(command.get("entity_id", "")).strip()
        visual_id = str(command.get("visual_id", "")).strip()
        details = entity_id or visual_id
        if entity_id and visual_id:
            details = f"{entity_id} ({visual_id})"
        if command_type == "play_animation":
            animation = str(command.get("animation", "")).strip()
            if animation:
                details = f"{details} -> {animation}" if details else animation
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type in {
        "add_inventory_item",
        "remove_inventory_item",
        "use_inventory_item",
    }:
        entity_id = str(command.get("entity_id", "")).strip()
        item_id = str(command.get("item_id", "")).strip()
        details = entity_id or item_id
        if entity_id and item_id:
            details = f"{entity_id} -> {item_id}"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type == "set_inventory_max_stacks":
        entity_id = str(command.get("entity_id", "")).strip()
        max_stacks = command.get("max_stacks")
        details = entity_id
        if not details and max_stacks not in (None, ""):
            details = str(max_stacks)
        if entity_id and max_stacks not in (None, ""):
            details = f"{entity_id} -> {max_stacks}"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type == "open_inventory_session":
        entity_id = str(command.get("entity_id", "")).strip()
        ui_preset = str(command.get("ui_preset", "")).strip()
        details = entity_id or ui_preset
        if entity_id and ui_preset:
            details = f"{entity_id} ({ui_preset})"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type in {"set_sound_volume", "set_music_volume"}:
        volume = command.get("volume")
        if volume not in (None, ""):
            return f"{index + 1}. {command_type}: {volume}"
    if command_type == "stop_music":
        fade_seconds = command.get("fade_seconds")
        if fade_seconds not in (None, ""):
            return f"{index + 1}. {command_type}: {fade_seconds}s"
    if command_type == "set_input_target":
        action = str(command.get("action", "")).strip()
        entity_id = str(command.get("entity_id", "")).strip()
        details = action or entity_id
        if action and entity_id:
            details = f"{action} -> {entity_id}"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type == "route_inputs_to_entity":
        entity_id = str(command.get("entity_id", "")).strip()
        actions = command.get("actions")
        action_count = len(actions) if isinstance(actions, list) else 0
        details = entity_id or f"{action_count} actions"
        if entity_id and action_count:
            details = f"{entity_id} ({action_count} actions)"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type == "push_input_routes":
        actions = command.get("actions")
        action_count = len(actions) if isinstance(actions, list) else 0
        if action_count:
            return f"{index + 1}. {command_type}: {action_count} actions"
    if command_type == "wait_frames":
        frames = command.get("frames")
        if frames not in (None, ""):
            return f"{index + 1}. {command_type}: {frames}"
    if command_type == "wait_seconds":
        seconds = command.get("seconds")
        if seconds not in (None, ""):
            return f"{index + 1}. {command_type}: {seconds}"
    if command_type == "step_entity_active_dialogue":
        entity_id = str(command.get("entity_id", "")).strip()
        delta = command.get("delta")
        details = entity_id or f"delta={delta}"
        if entity_id and delta not in (None, ""):
            details = f"{entity_id} delta={delta}"
        return f"{index + 1}. {command_type}: {details}"
    if command_type == "set_entity_active_dialogue_by_order":
        entity_id = str(command.get("entity_id", "")).strip()
        order = command.get("order")
        details = entity_id or f"order={order}"
        if entity_id and order not in (None, ""):
            details = f"{entity_id} order={order}"
        return f"{index + 1}. {command_type}: {details}"
    if command_type in {
        "set_current_area_var",
        "add_current_area_var",
        "toggle_current_area_var",
        "set_current_area_var_length",
        "append_current_area_var",
        "pop_current_area_var",
        "set_area_var",
    }:
        name = str(command.get("name", "")).strip()
        if name:
            return f"{index + 1}. {command_type}: {name}"
    if command_type in {
        "add_entity_var",
        "toggle_entity_var",
        "set_entity_var_length",
        "append_entity_var",
        "pop_entity_var",
        "set_area_entity_var",
    }:
        entity_id = str(command.get("entity_id", "")).strip()
        name = str(command.get("name", "")).strip()
        if entity_id or name:
            parts = [part for part in (entity_id, name) if part]
            return f"{index + 1}. {command_type}: {'.'.join(parts)}"
    if command_type in {"set_entity_field", "set_area_entity_field"}:
        entity_id = str(command.get("entity_id", "")).strip()
        field_name = str(command.get("field_name", "")).strip()
        if entity_id or field_name:
            parts = [part for part in (entity_id, field_name) if part]
            return f"{index + 1}. {command_type}: {'.'.join(parts)}"
    if command_type == "set_entity_fields":
        entity_id = str(command.get("entity_id", "")).strip()
        if entity_id:
            return f"{index + 1}. {command_type}: {entity_id}"
    if command_type == "spawn_entity":
        entity = command.get("entity")
        if isinstance(entity, dict):
            entity_id = str(entity.get("id", "")).strip()
            if entity_id:
                return f"{index + 1}. {command_type}: {entity_id}"
        entity_id = str(command.get("entity_id", "")).strip()
        template = str(command.get("template", "")).strip()
        details = entity_id or template
        if entity_id and template:
            details = f"{entity_id} ({template})"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type in {"reset_transient_state", "reset_persistent_state"}:
        apply = str(command.get("apply", "")).strip()
        entity_id = str(command.get("entity_id", "")).strip()
        details = entity_id or apply
        if entity_id and apply:
            details = f"{entity_id} ({apply})"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type == "set_entity_var":
        entity_id = str(command.get("entity_id", "")).strip()
        name = str(command.get("name", "")).strip()
        if entity_id or name:
            parts = [part for part in (entity_id, name) if part]
            return f"{index + 1}. {command_type}: {'.'.join(parts)}"
    if command_type in {"set_visible", "set_present"}:
        entity_id = str(command.get("entity_id", "")).strip()
        value_name = "visible" if command_type == "set_visible" else "present"
        value = command.get(value_name)
        details = entity_id
        if not details and value not in (None, ""):
            details = str(value)
        if entity_id and value not in (None, ""):
            details = f"{entity_id} -> {value}"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type == "set_color":
        entity_id = str(command.get("entity_id", "")).strip()
        color_text = _rgb_to_text(command.get("color"))
        details = entity_id or color_text
        if entity_id and color_text:
            details = f"{entity_id} -> {color_text}"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type == "destroy_entity":
        entity_id = str(command.get("entity_id", "")).strip()
        if entity_id:
            return f"{index + 1}. {command_type}: {entity_id}"
    if command_type == "set_visual_frame":
        entity_id = str(command.get("entity_id", "")).strip()
        frame = command.get("frame")
        details = entity_id
        if not details and frame not in (None, ""):
            details = f"frame={frame}"
        if entity_id and frame not in (None, ""):
            details = f"{entity_id} frame={frame}"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type == "set_visual_flip_x":
        entity_id = str(command.get("entity_id", "")).strip()
        flip_x = command.get("flip_x")
        details = entity_id
        if not details and flip_x not in (None, ""):
            details = f"flip_x={flip_x}"
        if entity_id and flip_x not in (None, ""):
            details = f"{entity_id} flip_x={flip_x}"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    if command_type == "set_entity_command_enabled":
        entity_id = str(command.get("entity_id", "")).strip()
        command_id = str(command.get("command_id", "")).strip()
        parts = [part for part in (entity_id, command_id) if part]
        if parts:
            return f"{index + 1}. {command_type}: {' -> '.join(parts)}"
    if command_type == "set_entity_commands_enabled":
        entity_id = str(command.get("entity_id", "")).strip()
        enabled = command.get("enabled")
        details = entity_id
        if not details and enabled not in (None, ""):
            details = str(enabled)
        if entity_id and enabled not in (None, ""):
            details = f"{entity_id} -> {enabled}"
        if details:
            return f"{index + 1}. {command_type}: {details}"
    return f"{index + 1}. {command_type}"


def _summarize_dialogue_definition(definition: object) -> str:
    if not isinstance(definition, dict):
        return "Invalid dialogue definition"
    segments = definition.get("segments")
    if not isinstance(segments, list):
        return "Dialogue has no segments array"
    segment_count = len(segments)
    choice_count = sum(
        1
        for segment in segments
        if isinstance(segment, dict)
        and str(segment.get("type", "text")).strip() == "choice"
    )
    text_count = max(0, segment_count - choice_count)
    parts = [f"{segment_count} segment{'s' if segment_count != 1 else ''}"]
    if text_count:
        parts.append(f"{text_count} text")
    if choice_count:
        parts.append(f"{choice_count} choice")
    return ", ".join(parts)


def _known_command_names() -> tuple[str, ...]:
    global _KNOWN_COMMAND_NAMES
    if _KNOWN_COMMAND_NAMES is None:
        registry = CommandRegistry()
        register_builtin_commands(registry)
        _KNOWN_COMMAND_NAMES = tuple(
            contract.name
            for contract in registry.iter_command_contracts()
        )
    return _KNOWN_COMMAND_NAMES


def _coerce_numeric_literal(value: float | int) -> float | int:
    numeric = float(value)
    if numeric.is_integer():
        return int(numeric)
    return numeric


def _parse_json_text_value(
    text: str,
    *,
    allow_blank: bool = False,
) -> Any:
    stripped = str(text).strip()
    if not stripped:
        if allow_blank:
            return None
        raise ValueError("Value cannot be blank.")
    return json.loads(stripped)


def _parse_json_object_text_value(
    text: str,
    *,
    allow_blank: bool = False,
) -> dict[str, Any] | None:
    value = _parse_json_text_value(text, allow_blank=allow_blank)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Value must be a JSON object.")
    return value


def _make_line_with_button(
    *,
    button_text: str,
) -> tuple[QWidget, QLineEdit, QPushButton]:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    edit = QLineEdit()
    button = QPushButton(button_text)
    button.setAutoDefault(False)
    button.setDefault(False)
    layout.addWidget(edit, 1)
    layout.addWidget(button)
    return row, edit, button


def _make_line_with_two_buttons(
    *,
    primary_button_text: str,
    secondary_button_text: str,
) -> tuple[QWidget, QLineEdit, QPushButton, QPushButton]:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    edit = QLineEdit()
    primary = QPushButton(primary_button_text)
    primary.setAutoDefault(False)
    primary.setDefault(False)
    secondary = QPushButton(secondary_button_text)
    secondary.setAutoDefault(False)
    secondary.setDefault(False)
    layout.addWidget(edit, 1)
    layout.addWidget(primary)
    layout.addWidget(secondary)
    return row, edit, primary, secondary


def _string_list_to_text(value: object) -> str:
    if not isinstance(value, (list, tuple)):
        return ""
    return ", ".join(
        str(item).strip()
        for item in value
        if str(item).strip()
    )


def _parse_string_list_text(text: str) -> list[str]:
    return [part.strip() for part in str(text).split(",") if part.strip()]


def _int_list_to_text(value: object) -> str:
    if not isinstance(value, (list, tuple)):
        return ""
    parts: list[str] = []
    for item in value:
        try:
            parts.append(str(int(item)))
        except (TypeError, ValueError):
            continue
    return ", ".join(parts)


def _parse_int_list_text(text: str) -> list[int]:
    values: list[int] = []
    for part in _parse_string_list_text(text):
        try:
            values.append(int(part))
        except ValueError as exc:
            raise ValueError(f"Expected a comma-separated integer list, got '{part}'.") from exc
    return values


def _rgb_to_text(value: object) -> str:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return ""
    parts: list[str] = []
    for item in value:
        try:
            parts.append(str(int(item)))
        except (TypeError, ValueError):
            return ""
    return ", ".join(parts)


def _parse_rgb_text(text: str) -> tuple[int, int, int]:
    parts = _parse_string_list_text(text)
    if len(parts) != 3:
        raise ValueError("Expected three comma-separated color channels (R, G, B).")
    channels: list[int] = []
    for part in parts:
        try:
            channel = int(part)
        except ValueError as exc:
            raise ValueError(f"Color channel '{part}' is not an integer.") from exc
        if channel < 0 or channel > 255:
            raise ValueError("Color channels must be between 0 and 255.")
        channels.append(channel)
    return (channels[0], channels[1], channels[2])


class _OptionalTextField(QWidget):
    """Text field with explicit presence control."""

    changed = Signal()

    def __init__(
        self,
        parent=None,
        *,
        button_text: str | None = None,
        extra_button_text: str | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._enabled_check = QCheckBox("Set")
        self._edit = QLineEdit()
        self._button = QPushButton(button_text) if button_text else None
        self._extra_button = QPushButton(extra_button_text) if extra_button_text else None
        if self._button is not None:
            self._button.setAutoDefault(False)
            self._button.setDefault(False)
        if self._extra_button is not None:
            self._extra_button.setAutoDefault(False)
            self._extra_button.setDefault(False)

        layout.addWidget(self._enabled_check)
        layout.addWidget(self._edit, 1)
        if self._button is not None:
            layout.addWidget(self._button)
        if self._extra_button is not None:
            layout.addWidget(self._extra_button)

        self._enabled_check.toggled.connect(self._sync_enabled_state)
        self._enabled_check.toggled.connect(lambda _checked: self.changed.emit())
        self._edit.textChanged.connect(lambda _text: self.changed.emit())
        self._sync_enabled_state(self._enabled_check.isChecked())

    @property
    def edit(self) -> QLineEdit:
        return self._edit

    @property
    def button(self) -> QPushButton | None:
        return self._button

    @property
    def extra_button(self) -> QPushButton | None:
        return self._extra_button

    def set_optional_value(self, value: object) -> None:
        text = str(value).strip() if isinstance(value, str) else ""
        enabled = bool(text)
        blockers = [QSignalBlocker(self._enabled_check), QSignalBlocker(self._edit)]
        self._enabled_check.setChecked(enabled)
        self._edit.setText(text if enabled else "")
        del blockers
        self._sync_enabled_state(enabled)

    def optional_value(self) -> str | None:
        if not self._enabled_check.isChecked():
            return None
        value = self._edit.text().strip()
        return value or None

    def _sync_enabled_state(self, enabled: bool) -> None:
        self._edit.setEnabled(enabled)
        if self._button is not None:
            self._button.setEnabled(enabled)
        if self._extra_button is not None:
            self._extra_button.setEnabled(True)


class _OptionalIntField(QWidget):
    """Integer field with explicit presence control."""

    changed = Signal()

    def __init__(
        self,
        parent=None,
        *,
        minimum: int,
        maximum: int,
        default_value: int,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._enabled_check = QCheckBox("Set")
        self._spin = QSpinBox()
        self._spin.setRange(minimum, maximum)
        self._spin.setValue(default_value)
        layout.addWidget(self._enabled_check)
        layout.addWidget(self._spin, 1)
        self._enabled_check.toggled.connect(self._sync_enabled_state)
        self._enabled_check.toggled.connect(lambda _checked: self.changed.emit())
        self._spin.valueChanged.connect(lambda _value: self.changed.emit())
        self._sync_enabled_state(self._enabled_check.isChecked())

    @property
    def spin_box(self) -> QSpinBox:
        return self._spin

    def set_optional_value(self, value: object) -> None:
        enabled = value not in (None, "")
        try:
            numeric_value = int(value) if enabled else self._spin.value()
        except (TypeError, ValueError):
            numeric_value = self._spin.value()
            enabled = False
        blockers = [QSignalBlocker(self._enabled_check), QSignalBlocker(self._spin)]
        self._enabled_check.setChecked(enabled)
        self._spin.setValue(numeric_value)
        del blockers
        self._sync_enabled_state(enabled)

    def optional_value(self) -> int | None:
        if not self._enabled_check.isChecked():
            return None
        return int(self._spin.value())

    def _sync_enabled_state(self, enabled: bool) -> None:
        self._spin.setEnabled(enabled)


class _OptionalFloatField(QWidget):
    """Floating-point field with explicit presence control."""

    changed = Signal()

    def __init__(
        self,
        parent=None,
        *,
        minimum: float,
        maximum: float,
        default_value: float,
        decimals: int = 3,
        step: float = 0.1,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._enabled_check = QCheckBox("Set")
        self._spin = QDoubleSpinBox()
        self._spin.setRange(minimum, maximum)
        self._spin.setDecimals(decimals)
        self._spin.setSingleStep(step)
        self._spin.setValue(default_value)
        layout.addWidget(self._enabled_check)
        layout.addWidget(self._spin, 1)
        self._enabled_check.toggled.connect(self._sync_enabled_state)
        self._enabled_check.toggled.connect(lambda _checked: self.changed.emit())
        self._spin.valueChanged.connect(lambda _value: self.changed.emit())
        self._sync_enabled_state(self._enabled_check.isChecked())

    @property
    def spin_box(self) -> QDoubleSpinBox:
        return self._spin

    def set_optional_value(self, value: object) -> None:
        enabled = value not in (None, "")
        try:
            numeric_value = float(value) if enabled else self._spin.value()
        except (TypeError, ValueError):
            numeric_value = self._spin.value()
            enabled = False
        blockers = [QSignalBlocker(self._enabled_check), QSignalBlocker(self._spin)]
        self._enabled_check.setChecked(enabled)
        self._spin.setValue(numeric_value)
        del blockers
        self._sync_enabled_state(enabled)

    def optional_value(self) -> float | None:
        if not self._enabled_check.isChecked():
            return None
        return float(self._spin.value())

    def _sync_enabled_state(self, enabled: bool) -> None:
        self._spin.setEnabled(enabled)


class _EntityRefRow(QWidget):
    """One editable named entity-ref row."""

    changed = Signal()
    remove_requested = Signal(object)

    def __init__(
        self,
        parent=None,
        *,
        pick_entity_callback: Callable[[QLineEdit, str], None] | None = None,
        show_token_menu_callback: Callable[[QLineEdit, QWidget], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._pick_entity_callback = pick_entity_callback
        self._show_token_menu_callback = show_token_menu_callback

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("ref name")
        self._value_edit = QLineEdit()
        self._value_edit.setPlaceholderText("entity id or token")
        self._pick_button = QPushButton("Pick...")
        self._pick_button.setAutoDefault(False)
        self._pick_button.setDefault(False)
        self._ref_button = QPushButton("Ref...")
        self._ref_button.setAutoDefault(False)
        self._ref_button.setDefault(False)
        self._remove_button = QPushButton("Remove")
        self._remove_button.setAutoDefault(False)
        self._remove_button.setDefault(False)

        layout.addWidget(self._name_edit)
        layout.addWidget(self._value_edit, 1)
        layout.addWidget(self._pick_button)
        layout.addWidget(self._ref_button)
        layout.addWidget(self._remove_button)

        self._name_edit.textChanged.connect(lambda _text: self.changed.emit())
        self._value_edit.textChanged.connect(lambda _text: self.changed.emit())
        self._pick_button.clicked.connect(self._on_pick_entity)
        self._ref_button.clicked.connect(self._on_show_ref_menu)
        self._remove_button.clicked.connect(lambda: self.remove_requested.emit(self))

    @property
    def name_edit(self) -> QLineEdit:
        return self._name_edit

    @property
    def value_edit(self) -> QLineEdit:
        return self._value_edit

    def set_values(self, name: object, value: object) -> None:
        name_text = str(name).strip() if isinstance(name, str) else ""
        value_text = str(value).strip() if isinstance(value, str) else ""
        blockers = [QSignalBlocker(self._name_edit), QSignalBlocker(self._value_edit)]
        self._name_edit.setText(name_text)
        self._value_edit.setText(value_text)
        del blockers

    def values(self) -> tuple[str, str]:
        return self._name_edit.text().strip(), self._value_edit.text().strip()

    def set_picker_enabled(self, enabled: bool) -> None:
        self._pick_button.setEnabled(enabled)

    def _on_pick_entity(self) -> None:
        if self._pick_entity_callback is None:
            return
        self._pick_entity_callback(self._value_edit, self._name_edit.text().strip())

    def _on_show_ref_menu(self) -> None:
        if self._show_token_menu_callback is None:
            return
        self._show_token_menu_callback(self._value_edit, self._ref_button)


class _NamedEntityRefsField(QWidget):
    """Editable list of explicit named entity refs."""

    changed = Signal()

    def __init__(
        self,
        parent=None,
        *,
        pick_entity_callback: Callable[[QLineEdit, str], None] | None = None,
        show_token_menu_callback: Callable[[QLineEdit, QWidget], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._pick_entity_callback = pick_entity_callback
        self._show_token_menu_callback = show_token_menu_callback
        self._rows: list[_EntityRefRow] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        self._note = QLabel("Pass related entities into child flows by name.")
        self._note.setWordWrap(True)
        self._note.setStyleSheet("color: #666;")
        outer.addWidget(self._note)

        self._rows_widget = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(6)
        outer.addWidget(self._rows_widget)

        self._empty_label = QLabel("No named refs.")
        self._empty_label.setStyleSheet("color: #666; font-style: italic;")
        self._rows_layout.addWidget(self._empty_label)

        self._add_button = QPushButton("Add Ref")
        self._add_button.setAutoDefault(False)
        self._add_button.setDefault(False)
        self._add_button.clicked.connect(self.add_empty_row)
        outer.addWidget(self._add_button, 0, Qt.AlignmentFlag.AlignLeft)

    def set_refs(self, refs: object) -> None:
        self._clear_rows()
        if isinstance(refs, dict):
            for name, value in refs.items():
                self._add_row(name, value)
        self._sync_empty_state()

    def ref_count(self) -> int:
        count = 0
        for row in self._rows:
            name, value = row.values()
            if name or value:
                count += 1
        return count

    def refs(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for row in self._rows:
            name, value = row.values()
            if not name and not value:
                continue
            if not name:
                raise ValueError("Named entity refs cannot have a blank ref name.")
            if not value:
                raise ValueError(f"Named entity ref '{name}' must choose an entity or token.")
            if name in result:
                raise ValueError(f"Named entity ref '{name}' is duplicated.")
            result[name] = value
        return result

    def add_empty_row(self) -> None:
        self._add_row("", "")
        self.changed.emit()

    def set_picker_enabled(self, enabled: bool) -> None:
        for row in self._rows:
            row.set_picker_enabled(enabled)

    def _add_row(self, name: object, value: object) -> _EntityRefRow:
        row = _EntityRefRow(
            self,
            pick_entity_callback=self._pick_entity_callback,
            show_token_menu_callback=self._show_token_menu_callback,
        )
        row.set_values(name, value)
        row.set_picker_enabled(self._pick_entity_callback is not None)
        row.changed.connect(self._on_row_changed)
        row.remove_requested.connect(self._remove_row)
        self._rows.append(row)
        self._rows_layout.addWidget(row)
        self._sync_empty_state()
        return row

    def _clear_rows(self) -> None:
        while self._rows:
            row = self._rows.pop()
            row.deleteLater()

    def _remove_row(self, row: object) -> None:
        if row not in self._rows:
            return
        self._rows.remove(row)
        assert isinstance(row, QWidget)
        row.deleteLater()
        self._sync_empty_state()
        self.changed.emit()

    def _on_row_changed(self) -> None:
        self._sync_empty_state()
        self.changed.emit()

    def _sync_empty_state(self) -> None:
        self._empty_label.setVisible(not self._rows)


class _NestedCommandListField(QWidget):
    """Compact summary row for editing one nested command list in a popup."""

    changed = Signal()
    edit_requested = Signal()

    def __init__(
        self,
        parent=None,
        *,
        button_text: str,
        note_text: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._commands: list[dict[str, Any]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        self._summary_label = QLabel("none")
        self._summary_label.setWordWrap(True)
        self._edit_button = QPushButton(button_text)
        self._edit_button.setAutoDefault(False)
        self._edit_button.setDefault(False)
        self._edit_button.clicked.connect(self.edit_requested.emit)

        row_layout.addWidget(self._summary_label, 1)
        row_layout.addWidget(self._edit_button)
        outer.addWidget(row)

        self._note_label: QLabel | None = None
        if isinstance(note_text, str) and note_text.strip():
            self._note_label = QLabel(note_text.strip())
            self._note_label.setWordWrap(True)
            self._note_label.setStyleSheet("color: #666;")
            outer.addWidget(self._note_label)

    @property
    def summary_label(self) -> QLabel:
        return self._summary_label

    def set_commands(self, commands: object) -> None:
        self._commands = _normalize_command_list(commands)
        self._summary_label.setText(summarize_command_list(self._commands))
        self.changed.emit()

    def commands(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._commands)


class _CameraFollowEditor(QWidget):
    """Structured editor for one camera follow spec."""

    changed = Signal()

    def __init__(
        self,
        parent=None,
        *,
        pick_entity_callback: Callable[[QLineEdit], None] | None = None,
        show_token_menu_callback: Callable[[QLineEdit, QWidget], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._pick_entity_callback = pick_entity_callback
        self._show_token_menu_callback = show_token_menu_callback
        self._entity_picker_enabled = pick_entity_callback is not None

        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("entity", "entity")
        self._mode_combo.addItem("input_target", "input_target")
        form.addRow("mode", self._mode_combo)

        (
            entity_row,
            self._entity_id_edit,
            self._entity_pick_button,
            self._entity_ref_button,
        ) = _make_line_with_two_buttons(
            primary_button_text="Pick...",
            secondary_button_text="Ref...",
        )
        self._entity_pick_button.clicked.connect(self._on_pick_entity)
        self._entity_ref_button.clicked.connect(self._on_show_entity_ref_menu)
        form.addRow("entity_id", entity_row)

        self._action_edit = QLineEdit()
        form.addRow("action", self._action_edit)

        self._offset_x_spin = QDoubleSpinBox()
        self._offset_x_spin.setRange(-999999.0, 999999.0)
        self._offset_x_spin.setDecimals(3)
        self._offset_x_spin.setSingleStep(1.0)
        form.addRow("offset_x", self._offset_x_spin)

        self._offset_y_spin = QDoubleSpinBox()
        self._offset_y_spin.setRange(-999999.0, 999999.0)
        self._offset_y_spin.setDecimals(3)
        self._offset_y_spin.setSingleStep(1.0)
        form.addRow("offset_y", self._offset_y_spin)

        note = QLabel(
            "Use 'entity' to follow one entity, or 'input_target' to follow the "
            "active target for one routed action."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        form.addRow(note)

        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._entity_id_edit.textChanged.connect(lambda _text: self.changed.emit())
        self._action_edit.textChanged.connect(lambda _text: self.changed.emit())
        self._offset_x_spin.valueChanged.connect(lambda _value: self.changed.emit())
        self._offset_y_spin.valueChanged.connect(lambda _value: self.changed.emit())
        self._sync_mode_state()

    def set_picker_enabled(self, enabled: bool) -> None:
        self._entity_picker_enabled = enabled and self._pick_entity_callback is not None
        self._sync_mode_state()

    def set_follow(self, follow: object) -> None:
        mode = "entity"
        entity_id = ""
        action = ""
        offset_x = 0.0
        offset_y = 0.0
        if isinstance(follow, dict):
            raw_mode = str(follow.get("mode", "")).strip()
            if raw_mode in {"entity", "input_target"}:
                mode = raw_mode
            entity_id = str(follow.get("entity_id", "")).strip()
            action = str(follow.get("action", "")).strip()
            try:
                offset_x = float(follow.get("offset_x", 0.0))
            except (TypeError, ValueError):
                offset_x = 0.0
            try:
                offset_y = float(follow.get("offset_y", 0.0))
            except (TypeError, ValueError):
                offset_y = 0.0
        blockers = [
            QSignalBlocker(self._mode_combo),
            QSignalBlocker(self._entity_id_edit),
            QSignalBlocker(self._action_edit),
            QSignalBlocker(self._offset_x_spin),
            QSignalBlocker(self._offset_y_spin),
        ]
        for index in range(self._mode_combo.count()):
            if self._mode_combo.itemData(index) == mode:
                self._mode_combo.setCurrentIndex(index)
                break
        self._entity_id_edit.setText(entity_id)
        self._action_edit.setText(action)
        self._offset_x_spin.setValue(offset_x)
        self._offset_y_spin.setValue(offset_y)
        del blockers
        self._sync_mode_state()

    def follow_value(self) -> dict[str, Any]:
        mode = str(self._mode_combo.currentData() or "entity").strip() or "entity"
        if mode == "entity":
            entity_id = self._entity_id_edit.text().strip()
            if not entity_id:
                raise ValueError("follow.mode 'entity' requires a non-empty entity_id.")
            result: dict[str, Any] = {"mode": "entity", "entity_id": entity_id}
        else:
            action = self._action_edit.text().strip()
            if not action:
                raise ValueError("follow.mode 'input_target' requires a non-empty action.")
            result = {"mode": "input_target", "action": action}

        offset_x = float(self._offset_x_spin.value())
        offset_y = float(self._offset_y_spin.value())
        if offset_x != 0.0:
            result["offset_x"] = offset_x
        if offset_y != 0.0:
            result["offset_y"] = offset_y
        return result

    def _on_mode_changed(self, _index: int) -> None:
        self._sync_mode_state()
        self.changed.emit()

    def _sync_mode_state(self) -> None:
        mode = str(self._mode_combo.currentData() or "entity").strip() or "entity"
        entity_mode = mode == "entity"
        action_mode = mode == "input_target"
        self._entity_id_edit.setEnabled(entity_mode)
        self._entity_pick_button.setEnabled(entity_mode and self._entity_picker_enabled)
        self._entity_ref_button.setEnabled(
            entity_mode and self._show_token_menu_callback is not None
        )
        self._action_edit.setEnabled(action_mode)
        self._offset_x_spin.setEnabled(True)
        self._offset_y_spin.setEnabled(True)

    def _on_pick_entity(self) -> None:
        if self._pick_entity_callback is None:
            return
        self._pick_entity_callback(self._entity_id_edit)

    def _on_show_entity_ref_menu(self) -> None:
        if self._show_token_menu_callback is None:
            return
        self._show_token_menu_callback(self._entity_id_edit, self._entity_ref_button)


class _CameraRectEditor(QWidget):
    """Structured editor for one camera rectangle spec."""

    changed = Signal()

    def __init__(
        self,
        parent=None,
        *,
        space_choices: list[tuple[str, str]] | tuple[tuple[str, str], ...],
    ) -> None:
        super().__init__(parent)
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)

        self._x_spin = QDoubleSpinBox()
        self._x_spin.setRange(-999999.0, 999999.0)
        self._x_spin.setDecimals(3)
        self._x_spin.setSingleStep(1.0)
        form.addRow("x", self._x_spin)

        self._y_spin = QDoubleSpinBox()
        self._y_spin.setRange(-999999.0, 999999.0)
        self._y_spin.setDecimals(3)
        self._y_spin.setSingleStep(1.0)
        form.addRow("y", self._y_spin)

        self._width_spin = QDoubleSpinBox()
        self._width_spin.setRange(0.0, 999999.0)
        self._width_spin.setDecimals(3)
        self._width_spin.setSingleStep(1.0)
        self._width_spin.setValue(1.0)
        form.addRow("width", self._width_spin)

        self._height_spin = QDoubleSpinBox()
        self._height_spin.setRange(0.0, 999999.0)
        self._height_spin.setDecimals(3)
        self._height_spin.setSingleStep(1.0)
        self._height_spin.setValue(1.0)
        form.addRow("height", self._height_spin)

        self._space_combo = QComboBox()
        for value, label in space_choices:
            self._space_combo.addItem(label, value)
        form.addRow("space", self._space_combo)

        for widget in (
            self._x_spin,
            self._y_spin,
            self._width_spin,
            self._height_spin,
        ):
            widget.valueChanged.connect(lambda _value: self.changed.emit())
        self._space_combo.currentIndexChanged.connect(lambda _index: self.changed.emit())

    def set_rect(self, rect: object) -> None:
        x = 0.0
        y = 0.0
        width = 1.0
        height = 1.0
        space = self._space_combo.itemData(0)
        if isinstance(rect, dict):
            try:
                x = float(rect.get("x", 0.0))
            except (TypeError, ValueError):
                x = 0.0
            try:
                y = float(rect.get("y", 0.0))
            except (TypeError, ValueError):
                y = 0.0
            try:
                width = float(rect.get("width", 1.0))
            except (TypeError, ValueError):
                width = 1.0
            try:
                height = float(rect.get("height", 1.0))
            except (TypeError, ValueError):
                height = 1.0
            candidate_space = str(rect.get("space", "")).strip()
            if candidate_space:
                space = candidate_space
        blockers = [
            QSignalBlocker(self._x_spin),
            QSignalBlocker(self._y_spin),
            QSignalBlocker(self._width_spin),
            QSignalBlocker(self._height_spin),
            QSignalBlocker(self._space_combo),
        ]
        self._x_spin.setValue(x)
        self._y_spin.setValue(y)
        self._width_spin.setValue(max(0.0, width))
        self._height_spin.setValue(max(0.0, height))
        matched = False
        for index in range(self._space_combo.count()):
            if self._space_combo.itemData(index) == space:
                self._space_combo.setCurrentIndex(index)
                matched = True
                break
        if not matched and self._space_combo.count() > 0:
            self._space_combo.setCurrentIndex(0)
        del blockers

    def rect_value(self) -> dict[str, Any]:
        width = float(self._width_spin.value())
        height = float(self._height_spin.value())
        if width <= 0.0 or height <= 0.0:
            raise ValueError("Camera rectangles must use width and height greater than 0.")
        return {
            "x": float(self._x_spin.value()),
            "y": float(self._y_spin.value()),
            "width": width,
            "height": height,
            "space": str(self._space_combo.currentData() or ""),
        }


class _CameraFollowPatchField(QWidget):
    """Camera follow field with omit/clear/set patch semantics."""

    changed = Signal()

    def __init__(
        self,
        parent=None,
        *,
        pick_entity_callback: Callable[[QLineEdit], None] | None = None,
        show_token_menu_callback: Callable[[QLineEdit, QWidget], None] | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Unchanged", "omit")
        self._mode_combo.addItem("Clear", "clear")
        self._mode_combo.addItem("Set", "set")
        layout.addWidget(self._mode_combo)
        self._editor = _CameraFollowEditor(
            pick_entity_callback=pick_entity_callback,
            show_token_menu_callback=show_token_menu_callback,
        )
        layout.addWidget(self._editor)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._editor.changed.connect(self.changed.emit)
        self._sync_mode_state(self.patch_mode())

    @property
    def editor(self) -> _CameraFollowEditor:
        return self._editor

    def set_picker_enabled(self, enabled: bool) -> None:
        self._editor.set_picker_enabled(enabled)

    def set_patch_state(self, mode: str, value: object = None) -> None:
        resolved_mode = mode if mode in {"omit", "clear", "set"} else "omit"
        blockers = [
            QSignalBlocker(self._mode_combo),
            QSignalBlocker(self._editor),
        ]
        for index in range(self._mode_combo.count()):
            if self._mode_combo.itemData(index) == resolved_mode:
                self._mode_combo.setCurrentIndex(index)
                break
        self._editor.set_follow(value if resolved_mode == "set" else None)
        del blockers
        self._sync_mode_state(resolved_mode)

    def patch_mode(self) -> str:
        return str(self._mode_combo.currentData() or "omit")

    def patch_value(self) -> dict[str, Any]:
        return self._editor.follow_value()

    def _on_mode_changed(self, _index: int) -> None:
        self._sync_mode_state(self.patch_mode())
        self.changed.emit()

    def _sync_mode_state(self, mode: str) -> None:
        self._editor.setEnabled(mode == "set")


class _CameraRectPatchField(QWidget):
    """Camera rect field with omit/clear/set patch semantics."""

    changed = Signal()

    def __init__(
        self,
        parent=None,
        *,
        space_choices: list[tuple[str, str]] | tuple[tuple[str, str], ...],
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Unchanged", "omit")
        self._mode_combo.addItem("Clear", "clear")
        self._mode_combo.addItem("Set", "set")
        layout.addWidget(self._mode_combo)
        self._editor = _CameraRectEditor(space_choices=space_choices)
        layout.addWidget(self._editor)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._editor.changed.connect(self.changed.emit)
        self._sync_mode_state(self.patch_mode())

    @property
    def editor(self) -> _CameraRectEditor:
        return self._editor

    def set_patch_state(self, mode: str, value: object = None) -> None:
        resolved_mode = mode if mode in {"omit", "clear", "set"} else "omit"
        blockers = [
            QSignalBlocker(self._mode_combo),
            QSignalBlocker(self._editor),
        ]
        for index in range(self._mode_combo.count()):
            if self._mode_combo.itemData(index) == resolved_mode:
                self._mode_combo.setCurrentIndex(index)
                break
        self._editor.set_rect(value if resolved_mode == "set" else None)
        del blockers
        self._sync_mode_state(resolved_mode)

    def patch_mode(self) -> str:
        return str(self._mode_combo.currentData() or "omit")

    def patch_value(self) -> dict[str, Any]:
        return self._editor.rect_value()

    def _on_mode_changed(self, _index: int) -> None:
        self._sync_mode_state(self.patch_mode())
        self.changed.emit()

    def _sync_mode_state(self, mode: str) -> None:
        self._editor.setEnabled(mode == "set")


class _CommandTypePickerDialog(QDialog):
    """Searchable popup for choosing one command type."""

    def __init__(
        self,
        parent=None,
        *,
        command_names: list[str] | tuple[str, ...],
        suggested_command_names: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Command")
        self.resize(420, 480)

        self._all_command_names = [name for name in command_names if str(name).strip()]
        suggested = []
        for name in suggested_command_names or ():
            normalized = str(name).strip()
            if (
                normalized
                and normalized in self._all_command_names
                and normalized not in suggested
            ):
                suggested.append(normalized)
        self._suggested_command_names = suggested

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        outer.addWidget(QLabel("Command Type"))

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search commands...")
        outer.addWidget(self._search_edit)

        self._command_list = QListWidget()
        outer.addWidget(self._command_list, 1)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

        self._search_edit.textChanged.connect(self._apply_filter)
        self._command_list.itemDoubleClicked.connect(lambda _item: self.accept())
        self._command_list.currentRowChanged.connect(
            lambda _row: self._sync_accept_button()
        )

        self._apply_filter("")

    def selected_command_type(self) -> str | None:
        item = self._command_list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    def _apply_filter(self, search_text: str) -> None:
        needle = str(search_text).strip().casefold()
        filtered = [
            name
            for name in self._all_command_names
            if not needle or needle in name.casefold()
        ]
        self._command_list.blockSignals(True)
        try:
            self._command_list.clear()
            first_selectable_row = self._populate_grouped_command_items(filtered)
            if first_selectable_row >= 0:
                self._command_list.setCurrentRow(first_selectable_row)
        finally:
            self._command_list.blockSignals(False)
        self._sync_accept_button()

    def _populate_grouped_command_items(self, command_names: list[str]) -> int:
        first_selectable_row = -1
        suggested = [
            name for name in self._suggested_command_names if name in command_names
        ]
        remaining = [name for name in command_names if name not in suggested]
        standard = [name for name in remaining if name not in _ADVANCED_COMMAND_TYPES]
        advanced = [name for name in remaining if name in _ADVANCED_COMMAND_TYPES]

        grouped_sections: list[tuple[str, list[str]]] = []
        if suggested:
            grouped_sections.append(("Suggested", suggested))
        if standard:
            grouped_sections.append(("Standard Commands", standard))
        if advanced:
            grouped_sections.append(("Advanced / Rare Commands", advanced))

        for header, names in grouped_sections:
            self._add_header_item(header)
            for name in names:
                item = self._add_command_item(name)
                if first_selectable_row < 0:
                    first_selectable_row = self._command_list.row(item)
        return first_selectable_row

    def _add_header_item(self, text: str) -> None:
        item = QListWidgetItem(text)
        header_font = item.font()
        header_font.setBold(True)
        item.setFont(header_font)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        self._command_list.addItem(item)

    def _add_command_item(self, command_name: str) -> QListWidgetItem:
        item = QListWidgetItem(command_name)
        item.setData(Qt.ItemDataRole.UserRole, command_name)
        self._command_list.addItem(item)
        return item

    def _sync_accept_button(self) -> None:
        ok_button = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button is not None:
            ok_button.setEnabled(self._command_list.currentItem() is not None)

    def accept(self) -> None:  # noqa: D401
        if self.selected_command_type() is None:
            return
        super().accept()


class _ReorderListWidget(QListWidget):
    """List widget that emits one stable visual-order snapshot after drops."""

    visual_order_changed = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        super().dropEvent(event)
        order: list[int] = []
        for row in range(self.count()):
            item = self.item(row)
            if item is None:
                continue
            value = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(value, int):
                order.append(value)
        if order:
            self.visual_order_changed.emit(order)


class CommandEditorDialog(QDialog):
    """Popup editor for one authored command."""

    def __init__(
        self,
        parent=None,
        *,
        area_picker: Callable[..., str | None] | None = None,
        asset_picker: Callable[..., str | None] | None = None,
        entity_picker: Callable[..., str | None] | None = None,
        entity_command_picker: Callable[..., str | None] | None = None,
        entity_dialogue_picker: Callable[..., str | None] | None = None,
        item_picker: Callable[..., str | None] | None = None,
        dialogue_picker: Callable[[str], str | None] | None = None,
        command_picker: Callable[[str], str | None] | None = None,
        command_spec_id_label: str | None = None,
        current_entity_id: str | None = None,
        current_area_id: str | None = None,
        current_entity_command_names: list[str] | tuple[str, ...] | None = None,
        current_entity_dialogue_names: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CommandEditorDialog")
        self.setWindowTitle("Edit Command")
        self.resize(820, 640)

        self._area_picker = area_picker
        self._asset_picker = asset_picker
        self._entity_picker = entity_picker
        self._entity_command_picker = entity_command_picker
        self._entity_dialogue_picker = entity_dialogue_picker
        self._item_picker = item_picker
        self._dialogue_picker = dialogue_picker
        self._command_picker = command_picker
        self._command_spec_id_label = (
            str(command_spec_id_label).strip() or None
            if command_spec_id_label is not None
            else None
        )
        self._current_entity_id = (
            str(current_entity_id).strip() or None if current_entity_id is not None else None
        )
        self._current_area_id = (
            str(current_area_id).strip() or None if current_area_id is not None else None
        )
        self._current_entity_command_names = tuple(
            str(name).strip()
            for name in (current_entity_command_names or ())
            if str(name).strip()
        )
        self._current_entity_dialogue_names = tuple(
            str(name).strip()
            for name in (current_entity_dialogue_names or ())
            if str(name).strip()
        )
        self._loaded_command: dict[str, Any] = {"type": ""}
        self._loading = False
        self._syncing_tabs = False
        self._inline_dialogue_definition: dict[str, Any] | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        note = QLabel(
            "Edit one command here. Supported commands get structured fields; use the JSON tab "
            "for advanced or unsupported parameters."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        outer.addWidget(note)

        self._tabs = QTabWidget()
        outer.addWidget(self._tabs, 1)

        structured = QWidget()
        structured_layout = QVBoxLayout(structured)
        structured_layout.setContentsMargins(0, 0, 0, 0)
        structured_layout.setSpacing(8)

        self._command_header = QLabel("Command")
        header_font = self._command_header.font()
        header_font.setBold(True)
        self._command_header.setFont(header_font)
        structured_layout.addWidget(self._command_header)

        type_row = QHBoxLayout()
        type_row.setContentsMargins(0, 0, 0, 0)
        type_row.addWidget(QLabel("type"))
        self._command_type_combo = QComboBox()
        self._command_type_combo.setEditable(False)
        self._command_type_combo.addItems(list(_known_command_names()))
        type_row.addWidget(self._command_type_combo, 1)
        structured_layout.addLayout(type_row)

        self._command_spec_id_widget = QWidget()
        command_spec_id_form = QFormLayout(self._command_spec_id_widget)
        command_spec_id_form.setContentsMargins(0, 0, 0, 0)
        self._command_spec_id_field = _OptionalTextField()
        command_spec_id_form.addRow(
            self._command_spec_id_label or "id",
            self._command_spec_id_field,
        )
        self._command_spec_id_widget.setVisible(self._command_spec_id_label is not None)
        structured_layout.addWidget(self._command_spec_id_widget)

        self._command_stack = QStackedWidget()
        structured_layout.addWidget(self._command_stack, 1)

        generic_font = QFont("Consolas", 10)
        generic_font.setStyleHint(QFont.StyleHint.Monospace)

        self._generic_page = QWidget()
        generic_layout = QVBoxLayout(self._generic_page)
        generic_layout.setContentsMargins(0, 0, 0, 0)
        generic_layout.addWidget(QLabel("Parameters JSON"))
        self._generic_params_edit = QPlainTextEdit()
        self._generic_params_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._generic_params_edit.setFont(generic_font)
        self._generic_params_edit.setPlaceholderText('{\n  "entity_id": "player_1"\n}')
        generic_layout.addWidget(self._generic_params_edit, 1)
        self._command_stack.addWidget(self._generic_page)

        def make_entity_id_row(
            *,
            parameter_name: str = "entity_id",
        ) -> tuple[QWidget, QLineEdit, QPushButton, QPushButton]:
            row, edit, pick_button, ref_button = _make_line_with_two_buttons(
                primary_button_text="Pick...",
                secondary_button_text="Ref...",
            )
            pick_button.clicked.connect(
                lambda: self._pick_entity_into_edit(
                    edit,
                    parameter_name=parameter_name,
                )
            )
            ref_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_edit(
                    edit,
                    ref_button,
                )
            )
            return row, edit, pick_button, ref_button

        def make_item_id_row() -> tuple[QWidget, QLineEdit, QPushButton]:
            row, edit, pick_button = _make_line_with_button(button_text="Pick...")
            pick_button.clicked.connect(lambda: self._pick_item_into_edit(edit))
            return row, edit, pick_button

        def make_area_id_row(
            *,
            parameter_name: str = "area_id",
        ) -> tuple[QWidget, QLineEdit, QPushButton]:
            row, edit, pick_button = _make_line_with_button(button_text="Pick...")
            pick_button.clicked.connect(
                lambda: self._pick_area_into_edit(
                    edit,
                    parameter_name=parameter_name,
                )
            )
            return row, edit, pick_button

        def make_field_name_combo() -> QComboBox:
            combo = QComboBox()
            combo.setEditable(True)
            for label, value in _ENTITY_FIELD_NAME_CHOICES:
                combo.addItem(label, value)
            return combo

        self._open_dialogue_page = QWidget()
        open_dialogue_form = QFormLayout(self._open_dialogue_page)
        open_dialogue_form.setContentsMargins(0, 0, 0, 0)
        self._dialogue_source_combo = QComboBox()
        self._dialogue_source_combo.addItems(["Inline Dialogue", "Dialogue File"])
        open_dialogue_form.addRow("dialogue_source", self._dialogue_source_combo)

        dialogue_file_row, self._dialogue_path_edit, self._dialogue_path_browse = _make_line_with_button(
            button_text="Browse..."
        )
        self._dialogue_path_browse.clicked.connect(self._on_browse_dialogue_path)
        open_dialogue_form.addRow("dialogue_path", dialogue_file_row)

        inline_row = QWidget()
        inline_layout = QHBoxLayout(inline_row)
        inline_layout.setContentsMargins(0, 0, 0, 0)
        inline_layout.setSpacing(6)
        self._inline_dialogue_summary = QLabel("0 segments")
        self._edit_inline_dialogue_button = QPushButton("Edit Dialogue...")
        self._edit_inline_dialogue_button.setAutoDefault(False)
        self._edit_inline_dialogue_button.setDefault(False)
        self._edit_inline_dialogue_button.clicked.connect(self._on_edit_inline_dialogue)
        inline_layout.addWidget(self._inline_dialogue_summary, 1)
        inline_layout.addWidget(self._edit_inline_dialogue_button)
        open_dialogue_form.addRow("dialogue_definition", inline_row)

        self._allow_cancel_field = QComboBox()
        self._setup_optional_bool_combo(self._allow_cancel_field)
        open_dialogue_form.addRow("allow_cancel", self._allow_cancel_field)

        self._open_dialogue_advanced_toggle = QToolButton()
        self._open_dialogue_advanced_toggle.setText("Advanced")
        self._open_dialogue_advanced_toggle.setCheckable(True)
        self._open_dialogue_advanced_toggle.setChecked(False)
        self._open_dialogue_advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._open_dialogue_advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._open_dialogue_advanced_toggle.toggled.connect(
            self._on_open_dialogue_advanced_toggled
        )
        open_dialogue_form.addRow(self._open_dialogue_advanced_toggle)

        self._open_dialogue_advanced_widget = QWidget()
        open_dialogue_advanced_form = QFormLayout(self._open_dialogue_advanced_widget)
        open_dialogue_advanced_form.setContentsMargins(12, 0, 0, 0)
        self._ui_preset_field = _OptionalTextField()
        self._ui_preset_field.changed.connect(self._sync_open_dialogue_advanced_state)
        open_dialogue_advanced_form.addRow("ui_preset", self._ui_preset_field)
        self._actor_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        self._actor_id_field.changed.connect(self._sync_open_dialogue_advanced_state)
        if self._actor_id_field.button is not None:
            self._actor_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._actor_id_field,
                    parameter_name="actor_id",
                )
            )
        if self._actor_id_field.extra_button is not None:
            self._actor_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._actor_id_field,
                    self._actor_id_field.extra_button,
                )
            )
        open_dialogue_advanced_form.addRow("actor_id", self._actor_id_field)
        self._caller_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        self._caller_id_field.changed.connect(self._sync_open_dialogue_advanced_state)
        if self._caller_id_field.button is not None:
            self._caller_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._caller_id_field,
                    parameter_name="caller_id",
                )
            )
        if self._caller_id_field.extra_button is not None:
            self._caller_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._caller_id_field,
                    self._caller_id_field.extra_button,
                )
            )
        open_dialogue_advanced_form.addRow("caller_id", self._caller_id_field)
        self._open_dialogue_entity_refs_field = _NamedEntityRefsField(
            pick_entity_callback=self._pick_entity_into_ref_value_edit,
            show_token_menu_callback=self._show_entity_token_menu_for_edit,
        )
        self._open_dialogue_entity_refs_field.changed.connect(
            self._sync_open_dialogue_advanced_state
        )
        open_dialogue_advanced_form.addRow(
            "entity_refs",
            self._open_dialogue_entity_refs_field,
        )
        open_dialogue_form.addRow(self._open_dialogue_advanced_widget)
        self._command_stack.addWidget(self._open_dialogue_page)

        self._run_project_command_page = QWidget()
        run_project_form = QFormLayout(self._run_project_command_page)
        run_project_form.setContentsMargins(0, 0, 0, 0)
        command_row, self._project_command_id_edit, self._project_command_browse = _make_line_with_button(
            button_text="Browse..."
        )
        self._project_command_browse.clicked.connect(self._on_browse_project_command_id)
        run_project_form.addRow("command_id", command_row)
        self._run_project_advanced_toggle = QToolButton()
        self._run_project_advanced_toggle.setText("Advanced")
        self._run_project_advanced_toggle.setCheckable(True)
        self._run_project_advanced_toggle.setChecked(False)
        self._run_project_advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._run_project_advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._run_project_advanced_toggle.toggled.connect(
            self._on_run_project_advanced_toggled
        )
        run_project_form.addRow(self._run_project_advanced_toggle)
        self._run_project_advanced_widget = QWidget()
        run_project_advanced_form = QFormLayout(self._run_project_advanced_widget)
        run_project_advanced_form.setContentsMargins(12, 0, 0, 0)
        self._run_project_source_entity_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        self._run_project_source_entity_id_field.changed.connect(
            self._sync_run_project_advanced_state
        )
        if self._run_project_source_entity_id_field.button is not None:
            self._run_project_source_entity_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._run_project_source_entity_id_field,
                    parameter_name="source_entity_id",
                )
            )
        if self._run_project_source_entity_id_field.extra_button is not None:
            self._run_project_source_entity_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._run_project_source_entity_id_field,
                    self._run_project_source_entity_id_field.extra_button,
                )
            )
        run_project_advanced_form.addRow(
            "source_entity_id",
            self._run_project_source_entity_id_field,
        )
        self._run_project_refs_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._run_project_refs_mode_field,
            [
                ("inherit", "inherit"),
                ("merge", "merge"),
                ("replace", "replace"),
            ],
        )
        self._run_project_refs_mode_field.currentIndexChanged.connect(
            self._sync_run_project_advanced_state
        )
        run_project_advanced_form.addRow("refs_mode", self._run_project_refs_mode_field)
        self._run_project_entity_refs_field = _NamedEntityRefsField(
            pick_entity_callback=self._pick_entity_into_ref_value_edit,
            show_token_menu_callback=self._show_entity_token_menu_for_edit,
        )
        self._run_project_entity_refs_field.changed.connect(
            self._sync_run_project_advanced_state
        )
        run_project_advanced_form.addRow(
            "entity_refs",
            self._run_project_entity_refs_field,
        )
        run_project_form.addRow(self._run_project_advanced_widget)
        self._command_stack.addWidget(self._run_project_command_page)

        self._run_entity_command_page = QWidget()
        run_entity_form = QFormLayout(self._run_entity_command_page)
        run_entity_form.setContentsMargins(0, 0, 0, 0)
        (
            run_entity_entity_row,
            self._run_entity_entity_id_edit,
            self._run_entity_entity_pick,
            self._run_entity_entity_ref,
        ) = _make_line_with_two_buttons(
            primary_button_text="Pick...",
            secondary_button_text="Ref...",
        )
        self._run_entity_entity_pick.clicked.connect(
            lambda: self._pick_entity_into_edit(
                self._run_entity_entity_id_edit,
                parameter_name="entity_id",
            )
        )
        self._run_entity_entity_ref.clicked.connect(
            lambda: self._show_entity_token_menu_for_edit(
                self._run_entity_entity_id_edit,
                self._run_entity_entity_ref,
            )
        )
        self._run_entity_entity_id_edit.textChanged.connect(
            self._sync_entity_command_picker_button_state
        )
        run_entity_form.addRow("entity_id", run_entity_entity_row)
        (
            run_entity_command_row,
            self._run_entity_command_id_edit,
            self._run_entity_command_pick,
        ) = _make_line_with_button(button_text="Pick...")
        self._run_entity_command_pick.clicked.connect(
            lambda: self._pick_entity_command_id_into_edit(
                self._run_entity_command_id_edit,
                entity_id_edit=self._run_entity_entity_id_edit,
            )
        )
        run_entity_form.addRow("command_id", run_entity_command_row)
        self._run_entity_advanced_toggle = QToolButton()
        self._run_entity_advanced_toggle.setText("Advanced")
        self._run_entity_advanced_toggle.setCheckable(True)
        self._run_entity_advanced_toggle.setChecked(False)
        self._run_entity_advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._run_entity_advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._run_entity_advanced_toggle.toggled.connect(
            self._on_run_entity_advanced_toggled
        )
        run_entity_form.addRow(self._run_entity_advanced_toggle)
        self._run_entity_advanced_widget = QWidget()
        run_entity_advanced_form = QFormLayout(self._run_entity_advanced_widget)
        run_entity_advanced_form.setContentsMargins(12, 0, 0, 0)
        self._run_entity_source_entity_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        self._run_entity_source_entity_id_field.changed.connect(
            self._sync_run_entity_advanced_state
        )
        if self._run_entity_source_entity_id_field.button is not None:
            self._run_entity_source_entity_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._run_entity_source_entity_id_field,
                    parameter_name="source_entity_id",
                )
            )
        if self._run_entity_source_entity_id_field.extra_button is not None:
            self._run_entity_source_entity_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._run_entity_source_entity_id_field,
                    self._run_entity_source_entity_id_field.extra_button,
                )
            )
        run_entity_advanced_form.addRow(
            "source_entity_id",
            self._run_entity_source_entity_id_field,
        )
        self._run_entity_refs_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._run_entity_refs_mode_field,
            [
                ("inherit", "inherit"),
                ("merge", "merge"),
                ("replace", "replace"),
            ],
        )
        self._run_entity_refs_mode_field.currentIndexChanged.connect(
            self._sync_run_entity_advanced_state
        )
        run_entity_advanced_form.addRow("refs_mode", self._run_entity_refs_mode_field)
        self._run_entity_entity_refs_field = _NamedEntityRefsField(
            pick_entity_callback=self._pick_entity_into_ref_value_edit,
            show_token_menu_callback=self._show_entity_token_menu_for_edit,
        )
        self._run_entity_entity_refs_field.changed.connect(
            self._sync_run_entity_advanced_state
        )
        run_entity_advanced_form.addRow("entity_refs", self._run_entity_entity_refs_field)
        run_entity_form.addRow(self._run_entity_advanced_widget)
        self._command_stack.addWidget(self._run_entity_command_page)

        self._run_sequence_page = QWidget()
        run_sequence_form = QFormLayout(self._run_sequence_page)
        run_sequence_form.setContentsMargins(0, 0, 0, 0)
        self._run_sequence_commands_field = _NestedCommandListField(
            button_text="Edit Child Commands...",
        )
        self._run_sequence_commands_field.edit_requested.connect(
            self._on_edit_run_sequence_commands
        )
        run_sequence_form.addRow("commands", self._run_sequence_commands_field)
        self._run_sequence_advanced_toggle = QToolButton()
        self._run_sequence_advanced_toggle.setText("Advanced")
        self._run_sequence_advanced_toggle.setCheckable(True)
        self._run_sequence_advanced_toggle.setChecked(False)
        self._run_sequence_advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._run_sequence_advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._run_sequence_advanced_toggle.toggled.connect(
            self._on_run_sequence_advanced_toggled
        )
        run_sequence_form.addRow(self._run_sequence_advanced_toggle)
        self._run_sequence_advanced_widget = QWidget()
        run_sequence_advanced_form = QFormLayout(self._run_sequence_advanced_widget)
        run_sequence_advanced_form.setContentsMargins(12, 0, 0, 0)
        self._run_sequence_source_entity_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        self._run_sequence_source_entity_id_field.changed.connect(
            self._sync_run_sequence_advanced_state
        )
        if self._run_sequence_source_entity_id_field.button is not None:
            self._run_sequence_source_entity_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._run_sequence_source_entity_id_field,
                    parameter_name="source_entity_id",
                )
            )
        if self._run_sequence_source_entity_id_field.extra_button is not None:
            self._run_sequence_source_entity_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._run_sequence_source_entity_id_field,
                    self._run_sequence_source_entity_id_field.extra_button,
                )
            )
        run_sequence_advanced_form.addRow(
            "source_entity_id",
            self._run_sequence_source_entity_id_field,
        )
        self._run_sequence_refs_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._run_sequence_refs_mode_field,
            [
                ("inherit", "inherit"),
                ("merge", "merge"),
                ("replace", "replace"),
            ],
        )
        self._run_sequence_refs_mode_field.currentIndexChanged.connect(
            self._sync_run_sequence_advanced_state
        )
        run_sequence_advanced_form.addRow("refs_mode", self._run_sequence_refs_mode_field)
        self._run_sequence_entity_refs_field = _NamedEntityRefsField(
            pick_entity_callback=self._pick_entity_into_ref_value_edit,
            show_token_menu_callback=self._show_entity_token_menu_for_edit,
        )
        self._run_sequence_entity_refs_field.changed.connect(
            self._sync_run_sequence_advanced_state
        )
        run_sequence_advanced_form.addRow(
            "entity_refs",
            self._run_sequence_entity_refs_field,
        )
        run_sequence_form.addRow(self._run_sequence_advanced_widget)
        self._command_stack.addWidget(self._run_sequence_page)

        self._spawn_flow_page = QWidget()
        spawn_flow_form = QFormLayout(self._spawn_flow_page)
        spawn_flow_form.setContentsMargins(0, 0, 0, 0)
        self._spawn_flow_commands_field = _NestedCommandListField(
            button_text="Edit Child Commands...",
            note_text="Starts the child flow immediately and returns without waiting.",
        )
        self._spawn_flow_commands_field.edit_requested.connect(
            self._on_edit_spawn_flow_commands
        )
        spawn_flow_form.addRow("commands", self._spawn_flow_commands_field)
        self._spawn_flow_advanced_toggle = QToolButton()
        self._spawn_flow_advanced_toggle.setText("Advanced")
        self._spawn_flow_advanced_toggle.setCheckable(True)
        self._spawn_flow_advanced_toggle.setChecked(False)
        self._spawn_flow_advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._spawn_flow_advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._spawn_flow_advanced_toggle.toggled.connect(
            self._on_spawn_flow_advanced_toggled
        )
        spawn_flow_form.addRow(self._spawn_flow_advanced_toggle)
        self._spawn_flow_advanced_widget = QWidget()
        spawn_flow_advanced_form = QFormLayout(self._spawn_flow_advanced_widget)
        spawn_flow_advanced_form.setContentsMargins(12, 0, 0, 0)
        self._spawn_flow_source_entity_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        self._spawn_flow_source_entity_id_field.changed.connect(
            self._sync_spawn_flow_advanced_state
        )
        if self._spawn_flow_source_entity_id_field.button is not None:
            self._spawn_flow_source_entity_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._spawn_flow_source_entity_id_field,
                    parameter_name="source_entity_id",
                )
            )
        if self._spawn_flow_source_entity_id_field.extra_button is not None:
            self._spawn_flow_source_entity_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._spawn_flow_source_entity_id_field,
                    self._spawn_flow_source_entity_id_field.extra_button,
                )
            )
        spawn_flow_advanced_form.addRow(
            "source_entity_id",
            self._spawn_flow_source_entity_id_field,
        )
        self._spawn_flow_refs_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._spawn_flow_refs_mode_field,
            [
                ("inherit", "inherit"),
                ("merge", "merge"),
                ("replace", "replace"),
            ],
        )
        self._spawn_flow_refs_mode_field.currentIndexChanged.connect(
            self._sync_spawn_flow_advanced_state
        )
        spawn_flow_advanced_form.addRow("refs_mode", self._spawn_flow_refs_mode_field)
        self._spawn_flow_entity_refs_field = _NamedEntityRefsField(
            pick_entity_callback=self._pick_entity_into_ref_value_edit,
            show_token_menu_callback=self._show_entity_token_menu_for_edit,
        )
        self._spawn_flow_entity_refs_field.changed.connect(
            self._sync_spawn_flow_advanced_state
        )
        spawn_flow_advanced_form.addRow(
            "entity_refs",
            self._spawn_flow_entity_refs_field,
        )
        spawn_flow_form.addRow(self._spawn_flow_advanced_widget)
        self._command_stack.addWidget(self._spawn_flow_page)

        self._run_parallel_page = QWidget()
        run_parallel_form = QFormLayout(self._run_parallel_page)
        run_parallel_form.setContentsMargins(0, 0, 0, 0)
        self._run_parallel_commands_field = _NestedCommandListField(
            button_text="Edit Parallel Branches...",
            note_text=(
                "Each entry is one parallel branch. Use run_sequence inside a branch "
                "when that branch needs multiple steps."
            ),
        )
        self._run_parallel_commands_field.edit_requested.connect(
            self._on_edit_run_parallel_commands
        )
        run_parallel_form.addRow("commands", self._run_parallel_commands_field)
        self._run_parallel_completion_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._run_parallel_completion_mode_field,
            [
                ("all", "all"),
                ("any", "any"),
                ("child", "child"),
            ],
            not_set_label="Default (all)",
        )
        self._run_parallel_completion_mode_field.currentIndexChanged.connect(
            self._sync_run_parallel_completion_visibility
        )
        run_parallel_form.addRow("completion.mode", self._run_parallel_completion_mode_field)
        self._run_parallel_child_id_row = QWidget()
        run_parallel_child_id_layout = QHBoxLayout(self._run_parallel_child_id_row)
        run_parallel_child_id_layout.setContentsMargins(0, 0, 0, 0)
        run_parallel_child_id_layout.setSpacing(0)
        self._run_parallel_child_id_combo = QComboBox()
        self._run_parallel_child_id_combo.setEditable(True)
        self._run_parallel_child_id_combo.setInsertPolicy(
            QComboBox.InsertPolicy.NoInsert
        )
        run_parallel_child_id_layout.addWidget(self._run_parallel_child_id_combo)
        run_parallel_form.addRow("completion.child_id", self._run_parallel_child_id_row)
        self._run_parallel_completion_note = QLabel(
            "Remaining branches keep running after early completion."
        )
        self._run_parallel_completion_note.setWordWrap(True)
        self._run_parallel_completion_note.setStyleSheet("color: #666;")
        run_parallel_form.addRow(self._run_parallel_completion_note)
        self._run_parallel_advanced_toggle = QToolButton()
        self._run_parallel_advanced_toggle.setText("Advanced")
        self._run_parallel_advanced_toggle.setCheckable(True)
        self._run_parallel_advanced_toggle.setChecked(False)
        self._run_parallel_advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._run_parallel_advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._run_parallel_advanced_toggle.toggled.connect(
            self._on_run_parallel_advanced_toggled
        )
        run_parallel_form.addRow(self._run_parallel_advanced_toggle)
        self._run_parallel_advanced_widget = QWidget()
        run_parallel_advanced_form = QFormLayout(self._run_parallel_advanced_widget)
        run_parallel_advanced_form.setContentsMargins(12, 0, 0, 0)
        self._run_parallel_source_entity_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        self._run_parallel_source_entity_id_field.changed.connect(
            self._sync_run_parallel_advanced_state
        )
        if self._run_parallel_source_entity_id_field.button is not None:
            self._run_parallel_source_entity_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._run_parallel_source_entity_id_field,
                    parameter_name="source_entity_id",
                )
            )
        if self._run_parallel_source_entity_id_field.extra_button is not None:
            self._run_parallel_source_entity_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._run_parallel_source_entity_id_field,
                    self._run_parallel_source_entity_id_field.extra_button,
                )
            )
        run_parallel_advanced_form.addRow(
            "source_entity_id",
            self._run_parallel_source_entity_id_field,
        )
        self._run_parallel_refs_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._run_parallel_refs_mode_field,
            [
                ("inherit", "inherit"),
                ("merge", "merge"),
                ("replace", "replace"),
            ],
        )
        self._run_parallel_refs_mode_field.currentIndexChanged.connect(
            self._sync_run_parallel_advanced_state
        )
        run_parallel_advanced_form.addRow("refs_mode", self._run_parallel_refs_mode_field)
        self._run_parallel_entity_refs_field = _NamedEntityRefsField(
            pick_entity_callback=self._pick_entity_into_ref_value_edit,
            show_token_menu_callback=self._show_entity_token_menu_for_edit,
        )
        self._run_parallel_entity_refs_field.changed.connect(
            self._sync_run_parallel_advanced_state
        )
        run_parallel_advanced_form.addRow(
            "entity_refs",
            self._run_parallel_entity_refs_field,
        )
        run_parallel_form.addRow(self._run_parallel_advanced_widget)
        self._command_stack.addWidget(self._run_parallel_page)

        self._run_commands_for_collection_page = QWidget()
        run_for_each_form = QFormLayout(self._run_commands_for_collection_page)
        run_for_each_form.setContentsMargins(0, 0, 0, 0)
        self._run_for_each_value_edit = QPlainTextEdit()
        self._run_for_each_value_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._run_for_each_value_edit.setPlaceholderText(
            '[{"entity_id": "door_1"}, {"entity_id": "door_2"}]\n"$self.targets_here"'
        )
        run_for_each_form.addRow("value", self._run_for_each_value_edit)
        self._run_for_each_value_note = QLabel(
            "Enter a JSON value that resolves to a list or null. Use JSON arrays directly, "
            "or a quoted token string such as \"$self.targets_here\"."
        )
        self._run_for_each_value_note.setWordWrap(True)
        self._run_for_each_value_note.setStyleSheet("color: #666;")
        run_for_each_form.addRow(self._run_for_each_value_note)
        self._run_for_each_item_param_field = _OptionalTextField()
        run_for_each_form.addRow("item_param", self._run_for_each_item_param_field)
        self._run_for_each_index_param_field = _OptionalTextField()
        run_for_each_form.addRow("index_param", self._run_for_each_index_param_field)
        self._run_for_each_tokens_note = QLabel(
            "Child commands can read the current loop values with $item and $index, "
            "or with your custom names when item_param / index_param are set."
        )
        self._run_for_each_tokens_note.setWordWrap(True)
        self._run_for_each_tokens_note.setStyleSheet("color: #666;")
        run_for_each_form.addRow(self._run_for_each_tokens_note)
        self._run_for_each_commands_field = _NestedCommandListField(
            button_text="Edit Child Commands...",
        )
        self._run_for_each_commands_field.edit_requested.connect(
            self._on_edit_run_commands_for_collection_commands
        )
        run_for_each_form.addRow("commands", self._run_for_each_commands_field)
        self._run_for_each_advanced_toggle = QToolButton()
        self._run_for_each_advanced_toggle.setText("Advanced")
        self._run_for_each_advanced_toggle.setCheckable(True)
        self._run_for_each_advanced_toggle.setChecked(False)
        self._run_for_each_advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._run_for_each_advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._run_for_each_advanced_toggle.toggled.connect(
            self._on_run_for_each_advanced_toggled
        )
        run_for_each_form.addRow(self._run_for_each_advanced_toggle)
        self._run_for_each_advanced_widget = QWidget()
        run_for_each_advanced_form = QFormLayout(self._run_for_each_advanced_widget)
        run_for_each_advanced_form.setContentsMargins(12, 0, 0, 0)
        self._run_for_each_source_entity_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        self._run_for_each_source_entity_id_field.changed.connect(
            self._sync_run_for_each_advanced_state
        )
        if self._run_for_each_source_entity_id_field.button is not None:
            self._run_for_each_source_entity_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._run_for_each_source_entity_id_field,
                    parameter_name="source_entity_id",
                )
            )
        if self._run_for_each_source_entity_id_field.extra_button is not None:
            self._run_for_each_source_entity_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._run_for_each_source_entity_id_field,
                    self._run_for_each_source_entity_id_field.extra_button,
                )
            )
        run_for_each_advanced_form.addRow(
            "source_entity_id",
            self._run_for_each_source_entity_id_field,
        )
        self._run_for_each_refs_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._run_for_each_refs_mode_field,
            [
                ("inherit", "inherit"),
                ("merge", "merge"),
                ("replace", "replace"),
            ],
        )
        self._run_for_each_refs_mode_field.currentIndexChanged.connect(
            self._sync_run_for_each_advanced_state
        )
        run_for_each_advanced_form.addRow("refs_mode", self._run_for_each_refs_mode_field)
        self._run_for_each_entity_refs_field = _NamedEntityRefsField(
            pick_entity_callback=self._pick_entity_into_ref_value_edit,
            show_token_menu_callback=self._show_entity_token_menu_for_edit,
        )
        self._run_for_each_entity_refs_field.changed.connect(
            self._sync_run_for_each_advanced_state
        )
        run_for_each_advanced_form.addRow(
            "entity_refs",
            self._run_for_each_entity_refs_field,
        )
        run_for_each_form.addRow(self._run_for_each_advanced_widget)
        self._command_stack.addWidget(self._run_commands_for_collection_page)

        self._if_page = QWidget()
        if_form = QFormLayout(self._if_page)
        if_form.setContentsMargins(0, 0, 0, 0)
        self._if_left_edit = QPlainTextEdit()
        self._if_left_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._if_left_edit.setPlaceholderText('"$current_area.gate_open"\n\nor\n\ntrue')
        if_form.addRow("left", self._if_left_edit)
        self._if_op_field = QComboBox()
        for value in ("eq", "neq", "gt", "gte", "lt", "lte"):
            self._if_op_field.addItem(value, value)
        if_form.addRow("op", self._if_op_field)
        self._if_right_edit = QPlainTextEdit()
        self._if_right_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._if_right_edit.setPlaceholderText("true\n\nor\n\n\"locked\"")
        if_form.addRow("right", self._if_right_edit)
        self._if_value_note = QLabel(
            "Enter any JSON value. Use literals directly, or a quoted token string such as "
            "\"$current_area.gate_open\"."
        )
        self._if_value_note.setWordWrap(True)
        self._if_value_note.setStyleSheet("color: #666;")
        if_form.addRow(self._if_value_note)
        self._if_then_commands_field = _NestedCommandListField(
            button_text="Edit Then Commands...",
        )
        self._if_then_commands_field.edit_requested.connect(self._on_edit_if_then_commands)
        if_form.addRow("then", self._if_then_commands_field)
        self._if_else_commands_field = _NestedCommandListField(
            button_text="Edit Else Commands...",
        )
        self._if_else_commands_field.edit_requested.connect(self._on_edit_if_else_commands)
        if_form.addRow("else", self._if_else_commands_field)
        self._command_stack.addWidget(self._if_page)

        self._change_area_page = QWidget()
        change_area_form = QFormLayout(self._change_area_page)
        change_area_form.setContentsMargins(0, 0, 0, 0)
        (
            change_area_area_row,
            self._change_area_area_id_edit,
            self._change_area_area_pick,
        ) = _make_line_with_button(button_text="Pick...")
        self._change_area_area_pick.clicked.connect(
            lambda: self._pick_area_into_edit(
                self._change_area_area_id_edit,
                parameter_name="area_id",
            )
        )
        change_area_form.addRow("area_id", change_area_area_row)
        self._change_area_entry_id_field = _OptionalTextField()
        change_area_form.addRow("entry_id", self._change_area_entry_id_field)
        self._change_area_destination_entity_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        if self._change_area_destination_entity_id_field.button is not None:
            self._change_area_destination_entity_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._change_area_destination_entity_id_field,
                    parameter_name="destination_entity_id",
                )
            )
        if self._change_area_destination_entity_id_field.extra_button is not None:
            self._change_area_destination_entity_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._change_area_destination_entity_id_field,
                    self._change_area_destination_entity_id_field.extra_button,
                )
            )
        change_area_form.addRow(
            "destination_entity_id",
            self._change_area_destination_entity_id_field,
        )
        self._change_area_transfer_entity_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        if self._change_area_transfer_entity_id_field.button is not None:
            self._change_area_transfer_entity_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._change_area_transfer_entity_id_field,
                    parameter_name="transfer_entity_id",
                )
            )
        if self._change_area_transfer_entity_id_field.extra_button is not None:
            self._change_area_transfer_entity_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._change_area_transfer_entity_id_field,
                    self._change_area_transfer_entity_id_field.extra_button,
                )
            )
        change_area_form.addRow(
            "transfer_entity_id",
            self._change_area_transfer_entity_id_field,
        )
        self._change_area_transfer_entity_ids_field = _OptionalTextField()
        change_area_form.addRow(
            "transfer_entity_ids",
            self._change_area_transfer_entity_ids_field,
        )
        self._change_area_transfer_note = QLabel(
            "transfer_entity_ids is a comma-separated list of entity ids or tokens."
        )
        self._change_area_transfer_note.setWordWrap(True)
        self._change_area_transfer_note.setStyleSheet("color: #666;")
        change_area_form.addRow(self._change_area_transfer_note)
        self._change_area_camera_follow_field = _CameraFollowPatchField(
            pick_entity_callback=lambda edit: self._pick_entity_into_edit(
                edit,
                parameter_name="camera_follow.entity_id",
            ),
            show_token_menu_callback=self._show_entity_token_menu_for_edit,
        )
        change_area_form.addRow("camera_follow", self._change_area_camera_follow_field)
        self._change_area_advanced_toggle = QToolButton()
        self._change_area_advanced_toggle.setText("Advanced")
        self._change_area_advanced_toggle.setCheckable(True)
        self._change_area_advanced_toggle.setChecked(False)
        self._change_area_advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._change_area_advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._change_area_advanced_toggle.toggled.connect(
            self._on_change_area_advanced_toggled
        )
        change_area_form.addRow(self._change_area_advanced_toggle)
        self._change_area_advanced_widget = QWidget()
        change_area_advanced_form = QFormLayout(self._change_area_advanced_widget)
        change_area_advanced_form.setContentsMargins(12, 0, 0, 0)
        self._change_area_allowed_instigator_kinds_field = _OptionalTextField()
        self._change_area_allowed_instigator_kinds_field.changed.connect(
            self._sync_change_area_advanced_state
        )
        change_area_advanced_form.addRow(
            "allowed_instigator_kinds",
            self._change_area_allowed_instigator_kinds_field,
        )
        self._change_area_source_entity_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        self._change_area_source_entity_id_field.changed.connect(
            self._sync_change_area_advanced_state
        )
        if self._change_area_source_entity_id_field.button is not None:
            self._change_area_source_entity_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._change_area_source_entity_id_field,
                    parameter_name="source_entity_id",
                )
            )
        if self._change_area_source_entity_id_field.extra_button is not None:
            self._change_area_source_entity_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._change_area_source_entity_id_field,
                    self._change_area_source_entity_id_field.extra_button,
                )
            )
        change_area_advanced_form.addRow(
            "source_entity_id",
            self._change_area_source_entity_id_field,
        )
        self._change_area_entity_refs_field = _NamedEntityRefsField(
            pick_entity_callback=self._pick_entity_into_ref_value_edit,
            show_token_menu_callback=self._show_entity_token_menu_for_edit,
        )
        self._change_area_entity_refs_field.changed.connect(
            self._sync_change_area_advanced_state
        )
        change_area_advanced_form.addRow("entity_refs", self._change_area_entity_refs_field)
        change_area_form.addRow(self._change_area_advanced_widget)
        self._command_stack.addWidget(self._change_area_page)

        self._new_game_page = QWidget()
        new_game_form = QFormLayout(self._new_game_page)
        new_game_form.setContentsMargins(0, 0, 0, 0)
        (
            new_game_area_row,
            self._new_game_area_id_edit,
            self._new_game_area_pick,
        ) = _make_line_with_button(button_text="Pick...")
        self._new_game_area_pick.clicked.connect(
            lambda: self._pick_area_into_edit(
                self._new_game_area_id_edit,
                parameter_name="area_id",
            )
        )
        new_game_form.addRow("area_id", new_game_area_row)
        self._new_game_entry_id_field = _OptionalTextField()
        new_game_form.addRow("entry_id", self._new_game_entry_id_field)
        self._new_game_destination_entity_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        if self._new_game_destination_entity_id_field.button is not None:
            self._new_game_destination_entity_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._new_game_destination_entity_id_field,
                    parameter_name="destination_entity_id",
                )
            )
        if self._new_game_destination_entity_id_field.extra_button is not None:
            self._new_game_destination_entity_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._new_game_destination_entity_id_field,
                    self._new_game_destination_entity_id_field.extra_button,
                )
            )
        new_game_form.addRow(
            "destination_entity_id",
            self._new_game_destination_entity_id_field,
        )
        self._new_game_source_entity_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        if self._new_game_source_entity_id_field.button is not None:
            self._new_game_source_entity_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._new_game_source_entity_id_field,
                    parameter_name="source_entity_id",
                )
            )
        if self._new_game_source_entity_id_field.extra_button is not None:
            self._new_game_source_entity_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._new_game_source_entity_id_field,
                    self._new_game_source_entity_id_field.extra_button,
                )
            )
        new_game_form.addRow("source_entity_id", self._new_game_source_entity_id_field)
        self._new_game_camera_follow_field = _CameraFollowPatchField(
            pick_entity_callback=lambda edit: self._pick_entity_into_edit(
                edit,
                parameter_name="camera_follow.entity_id",
            ),
            show_token_menu_callback=self._show_entity_token_menu_for_edit,
        )
        new_game_form.addRow("camera_follow", self._new_game_camera_follow_field)
        self._command_stack.addWidget(self._new_game_page)

        self._set_camera_follow_entity_page = QWidget()
        set_camera_follow_entity_form = QFormLayout(self._set_camera_follow_entity_page)
        set_camera_follow_entity_form.setContentsMargins(0, 0, 0, 0)
        (
            entity_follow_row,
            self._set_camera_follow_entity_id_edit,
            self._set_camera_follow_entity_pick,
            self._set_camera_follow_entity_ref,
        ) = _make_line_with_two_buttons(
            primary_button_text="Pick...",
            secondary_button_text="Ref...",
        )
        self._set_camera_follow_entity_pick.clicked.connect(
            lambda: self._pick_entity_into_edit(
                self._set_camera_follow_entity_id_edit,
                parameter_name="entity_id",
            )
        )
        self._set_camera_follow_entity_ref.clicked.connect(
            lambda: self._show_entity_token_menu_for_edit(
                self._set_camera_follow_entity_id_edit,
                self._set_camera_follow_entity_ref,
            )
        )
        set_camera_follow_entity_form.addRow("entity_id", entity_follow_row)
        self._set_camera_follow_entity_offset_x_spin = QDoubleSpinBox()
        self._set_camera_follow_entity_offset_x_spin.setRange(-999999.0, 999999.0)
        self._set_camera_follow_entity_offset_x_spin.setDecimals(3)
        self._set_camera_follow_entity_offset_x_spin.setSingleStep(1.0)
        set_camera_follow_entity_form.addRow("offset_x", self._set_camera_follow_entity_offset_x_spin)
        self._set_camera_follow_entity_offset_y_spin = QDoubleSpinBox()
        self._set_camera_follow_entity_offset_y_spin.setRange(-999999.0, 999999.0)
        self._set_camera_follow_entity_offset_y_spin.setDecimals(3)
        self._set_camera_follow_entity_offset_y_spin.setSingleStep(1.0)
        set_camera_follow_entity_form.addRow("offset_y", self._set_camera_follow_entity_offset_y_spin)
        self._command_stack.addWidget(self._set_camera_follow_entity_page)

        self._set_camera_follow_input_target_page = QWidget()
        set_camera_follow_input_form = QFormLayout(self._set_camera_follow_input_target_page)
        set_camera_follow_input_form.setContentsMargins(0, 0, 0, 0)
        self._set_camera_follow_input_action_edit = QLineEdit()
        set_camera_follow_input_form.addRow("action", self._set_camera_follow_input_action_edit)
        self._set_camera_follow_input_offset_x_spin = QDoubleSpinBox()
        self._set_camera_follow_input_offset_x_spin.setRange(-999999.0, 999999.0)
        self._set_camera_follow_input_offset_x_spin.setDecimals(3)
        self._set_camera_follow_input_offset_x_spin.setSingleStep(1.0)
        set_camera_follow_input_form.addRow("offset_x", self._set_camera_follow_input_offset_x_spin)
        self._set_camera_follow_input_offset_y_spin = QDoubleSpinBox()
        self._set_camera_follow_input_offset_y_spin.setRange(-999999.0, 999999.0)
        self._set_camera_follow_input_offset_y_spin.setDecimals(3)
        self._set_camera_follow_input_offset_y_spin.setSingleStep(1.0)
        set_camera_follow_input_form.addRow("offset_y", self._set_camera_follow_input_offset_y_spin)
        self._command_stack.addWidget(self._set_camera_follow_input_target_page)

        self._clear_camera_follow_page = QWidget()
        clear_camera_follow_layout = QVBoxLayout(self._clear_camera_follow_page)
        clear_camera_follow_layout.setContentsMargins(0, 0, 0, 0)
        self._clear_camera_follow_note = QLabel(
            "Clear the current camera follow target without changing bounds or deadzone."
        )
        self._clear_camera_follow_note.setWordWrap(True)
        self._clear_camera_follow_note.setStyleSheet("color: #666;")
        clear_camera_follow_layout.addWidget(self._clear_camera_follow_note)
        clear_camera_follow_layout.addStretch(1)
        self._command_stack.addWidget(self._clear_camera_follow_page)

        self._set_camera_policy_page = QWidget()
        set_camera_policy_form = QFormLayout(self._set_camera_policy_page)
        set_camera_policy_form.setContentsMargins(0, 0, 0, 0)
        self._set_camera_policy_follow_field = _CameraFollowPatchField(
            pick_entity_callback=lambda edit: self._pick_entity_into_edit(
                edit,
                parameter_name="follow.entity_id",
            ),
            show_token_menu_callback=self._show_entity_token_menu_for_edit,
        )
        set_camera_policy_form.addRow("follow", self._set_camera_policy_follow_field)
        self._set_camera_policy_bounds_field = _CameraRectPatchField(
            space_choices=_CAMERA_WORLD_SPACE_CHOICES,
        )
        set_camera_policy_form.addRow("bounds", self._set_camera_policy_bounds_field)
        self._set_camera_policy_deadzone_field = _CameraRectPatchField(
            space_choices=_CAMERA_VIEWPORT_SPACE_CHOICES,
        )
        set_camera_policy_form.addRow("deadzone", self._set_camera_policy_deadzone_field)
        self._command_stack.addWidget(self._set_camera_policy_page)

        self._push_camera_state_page = QWidget()
        push_camera_state_layout = QVBoxLayout(self._push_camera_state_page)
        push_camera_state_layout.setContentsMargins(0, 0, 0, 0)
        self._push_camera_state_note = QLabel(
            "Push the current camera state onto the runtime camera stack."
        )
        self._push_camera_state_note.setWordWrap(True)
        self._push_camera_state_note.setStyleSheet("color: #666;")
        push_camera_state_layout.addWidget(self._push_camera_state_note)
        push_camera_state_layout.addStretch(1)
        self._command_stack.addWidget(self._push_camera_state_page)

        self._pop_camera_state_page = QWidget()
        pop_camera_state_layout = QVBoxLayout(self._pop_camera_state_page)
        pop_camera_state_layout.setContentsMargins(0, 0, 0, 0)
        self._pop_camera_state_note = QLabel(
            "Restore the most recently pushed camera state."
        )
        self._pop_camera_state_note.setWordWrap(True)
        self._pop_camera_state_note.setStyleSheet("color: #666;")
        pop_camera_state_layout.addWidget(self._pop_camera_state_note)
        pop_camera_state_layout.addStretch(1)
        self._command_stack.addWidget(self._pop_camera_state_page)

        self._set_camera_bounds_page = QWidget()
        set_camera_bounds_form = QFormLayout(self._set_camera_bounds_page)
        set_camera_bounds_form.setContentsMargins(0, 0, 0, 0)
        self._set_camera_bounds_editor = _CameraRectEditor(
            space_choices=_CAMERA_WORLD_SPACE_CHOICES,
        )
        set_camera_bounds_form.addRow("bounds", self._set_camera_bounds_editor)
        self._command_stack.addWidget(self._set_camera_bounds_page)

        self._clear_camera_bounds_page = QWidget()
        clear_camera_bounds_layout = QVBoxLayout(self._clear_camera_bounds_page)
        clear_camera_bounds_layout.setContentsMargins(0, 0, 0, 0)
        self._clear_camera_bounds_note = QLabel(
            "Remove the active camera bounds rectangle."
        )
        self._clear_camera_bounds_note.setWordWrap(True)
        self._clear_camera_bounds_note.setStyleSheet("color: #666;")
        clear_camera_bounds_layout.addWidget(self._clear_camera_bounds_note)
        clear_camera_bounds_layout.addStretch(1)
        self._command_stack.addWidget(self._clear_camera_bounds_page)

        self._set_camera_deadzone_page = QWidget()
        set_camera_deadzone_form = QFormLayout(self._set_camera_deadzone_page)
        set_camera_deadzone_form.setContentsMargins(0, 0, 0, 0)
        self._set_camera_deadzone_editor = _CameraRectEditor(
            space_choices=_CAMERA_VIEWPORT_SPACE_CHOICES,
        )
        set_camera_deadzone_form.addRow("deadzone", self._set_camera_deadzone_editor)
        self._command_stack.addWidget(self._set_camera_deadzone_page)

        self._clear_camera_deadzone_page = QWidget()
        clear_camera_deadzone_layout = QVBoxLayout(self._clear_camera_deadzone_page)
        clear_camera_deadzone_layout.setContentsMargins(0, 0, 0, 0)
        self._clear_camera_deadzone_note = QLabel(
            "Remove the active camera deadzone rectangle."
        )
        self._clear_camera_deadzone_note.setWordWrap(True)
        self._clear_camera_deadzone_note.setStyleSheet("color: #666;")
        clear_camera_deadzone_layout.addWidget(self._clear_camera_deadzone_note)
        clear_camera_deadzone_layout.addStretch(1)
        self._command_stack.addWidget(self._clear_camera_deadzone_page)

        self._move_camera_page = QWidget()
        move_camera_form = QFormLayout(self._move_camera_page)
        move_camera_form.setContentsMargins(0, 0, 0, 0)
        self._move_camera_x_spin = QDoubleSpinBox()
        self._move_camera_x_spin.setRange(-999999.0, 999999.0)
        self._move_camera_x_spin.setDecimals(3)
        self._move_camera_x_spin.setSingleStep(1.0)
        move_camera_form.addRow("x", self._move_camera_x_spin)
        self._move_camera_y_spin = QDoubleSpinBox()
        self._move_camera_y_spin.setRange(-999999.0, 999999.0)
        self._move_camera_y_spin.setDecimals(3)
        self._move_camera_y_spin.setSingleStep(1.0)
        move_camera_form.addRow("y", self._move_camera_y_spin)
        self._move_camera_space_field = QComboBox()
        self._setup_optional_choice_combo(
            self._move_camera_space_field,
            list(_CAMERA_WORLD_SPACE_CHOICES),
        )
        move_camera_form.addRow("space", self._move_camera_space_field)
        self._move_camera_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._move_camera_mode_field,
            list(_CAMERA_MOVE_MODE_CHOICES),
        )
        move_camera_form.addRow("mode", self._move_camera_mode_field)
        self._move_camera_duration_field = _OptionalFloatField(
            minimum=0.0,
            maximum=999999.0,
            default_value=0.0,
            decimals=3,
            step=0.1,
        )
        move_camera_form.addRow("duration", self._move_camera_duration_field)
        self._move_camera_frames_needed_field = _OptionalIntField(
            minimum=1,
            maximum=999999,
            default_value=1,
        )
        move_camera_form.addRow("frames_needed", self._move_camera_frames_needed_field)
        self._move_camera_speed_field = _OptionalFloatField(
            minimum=0.0,
            maximum=999999.0,
            default_value=0.0,
            decimals=3,
            step=1.0,
        )
        move_camera_form.addRow(
            "speed_px_per_second",
            self._move_camera_speed_field,
        )
        self._command_stack.addWidget(self._move_camera_page)

        self._teleport_camera_page = QWidget()
        teleport_camera_form = QFormLayout(self._teleport_camera_page)
        teleport_camera_form.setContentsMargins(0, 0, 0, 0)
        self._teleport_camera_x_spin = QDoubleSpinBox()
        self._teleport_camera_x_spin.setRange(-999999.0, 999999.0)
        self._teleport_camera_x_spin.setDecimals(3)
        self._teleport_camera_x_spin.setSingleStep(1.0)
        teleport_camera_form.addRow("x", self._teleport_camera_x_spin)
        self._teleport_camera_y_spin = QDoubleSpinBox()
        self._teleport_camera_y_spin.setRange(-999999.0, 999999.0)
        self._teleport_camera_y_spin.setDecimals(3)
        self._teleport_camera_y_spin.setSingleStep(1.0)
        teleport_camera_form.addRow("y", self._teleport_camera_y_spin)
        self._teleport_camera_space_field = QComboBox()
        self._setup_optional_choice_combo(
            self._teleport_camera_space_field,
            list(_CAMERA_WORLD_SPACE_CHOICES),
        )
        teleport_camera_form.addRow("space", self._teleport_camera_space_field)
        self._teleport_camera_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._teleport_camera_mode_field,
            list(_CAMERA_MOVE_MODE_CHOICES),
        )
        teleport_camera_form.addRow("mode", self._teleport_camera_mode_field)
        self._command_stack.addWidget(self._teleport_camera_page)

        self._load_game_page = QWidget()
        load_game_form = QFormLayout(self._load_game_page)
        load_game_form.setContentsMargins(0, 0, 0, 0)
        self._load_game_save_path_field = _OptionalTextField()
        load_game_form.addRow("save_path", self._load_game_save_path_field)
        self._load_game_note = QLabel(
            "Leave save_path unset to open the save-slot picker."
        )
        self._load_game_note.setWordWrap(True)
        self._load_game_note.setStyleSheet("color: #666;")
        load_game_form.addRow(self._load_game_note)
        self._command_stack.addWidget(self._load_game_page)

        self._save_game_page = QWidget()
        save_game_form = QFormLayout(self._save_game_page)
        save_game_form.setContentsMargins(0, 0, 0, 0)
        self._save_game_save_path_field = _OptionalTextField()
        save_game_form.addRow("save_path", self._save_game_save_path_field)
        self._save_game_note = QLabel(
            "Leave save_path unset to open the save-slot writer."
        )
        self._save_game_note.setWordWrap(True)
        self._save_game_note.setStyleSheet("color: #666;")
        save_game_form.addRow(self._save_game_note)
        self._command_stack.addWidget(self._save_game_page)

        self._quit_game_page = QWidget()
        quit_game_layout = QVBoxLayout(self._quit_game_page)
        quit_game_layout.setContentsMargins(0, 0, 0, 0)
        self._quit_game_note = QLabel("Request that the runtime close the game window.")
        self._quit_game_note.setWordWrap(True)
        self._quit_game_note.setStyleSheet("color: #666;")
        quit_game_layout.addWidget(self._quit_game_note)
        quit_game_layout.addStretch(1)
        self._command_stack.addWidget(self._quit_game_page)

        self._set_simulation_paused_page = QWidget()
        set_simulation_paused_form = QFormLayout(self._set_simulation_paused_page)
        set_simulation_paused_form.setContentsMargins(0, 0, 0, 0)
        self._set_simulation_paused_field = QComboBox()
        self._setup_optional_bool_combo(self._set_simulation_paused_field)
        set_simulation_paused_form.addRow("paused", self._set_simulation_paused_field)
        self._set_simulation_paused_note = QLabel(
            "These commands only affect debug inspection sessions."
        )
        self._set_simulation_paused_note.setWordWrap(True)
        self._set_simulation_paused_note.setStyleSheet("color: #666;")
        set_simulation_paused_form.addRow(self._set_simulation_paused_note)
        self._command_stack.addWidget(self._set_simulation_paused_page)

        self._toggle_simulation_paused_page = QWidget()
        toggle_simulation_paused_layout = QVBoxLayout(self._toggle_simulation_paused_page)
        toggle_simulation_paused_layout.setContentsMargins(0, 0, 0, 0)
        self._toggle_simulation_paused_note = QLabel(
            "Toggle debug simulation pause when inspection mode is enabled."
        )
        self._toggle_simulation_paused_note.setWordWrap(True)
        self._toggle_simulation_paused_note.setStyleSheet("color: #666;")
        toggle_simulation_paused_layout.addWidget(self._toggle_simulation_paused_note)
        toggle_simulation_paused_layout.addStretch(1)
        self._command_stack.addWidget(self._toggle_simulation_paused_page)

        self._step_simulation_tick_page = QWidget()
        step_simulation_tick_layout = QVBoxLayout(self._step_simulation_tick_page)
        step_simulation_tick_layout.setContentsMargins(0, 0, 0, 0)
        self._step_simulation_tick_note = QLabel(
            "Advance the runtime by one debug simulation tick."
        )
        self._step_simulation_tick_note.setWordWrap(True)
        self._step_simulation_tick_note.setStyleSheet("color: #666;")
        step_simulation_tick_layout.addWidget(self._step_simulation_tick_note)
        step_simulation_tick_layout.addStretch(1)
        self._command_stack.addWidget(self._step_simulation_tick_page)

        self._adjust_output_scale_page = QWidget()
        adjust_output_scale_form = QFormLayout(self._adjust_output_scale_page)
        adjust_output_scale_form.setContentsMargins(0, 0, 0, 0)
        self._adjust_output_scale_delta_spin = QSpinBox()
        self._adjust_output_scale_delta_spin.setRange(-100, 100)
        self._adjust_output_scale_delta_spin.setValue(1)
        adjust_output_scale_form.addRow("delta", self._adjust_output_scale_delta_spin)
        self._adjust_output_scale_note = QLabel(
            "Positive delta zooms in; negative delta zooms out in debug inspection."
        )
        self._adjust_output_scale_note.setWordWrap(True)
        self._adjust_output_scale_note.setStyleSheet("color: #666;")
        adjust_output_scale_form.addRow(self._adjust_output_scale_note)
        self._command_stack.addWidget(self._adjust_output_scale_page)

        self._play_audio_page = QWidget()
        play_audio_form = QFormLayout(self._play_audio_page)
        play_audio_form.setContentsMargins(0, 0, 0, 0)
        (
            play_audio_path_row,
            self._play_audio_path_edit,
            self._play_audio_browse,
        ) = _make_line_with_button(button_text="Browse...")
        self._play_audio_browse.clicked.connect(
            lambda: self._browse_asset_into_edit(self._play_audio_path_edit)
        )
        play_audio_form.addRow("path", play_audio_path_row)
        self._play_audio_volume_field = _OptionalFloatField(
            minimum=0.0,
            maximum=10.0,
            default_value=1.0,
            decimals=3,
            step=0.1,
        )
        play_audio_form.addRow("volume", self._play_audio_volume_field)
        self._command_stack.addWidget(self._play_audio_page)

        self._set_sound_volume_page = QWidget()
        set_sound_volume_form = QFormLayout(self._set_sound_volume_page)
        set_sound_volume_form.setContentsMargins(0, 0, 0, 0)
        self._set_sound_volume_spin = QDoubleSpinBox()
        self._set_sound_volume_spin.setRange(0.0, 10.0)
        self._set_sound_volume_spin.setDecimals(3)
        self._set_sound_volume_spin.setSingleStep(0.1)
        self._set_sound_volume_spin.setValue(1.0)
        set_sound_volume_form.addRow("volume", self._set_sound_volume_spin)
        self._command_stack.addWidget(self._set_sound_volume_page)

        self._play_music_page = QWidget()
        play_music_form = QFormLayout(self._play_music_page)
        play_music_form.setContentsMargins(0, 0, 0, 0)
        (
            play_music_path_row,
            self._play_music_path_edit,
            self._play_music_browse,
        ) = _make_line_with_button(button_text="Browse...")
        self._play_music_browse.clicked.connect(
            lambda: self._browse_asset_into_edit(self._play_music_path_edit)
        )
        play_music_form.addRow("path", play_music_path_row)
        self._play_music_loop_field = QComboBox()
        self._setup_optional_bool_combo(self._play_music_loop_field)
        play_music_form.addRow("loop", self._play_music_loop_field)
        self._play_music_volume_field = _OptionalFloatField(
            minimum=0.0,
            maximum=10.0,
            default_value=1.0,
            decimals=3,
            step=0.1,
        )
        play_music_form.addRow("volume", self._play_music_volume_field)
        self._play_music_restart_if_same_field = QComboBox()
        self._setup_optional_bool_combo(self._play_music_restart_if_same_field)
        play_music_form.addRow(
            "restart_if_same",
            self._play_music_restart_if_same_field,
        )
        self._command_stack.addWidget(self._play_music_page)

        self._stop_music_page = QWidget()
        stop_music_form = QFormLayout(self._stop_music_page)
        stop_music_form.setContentsMargins(0, 0, 0, 0)
        self._stop_music_fade_seconds_field = _OptionalFloatField(
            minimum=0.0,
            maximum=999999.0,
            default_value=0.0,
            decimals=3,
            step=0.1,
        )
        stop_music_form.addRow("fade_seconds", self._stop_music_fade_seconds_field)
        self._command_stack.addWidget(self._stop_music_page)

        self._pause_music_page = QWidget()
        pause_music_layout = QVBoxLayout(self._pause_music_page)
        pause_music_layout.setContentsMargins(0, 0, 0, 0)
        self._pause_music_note = QLabel("Pause the currently playing music track.")
        self._pause_music_note.setWordWrap(True)
        self._pause_music_note.setStyleSheet("color: #666;")
        pause_music_layout.addWidget(self._pause_music_note)
        pause_music_layout.addStretch(1)
        self._command_stack.addWidget(self._pause_music_page)

        self._resume_music_page = QWidget()
        resume_music_layout = QVBoxLayout(self._resume_music_page)
        resume_music_layout.setContentsMargins(0, 0, 0, 0)
        self._resume_music_note = QLabel("Resume the paused music track.")
        self._resume_music_note.setWordWrap(True)
        self._resume_music_note.setStyleSheet("color: #666;")
        resume_music_layout.addWidget(self._resume_music_note)
        resume_music_layout.addStretch(1)
        self._command_stack.addWidget(self._resume_music_page)

        self._set_music_volume_page = QWidget()
        set_music_volume_form = QFormLayout(self._set_music_volume_page)
        set_music_volume_form.setContentsMargins(0, 0, 0, 0)
        self._set_music_volume_spin = QDoubleSpinBox()
        self._set_music_volume_spin.setRange(0.0, 10.0)
        self._set_music_volume_spin.setDecimals(3)
        self._set_music_volume_spin.setSingleStep(0.1)
        self._set_music_volume_spin.setValue(1.0)
        set_music_volume_form.addRow("volume", self._set_music_volume_spin)
        self._command_stack.addWidget(self._set_music_volume_page)

        self._show_screen_image_page = QWidget()
        show_screen_image_form = QFormLayout(self._show_screen_image_page)
        show_screen_image_form.setContentsMargins(0, 0, 0, 0)
        self._show_screen_image_element_id_edit = QLineEdit()
        show_screen_image_form.addRow("element_id", self._show_screen_image_element_id_edit)
        (
            show_screen_image_path_row,
            self._show_screen_image_path_edit,
            self._show_screen_image_path_browse,
        ) = _make_line_with_button(button_text="Browse...")
        self._show_screen_image_path_browse.clicked.connect(
            lambda: self._browse_asset_into_edit(self._show_screen_image_path_edit)
        )
        show_screen_image_form.addRow("path", show_screen_image_path_row)
        self._show_screen_image_x_spin = QDoubleSpinBox()
        self._show_screen_image_x_spin.setRange(-999999.0, 999999.0)
        self._show_screen_image_x_spin.setDecimals(3)
        self._show_screen_image_x_spin.setSingleStep(1.0)
        show_screen_image_form.addRow("x", self._show_screen_image_x_spin)
        self._show_screen_image_y_spin = QDoubleSpinBox()
        self._show_screen_image_y_spin.setRange(-999999.0, 999999.0)
        self._show_screen_image_y_spin.setDecimals(3)
        self._show_screen_image_y_spin.setSingleStep(1.0)
        show_screen_image_form.addRow("y", self._show_screen_image_y_spin)
        self._show_screen_image_frame_width_field = _OptionalIntField(
            minimum=1,
            maximum=999999,
            default_value=1,
        )
        show_screen_image_form.addRow("frame_width", self._show_screen_image_frame_width_field)
        self._show_screen_image_frame_height_field = _OptionalIntField(
            minimum=1,
            maximum=999999,
            default_value=1,
        )
        show_screen_image_form.addRow("frame_height", self._show_screen_image_frame_height_field)
        self._show_screen_image_frame_field = _OptionalIntField(
            minimum=0,
            maximum=999999,
            default_value=0,
        )
        show_screen_image_form.addRow("frame", self._show_screen_image_frame_field)
        self._show_screen_image_layer_field = _OptionalIntField(
            minimum=-999999,
            maximum=999999,
            default_value=0,
        )
        show_screen_image_form.addRow("layer", self._show_screen_image_layer_field)
        self._show_screen_image_anchor_field = QComboBox()
        self._setup_optional_choice_combo(
            self._show_screen_image_anchor_field,
            list(_SCREEN_ANCHOR_CHOICES),
        )
        show_screen_image_form.addRow("anchor", self._show_screen_image_anchor_field)
        self._show_screen_image_flip_x_field = QComboBox()
        self._setup_optional_bool_combo(self._show_screen_image_flip_x_field)
        show_screen_image_form.addRow("flip_x", self._show_screen_image_flip_x_field)
        self._show_screen_image_tint_field = _OptionalTextField()
        show_screen_image_form.addRow("tint", self._show_screen_image_tint_field)
        self._show_screen_image_tint_note = QLabel(
            "Use comma-separated RGB, for example: 255, 255, 255"
        )
        self._show_screen_image_tint_note.setWordWrap(True)
        self._show_screen_image_tint_note.setStyleSheet("color: #666;")
        show_screen_image_form.addRow(self._show_screen_image_tint_note)
        self._show_screen_image_visible_field = QComboBox()
        self._setup_optional_bool_combo(self._show_screen_image_visible_field)
        show_screen_image_form.addRow("visible", self._show_screen_image_visible_field)
        self._command_stack.addWidget(self._show_screen_image_page)

        self._show_screen_text_page = QWidget()
        show_screen_text_form = QFormLayout(self._show_screen_text_page)
        show_screen_text_form.setContentsMargins(0, 0, 0, 0)
        self._show_screen_text_element_id_edit = QLineEdit()
        show_screen_text_form.addRow("element_id", self._show_screen_text_element_id_edit)
        self._show_screen_text_text_edit = QLineEdit()
        show_screen_text_form.addRow("text", self._show_screen_text_text_edit)
        self._show_screen_text_x_spin = QDoubleSpinBox()
        self._show_screen_text_x_spin.setRange(-999999.0, 999999.0)
        self._show_screen_text_x_spin.setDecimals(3)
        self._show_screen_text_x_spin.setSingleStep(1.0)
        show_screen_text_form.addRow("x", self._show_screen_text_x_spin)
        self._show_screen_text_y_spin = QDoubleSpinBox()
        self._show_screen_text_y_spin.setRange(-999999.0, 999999.0)
        self._show_screen_text_y_spin.setDecimals(3)
        self._show_screen_text_y_spin.setSingleStep(1.0)
        show_screen_text_form.addRow("y", self._show_screen_text_y_spin)
        self._show_screen_text_layer_field = _OptionalIntField(
            minimum=-999999,
            maximum=999999,
            default_value=0,
        )
        show_screen_text_form.addRow("layer", self._show_screen_text_layer_field)
        self._show_screen_text_anchor_field = QComboBox()
        self._setup_optional_choice_combo(
            self._show_screen_text_anchor_field,
            list(_SCREEN_ANCHOR_CHOICES),
        )
        show_screen_text_form.addRow("anchor", self._show_screen_text_anchor_field)
        self._show_screen_text_color_field = _OptionalTextField()
        show_screen_text_form.addRow("color", self._show_screen_text_color_field)
        self._show_screen_text_color_note = QLabel(
            "Use comma-separated RGB, for example: 255, 255, 255"
        )
        self._show_screen_text_color_note.setWordWrap(True)
        self._show_screen_text_color_note.setStyleSheet("color: #666;")
        show_screen_text_form.addRow(self._show_screen_text_color_note)
        self._show_screen_text_font_id_field = _OptionalTextField()
        show_screen_text_form.addRow("font_id", self._show_screen_text_font_id_field)
        self._show_screen_text_max_width_field = _OptionalIntField(
            minimum=1,
            maximum=999999,
            default_value=1,
        )
        show_screen_text_form.addRow("max_width", self._show_screen_text_max_width_field)
        self._show_screen_text_visible_field = QComboBox()
        self._setup_optional_bool_combo(self._show_screen_text_visible_field)
        show_screen_text_form.addRow("visible", self._show_screen_text_visible_field)
        self._command_stack.addWidget(self._show_screen_text_page)

        self._set_screen_text_page = QWidget()
        set_screen_text_form = QFormLayout(self._set_screen_text_page)
        set_screen_text_form.setContentsMargins(0, 0, 0, 0)
        self._set_screen_text_element_id_edit = QLineEdit()
        set_screen_text_form.addRow("element_id", self._set_screen_text_element_id_edit)
        self._set_screen_text_text_edit = QLineEdit()
        set_screen_text_form.addRow("text", self._set_screen_text_text_edit)
        self._command_stack.addWidget(self._set_screen_text_page)

        self._remove_screen_element_page = QWidget()
        remove_screen_element_form = QFormLayout(self._remove_screen_element_page)
        remove_screen_element_form.setContentsMargins(0, 0, 0, 0)
        self._remove_screen_element_id_edit = QLineEdit()
        remove_screen_element_form.addRow("element_id", self._remove_screen_element_id_edit)
        self._command_stack.addWidget(self._remove_screen_element_page)

        self._clear_screen_elements_page = QWidget()
        clear_screen_elements_form = QFormLayout(self._clear_screen_elements_page)
        clear_screen_elements_form.setContentsMargins(0, 0, 0, 0)
        self._clear_screen_elements_layer_field = _OptionalIntField(
            minimum=-999999,
            maximum=999999,
            default_value=0,
        )
        clear_screen_elements_form.addRow("layer", self._clear_screen_elements_layer_field)
        self._clear_screen_elements_note = QLabel(
            "Leave layer unset to clear every screen-space element."
        )
        self._clear_screen_elements_note.setWordWrap(True)
        self._clear_screen_elements_note.setStyleSheet("color: #666;")
        clear_screen_elements_form.addRow(self._clear_screen_elements_note)
        self._command_stack.addWidget(self._clear_screen_elements_page)

        self._play_screen_animation_page = QWidget()
        play_screen_animation_form = QFormLayout(self._play_screen_animation_page)
        play_screen_animation_form.setContentsMargins(0, 0, 0, 0)
        self._play_screen_animation_element_id_edit = QLineEdit()
        play_screen_animation_form.addRow(
            "element_id",
            self._play_screen_animation_element_id_edit,
        )
        self._play_screen_animation_frame_sequence_edit = QLineEdit()
        play_screen_animation_form.addRow(
            "frame_sequence",
            self._play_screen_animation_frame_sequence_edit,
        )
        self._play_screen_animation_frame_sequence_note = QLabel(
            "Use a comma-separated list of frame numbers, for example: 0, 1, 2, 1"
        )
        self._play_screen_animation_frame_sequence_note.setWordWrap(True)
        self._play_screen_animation_frame_sequence_note.setStyleSheet("color: #666;")
        play_screen_animation_form.addRow(self._play_screen_animation_frame_sequence_note)
        self._play_screen_animation_ticks_per_frame_field = _OptionalIntField(
            minimum=1,
            maximum=999999,
            default_value=1,
        )
        play_screen_animation_form.addRow(
            "ticks_per_frame",
            self._play_screen_animation_ticks_per_frame_field,
        )
        self._play_screen_animation_hold_last_frame_field = QComboBox()
        self._setup_optional_bool_combo(self._play_screen_animation_hold_last_frame_field)
        play_screen_animation_form.addRow(
            "hold_last_frame",
            self._play_screen_animation_hold_last_frame_field,
        )
        self._play_screen_animation_wait_field = QComboBox()
        self._setup_optional_bool_combo(self._play_screen_animation_wait_field)
        play_screen_animation_form.addRow("wait", self._play_screen_animation_wait_field)
        self._command_stack.addWidget(self._play_screen_animation_page)

        self._wait_for_screen_animation_page = QWidget()
        wait_for_screen_animation_form = QFormLayout(self._wait_for_screen_animation_page)
        wait_for_screen_animation_form.setContentsMargins(0, 0, 0, 0)
        self._wait_for_screen_animation_element_id_edit = QLineEdit()
        wait_for_screen_animation_form.addRow(
            "element_id",
            self._wait_for_screen_animation_element_id_edit,
        )
        self._command_stack.addWidget(self._wait_for_screen_animation_page)

        self._play_animation_page = QWidget()
        play_animation_form = QFormLayout(self._play_animation_page)
        play_animation_form.setContentsMargins(0, 0, 0, 0)
        (
            play_animation_entity_row,
            self._play_animation_entity_id_edit,
            self._play_animation_entity_pick,
            self._play_animation_entity_ref,
        ) = make_entity_id_row()
        play_animation_form.addRow("entity_id", play_animation_entity_row)
        self._play_animation_visual_id_field = _OptionalTextField()
        play_animation_form.addRow("visual_id", self._play_animation_visual_id_field)
        self._play_animation_name_edit = QLineEdit()
        play_animation_form.addRow("animation", self._play_animation_name_edit)
        self._play_animation_frame_count_field = _OptionalIntField(
            minimum=1,
            maximum=999999,
            default_value=1,
        )
        play_animation_form.addRow("frame_count", self._play_animation_frame_count_field)
        self._play_animation_duration_ticks_field = _OptionalIntField(
            minimum=1,
            maximum=999999,
            default_value=1,
        )
        play_animation_form.addRow(
            "duration_ticks",
            self._play_animation_duration_ticks_field,
        )
        self._play_animation_wait_field = QComboBox()
        self._setup_optional_bool_combo(self._play_animation_wait_field)
        play_animation_form.addRow("wait", self._play_animation_wait_field)
        self._command_stack.addWidget(self._play_animation_page)

        self._wait_for_animation_page = QWidget()
        wait_for_animation_form = QFormLayout(self._wait_for_animation_page)
        wait_for_animation_form.setContentsMargins(0, 0, 0, 0)
        (
            wait_for_animation_entity_row,
            self._wait_for_animation_entity_id_edit,
            self._wait_for_animation_entity_pick,
            self._wait_for_animation_entity_ref,
        ) = make_entity_id_row()
        wait_for_animation_form.addRow("entity_id", wait_for_animation_entity_row)
        self._wait_for_animation_visual_id_field = _OptionalTextField()
        wait_for_animation_form.addRow("visual_id", self._wait_for_animation_visual_id_field)
        self._command_stack.addWidget(self._wait_for_animation_page)

        self._stop_animation_page = QWidget()
        stop_animation_form = QFormLayout(self._stop_animation_page)
        stop_animation_form.setContentsMargins(0, 0, 0, 0)
        (
            stop_animation_entity_row,
            self._stop_animation_entity_id_edit,
            self._stop_animation_entity_pick,
            self._stop_animation_entity_ref,
        ) = make_entity_id_row()
        stop_animation_form.addRow("entity_id", stop_animation_entity_row)
        self._stop_animation_visual_id_field = _OptionalTextField()
        stop_animation_form.addRow("visual_id", self._stop_animation_visual_id_field)
        self._stop_animation_reset_field = QComboBox()
        self._setup_optional_bool_combo(self._stop_animation_reset_field)
        stop_animation_form.addRow("reset_to_default", self._stop_animation_reset_field)
        self._command_stack.addWidget(self._stop_animation_page)

        self._add_inventory_item_page = QWidget()
        add_inventory_form = QFormLayout(self._add_inventory_item_page)
        add_inventory_form.setContentsMargins(0, 0, 0, 0)
        (
            add_inventory_entity_row,
            self._add_inventory_entity_id_edit,
            self._add_inventory_entity_pick,
            self._add_inventory_entity_ref,
        ) = make_entity_id_row()
        add_inventory_form.addRow("entity_id", add_inventory_entity_row)
        (
            add_inventory_item_row,
            self._add_inventory_item_id_edit,
            self._add_inventory_item_pick,
        ) = make_item_id_row()
        add_inventory_form.addRow("item_id", add_inventory_item_row)
        self._add_inventory_quantity_field = _OptionalIntField(
            minimum=1,
            maximum=999999,
            default_value=1,
        )
        add_inventory_form.addRow("quantity", self._add_inventory_quantity_field)
        self._add_inventory_quantity_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._add_inventory_quantity_mode_field,
            list(_INVENTORY_QUANTITY_MODE_CHOICES),
            not_set_label="Choose quantity mode",
        )
        add_inventory_form.addRow("quantity_mode", self._add_inventory_quantity_mode_field)
        self._add_inventory_result_var_field = _OptionalTextField()
        add_inventory_form.addRow("result_var_name", self._add_inventory_result_var_field)
        self._add_inventory_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._add_inventory_persistent_field)
        add_inventory_form.addRow("persistent", self._add_inventory_persistent_field)
        self._command_stack.addWidget(self._add_inventory_item_page)

        self._remove_inventory_item_page = QWidget()
        remove_inventory_form = QFormLayout(self._remove_inventory_item_page)
        remove_inventory_form.setContentsMargins(0, 0, 0, 0)
        (
            remove_inventory_entity_row,
            self._remove_inventory_entity_id_edit,
            self._remove_inventory_entity_pick,
            self._remove_inventory_entity_ref,
        ) = make_entity_id_row()
        remove_inventory_form.addRow("entity_id", remove_inventory_entity_row)
        (
            remove_inventory_item_row,
            self._remove_inventory_item_id_edit,
            self._remove_inventory_item_pick,
        ) = make_item_id_row()
        remove_inventory_form.addRow("item_id", remove_inventory_item_row)
        self._remove_inventory_quantity_field = _OptionalIntField(
            minimum=1,
            maximum=999999,
            default_value=1,
        )
        remove_inventory_form.addRow("quantity", self._remove_inventory_quantity_field)
        self._remove_inventory_quantity_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._remove_inventory_quantity_mode_field,
            list(_INVENTORY_QUANTITY_MODE_CHOICES),
            not_set_label="Choose quantity mode",
        )
        remove_inventory_form.addRow(
            "quantity_mode",
            self._remove_inventory_quantity_mode_field,
        )
        self._remove_inventory_result_var_field = _OptionalTextField()
        remove_inventory_form.addRow("result_var_name", self._remove_inventory_result_var_field)
        self._remove_inventory_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._remove_inventory_persistent_field)
        remove_inventory_form.addRow("persistent", self._remove_inventory_persistent_field)
        self._command_stack.addWidget(self._remove_inventory_item_page)

        self._use_inventory_item_page = QWidget()
        use_inventory_form = QFormLayout(self._use_inventory_item_page)
        use_inventory_form.setContentsMargins(0, 0, 0, 0)
        (
            use_inventory_entity_row,
            self._use_inventory_entity_id_edit,
            self._use_inventory_entity_pick,
            self._use_inventory_entity_ref,
        ) = make_entity_id_row()
        use_inventory_form.addRow("entity_id", use_inventory_entity_row)
        (
            use_inventory_item_row,
            self._use_inventory_item_id_edit,
            self._use_inventory_item_pick,
        ) = make_item_id_row()
        use_inventory_form.addRow("item_id", use_inventory_item_row)
        self._use_inventory_quantity_field = _OptionalIntField(
            minimum=1,
            maximum=999999,
            default_value=1,
        )
        use_inventory_form.addRow("quantity", self._use_inventory_quantity_field)
        self._use_inventory_result_var_field = _OptionalTextField()
        use_inventory_form.addRow("result_var_name", self._use_inventory_result_var_field)
        self._use_inventory_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._use_inventory_persistent_field)
        use_inventory_form.addRow("persistent", self._use_inventory_persistent_field)
        self._command_stack.addWidget(self._use_inventory_item_page)

        self._set_inventory_max_stacks_page = QWidget()
        set_inventory_max_form = QFormLayout(self._set_inventory_max_stacks_page)
        set_inventory_max_form.setContentsMargins(0, 0, 0, 0)
        (
            set_inventory_max_entity_row,
            self._set_inventory_max_entity_id_edit,
            self._set_inventory_max_entity_pick,
            self._set_inventory_max_entity_ref,
        ) = make_entity_id_row()
        set_inventory_max_form.addRow("entity_id", set_inventory_max_entity_row)
        self._set_inventory_max_stacks_spin = QSpinBox()
        self._set_inventory_max_stacks_spin.setRange(0, 999999)
        set_inventory_max_form.addRow("max_stacks", self._set_inventory_max_stacks_spin)
        self._set_inventory_max_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_inventory_max_persistent_field)
        set_inventory_max_form.addRow("persistent", self._set_inventory_max_persistent_field)
        self._command_stack.addWidget(self._set_inventory_max_stacks_page)

        self._open_inventory_session_page = QWidget()
        open_inventory_form = QFormLayout(self._open_inventory_session_page)
        open_inventory_form.setContentsMargins(0, 0, 0, 0)
        (
            open_inventory_entity_row,
            self._open_inventory_entity_id_edit,
            self._open_inventory_entity_pick,
            self._open_inventory_entity_ref,
        ) = make_entity_id_row()
        open_inventory_form.addRow("entity_id", open_inventory_entity_row)
        self._open_inventory_ui_preset_field = _OptionalTextField()
        open_inventory_form.addRow("ui_preset", self._open_inventory_ui_preset_field)
        self._open_inventory_wait_field = QComboBox()
        self._setup_optional_bool_combo(self._open_inventory_wait_field)
        open_inventory_form.addRow("wait", self._open_inventory_wait_field)
        self._open_inventory_wait_note = QLabel(
            "Leave wait unset to use the runtime default and wait for the session to close."
        )
        self._open_inventory_wait_note.setWordWrap(True)
        self._open_inventory_wait_note.setStyleSheet("color: #666;")
        open_inventory_form.addRow(self._open_inventory_wait_note)
        self._command_stack.addWidget(self._open_inventory_session_page)

        self._close_inventory_session_page = QWidget()
        close_inventory_form = QFormLayout(self._close_inventory_session_page)
        close_inventory_form.setContentsMargins(0, 0, 0, 0)
        self._close_inventory_note = QLabel(
            "Closes the currently active engine-owned inventory session."
        )
        self._close_inventory_note.setWordWrap(True)
        self._close_inventory_note.setStyleSheet("color: #666;")
        close_inventory_form.addRow(self._close_inventory_note)
        self._command_stack.addWidget(self._close_inventory_session_page)

        self._set_current_area_var_page = QWidget()
        set_current_area_var_form = QFormLayout(self._set_current_area_var_page)
        set_current_area_var_form.setContentsMargins(0, 0, 0, 0)
        self._set_current_area_var_name_edit = QLineEdit()
        set_current_area_var_form.addRow("name", self._set_current_area_var_name_edit)
        self._set_current_area_var_value_edit = QPlainTextEdit()
        self._set_current_area_var_value_edit.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.NoWrap
        )
        self._set_current_area_var_value_edit.setFont(generic_font)
        self._set_current_area_var_value_edit.setPlaceholderText(
            '"hello"\n\nor\n\n42\n\nor\n\n{\n  "x": 1\n}'
        )
        self._set_current_area_var_value_edit.setFixedHeight(140)
        set_current_area_var_form.addRow("value", self._set_current_area_var_value_edit)
        self._set_current_area_var_value_note = QLabel(
            "Value uses JSON syntax. Wrap strings in quotes."
        )
        self._set_current_area_var_value_note.setWordWrap(True)
        self._set_current_area_var_value_note.setStyleSheet("color: #666;")
        set_current_area_var_form.addRow(self._set_current_area_var_value_note)
        self._set_current_area_var_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_current_area_var_persistent_field)
        set_current_area_var_form.addRow(
            "persistent",
            self._set_current_area_var_persistent_field,
        )
        self._set_current_area_var_value_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._set_current_area_var_value_mode_field,
            [("raw", "raw")],
            not_set_label="Default",
        )
        set_current_area_var_form.addRow(
            "value_mode",
            self._set_current_area_var_value_mode_field,
        )
        self._command_stack.addWidget(self._set_current_area_var_page)

        self._add_current_area_var_page = QWidget()
        add_current_area_var_form = QFormLayout(self._add_current_area_var_page)
        add_current_area_var_form.setContentsMargins(0, 0, 0, 0)
        self._add_current_area_var_name_edit = QLineEdit()
        add_current_area_var_form.addRow("name", self._add_current_area_var_name_edit)
        self._add_current_area_var_amount_field = _OptionalFloatField(
            minimum=-999999.0,
            maximum=999999.0,
            default_value=1.0,
            decimals=3,
            step=1.0,
        )
        add_current_area_var_form.addRow(
            "amount",
            self._add_current_area_var_amount_field,
        )
        self._add_current_area_var_amount_note = QLabel(
            "Leave amount unset to add 1."
        )
        self._add_current_area_var_amount_note.setWordWrap(True)
        self._add_current_area_var_amount_note.setStyleSheet("color: #666;")
        add_current_area_var_form.addRow(self._add_current_area_var_amount_note)
        self._add_current_area_var_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._add_current_area_var_persistent_field)
        add_current_area_var_form.addRow(
            "persistent",
            self._add_current_area_var_persistent_field,
        )
        self._command_stack.addWidget(self._add_current_area_var_page)

        self._add_entity_var_page = QWidget()
        add_entity_var_form = QFormLayout(self._add_entity_var_page)
        add_entity_var_form.setContentsMargins(0, 0, 0, 0)
        (
            add_entity_var_entity_row,
            self._add_entity_var_entity_id_edit,
            self._add_entity_var_entity_pick,
            self._add_entity_var_entity_ref,
        ) = make_entity_id_row()
        add_entity_var_form.addRow("entity_id", add_entity_var_entity_row)
        self._add_entity_var_name_edit = QLineEdit()
        add_entity_var_form.addRow("name", self._add_entity_var_name_edit)
        self._add_entity_var_amount_field = _OptionalFloatField(
            minimum=-999999.0,
            maximum=999999.0,
            default_value=1.0,
            decimals=3,
            step=1.0,
        )
        add_entity_var_form.addRow("amount", self._add_entity_var_amount_field)
        self._add_entity_var_amount_note = QLabel("Leave amount unset to add 1.")
        self._add_entity_var_amount_note.setWordWrap(True)
        self._add_entity_var_amount_note.setStyleSheet("color: #666;")
        add_entity_var_form.addRow(self._add_entity_var_amount_note)
        self._add_entity_var_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._add_entity_var_persistent_field)
        add_entity_var_form.addRow("persistent", self._add_entity_var_persistent_field)
        self._command_stack.addWidget(self._add_entity_var_page)

        self._toggle_current_area_var_page = QWidget()
        toggle_current_area_var_form = QFormLayout(self._toggle_current_area_var_page)
        toggle_current_area_var_form.setContentsMargins(0, 0, 0, 0)
        self._toggle_current_area_var_name_edit = QLineEdit()
        toggle_current_area_var_form.addRow("name", self._toggle_current_area_var_name_edit)
        self._toggle_current_area_var_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._toggle_current_area_var_persistent_field)
        toggle_current_area_var_form.addRow(
            "persistent",
            self._toggle_current_area_var_persistent_field,
        )
        self._toggle_current_area_var_note = QLabel(
            "Missing or null values are treated as false before toggling."
        )
        self._toggle_current_area_var_note.setWordWrap(True)
        self._toggle_current_area_var_note.setStyleSheet("color: #666;")
        toggle_current_area_var_form.addRow(self._toggle_current_area_var_note)
        self._command_stack.addWidget(self._toggle_current_area_var_page)

        self._toggle_entity_var_page = QWidget()
        toggle_entity_var_form = QFormLayout(self._toggle_entity_var_page)
        toggle_entity_var_form.setContentsMargins(0, 0, 0, 0)
        (
            toggle_entity_var_entity_row,
            self._toggle_entity_var_entity_id_edit,
            self._toggle_entity_var_entity_pick,
            self._toggle_entity_var_entity_ref,
        ) = make_entity_id_row()
        toggle_entity_var_form.addRow("entity_id", toggle_entity_var_entity_row)
        self._toggle_entity_var_name_edit = QLineEdit()
        toggle_entity_var_form.addRow("name", self._toggle_entity_var_name_edit)
        self._toggle_entity_var_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._toggle_entity_var_persistent_field)
        toggle_entity_var_form.addRow("persistent", self._toggle_entity_var_persistent_field)
        self._toggle_entity_var_note = QLabel(
            "Missing or null values are treated as false before toggling."
        )
        self._toggle_entity_var_note.setWordWrap(True)
        self._toggle_entity_var_note.setStyleSheet("color: #666;")
        toggle_entity_var_form.addRow(self._toggle_entity_var_note)
        self._command_stack.addWidget(self._toggle_entity_var_page)

        self._set_current_area_var_length_page = QWidget()
        set_current_area_var_length_form = QFormLayout(self._set_current_area_var_length_page)
        set_current_area_var_length_form.setContentsMargins(0, 0, 0, 0)
        self._set_current_area_var_length_name_edit = QLineEdit()
        set_current_area_var_length_form.addRow(
            "name",
            self._set_current_area_var_length_name_edit,
        )
        self._set_current_area_var_length_value_edit = QPlainTextEdit()
        self._set_current_area_var_length_value_edit.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.NoWrap
        )
        self._set_current_area_var_length_value_edit.setFont(generic_font)
        self._set_current_area_var_length_value_edit.setPlaceholderText(
            '[1, 2, 3]\n\nor\n\n"hello"\n\nLeave blank to store 0.'
        )
        self._set_current_area_var_length_value_edit.setFixedHeight(110)
        set_current_area_var_length_form.addRow(
            "value",
            self._set_current_area_var_length_value_edit,
        )
        self._set_current_area_var_length_note = QLabel(
            "Stores the length of the supplied value, not the value itself."
        )
        self._set_current_area_var_length_note.setWordWrap(True)
        self._set_current_area_var_length_note.setStyleSheet("color: #666;")
        set_current_area_var_length_form.addRow(self._set_current_area_var_length_note)
        self._set_current_area_var_length_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_current_area_var_length_persistent_field)
        set_current_area_var_length_form.addRow(
            "persistent",
            self._set_current_area_var_length_persistent_field,
        )
        self._command_stack.addWidget(self._set_current_area_var_length_page)

        self._set_entity_var_length_page = QWidget()
        set_entity_var_length_form = QFormLayout(self._set_entity_var_length_page)
        set_entity_var_length_form.setContentsMargins(0, 0, 0, 0)
        (
            set_entity_var_length_entity_row,
            self._set_entity_var_length_entity_id_edit,
            self._set_entity_var_length_entity_pick,
            self._set_entity_var_length_entity_ref,
        ) = make_entity_id_row()
        set_entity_var_length_form.addRow("entity_id", set_entity_var_length_entity_row)
        self._set_entity_var_length_name_edit = QLineEdit()
        set_entity_var_length_form.addRow("name", self._set_entity_var_length_name_edit)
        self._set_entity_var_length_value_edit = QPlainTextEdit()
        self._set_entity_var_length_value_edit.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.NoWrap
        )
        self._set_entity_var_length_value_edit.setFont(generic_font)
        self._set_entity_var_length_value_edit.setPlaceholderText(
            '[1, 2, 3]\n\nor\n\n"hello"\n\nLeave blank to store 0.'
        )
        self._set_entity_var_length_value_edit.setFixedHeight(110)
        set_entity_var_length_form.addRow("value", self._set_entity_var_length_value_edit)
        self._set_entity_var_length_note = QLabel(
            "Stores the length of the supplied value, not the value itself."
        )
        self._set_entity_var_length_note.setWordWrap(True)
        self._set_entity_var_length_note.setStyleSheet("color: #666;")
        set_entity_var_length_form.addRow(self._set_entity_var_length_note)
        self._set_entity_var_length_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_entity_var_length_persistent_field)
        set_entity_var_length_form.addRow(
            "persistent",
            self._set_entity_var_length_persistent_field,
        )
        self._command_stack.addWidget(self._set_entity_var_length_page)

        self._append_current_area_var_page = QWidget()
        append_current_area_var_form = QFormLayout(self._append_current_area_var_page)
        append_current_area_var_form.setContentsMargins(0, 0, 0, 0)
        self._append_current_area_var_name_edit = QLineEdit()
        append_current_area_var_form.addRow("name", self._append_current_area_var_name_edit)
        self._append_current_area_var_value_edit = QPlainTextEdit()
        self._append_current_area_var_value_edit.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.NoWrap
        )
        self._append_current_area_var_value_edit.setFont(generic_font)
        self._append_current_area_var_value_edit.setPlaceholderText(
            '"hello"\n\nor\n\n{\n  "choice": 1\n}'
        )
        self._append_current_area_var_value_edit.setFixedHeight(120)
        append_current_area_var_form.addRow("value", self._append_current_area_var_value_edit)
        self._append_current_area_var_value_note = QLabel(
            "Appends one item to a list variable. Value uses JSON syntax."
        )
        self._append_current_area_var_value_note.setWordWrap(True)
        self._append_current_area_var_value_note.setStyleSheet("color: #666;")
        append_current_area_var_form.addRow(self._append_current_area_var_value_note)
        self._append_current_area_var_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._append_current_area_var_persistent_field)
        append_current_area_var_form.addRow(
            "persistent",
            self._append_current_area_var_persistent_field,
        )
        self._append_current_area_var_value_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._append_current_area_var_value_mode_field,
            [("raw", "raw")],
            not_set_label="Default",
        )
        append_current_area_var_form.addRow(
            "value_mode",
            self._append_current_area_var_value_mode_field,
        )
        self._command_stack.addWidget(self._append_current_area_var_page)

        self._append_entity_var_page = QWidget()
        append_entity_var_form = QFormLayout(self._append_entity_var_page)
        append_entity_var_form.setContentsMargins(0, 0, 0, 0)
        (
            append_entity_var_entity_row,
            self._append_entity_var_entity_id_edit,
            self._append_entity_var_entity_pick,
            self._append_entity_var_entity_ref,
        ) = make_entity_id_row()
        append_entity_var_form.addRow("entity_id", append_entity_var_entity_row)
        self._append_entity_var_name_edit = QLineEdit()
        append_entity_var_form.addRow("name", self._append_entity_var_name_edit)
        self._append_entity_var_value_edit = QPlainTextEdit()
        self._append_entity_var_value_edit.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.NoWrap
        )
        self._append_entity_var_value_edit.setFont(generic_font)
        self._append_entity_var_value_edit.setPlaceholderText(
            '"hello"\n\nor\n\n{\n  "choice": 1\n}'
        )
        self._append_entity_var_value_edit.setFixedHeight(120)
        append_entity_var_form.addRow("value", self._append_entity_var_value_edit)
        self._append_entity_var_value_note = QLabel(
            "Appends one item to a list variable. Value uses JSON syntax."
        )
        self._append_entity_var_value_note.setWordWrap(True)
        self._append_entity_var_value_note.setStyleSheet("color: #666;")
        append_entity_var_form.addRow(self._append_entity_var_value_note)
        self._append_entity_var_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._append_entity_var_persistent_field)
        append_entity_var_form.addRow("persistent", self._append_entity_var_persistent_field)
        self._append_entity_var_value_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._append_entity_var_value_mode_field,
            [("raw", "raw")],
            not_set_label="Default",
        )
        append_entity_var_form.addRow(
            "value_mode",
            self._append_entity_var_value_mode_field,
        )
        self._command_stack.addWidget(self._append_entity_var_page)

        self._pop_current_area_var_page = QWidget()
        pop_current_area_var_form = QFormLayout(self._pop_current_area_var_page)
        pop_current_area_var_form.setContentsMargins(0, 0, 0, 0)
        self._pop_current_area_var_name_edit = QLineEdit()
        pop_current_area_var_form.addRow("name", self._pop_current_area_var_name_edit)
        self._pop_current_area_var_store_var_field = _OptionalTextField()
        pop_current_area_var_form.addRow(
            "store_var",
            self._pop_current_area_var_store_var_field,
        )
        self._pop_current_area_var_default_edit = QPlainTextEdit()
        self._pop_current_area_var_default_edit.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.NoWrap
        )
        self._pop_current_area_var_default_edit.setFont(generic_font)
        self._pop_current_area_var_default_edit.setPlaceholderText(
            '{}\n\nor\n\n"fallback"\n\nLeave blank to use null.'
        )
        self._pop_current_area_var_default_edit.setFixedHeight(110)
        pop_current_area_var_form.addRow("default", self._pop_current_area_var_default_edit)
        self._pop_current_area_var_default_note = QLabel(
            "Pops the last list item. If the list is empty, default is stored instead."
        )
        self._pop_current_area_var_default_note.setWordWrap(True)
        self._pop_current_area_var_default_note.setStyleSheet("color: #666;")
        pop_current_area_var_form.addRow(self._pop_current_area_var_default_note)
        self._pop_current_area_var_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._pop_current_area_var_persistent_field)
        pop_current_area_var_form.addRow(
            "persistent",
            self._pop_current_area_var_persistent_field,
        )
        self._command_stack.addWidget(self._pop_current_area_var_page)

        self._pop_entity_var_page = QWidget()
        pop_entity_var_form = QFormLayout(self._pop_entity_var_page)
        pop_entity_var_form.setContentsMargins(0, 0, 0, 0)
        (
            pop_entity_var_entity_row,
            self._pop_entity_var_entity_id_edit,
            self._pop_entity_var_entity_pick,
            self._pop_entity_var_entity_ref,
        ) = make_entity_id_row()
        pop_entity_var_form.addRow("entity_id", pop_entity_var_entity_row)
        self._pop_entity_var_name_edit = QLineEdit()
        pop_entity_var_form.addRow("name", self._pop_entity_var_name_edit)
        self._pop_entity_var_store_var_field = _OptionalTextField()
        pop_entity_var_form.addRow("store_var", self._pop_entity_var_store_var_field)
        self._pop_entity_var_default_edit = QPlainTextEdit()
        self._pop_entity_var_default_edit.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.NoWrap
        )
        self._pop_entity_var_default_edit.setFont(generic_font)
        self._pop_entity_var_default_edit.setPlaceholderText(
            '{}\n\nor\n\n"fallback"\n\nLeave blank to use null.'
        )
        self._pop_entity_var_default_edit.setFixedHeight(110)
        pop_entity_var_form.addRow("default", self._pop_entity_var_default_edit)
        self._pop_entity_var_default_note = QLabel(
            "Pops the last list item. If the list is empty, default is stored instead."
        )
        self._pop_entity_var_default_note.setWordWrap(True)
        self._pop_entity_var_default_note.setStyleSheet("color: #666;")
        pop_entity_var_form.addRow(self._pop_entity_var_default_note)
        self._pop_entity_var_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._pop_entity_var_persistent_field)
        pop_entity_var_form.addRow("persistent", self._pop_entity_var_persistent_field)
        self._command_stack.addWidget(self._pop_entity_var_page)

        self._set_entity_field_page = QWidget()
        set_entity_field_form = QFormLayout(self._set_entity_field_page)
        set_entity_field_form.setContentsMargins(0, 0, 0, 0)
        (
            set_entity_field_entity_row,
            self._set_entity_field_entity_id_edit,
            self._set_entity_field_entity_pick,
            self._set_entity_field_entity_ref,
        ) = make_entity_id_row()
        set_entity_field_form.addRow("entity_id", set_entity_field_entity_row)
        self._set_entity_field_name_combo = make_field_name_combo()
        set_entity_field_form.addRow("field_name", self._set_entity_field_name_combo)
        self._set_entity_field_value_edit = QPlainTextEdit()
        self._set_entity_field_value_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._set_entity_field_value_edit.setFont(generic_font)
        self._set_entity_field_value_edit.setPlaceholderText(
            'true\n\nor\n\n"down"\n\nor\n\n[255, 255, 255]'
        )
        self._set_entity_field_value_edit.setFixedHeight(120)
        set_entity_field_form.addRow("value", self._set_entity_field_value_edit)
        self._set_entity_field_note = QLabel(
            "Value uses JSON syntax. Visual fields use names like visuals.main.flip_x."
        )
        self._set_entity_field_note.setWordWrap(True)
        self._set_entity_field_note.setStyleSheet("color: #666;")
        set_entity_field_form.addRow(self._set_entity_field_note)
        self._set_entity_field_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_entity_field_persistent_field)
        set_entity_field_form.addRow("persistent", self._set_entity_field_persistent_field)
        self._command_stack.addWidget(self._set_entity_field_page)

        self._set_entity_fields_page = QWidget()
        set_entity_fields_form = QFormLayout(self._set_entity_fields_page)
        set_entity_fields_form.setContentsMargins(0, 0, 0, 0)
        (
            set_entity_fields_entity_row,
            self._set_entity_fields_entity_id_edit,
            self._set_entity_fields_entity_pick,
            self._set_entity_fields_entity_ref,
        ) = make_entity_id_row()
        set_entity_fields_form.addRow("entity_id", set_entity_fields_entity_row)
        self._set_entity_fields_payload_edit = QPlainTextEdit()
        self._set_entity_fields_payload_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._set_entity_fields_payload_edit.setFont(generic_font)
        self._set_entity_fields_payload_edit.setPlaceholderText(
            '{\n  "fields": {\n    "visible": true\n  },\n  "variables": {\n    "toggled": false\n  },\n  "visuals": {\n    "main": {\n      "offset_y": -1\n    }\n  }\n}'
        )
        self._set_entity_fields_payload_edit.setFixedHeight(170)
        set_entity_fields_form.addRow("set", self._set_entity_fields_payload_edit)
        self._set_entity_fields_note = QLabel(
            "Set uses a JSON object with fields, variables, and visuals sections."
        )
        self._set_entity_fields_note.setWordWrap(True)
        self._set_entity_fields_note.setStyleSheet("color: #666;")
        set_entity_fields_form.addRow(self._set_entity_fields_note)
        self._set_entity_fields_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_entity_fields_persistent_field)
        set_entity_fields_form.addRow("persistent", self._set_entity_fields_persistent_field)
        self._command_stack.addWidget(self._set_entity_fields_page)

        self._spawn_entity_page = QWidget()
        spawn_entity_form = QFormLayout(self._spawn_entity_page)
        spawn_entity_form.setContentsMargins(0, 0, 0, 0)
        self._spawn_entity_mode_combo = QComboBox()
        self._spawn_entity_mode_combo.addItem("Template / Partial", "partial")
        self._spawn_entity_mode_combo.addItem("Full Entity JSON", "full")
        self._spawn_entity_mode_combo.currentIndexChanged.connect(
            self._sync_spawn_entity_mode_visibility
        )
        spawn_entity_form.addRow("mode", self._spawn_entity_mode_combo)

        self._spawn_entity_partial_widget = QWidget()
        spawn_partial_form = QFormLayout(self._spawn_entity_partial_widget)
        spawn_partial_form.setContentsMargins(12, 0, 0, 0)
        self._spawn_entity_id_edit = QLineEdit()
        spawn_partial_form.addRow("entity_id", self._spawn_entity_id_edit)
        self._spawn_entity_template_field = _OptionalTextField()
        spawn_partial_form.addRow("template", self._spawn_entity_template_field)
        self._spawn_entity_kind_field = _OptionalTextField()
        spawn_partial_form.addRow("kind", self._spawn_entity_kind_field)
        self._spawn_entity_x_spin = QSpinBox()
        self._spawn_entity_x_spin.setRange(-999999, 999999)
        spawn_partial_form.addRow("x", self._spawn_entity_x_spin)
        self._spawn_entity_y_spin = QSpinBox()
        self._spawn_entity_y_spin.setRange(-999999, 999999)
        spawn_partial_form.addRow("y", self._spawn_entity_y_spin)
        self._spawn_entity_parameters_edit = QPlainTextEdit()
        self._spawn_entity_parameters_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._spawn_entity_parameters_edit.setFont(generic_font)
        self._spawn_entity_parameters_edit.setPlaceholderText(
            '{\n  "dialogue_definition": {\n    "segments": []\n  }\n}'
        )
        self._spawn_entity_parameters_edit.setFixedHeight(120)
        spawn_partial_form.addRow("parameters", self._spawn_entity_parameters_edit)
        self._spawn_entity_parameters_note = QLabel(
            "Parameters uses a JSON object. Leave blank when not using template parameters."
        )
        self._spawn_entity_parameters_note.setWordWrap(True)
        self._spawn_entity_parameters_note.setStyleSheet("color: #666;")
        spawn_partial_form.addRow(self._spawn_entity_parameters_note)
        spawn_entity_form.addRow(self._spawn_entity_partial_widget)

        self._spawn_entity_full_widget = QWidget()
        spawn_full_form = QFormLayout(self._spawn_entity_full_widget)
        spawn_full_form.setContentsMargins(12, 0, 0, 0)
        self._spawn_entity_full_edit = QPlainTextEdit()
        self._spawn_entity_full_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._spawn_entity_full_edit.setFont(generic_font)
        self._spawn_entity_full_edit.setPlaceholderText(
            '{\n  "id": "sparkle_1",\n  "x": 10,\n  "y": 5,\n  "template": "fx/sparkle"\n}'
        )
        self._spawn_entity_full_edit.setFixedHeight(180)
        spawn_full_form.addRow("entity", self._spawn_entity_full_edit)
        self._spawn_entity_full_note = QLabel(
            "Use full entity JSON when the common partial form is not enough."
        )
        self._spawn_entity_full_note.setWordWrap(True)
        self._spawn_entity_full_note.setStyleSheet("color: #666;")
        spawn_full_form.addRow(self._spawn_entity_full_note)
        spawn_entity_form.addRow(self._spawn_entity_full_widget)

        self._spawn_entity_present_field = QComboBox()
        self._setup_optional_bool_combo(self._spawn_entity_present_field)
        spawn_entity_form.addRow("present", self._spawn_entity_present_field)
        self._spawn_entity_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._spawn_entity_persistent_field)
        spawn_entity_form.addRow("persistent", self._spawn_entity_persistent_field)
        self._command_stack.addWidget(self._spawn_entity_page)

        self._set_area_var_page = QWidget()
        set_area_var_form = QFormLayout(self._set_area_var_page)
        set_area_var_form.setContentsMargins(0, 0, 0, 0)
        (
            set_area_var_area_row,
            self._set_area_var_area_id_edit,
            self._set_area_var_area_pick,
        ) = make_area_id_row()
        set_area_var_form.addRow("area_id", set_area_var_area_row)
        self._set_area_var_name_edit = QLineEdit()
        set_area_var_form.addRow("name", self._set_area_var_name_edit)
        self._set_area_var_value_edit = QPlainTextEdit()
        self._set_area_var_value_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._set_area_var_value_edit.setFont(generic_font)
        self._set_area_var_value_edit.setPlaceholderText(
            'true\n\nor\n\n"opened"\n\nor\n\n{\n  "phase": 2\n}'
        )
        self._set_area_var_value_edit.setFixedHeight(120)
        set_area_var_form.addRow("value", self._set_area_var_value_edit)
        self._set_area_var_note = QLabel("This is always a persistent cross-area write.")
        self._set_area_var_note.setWordWrap(True)
        self._set_area_var_note.setStyleSheet("color: #666;")
        set_area_var_form.addRow(self._set_area_var_note)
        self._command_stack.addWidget(self._set_area_var_page)

        self._set_area_entity_var_page = QWidget()
        set_area_entity_var_form = QFormLayout(self._set_area_entity_var_page)
        set_area_entity_var_form.setContentsMargins(0, 0, 0, 0)
        (
            set_area_entity_var_area_row,
            self._set_area_entity_var_area_id_edit,
            self._set_area_entity_var_area_pick,
        ) = make_area_id_row()
        set_area_entity_var_form.addRow("area_id", set_area_entity_var_area_row)
        self._set_area_entity_var_entity_id_edit = QLineEdit()
        set_area_entity_var_form.addRow("entity_id", self._set_area_entity_var_entity_id_edit)
        self._set_area_entity_var_name_edit = QLineEdit()
        set_area_entity_var_form.addRow("name", self._set_area_entity_var_name_edit)
        self._set_area_entity_var_value_edit = QPlainTextEdit()
        self._set_area_entity_var_value_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._set_area_entity_var_value_edit.setFont(generic_font)
        self._set_area_entity_var_value_edit.setPlaceholderText(
            'true\n\nor\n\n"opened"\n\nor\n\n{\n  "phase": 2\n}'
        )
        self._set_area_entity_var_value_edit.setFixedHeight(120)
        set_area_entity_var_form.addRow("value", self._set_area_entity_var_value_edit)
        self._set_area_entity_var_note = QLabel("This is always a persistent cross-area write.")
        self._set_area_entity_var_note.setWordWrap(True)
        self._set_area_entity_var_note.setStyleSheet("color: #666;")
        set_area_entity_var_form.addRow(self._set_area_entity_var_note)
        self._command_stack.addWidget(self._set_area_entity_var_page)

        self._set_area_entity_field_page = QWidget()
        set_area_entity_field_form = QFormLayout(self._set_area_entity_field_page)
        set_area_entity_field_form.setContentsMargins(0, 0, 0, 0)
        (
            set_area_entity_field_area_row,
            self._set_area_entity_field_area_id_edit,
            self._set_area_entity_field_area_pick,
        ) = make_area_id_row()
        set_area_entity_field_form.addRow("area_id", set_area_entity_field_area_row)
        self._set_area_entity_field_entity_id_edit = QLineEdit()
        set_area_entity_field_form.addRow("entity_id", self._set_area_entity_field_entity_id_edit)
        self._set_area_entity_field_name_combo = make_field_name_combo()
        set_area_entity_field_form.addRow("field_name", self._set_area_entity_field_name_combo)
        self._set_area_entity_field_value_edit = QPlainTextEdit()
        self._set_area_entity_field_value_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._set_area_entity_field_value_edit.setFont(generic_font)
        self._set_area_entity_field_value_edit.setPlaceholderText(
            'false\n\nor\n\n"left"\n\nor\n\n[255, 255, 255]'
        )
        self._set_area_entity_field_value_edit.setFixedHeight(120)
        set_area_entity_field_form.addRow("value", self._set_area_entity_field_value_edit)
        self._set_area_entity_field_note = QLabel("This is always a persistent cross-area write.")
        self._set_area_entity_field_note.setWordWrap(True)
        self._set_area_entity_field_note.setStyleSheet("color: #666;")
        set_area_entity_field_form.addRow(self._set_area_entity_field_note)
        self._command_stack.addWidget(self._set_area_entity_field_page)

        self._reset_transient_state_page = QWidget()
        reset_transient_form = QFormLayout(self._reset_transient_state_page)
        reset_transient_form.setContentsMargins(0, 0, 0, 0)
        (
            reset_transient_entity_row,
            self._reset_transient_entity_id_edit,
            self._reset_transient_entity_pick,
            self._reset_transient_entity_ref,
        ) = make_entity_id_row()
        reset_transient_form.addRow("entity_id", reset_transient_entity_row)
        self._reset_transient_entity_ids_field = _OptionalTextField()
        reset_transient_form.addRow("entity_ids", self._reset_transient_entity_ids_field)
        self._reset_transient_include_tags_field = _OptionalTextField()
        reset_transient_form.addRow("include_tags", self._reset_transient_include_tags_field)
        self._reset_transient_exclude_tags_field = _OptionalTextField()
        reset_transient_form.addRow("exclude_tags", self._reset_transient_exclude_tags_field)
        self._reset_transient_apply_field = QComboBox()
        self._setup_optional_choice_combo(
            self._reset_transient_apply_field,
            list(_RESET_APPLY_CHOICES),
            not_set_label="Default (immediate)",
        )
        reset_transient_form.addRow("apply", self._reset_transient_apply_field)
        self._reset_transient_note = QLabel("entity_ids and tag fields use comma-separated lists.")
        self._reset_transient_note.setWordWrap(True)
        self._reset_transient_note.setStyleSheet("color: #666;")
        reset_transient_form.addRow(self._reset_transient_note)
        self._command_stack.addWidget(self._reset_transient_state_page)

        self._reset_persistent_state_page = QWidget()
        reset_persistent_form = QFormLayout(self._reset_persistent_state_page)
        reset_persistent_form.setContentsMargins(0, 0, 0, 0)
        self._reset_persistent_include_tags_field = _OptionalTextField()
        reset_persistent_form.addRow("include_tags", self._reset_persistent_include_tags_field)
        self._reset_persistent_exclude_tags_field = _OptionalTextField()
        reset_persistent_form.addRow("exclude_tags", self._reset_persistent_exclude_tags_field)
        self._reset_persistent_apply_field = QComboBox()
        self._setup_optional_choice_combo(
            self._reset_persistent_apply_field,
            list(_RESET_APPLY_CHOICES),
            not_set_label="Default (immediate)",
        )
        reset_persistent_form.addRow("apply", self._reset_persistent_apply_field)
        self._reset_persistent_note = QLabel("Tag fields use comma-separated lists.")
        self._reset_persistent_note.setWordWrap(True)
        self._reset_persistent_note.setStyleSheet("color: #666;")
        reset_persistent_form.addRow(self._reset_persistent_note)
        self._command_stack.addWidget(self._reset_persistent_state_page)

        self._open_entity_dialogue_page = QWidget()
        open_entity_form = QFormLayout(self._open_entity_dialogue_page)
        open_entity_form.setContentsMargins(0, 0, 0, 0)
        (
            open_entity_entity_row,
            self._open_entity_entity_id_edit,
            self._open_entity_entity_pick,
            self._open_entity_entity_ref,
        ) = _make_line_with_two_buttons(
            primary_button_text="Pick...",
            secondary_button_text="Ref...",
        )
        self._open_entity_entity_pick.clicked.connect(
            lambda: self._pick_entity_into_edit(
                self._open_entity_entity_id_edit,
                parameter_name="entity_id",
            )
        )
        self._open_entity_entity_ref.clicked.connect(
            lambda: self._show_entity_token_menu_for_edit(
                self._open_entity_entity_id_edit,
                self._open_entity_entity_ref,
            )
        )
        self._open_entity_entity_id_edit.textChanged.connect(
            self._sync_entity_dialogue_picker_button_state
        )
        open_entity_form.addRow("entity_id", open_entity_entity_row)
        self._open_entity_dialogue_id_field = _OptionalTextField(button_text="Pick...")
        if self._open_entity_dialogue_id_field.button is not None:
            self._open_entity_dialogue_id_field.button.clicked.connect(
                lambda: self._pick_dialogue_id_into_optional_field(
                    self._open_entity_dialogue_id_field,
                    entity_id_edit=self._open_entity_entity_id_edit,
                )
            )
        open_entity_form.addRow("dialogue_id", self._open_entity_dialogue_id_field)
        self._open_entity_dialogue_id_note = QLabel(
            "Leave dialogue_id unset to use the entity's active dialogue."
        )
        self._open_entity_dialogue_id_note.setWordWrap(True)
        self._open_entity_dialogue_id_note.setStyleSheet("color: #666;")
        open_entity_form.addRow(self._open_entity_dialogue_id_note)
        self._open_entity_allow_cancel_field = QComboBox()
        self._setup_optional_bool_combo(self._open_entity_allow_cancel_field)
        open_entity_form.addRow("allow_cancel", self._open_entity_allow_cancel_field)

        self._open_entity_advanced_toggle = QToolButton()
        self._open_entity_advanced_toggle.setText("Advanced")
        self._open_entity_advanced_toggle.setCheckable(True)
        self._open_entity_advanced_toggle.setChecked(False)
        self._open_entity_advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._open_entity_advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._open_entity_advanced_toggle.toggled.connect(
            self._on_open_entity_advanced_toggled
        )
        open_entity_form.addRow(self._open_entity_advanced_toggle)

        self._open_entity_advanced_widget = QWidget()
        open_entity_advanced_form = QFormLayout(self._open_entity_advanced_widget)
        open_entity_advanced_form.setContentsMargins(12, 0, 0, 0)
        self._open_entity_ui_preset_field = _OptionalTextField()
        self._open_entity_ui_preset_field.changed.connect(
            self._sync_open_entity_advanced_state
        )
        open_entity_advanced_form.addRow("ui_preset", self._open_entity_ui_preset_field)
        self._open_entity_actor_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        self._open_entity_actor_id_field.changed.connect(
            self._sync_open_entity_advanced_state
        )
        if self._open_entity_actor_id_field.button is not None:
            self._open_entity_actor_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._open_entity_actor_id_field,
                    parameter_name="actor_id",
                )
            )
        if self._open_entity_actor_id_field.extra_button is not None:
            self._open_entity_actor_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._open_entity_actor_id_field,
                    self._open_entity_actor_id_field.extra_button,
                )
            )
        open_entity_advanced_form.addRow("actor_id", self._open_entity_actor_id_field)
        self._open_entity_caller_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        self._open_entity_caller_id_field.changed.connect(
            self._sync_open_entity_advanced_state
        )
        if self._open_entity_caller_id_field.button is not None:
            self._open_entity_caller_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._open_entity_caller_id_field,
                    parameter_name="caller_id",
                )
            )
        if self._open_entity_caller_id_field.extra_button is not None:
            self._open_entity_caller_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._open_entity_caller_id_field,
                    self._open_entity_caller_id_field.extra_button,
                )
            )
        open_entity_advanced_form.addRow("caller_id", self._open_entity_caller_id_field)
        self._open_entity_entity_refs_field = _NamedEntityRefsField(
            pick_entity_callback=self._pick_entity_into_ref_value_edit,
            show_token_menu_callback=self._show_entity_token_menu_for_edit,
        )
        self._open_entity_entity_refs_field.changed.connect(
            self._sync_open_entity_advanced_state
        )
        open_entity_advanced_form.addRow(
            "entity_refs",
            self._open_entity_entity_refs_field,
        )
        open_entity_form.addRow(self._open_entity_advanced_widget)
        self._command_stack.addWidget(self._open_entity_dialogue_page)

        self._set_entity_grid_position_page = QWidget()
        set_grid_position_form = QFormLayout(self._set_entity_grid_position_page)
        set_grid_position_form.setContentsMargins(0, 0, 0, 0)
        (
            set_grid_entity_row,
            self._set_grid_entity_id_edit,
            self._set_grid_entity_pick,
            self._set_grid_entity_ref,
        ) = make_entity_id_row()
        set_grid_position_form.addRow("entity_id", set_grid_entity_row)
        self._set_grid_x_spin = QSpinBox()
        self._set_grid_x_spin.setRange(-999999, 999999)
        set_grid_position_form.addRow("x", self._set_grid_x_spin)
        self._set_grid_y_spin = QSpinBox()
        self._set_grid_y_spin.setRange(-999999, 999999)
        set_grid_position_form.addRow("y", self._set_grid_y_spin)
        self._set_grid_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._set_grid_mode_field,
            list(_CAMERA_MOVE_MODE_CHOICES),
            not_set_label="Default (absolute)",
        )
        set_grid_position_form.addRow("mode", self._set_grid_mode_field)
        self._set_grid_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_grid_persistent_field)
        set_grid_position_form.addRow("persistent", self._set_grid_persistent_field)
        self._set_grid_position_note = QLabel("Requires a world-space entity.")
        self._set_grid_position_note.setWordWrap(True)
        self._set_grid_position_note.setStyleSheet("color: #666;")
        set_grid_position_form.addRow(self._set_grid_position_note)
        self._command_stack.addWidget(self._set_entity_grid_position_page)

        self._set_entity_world_position_page = QWidget()
        set_world_position_form = QFormLayout(self._set_entity_world_position_page)
        set_world_position_form.setContentsMargins(0, 0, 0, 0)
        (
            set_world_entity_row,
            self._set_world_entity_id_edit,
            self._set_world_entity_pick,
            self._set_world_entity_ref,
        ) = make_entity_id_row()
        set_world_position_form.addRow("entity_id", set_world_entity_row)
        self._set_world_x_spin = QDoubleSpinBox()
        self._set_world_x_spin.setRange(-999999.0, 999999.0)
        self._set_world_x_spin.setDecimals(3)
        self._set_world_x_spin.setSingleStep(1.0)
        set_world_position_form.addRow("x", self._set_world_x_spin)
        self._set_world_y_spin = QDoubleSpinBox()
        self._set_world_y_spin.setRange(-999999.0, 999999.0)
        self._set_world_y_spin.setDecimals(3)
        self._set_world_y_spin.setSingleStep(1.0)
        set_world_position_form.addRow("y", self._set_world_y_spin)
        self._set_world_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._set_world_mode_field,
            list(_CAMERA_MOVE_MODE_CHOICES),
            not_set_label="Default (absolute)",
        )
        set_world_position_form.addRow("mode", self._set_world_mode_field)
        self._set_world_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_world_persistent_field)
        set_world_position_form.addRow("persistent", self._set_world_persistent_field)
        self._set_world_position_note = QLabel("Requires a world-space entity.")
        self._set_world_position_note.setWordWrap(True)
        self._set_world_position_note.setStyleSheet("color: #666;")
        set_world_position_form.addRow(self._set_world_position_note)
        self._command_stack.addWidget(self._set_entity_world_position_page)

        self._set_entity_screen_position_page = QWidget()
        set_screen_position_form = QFormLayout(self._set_entity_screen_position_page)
        set_screen_position_form.setContentsMargins(0, 0, 0, 0)
        (
            set_screen_entity_row,
            self._set_screen_entity_id_edit,
            self._set_screen_entity_pick,
            self._set_screen_entity_ref,
        ) = make_entity_id_row()
        set_screen_position_form.addRow("entity_id", set_screen_entity_row)
        self._set_screen_x_spin = QDoubleSpinBox()
        self._set_screen_x_spin.setRange(-999999.0, 999999.0)
        self._set_screen_x_spin.setDecimals(3)
        self._set_screen_x_spin.setSingleStep(1.0)
        set_screen_position_form.addRow("x", self._set_screen_x_spin)
        self._set_screen_y_spin = QDoubleSpinBox()
        self._set_screen_y_spin.setRange(-999999.0, 999999.0)
        self._set_screen_y_spin.setDecimals(3)
        self._set_screen_y_spin.setSingleStep(1.0)
        set_screen_position_form.addRow("y", self._set_screen_y_spin)
        self._set_screen_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._set_screen_mode_field,
            list(_CAMERA_MOVE_MODE_CHOICES),
            not_set_label="Default (absolute)",
        )
        set_screen_position_form.addRow("mode", self._set_screen_mode_field)
        self._set_screen_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_screen_persistent_field)
        set_screen_position_form.addRow("persistent", self._set_screen_persistent_field)
        self._set_screen_position_note = QLabel("Requires a screen-space entity.")
        self._set_screen_position_note.setWordWrap(True)
        self._set_screen_position_note.setStyleSheet("color: #666;")
        set_screen_position_form.addRow(self._set_screen_position_note)
        self._command_stack.addWidget(self._set_entity_screen_position_page)

        self._move_entity_world_position_page = QWidget()
        move_world_position_form = QFormLayout(self._move_entity_world_position_page)
        move_world_position_form.setContentsMargins(0, 0, 0, 0)
        (
            move_world_entity_row,
            self._move_world_entity_id_edit,
            self._move_world_entity_pick,
            self._move_world_entity_ref,
        ) = make_entity_id_row()
        move_world_position_form.addRow("entity_id", move_world_entity_row)
        self._move_world_x_spin = QDoubleSpinBox()
        self._move_world_x_spin.setRange(-999999.0, 999999.0)
        self._move_world_x_spin.setDecimals(3)
        self._move_world_x_spin.setSingleStep(1.0)
        move_world_position_form.addRow("x", self._move_world_x_spin)
        self._move_world_y_spin = QDoubleSpinBox()
        self._move_world_y_spin.setRange(-999999.0, 999999.0)
        self._move_world_y_spin.setDecimals(3)
        self._move_world_y_spin.setSingleStep(1.0)
        move_world_position_form.addRow("y", self._move_world_y_spin)
        self._move_world_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._move_world_mode_field,
            list(_CAMERA_MOVE_MODE_CHOICES),
            not_set_label="Default (absolute)",
        )
        move_world_position_form.addRow("mode", self._move_world_mode_field)
        self._move_world_duration_field = _OptionalFloatField(
            minimum=0.0,
            maximum=999999.0,
            default_value=0.0,
            decimals=3,
            step=0.1,
        )
        move_world_position_form.addRow("duration", self._move_world_duration_field)
        self._move_world_frames_needed_field = _OptionalIntField(
            minimum=1,
            maximum=999999,
            default_value=1,
        )
        move_world_position_form.addRow(
            "frames_needed",
            self._move_world_frames_needed_field,
        )
        self._move_world_speed_field = _OptionalFloatField(
            minimum=0.0,
            maximum=999999.0,
            default_value=0.0,
            decimals=3,
            step=1.0,
        )
        move_world_position_form.addRow(
            "speed_px_per_second",
            self._move_world_speed_field,
        )
        self._move_world_wait_field = QComboBox()
        self._setup_optional_bool_combo(self._move_world_wait_field)
        move_world_position_form.addRow("wait", self._move_world_wait_field)
        self._move_world_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._move_world_persistent_field)
        move_world_position_form.addRow("persistent", self._move_world_persistent_field)
        self._move_world_position_note = QLabel("Requires a world-space entity.")
        self._move_world_position_note.setWordWrap(True)
        self._move_world_position_note.setStyleSheet("color: #666;")
        move_world_position_form.addRow(self._move_world_position_note)
        self._command_stack.addWidget(self._move_entity_world_position_page)

        self._move_entity_screen_position_page = QWidget()
        move_screen_position_form = QFormLayout(self._move_entity_screen_position_page)
        move_screen_position_form.setContentsMargins(0, 0, 0, 0)
        (
            move_screen_entity_row,
            self._move_screen_entity_id_edit,
            self._move_screen_entity_pick,
            self._move_screen_entity_ref,
        ) = make_entity_id_row()
        move_screen_position_form.addRow("entity_id", move_screen_entity_row)
        self._move_screen_x_spin = QDoubleSpinBox()
        self._move_screen_x_spin.setRange(-999999.0, 999999.0)
        self._move_screen_x_spin.setDecimals(3)
        self._move_screen_x_spin.setSingleStep(1.0)
        move_screen_position_form.addRow("x", self._move_screen_x_spin)
        self._move_screen_y_spin = QDoubleSpinBox()
        self._move_screen_y_spin.setRange(-999999.0, 999999.0)
        self._move_screen_y_spin.setDecimals(3)
        self._move_screen_y_spin.setSingleStep(1.0)
        move_screen_position_form.addRow("y", self._move_screen_y_spin)
        self._move_screen_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._move_screen_mode_field,
            list(_CAMERA_MOVE_MODE_CHOICES),
            not_set_label="Default (absolute)",
        )
        move_screen_position_form.addRow("mode", self._move_screen_mode_field)
        self._move_screen_duration_field = _OptionalFloatField(
            minimum=0.0,
            maximum=999999.0,
            default_value=0.0,
            decimals=3,
            step=0.1,
        )
        move_screen_position_form.addRow("duration", self._move_screen_duration_field)
        self._move_screen_frames_needed_field = _OptionalIntField(
            minimum=1,
            maximum=999999,
            default_value=1,
        )
        move_screen_position_form.addRow(
            "frames_needed",
            self._move_screen_frames_needed_field,
        )
        self._move_screen_speed_field = _OptionalFloatField(
            minimum=0.0,
            maximum=999999.0,
            default_value=0.0,
            decimals=3,
            step=1.0,
        )
        move_screen_position_form.addRow(
            "speed_px_per_second",
            self._move_screen_speed_field,
        )
        self._move_screen_wait_field = QComboBox()
        self._setup_optional_bool_combo(self._move_screen_wait_field)
        move_screen_position_form.addRow("wait", self._move_screen_wait_field)
        self._move_screen_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._move_screen_persistent_field)
        move_screen_position_form.addRow("persistent", self._move_screen_persistent_field)
        self._move_screen_position_note = QLabel("Requires a screen-space entity.")
        self._move_screen_position_note.setWordWrap(True)
        self._move_screen_position_note.setStyleSheet("color: #666;")
        move_screen_position_form.addRow(self._move_screen_position_note)
        self._command_stack.addWidget(self._move_entity_screen_position_page)

        self._push_facing_page = QWidget()
        push_facing_form = QFormLayout(self._push_facing_page)
        push_facing_form.setContentsMargins(0, 0, 0, 0)
        (
            push_facing_entity_row,
            self._push_facing_entity_id_edit,
            self._push_facing_entity_pick,
            self._push_facing_entity_ref,
        ) = make_entity_id_row()
        push_facing_form.addRow("entity_id", push_facing_entity_row)
        self._push_facing_direction_field = QComboBox()
        self._setup_optional_choice_combo(
            self._push_facing_direction_field,
            list(_STANDARD_DIRECTION_CHOICES),
            not_set_label="Use Facing",
        )
        push_facing_form.addRow("direction", self._push_facing_direction_field)
        self._push_facing_push_strength_field = _OptionalIntField(
            minimum=0,
            maximum=999999,
            default_value=0,
        )
        push_facing_form.addRow("push_strength", self._push_facing_push_strength_field)
        self._push_facing_duration_field = _OptionalFloatField(
            minimum=0.0,
            maximum=999999.0,
            default_value=0.0,
            decimals=3,
            step=0.1,
        )
        push_facing_form.addRow("duration", self._push_facing_duration_field)
        self._push_facing_frames_needed_field = _OptionalIntField(
            minimum=1,
            maximum=999999,
            default_value=1,
        )
        push_facing_form.addRow(
            "frames_needed",
            self._push_facing_frames_needed_field,
        )
        self._push_facing_speed_field = _OptionalFloatField(
            minimum=0.0,
            maximum=999999.0,
            default_value=0.0,
            decimals=3,
            step=1.0,
        )
        push_facing_form.addRow(
            "speed_px_per_second",
            self._push_facing_speed_field,
        )
        self._push_facing_wait_field = QComboBox()
        self._setup_optional_bool_combo(self._push_facing_wait_field)
        push_facing_form.addRow("wait", self._push_facing_wait_field)
        self._push_facing_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._push_facing_persistent_field)
        push_facing_form.addRow("persistent", self._push_facing_persistent_field)
        self._command_stack.addWidget(self._push_facing_page)

        self._wait_for_move_page = QWidget()
        wait_for_move_form = QFormLayout(self._wait_for_move_page)
        wait_for_move_form.setContentsMargins(0, 0, 0, 0)
        (
            wait_for_move_entity_row,
            self._wait_for_move_entity_id_edit,
            self._wait_for_move_entity_pick,
            self._wait_for_move_entity_ref,
        ) = make_entity_id_row()
        wait_for_move_form.addRow("entity_id", wait_for_move_entity_row)
        self._command_stack.addWidget(self._wait_for_move_page)

        self._step_in_direction_page = QWidget()
        step_in_direction_form = QFormLayout(self._step_in_direction_page)
        step_in_direction_form.setContentsMargins(0, 0, 0, 0)
        (
            step_in_direction_entity_row,
            self._step_in_direction_entity_id_edit,
            self._step_in_direction_entity_pick,
            self._step_in_direction_entity_ref,
        ) = _make_line_with_two_buttons(
            primary_button_text="Pick...",
            secondary_button_text="Ref...",
        )
        self._step_in_direction_entity_pick.clicked.connect(
            lambda: self._pick_entity_into_edit(
                self._step_in_direction_entity_id_edit,
                parameter_name="entity_id",
            )
        )
        self._step_in_direction_entity_ref.clicked.connect(
            lambda: self._show_entity_token_menu_for_edit(
                self._step_in_direction_entity_id_edit,
                self._step_in_direction_entity_ref,
            )
        )
        step_in_direction_form.addRow("entity_id", step_in_direction_entity_row)
        self._step_in_direction_direction_field = QComboBox()
        self._setup_optional_choice_combo(
            self._step_in_direction_direction_field,
            list(_STANDARD_DIRECTION_CHOICES),
            not_set_label="Use Facing",
        )
        step_in_direction_form.addRow("direction", self._step_in_direction_direction_field)
        self._step_in_direction_push_strength_field = _OptionalIntField(
            minimum=0,
            maximum=999999,
            default_value=0,
        )
        step_in_direction_form.addRow(
            "push_strength",
            self._step_in_direction_push_strength_field,
        )
        self._step_in_direction_frames_needed_field = _OptionalIntField(
            minimum=1,
            maximum=999999,
            default_value=1,
        )
        step_in_direction_form.addRow(
            "frames_needed",
            self._step_in_direction_frames_needed_field,
        )
        self._step_in_direction_wait_field = QComboBox()
        self._setup_optional_bool_combo(self._step_in_direction_wait_field)
        step_in_direction_form.addRow("wait", self._step_in_direction_wait_field)
        self._step_in_direction_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._step_in_direction_persistent_field)
        step_in_direction_form.addRow(
            "persistent",
            self._step_in_direction_persistent_field,
        )
        self._command_stack.addWidget(self._step_in_direction_page)

        self._set_entity_var_page = QWidget()
        set_var_form = QFormLayout(self._set_entity_var_page)
        set_var_form.setContentsMargins(0, 0, 0, 0)
        (
            set_var_entity_row,
            self._set_var_entity_id_edit,
            self._set_var_entity_pick,
            self._set_var_entity_ref,
        ) = _make_line_with_two_buttons(
            primary_button_text="Pick...",
            secondary_button_text="Ref...",
        )
        self._set_var_entity_pick.clicked.connect(
            lambda: self._pick_entity_into_edit(
                self._set_var_entity_id_edit,
                parameter_name="entity_id",
            )
        )
        self._set_var_entity_ref.clicked.connect(
            lambda: self._show_entity_token_menu_for_edit(
                self._set_var_entity_id_edit,
                self._set_var_entity_ref,
            )
        )
        set_var_form.addRow("entity_id", set_var_entity_row)
        self._set_var_name_edit = QLineEdit()
        set_var_form.addRow("name", self._set_var_name_edit)
        self._set_var_value_edit = QPlainTextEdit()
        self._set_var_value_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._set_var_value_edit.setFont(generic_font)
        self._set_var_value_edit.setPlaceholderText(
            '"hello"\n\nor\n\n42\n\nor\n\n{\n  "x": 1\n}'
        )
        self._set_var_value_edit.setFixedHeight(140)
        set_var_form.addRow("value", self._set_var_value_edit)
        self._set_var_value_note = QLabel(
            "Value uses JSON syntax. Wrap strings in quotes."
        )
        self._set_var_value_note.setWordWrap(True)
        self._set_var_value_note.setStyleSheet("color: #666;")
        set_var_form.addRow(self._set_var_value_note)
        self._set_var_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_var_persistent_field)
        set_var_form.addRow("persistent", self._set_var_persistent_field)
        self._set_var_value_mode_field = QComboBox()
        self._setup_optional_choice_combo(
            self._set_var_value_mode_field,
            [("raw", "raw")],
            not_set_label="Default",
        )
        set_var_form.addRow("value_mode", self._set_var_value_mode_field)
        self._command_stack.addWidget(self._set_entity_var_page)

        self._set_visible_page = QWidget()
        set_visible_form = QFormLayout(self._set_visible_page)
        set_visible_form.setContentsMargins(0, 0, 0, 0)
        (
            set_visible_entity_row,
            self._set_visible_entity_id_edit,
            self._set_visible_entity_pick,
            self._set_visible_entity_ref,
        ) = make_entity_id_row()
        set_visible_form.addRow("entity_id", set_visible_entity_row)
        self._set_visible_value_field = QComboBox()
        self._setup_optional_bool_combo(self._set_visible_value_field)
        set_visible_form.addRow("visible", self._set_visible_value_field)
        self._set_visible_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_visible_persistent_field)
        set_visible_form.addRow("persistent", self._set_visible_persistent_field)
        self._command_stack.addWidget(self._set_visible_page)

        self._set_present_page = QWidget()
        set_present_form = QFormLayout(self._set_present_page)
        set_present_form.setContentsMargins(0, 0, 0, 0)
        (
            set_present_entity_row,
            self._set_present_entity_id_edit,
            self._set_present_entity_pick,
            self._set_present_entity_ref,
        ) = make_entity_id_row()
        set_present_form.addRow("entity_id", set_present_entity_row)
        self._set_present_value_field = QComboBox()
        self._setup_optional_bool_combo(self._set_present_value_field)
        set_present_form.addRow("present", self._set_present_value_field)
        self._set_present_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_present_persistent_field)
        set_present_form.addRow("persistent", self._set_present_persistent_field)
        self._command_stack.addWidget(self._set_present_page)

        self._set_color_page = QWidget()
        set_color_form = QFormLayout(self._set_color_page)
        set_color_form.setContentsMargins(0, 0, 0, 0)
        (
            set_color_entity_row,
            self._set_color_entity_id_edit,
            self._set_color_entity_pick,
            self._set_color_entity_ref,
        ) = make_entity_id_row()
        set_color_form.addRow("entity_id", set_color_entity_row)
        self._set_color_value_edit = QLineEdit()
        set_color_form.addRow("color", self._set_color_value_edit)
        self._set_color_note = QLabel(
            "Use comma-separated RGB, for example: 255, 255, 255"
        )
        self._set_color_note.setWordWrap(True)
        self._set_color_note.setStyleSheet("color: #666;")
        set_color_form.addRow(self._set_color_note)
        self._set_color_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_color_persistent_field)
        set_color_form.addRow("persistent", self._set_color_persistent_field)
        self._command_stack.addWidget(self._set_color_page)

        self._destroy_entity_page = QWidget()
        destroy_entity_form = QFormLayout(self._destroy_entity_page)
        destroy_entity_form.setContentsMargins(0, 0, 0, 0)
        (
            destroy_entity_row,
            self._destroy_entity_id_edit,
            self._destroy_entity_pick,
            self._destroy_entity_ref,
        ) = make_entity_id_row()
        destroy_entity_form.addRow("entity_id", destroy_entity_row)
        self._destroy_entity_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._destroy_entity_persistent_field)
        destroy_entity_form.addRow("persistent", self._destroy_entity_persistent_field)
        self._destroy_entity_note = QLabel(
            "Destroying an entity removes it from the current runtime scene."
        )
        self._destroy_entity_note.setWordWrap(True)
        self._destroy_entity_note.setStyleSheet("color: #666;")
        destroy_entity_form.addRow(self._destroy_entity_note)
        self._command_stack.addWidget(self._destroy_entity_page)

        self._set_visual_frame_page = QWidget()
        set_visual_frame_form = QFormLayout(self._set_visual_frame_page)
        set_visual_frame_form.setContentsMargins(0, 0, 0, 0)
        (
            set_visual_frame_entity_row,
            self._set_visual_frame_entity_id_edit,
            self._set_visual_frame_entity_pick,
            self._set_visual_frame_entity_ref,
        ) = make_entity_id_row()
        set_visual_frame_form.addRow("entity_id", set_visual_frame_entity_row)
        self._set_visual_frame_visual_id_field = _OptionalTextField()
        set_visual_frame_form.addRow("visual_id", self._set_visual_frame_visual_id_field)
        self._set_visual_frame_spin = QSpinBox()
        self._set_visual_frame_spin.setRange(0, 999999)
        set_visual_frame_form.addRow("frame", self._set_visual_frame_spin)
        self._set_visual_frame_note = QLabel(
            "Leave visual_id unset to target the entity's primary visual."
        )
        self._set_visual_frame_note.setWordWrap(True)
        self._set_visual_frame_note.setStyleSheet("color: #666;")
        set_visual_frame_form.addRow(self._set_visual_frame_note)
        self._command_stack.addWidget(self._set_visual_frame_page)

        self._set_visual_flip_x_page = QWidget()
        set_visual_flip_x_form = QFormLayout(self._set_visual_flip_x_page)
        set_visual_flip_x_form.setContentsMargins(0, 0, 0, 0)
        (
            set_visual_flip_entity_row,
            self._set_visual_flip_entity_id_edit,
            self._set_visual_flip_entity_pick,
            self._set_visual_flip_entity_ref,
        ) = make_entity_id_row()
        set_visual_flip_x_form.addRow("entity_id", set_visual_flip_entity_row)
        self._set_visual_flip_visual_id_field = _OptionalTextField()
        set_visual_flip_x_form.addRow("visual_id", self._set_visual_flip_visual_id_field)
        self._set_visual_flip_x_value_field = QComboBox()
        self._setup_optional_bool_combo(self._set_visual_flip_x_value_field)
        set_visual_flip_x_form.addRow("flip_x", self._set_visual_flip_x_value_field)
        self._set_visual_flip_note = QLabel(
            "Leave visual_id unset to target the entity's primary visual."
        )
        self._set_visual_flip_note.setWordWrap(True)
        self._set_visual_flip_note.setStyleSheet("color: #666;")
        set_visual_flip_x_form.addRow(self._set_visual_flip_note)
        self._command_stack.addWidget(self._set_visual_flip_x_page)

        self._set_entity_command_enabled_page = QWidget()
        set_entity_command_form = QFormLayout(self._set_entity_command_enabled_page)
        set_entity_command_form.setContentsMargins(0, 0, 0, 0)
        (
            set_entity_command_entity_row,
            self._set_entity_command_entity_id_edit,
            self._set_entity_command_entity_pick,
            self._set_entity_command_entity_ref,
        ) = make_entity_id_row()
        self._set_entity_command_entity_id_edit.textChanged.connect(
            self._sync_entity_command_picker_button_state
        )
        set_entity_command_form.addRow("entity_id", set_entity_command_entity_row)
        (
            set_entity_command_id_row,
            self._set_entity_command_id_edit,
            self._set_entity_command_pick,
        ) = _make_line_with_button(button_text="Pick...")
        self._set_entity_command_pick.clicked.connect(
            lambda: self._pick_entity_command_id_into_edit(
                self._set_entity_command_id_edit,
                entity_id_edit=self._set_entity_command_entity_id_edit,
            )
        )
        set_entity_command_form.addRow("command_id", set_entity_command_id_row)
        self._set_entity_command_enabled_field = QComboBox()
        self._setup_optional_bool_combo(self._set_entity_command_enabled_field)
        set_entity_command_form.addRow("enabled", self._set_entity_command_enabled_field)
        self._set_entity_command_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_entity_command_persistent_field)
        set_entity_command_form.addRow(
            "persistent",
            self._set_entity_command_persistent_field,
        )
        self._command_stack.addWidget(self._set_entity_command_enabled_page)

        self._set_entity_commands_enabled_page = QWidget()
        set_entity_commands_form = QFormLayout(self._set_entity_commands_enabled_page)
        set_entity_commands_form.setContentsMargins(0, 0, 0, 0)
        (
            set_entity_commands_entity_row,
            self._set_entity_commands_entity_id_edit,
            self._set_entity_commands_entity_pick,
            self._set_entity_commands_entity_ref,
        ) = make_entity_id_row()
        set_entity_commands_form.addRow("entity_id", set_entity_commands_entity_row)
        self._set_entity_commands_enabled_field = QComboBox()
        self._setup_optional_bool_combo(self._set_entity_commands_enabled_field)
        set_entity_commands_form.addRow("enabled", self._set_entity_commands_enabled_field)
        self._set_entity_commands_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_entity_commands_persistent_field)
        set_entity_commands_form.addRow(
            "persistent",
            self._set_entity_commands_persistent_field,
        )
        self._set_entity_commands_note = QLabel(
            "This toggles the entity-wide command switch without rewriting each command entry."
        )
        self._set_entity_commands_note.setWordWrap(True)
        self._set_entity_commands_note.setStyleSheet("color: #666;")
        set_entity_commands_form.addRow(self._set_entity_commands_note)
        self._command_stack.addWidget(self._set_entity_commands_enabled_page)

        self._interact_facing_page = QWidget()
        interact_form = QFormLayout(self._interact_facing_page)
        interact_form.setContentsMargins(0, 0, 0, 0)
        (
            interact_entity_row,
            self._interact_entity_id_edit,
            self._interact_entity_pick,
            self._interact_entity_ref,
        ) = _make_line_with_two_buttons(
            primary_button_text="Pick...",
            secondary_button_text="Ref...",
        )
        self._interact_entity_pick.clicked.connect(
            lambda: self._pick_entity_into_edit(
                self._interact_entity_id_edit,
                parameter_name="entity_id",
            )
        )
        self._interact_entity_ref.clicked.connect(
            lambda: self._show_entity_token_menu_for_edit(
                self._interact_entity_id_edit,
                self._interact_entity_ref,
            )
        )
        interact_form.addRow("entity_id", interact_entity_row)
        self._interact_direction_field = QComboBox()
        self._setup_optional_choice_combo(
            self._interact_direction_field,
            [
                ("up", "up"),
                ("down", "down"),
                ("left", "left"),
                ("right", "right"),
            ],
            not_set_label="Use Facing",
        )
        interact_form.addRow("direction", self._interact_direction_field)
        self._command_stack.addWidget(self._interact_facing_page)

        self._set_input_target_page = QWidget()
        set_input_target_form = QFormLayout(self._set_input_target_page)
        set_input_target_form.setContentsMargins(0, 0, 0, 0)
        self._set_input_target_action_edit = QLineEdit()
        set_input_target_form.addRow("action", self._set_input_target_action_edit)
        self._set_input_target_entity_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        if self._set_input_target_entity_id_field.button is not None:
            self._set_input_target_entity_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._set_input_target_entity_id_field,
                    parameter_name="entity_id",
                )
            )
        if self._set_input_target_entity_id_field.extra_button is not None:
            self._set_input_target_entity_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._set_input_target_entity_id_field,
                    self._set_input_target_entity_id_field.extra_button,
                )
            )
        set_input_target_form.addRow("entity_id", self._set_input_target_entity_id_field)
        self._set_input_target_note = QLabel(
            "Leave entity_id unset to clear the routed target for this action."
        )
        self._set_input_target_note.setWordWrap(True)
        self._set_input_target_note.setStyleSheet("color: #666;")
        set_input_target_form.addRow(self._set_input_target_note)
        self._command_stack.addWidget(self._set_input_target_page)

        self._route_inputs_to_entity_page = QWidget()
        route_inputs_form = QFormLayout(self._route_inputs_to_entity_page)
        route_inputs_form.setContentsMargins(0, 0, 0, 0)
        self._route_inputs_entity_id_field = _OptionalTextField(
            button_text="Pick...",
            extra_button_text="Ref...",
        )
        if self._route_inputs_entity_id_field.button is not None:
            self._route_inputs_entity_id_field.button.clicked.connect(
                lambda: self._pick_entity_into_optional_field(
                    self._route_inputs_entity_id_field,
                    parameter_name="entity_id",
                )
            )
        if self._route_inputs_entity_id_field.extra_button is not None:
            self._route_inputs_entity_id_field.extra_button.clicked.connect(
                lambda: self._show_entity_token_menu_for_optional_field(
                    self._route_inputs_entity_id_field,
                    self._route_inputs_entity_id_field.extra_button,
                )
            )
        route_inputs_form.addRow("entity_id", self._route_inputs_entity_id_field)
        self._route_inputs_actions_field = _OptionalTextField()
        route_inputs_form.addRow("actions", self._route_inputs_actions_field)
        self._route_inputs_note = QLabel(
            "Actions are comma-separated. Leave entity_id unset to clear routing."
        )
        self._route_inputs_note.setWordWrap(True)
        self._route_inputs_note.setStyleSheet("color: #666;")
        route_inputs_form.addRow(self._route_inputs_note)
        self._command_stack.addWidget(self._route_inputs_to_entity_page)

        self._push_input_routes_page = QWidget()
        push_inputs_form = QFormLayout(self._push_input_routes_page)
        push_inputs_form.setContentsMargins(0, 0, 0, 0)
        self._push_input_routes_actions_field = _OptionalTextField()
        push_inputs_form.addRow("actions", self._push_input_routes_actions_field)
        self._push_input_routes_note = QLabel(
            "Actions are comma-separated. Leave unset to snapshot all routed actions."
        )
        self._push_input_routes_note.setWordWrap(True)
        self._push_input_routes_note.setStyleSheet("color: #666;")
        push_inputs_form.addRow(self._push_input_routes_note)
        self._command_stack.addWidget(self._push_input_routes_page)

        self._pop_input_routes_page = QWidget()
        pop_inputs_layout = QVBoxLayout(self._pop_input_routes_page)
        pop_inputs_layout.setContentsMargins(0, 0, 0, 0)
        self._pop_input_routes_note = QLabel(
            "Restore the last remembered routed targets."
        )
        self._pop_input_routes_note.setWordWrap(True)
        self._pop_input_routes_note.setStyleSheet("color: #666;")
        pop_inputs_layout.addWidget(self._pop_input_routes_note)
        pop_inputs_layout.addStretch(1)
        self._command_stack.addWidget(self._pop_input_routes_page)

        self._wait_frames_page = QWidget()
        wait_frames_form = QFormLayout(self._wait_frames_page)
        wait_frames_form.setContentsMargins(0, 0, 0, 0)
        self._wait_frames_spin = QSpinBox()
        self._wait_frames_spin.setRange(0, 999999)
        self._wait_frames_spin.setValue(1)
        wait_frames_form.addRow("frames", self._wait_frames_spin)
        self._command_stack.addWidget(self._wait_frames_page)

        self._wait_seconds_page = QWidget()
        wait_seconds_form = QFormLayout(self._wait_seconds_page)
        wait_seconds_form.setContentsMargins(0, 0, 0, 0)
        self._wait_seconds_spin = QDoubleSpinBox()
        self._wait_seconds_spin.setRange(0.0, 999999.0)
        self._wait_seconds_spin.setDecimals(3)
        self._wait_seconds_spin.setSingleStep(0.1)
        self._wait_seconds_spin.setValue(1.0)
        wait_seconds_form.addRow("seconds", self._wait_seconds_spin)
        self._command_stack.addWidget(self._wait_seconds_page)

        self._close_dialogue_session_page = QWidget()
        close_dialogue_layout = QVBoxLayout(self._close_dialogue_session_page)
        close_dialogue_layout.setContentsMargins(0, 0, 0, 0)
        self._close_dialogue_session_note = QLabel(
            "Close the currently active dialogue session."
        )
        self._close_dialogue_session_note.setWordWrap(True)
        self._close_dialogue_session_note.setStyleSheet("color: #666;")
        close_dialogue_layout.addWidget(self._close_dialogue_session_note)
        close_dialogue_layout.addStretch(1)
        self._command_stack.addWidget(self._close_dialogue_session_page)

        self._set_active_dialogue_page = QWidget()
        set_active_form = QFormLayout(self._set_active_dialogue_page)
        set_active_form.setContentsMargins(0, 0, 0, 0)
        (
            set_active_entity_row,
            self._set_active_entity_id_edit,
            self._set_active_entity_pick,
            self._set_active_entity_ref,
        ) = _make_line_with_two_buttons(
            primary_button_text="Pick...",
            secondary_button_text="Ref...",
        )
        self._set_active_entity_pick.clicked.connect(
            lambda: self._pick_entity_into_edit(
                self._set_active_entity_id_edit,
                parameter_name="entity_id",
            )
        )
        self._set_active_entity_ref.clicked.connect(
            lambda: self._show_entity_token_menu_for_edit(
                self._set_active_entity_id_edit,
                self._set_active_entity_ref,
            )
        )
        self._set_active_entity_id_edit.textChanged.connect(
            self._sync_entity_dialogue_picker_button_state
        )
        set_active_form.addRow("entity_id", set_active_entity_row)
        (
            set_active_dialogue_row,
            self._set_active_dialogue_id_edit,
            self._set_active_dialogue_pick,
        ) = _make_line_with_button(button_text="Pick...")
        self._set_active_dialogue_pick.clicked.connect(
            lambda: self._pick_dialogue_id_into_edit(
                self._set_active_dialogue_id_edit,
                entity_id_edit=self._set_active_entity_id_edit,
            )
        )
        set_active_form.addRow("dialogue_id", set_active_dialogue_row)
        self._set_active_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_active_persistent_field)
        set_active_form.addRow("persistent", self._set_active_persistent_field)
        self._command_stack.addWidget(self._set_active_dialogue_page)

        self._step_active_dialogue_page = QWidget()
        step_form = QFormLayout(self._step_active_dialogue_page)
        step_form.setContentsMargins(0, 0, 0, 0)
        (
            step_entity_row,
            self._step_entity_id_edit,
            self._step_entity_pick,
            self._step_entity_ref,
        ) = _make_line_with_two_buttons(
            primary_button_text="Pick...",
            secondary_button_text="Ref...",
        )
        self._step_entity_pick.clicked.connect(
            lambda: self._pick_entity_into_edit(
                self._step_entity_id_edit,
                parameter_name="entity_id",
            )
        )
        self._step_entity_ref.clicked.connect(
            lambda: self._show_entity_token_menu_for_edit(
                self._step_entity_id_edit,
                self._step_entity_ref,
            )
        )
        step_form.addRow("entity_id", step_entity_row)
        self._step_delta_field = _OptionalIntField(
            minimum=-999999,
            maximum=999999,
            default_value=1,
        )
        step_form.addRow("delta", self._step_delta_field)
        self._step_wrap_field = QComboBox()
        self._setup_optional_bool_combo(self._step_wrap_field)
        step_form.addRow("wrap", self._step_wrap_field)
        self._step_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._step_persistent_field)
        step_form.addRow("persistent", self._step_persistent_field)
        self._command_stack.addWidget(self._step_active_dialogue_page)

        self._set_active_by_order_page = QWidget()
        by_order_form = QFormLayout(self._set_active_by_order_page)
        by_order_form.setContentsMargins(0, 0, 0, 0)
        (
            by_order_entity_row,
            self._set_active_by_order_entity_id_edit,
            self._set_active_by_order_entity_pick,
            self._set_active_by_order_entity_ref,
        ) = _make_line_with_two_buttons(
            primary_button_text="Pick...",
            secondary_button_text="Ref...",
        )
        self._set_active_by_order_entity_pick.clicked.connect(
            lambda: self._pick_entity_into_edit(
                self._set_active_by_order_entity_id_edit,
                parameter_name="entity_id",
            )
        )
        self._set_active_by_order_entity_ref.clicked.connect(
            lambda: self._show_entity_token_menu_for_edit(
                self._set_active_by_order_entity_id_edit,
                self._set_active_by_order_entity_ref,
            )
        )
        by_order_form.addRow("entity_id", by_order_entity_row)
        self._set_active_by_order_spin = QSpinBox()
        self._set_active_by_order_spin.setRange(1, 999999)
        self._set_active_by_order_spin.setValue(1)
        by_order_form.addRow("order", self._set_active_by_order_spin)
        self._set_active_by_order_wrap_field = QComboBox()
        self._setup_optional_bool_combo(self._set_active_by_order_wrap_field)
        by_order_form.addRow("wrap", self._set_active_by_order_wrap_field)
        self._set_active_by_order_persistent_field = QComboBox()
        self._setup_optional_bool_combo(self._set_active_by_order_persistent_field)
        by_order_form.addRow("persistent", self._set_active_by_order_persistent_field)
        self._command_stack.addWidget(self._set_active_by_order_page)

        self._tabs.addTab(structured, "Command Editor")

        self._command_json_edit = QPlainTextEdit()
        self._command_json_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._command_json_edit.setFont(generic_font)
        self._tabs.addTab(self._command_json_edit, "Command JSON")

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

        self._command_type_combo.currentTextChanged.connect(self._on_command_type_changed)
        self._dialogue_source_combo.currentTextChanged.connect(
            self._sync_open_dialogue_source_visibility
        )
        self._tabs.currentChanged.connect(self._on_tab_changed)

        self._sync_area_picker_button_state()
        self._sync_asset_picker_button_state()
        self._sync_item_picker_button_state()
        self._sync_entity_picker_button_state()
        self._sync_entity_command_picker_button_state()
        self._sync_entity_dialogue_picker_button_state()
        self._sync_open_dialogue_advanced_state(expanded=False)
        self._sync_run_project_advanced_state(expanded=False)
        self._sync_run_entity_advanced_state(expanded=False)
        self._sync_run_sequence_advanced_state(expanded=False)
        self._sync_spawn_flow_advanced_state(expanded=False)
        self._sync_run_parallel_advanced_state(expanded=False)
        self._sync_run_parallel_completion_visibility()
        self._sync_run_for_each_advanced_state(expanded=False)
        self._sync_change_area_advanced_state(expanded=False)
        self._sync_open_entity_advanced_state(expanded=False)
        self._sync_spawn_entity_mode_visibility()

    def load_command(self, command: object) -> None:
        if isinstance(command, dict):
            self._loaded_command = copy.deepcopy(command)
        else:
            self._loaded_command = {"type": ""}
        self._loading = True
        try:
            command_type = str(self._loaded_command.get("type", "")).strip()
            self._ensure_command_type_visible(command_type)
            self._command_type_combo.setCurrentText(command_type)
            self._command_header.setText(command_type or "Command")
            self._generic_params_edit.setPlainText(
                json.dumps(
                    {
                        key: value
                        for key, value in self._loaded_command.items()
                        if key != "type"
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
            self._command_json_edit.setPlainText(
                json.dumps(self._loaded_command, indent=2, ensure_ascii=False)
            )
            self._command_spec_id_field.set_optional_value(self._loaded_command.get("id"))
            self._load_supported_fields(self._loaded_command)
            self._sync_structured_page(command_type)
        finally:
            self._loading = False

        self._sync_entity_dialogue_picker_button_state()
        self._sync_entity_command_picker_button_state()
        self._sync_open_dialogue_source_visibility()
        if command_type == "open_dialogue_session":
            self._sync_open_dialogue_advanced_state(
                expanded=self._open_dialogue_advanced_field_count() > 0
            )
        if command_type == "run_project_command":
            self._sync_run_project_advanced_state(
                expanded=self._run_project_advanced_field_count() > 0
            )
        if command_type == "run_entity_command":
            self._sync_run_entity_advanced_state(
                expanded=self._run_entity_advanced_field_count() > 0
            )
        if command_type == "run_sequence":
            self._sync_run_sequence_advanced_state(
                expanded=self._run_sequence_advanced_field_count() > 0
            )
        if command_type == "spawn_flow":
            self._sync_spawn_flow_advanced_state(
                expanded=self._spawn_flow_advanced_field_count() > 0
            )
        if command_type == "run_parallel":
            self._sync_run_parallel_advanced_state(
                expanded=self._run_parallel_advanced_field_count() > 0
            )
            self._sync_run_parallel_completion_visibility()
        if command_type == "run_commands_for_collection":
            self._sync_run_for_each_advanced_state(
                expanded=self._run_for_each_advanced_field_count() > 0
            )
        if command_type == "change_area":
            self._sync_change_area_advanced_state(
                expanded=self._change_area_advanced_field_count() > 0
            )
        if command_type == "open_entity_dialogue":
            self._sync_open_entity_advanced_state(
                expanded=self._open_entity_advanced_field_count() > 0
            )
        self._tabs.setCurrentIndex(0)

    def command(self) -> dict[str, Any]:
        if self._tabs.currentIndex() == 1:
            return self._command_from_json_tab(show_message=True)
        command = self._build_structured_command(show_message=True)
        if command is None:
            raise ValueError("Invalid command")
        return command

    def accept(self) -> None:  # noqa: D401
        try:
            self._loaded_command = self.command()
        except ValueError:
            return
        super().accept()

    @staticmethod
    def _setup_optional_bool_combo(combo: QComboBox) -> None:
        combo.addItem("Not Set", None)
        combo.addItem("True", True)
        combo.addItem("False", False)

    @staticmethod
    def _setup_optional_choice_combo(
        combo: QComboBox,
        choices: list[tuple[str, object]],
        *,
        not_set_label: str = "Not Set",
    ) -> None:
        combo.addItem(not_set_label, None)
        for label, value in choices:
            combo.addItem(label, value)

    @staticmethod
    def _set_optional_bool_combo_value(combo: QComboBox, value: object) -> None:
        if value is True:
            combo.setCurrentIndex(1)
        elif value is False:
            combo.setCurrentIndex(2)
        else:
            combo.setCurrentIndex(0)

    @staticmethod
    def _set_optional_choice_combo_value(combo: QComboBox, value: object) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return
        combo.setCurrentIndex(0)

    @staticmethod
    def _set_editable_combo_value(combo: QComboBox, value: object) -> None:
        text = str(value).strip() if value not in (None, "") else ""
        for index in range(combo.count()):
            item_data = combo.itemData(index)
            if (
                item_data == value
                or str(item_data).strip() == text
                or combo.itemText(index).strip() == text
            ):
                combo.setCurrentIndex(index)
                if combo.isEditable():
                    combo.setEditText(combo.itemText(index))
                return
        if combo.isEditable():
            combo.setEditText(text)
        elif combo.count() > 0:
            combo.setCurrentIndex(0)

    @staticmethod
    def _optional_bool_combo_value(combo: QComboBox) -> bool | None:
        value = combo.currentData()
        if value is True:
            return True
        if value is False:
            return False
        return None

    @staticmethod
    def _optional_choice_combo_value(combo: QComboBox) -> object | None:
        return combo.currentData()

    @staticmethod
    def _editable_combo_text(combo: QComboBox) -> str:
        return combo.currentText().strip()

    def _sync_spawn_entity_mode_visibility(self) -> None:
        mode = self._optional_choice_combo_value(self._spawn_entity_mode_combo)
        if mode not in {"partial", "full"}:
            mode = "partial"
        self._spawn_entity_partial_widget.setVisible(mode == "partial")
        self._spawn_entity_full_widget.setVisible(mode == "full")

    def _load_supported_fields(self, command: dict[str, Any]) -> None:
        command_type = str(command.get("type", "")).strip()

        source = "Inline Dialogue"
        if str(command.get("dialogue_path", "")).strip():
            source = "Dialogue File"
        self._dialogue_source_combo.setCurrentText(source)
        self._dialogue_path_edit.setText(str(command.get("dialogue_path", "")))
        dialogue_definition = command.get("dialogue_definition")
        if isinstance(dialogue_definition, dict):
            self._inline_dialogue_definition = copy.deepcopy(dialogue_definition)
        else:
            self._inline_dialogue_definition = {"segments": []}
        self._inline_dialogue_summary.setText(
            _summarize_dialogue_definition(self._inline_dialogue_definition)
        )
        self._set_optional_bool_combo_value(
            self._allow_cancel_field,
            command.get("allow_cancel"),
        )
        self._ui_preset_field.set_optional_value(command.get("ui_preset"))
        self._actor_id_field.set_optional_value(command.get("actor_id"))
        self._caller_id_field.set_optional_value(command.get("caller_id"))
        self._open_dialogue_entity_refs_field.set_refs(command.get("entity_refs"))

        self._project_command_id_edit.setText(str(command.get("command_id", "")))
        self._run_project_source_entity_id_field.set_optional_value(
            command.get("source_entity_id")
        )
        self._set_optional_choice_combo_value(
            self._run_project_refs_mode_field,
            command.get("refs_mode"),
        )
        self._run_project_entity_refs_field.set_refs(command.get("entity_refs"))

        self._run_entity_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._run_entity_command_id_edit.setText(str(command.get("command_id", "")))
        self._run_entity_source_entity_id_field.set_optional_value(
            command.get("source_entity_id")
        )
        self._set_optional_choice_combo_value(
            self._run_entity_refs_mode_field,
            command.get("refs_mode"),
        )
        self._run_entity_entity_refs_field.set_refs(command.get("entity_refs"))

        self._run_sequence_commands_field.set_commands(command.get("commands"))
        self._run_sequence_source_entity_id_field.set_optional_value(
            command.get("source_entity_id")
        )
        self._set_optional_choice_combo_value(
            self._run_sequence_refs_mode_field,
            command.get("refs_mode"),
        )
        self._run_sequence_entity_refs_field.set_refs(command.get("entity_refs"))

        self._spawn_flow_commands_field.set_commands(command.get("commands"))
        self._spawn_flow_source_entity_id_field.set_optional_value(
            command.get("source_entity_id")
        )
        self._set_optional_choice_combo_value(
            self._spawn_flow_refs_mode_field,
            command.get("refs_mode"),
        )
        self._spawn_flow_entity_refs_field.set_refs(command.get("entity_refs"))

        self._run_parallel_commands_field.set_commands(command.get("commands"))
        self._refresh_run_parallel_child_id_choices()
        completion = command.get("completion")
        if isinstance(completion, dict):
            self._set_optional_choice_combo_value(
                self._run_parallel_completion_mode_field,
                completion.get("mode"),
            )
            self._set_editable_combo_value(
                self._run_parallel_child_id_combo,
                completion.get("child_id"),
            )
        else:
            self._set_optional_choice_combo_value(
                self._run_parallel_completion_mode_field,
                None,
            )
            self._set_editable_combo_value(self._run_parallel_child_id_combo, None)
        self._run_parallel_source_entity_id_field.set_optional_value(
            command.get("source_entity_id")
        )
        self._set_optional_choice_combo_value(
            self._run_parallel_refs_mode_field,
            command.get("refs_mode"),
        )
        self._run_parallel_entity_refs_field.set_refs(command.get("entity_refs"))

        value_text = ""
        if "value" in command:
            value_text = json.dumps(command.get("value"), indent=2, ensure_ascii=False)
        self._run_for_each_value_edit.setPlainText(value_text)
        self._run_for_each_item_param_field.set_optional_value(command.get("item_param"))
        self._run_for_each_index_param_field.set_optional_value(command.get("index_param"))
        self._run_for_each_commands_field.set_commands(command.get("commands"))
        self._run_for_each_source_entity_id_field.set_optional_value(
            command.get("source_entity_id")
        )
        self._set_optional_choice_combo_value(
            self._run_for_each_refs_mode_field,
            command.get("refs_mode"),
        )
        self._run_for_each_entity_refs_field.set_refs(command.get("entity_refs"))

        left_text = ""
        if "left" in command:
            left_text = json.dumps(command.get("left"), indent=2, ensure_ascii=False)
        self._if_left_edit.setPlainText(left_text)
        self._set_optional_choice_combo_value(
            self._if_op_field,
            command.get("op"),
        )
        if self._if_op_field.currentIndex() < 0:
            self._if_op_field.setCurrentIndex(0)
        right_text = ""
        if "right" in command:
            right_text = json.dumps(command.get("right"), indent=2, ensure_ascii=False)
        self._if_right_edit.setPlainText(right_text)
        self._if_then_commands_field.set_commands(command.get("then"))
        self._if_else_commands_field.set_commands(command.get("else"))

        self._change_area_area_id_edit.setText(str(command.get("area_id", "")))
        self._change_area_entry_id_field.set_optional_value(command.get("entry_id"))
        self._change_area_destination_entity_id_field.set_optional_value(
            command.get("destination_entity_id")
        )
        self._change_area_transfer_entity_id_field.set_optional_value(
            command.get("transfer_entity_id")
        )
        self._change_area_transfer_entity_ids_field.set_optional_value(
            _string_list_to_text(command.get("transfer_entity_ids"))
        )
        self._change_area_camera_follow_field.set_patch_state(
            "set"
            if isinstance(command.get("camera_follow"), dict)
            else ("clear" if "camera_follow" in command else "omit"),
            command.get("camera_follow"),
        )
        self._change_area_allowed_instigator_kinds_field.set_optional_value(
            _string_list_to_text(command.get("allowed_instigator_kinds"))
        )
        self._change_area_source_entity_id_field.set_optional_value(
            command.get("source_entity_id")
        )
        self._change_area_entity_refs_field.set_refs(command.get("entity_refs"))

        self._new_game_area_id_edit.setText(str(command.get("area_id", "")))
        self._new_game_entry_id_field.set_optional_value(command.get("entry_id"))
        self._new_game_destination_entity_id_field.set_optional_value(
            command.get("destination_entity_id")
        )
        self._new_game_source_entity_id_field.set_optional_value(
            command.get("source_entity_id")
        )
        self._new_game_camera_follow_field.set_patch_state(
            "set"
            if isinstance(command.get("camera_follow"), dict)
            else ("clear" if "camera_follow" in command else "omit"),
            command.get("camera_follow"),
        )

        self._load_game_save_path_field.set_optional_value(command.get("save_path"))
        self._save_game_save_path_field.set_optional_value(command.get("save_path"))
        self._set_optional_bool_combo_value(
            self._set_simulation_paused_field,
            command.get("paused"),
        )
        try:
            self._adjust_output_scale_delta_spin.setValue(int(command.get("delta", 1)))
        except (TypeError, ValueError):
            self._adjust_output_scale_delta_spin.setValue(1)

        self._open_entity_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._open_entity_dialogue_id_field.set_optional_value(command.get("dialogue_id"))
        self._set_optional_bool_combo_value(
            self._open_entity_allow_cancel_field,
            command.get("allow_cancel"),
        )
        self._open_entity_ui_preset_field.set_optional_value(command.get("ui_preset"))
        self._open_entity_actor_id_field.set_optional_value(command.get("actor_id"))
        self._open_entity_caller_id_field.set_optional_value(command.get("caller_id"))
        self._open_entity_entity_refs_field.set_refs(command.get("entity_refs"))

        self._set_grid_entity_id_edit.setText(str(command.get("entity_id", "")))
        try:
            self._set_grid_x_spin.setValue(int(command.get("x", 0)))
        except (TypeError, ValueError):
            self._set_grid_x_spin.setValue(0)
        try:
            self._set_grid_y_spin.setValue(int(command.get("y", 0)))
        except (TypeError, ValueError):
            self._set_grid_y_spin.setValue(0)
        self._set_optional_choice_combo_value(
            self._set_grid_mode_field,
            command.get("mode"),
        )
        self._set_optional_bool_combo_value(
            self._set_grid_persistent_field,
            command.get("persistent"),
        )

        self._set_world_entity_id_edit.setText(str(command.get("entity_id", "")))
        try:
            self._set_world_x_spin.setValue(float(command.get("x", 0.0)))
        except (TypeError, ValueError):
            self._set_world_x_spin.setValue(0.0)
        try:
            self._set_world_y_spin.setValue(float(command.get("y", 0.0)))
        except (TypeError, ValueError):
            self._set_world_y_spin.setValue(0.0)
        self._set_optional_choice_combo_value(
            self._set_world_mode_field,
            command.get("mode"),
        )
        self._set_optional_bool_combo_value(
            self._set_world_persistent_field,
            command.get("persistent"),
        )

        self._set_screen_entity_id_edit.setText(str(command.get("entity_id", "")))
        try:
            self._set_screen_x_spin.setValue(float(command.get("x", 0.0)))
        except (TypeError, ValueError):
            self._set_screen_x_spin.setValue(0.0)
        try:
            self._set_screen_y_spin.setValue(float(command.get("y", 0.0)))
        except (TypeError, ValueError):
            self._set_screen_y_spin.setValue(0.0)
        self._set_optional_choice_combo_value(
            self._set_screen_mode_field,
            command.get("mode"),
        )
        self._set_optional_bool_combo_value(
            self._set_screen_persistent_field,
            command.get("persistent"),
        )

        self._move_world_entity_id_edit.setText(str(command.get("entity_id", "")))
        try:
            self._move_world_x_spin.setValue(float(command.get("x", 0.0)))
        except (TypeError, ValueError):
            self._move_world_x_spin.setValue(0.0)
        try:
            self._move_world_y_spin.setValue(float(command.get("y", 0.0)))
        except (TypeError, ValueError):
            self._move_world_y_spin.setValue(0.0)
        self._set_optional_choice_combo_value(
            self._move_world_mode_field,
            command.get("mode"),
        )
        self._move_world_duration_field.set_optional_value(command.get("duration"))
        self._move_world_frames_needed_field.set_optional_value(
            command.get("frames_needed")
        )
        self._move_world_speed_field.set_optional_value(
            command.get("speed_px_per_second")
        )
        self._set_optional_bool_combo_value(
            self._move_world_wait_field,
            command.get("wait"),
        )
        self._set_optional_bool_combo_value(
            self._move_world_persistent_field,
            command.get("persistent"),
        )

        self._move_screen_entity_id_edit.setText(str(command.get("entity_id", "")))
        try:
            self._move_screen_x_spin.setValue(float(command.get("x", 0.0)))
        except (TypeError, ValueError):
            self._move_screen_x_spin.setValue(0.0)
        try:
            self._move_screen_y_spin.setValue(float(command.get("y", 0.0)))
        except (TypeError, ValueError):
            self._move_screen_y_spin.setValue(0.0)
        self._set_optional_choice_combo_value(
            self._move_screen_mode_field,
            command.get("mode"),
        )
        self._move_screen_duration_field.set_optional_value(command.get("duration"))
        self._move_screen_frames_needed_field.set_optional_value(
            command.get("frames_needed")
        )
        self._move_screen_speed_field.set_optional_value(
            command.get("speed_px_per_second")
        )
        self._set_optional_bool_combo_value(
            self._move_screen_wait_field,
            command.get("wait"),
        )
        self._set_optional_bool_combo_value(
            self._move_screen_persistent_field,
            command.get("persistent"),
        )

        self._push_facing_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_optional_choice_combo_value(
            self._push_facing_direction_field,
            command.get("direction"),
        )
        self._push_facing_push_strength_field.set_optional_value(
            command.get("push_strength")
        )
        self._push_facing_duration_field.set_optional_value(command.get("duration"))
        self._push_facing_frames_needed_field.set_optional_value(
            command.get("frames_needed")
        )
        self._push_facing_speed_field.set_optional_value(
            command.get("speed_px_per_second")
        )
        self._set_optional_bool_combo_value(
            self._push_facing_wait_field,
            command.get("wait"),
        )
        self._set_optional_bool_combo_value(
            self._push_facing_persistent_field,
            command.get("persistent"),
        )

        self._wait_for_move_entity_id_edit.setText(str(command.get("entity_id", "")))

        self._step_in_direction_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_optional_choice_combo_value(
            self._step_in_direction_direction_field,
            command.get("direction"),
        )
        self._step_in_direction_push_strength_field.set_optional_value(
            command.get("push_strength")
        )
        self._step_in_direction_frames_needed_field.set_optional_value(
            command.get("frames_needed")
        )
        self._set_optional_bool_combo_value(
            self._step_in_direction_wait_field,
            command.get("wait"),
        )
        self._set_optional_bool_combo_value(
            self._step_in_direction_persistent_field,
            command.get("persistent"),
        )

        self._set_camera_follow_entity_id_edit.setText(str(command.get("entity_id", "")))
        try:
            self._set_camera_follow_entity_offset_x_spin.setValue(
                float(command.get("offset_x", 0.0))
            )
        except (TypeError, ValueError):
            self._set_camera_follow_entity_offset_x_spin.setValue(0.0)
        try:
            self._set_camera_follow_entity_offset_y_spin.setValue(
                float(command.get("offset_y", 0.0))
            )
        except (TypeError, ValueError):
            self._set_camera_follow_entity_offset_y_spin.setValue(0.0)
        self._set_camera_follow_input_action_edit.setText(str(command.get("action", "")))
        try:
            self._set_camera_follow_input_offset_x_spin.setValue(
                float(command.get("offset_x", 0.0))
            )
        except (TypeError, ValueError):
            self._set_camera_follow_input_offset_x_spin.setValue(0.0)
        try:
            self._set_camera_follow_input_offset_y_spin.setValue(
                float(command.get("offset_y", 0.0))
            )
        except (TypeError, ValueError):
            self._set_camera_follow_input_offset_y_spin.setValue(0.0)
        self._set_camera_policy_follow_field.set_patch_state(
            "set"
            if isinstance(command.get("follow"), dict)
            else ("clear" if "follow" in command else "omit"),
            command.get("follow"),
        )
        self._set_camera_policy_bounds_field.set_patch_state(
            "set"
            if isinstance(command.get("bounds"), dict)
            else ("clear" if "bounds" in command else "omit"),
            command.get("bounds"),
        )
        self._set_camera_policy_deadzone_field.set_patch_state(
            "set"
            if isinstance(command.get("deadzone"), dict)
            else ("clear" if "deadzone" in command else "omit"),
            command.get("deadzone"),
        )
        self._set_camera_bounds_editor.set_rect(command)
        self._set_camera_deadzone_editor.set_rect(command)

        try:
            self._move_camera_x_spin.setValue(float(command.get("x", 0.0)))
        except (TypeError, ValueError):
            self._move_camera_x_spin.setValue(0.0)
        try:
            self._move_camera_y_spin.setValue(float(command.get("y", 0.0)))
        except (TypeError, ValueError):
            self._move_camera_y_spin.setValue(0.0)
        self._set_optional_choice_combo_value(
            self._move_camera_space_field,
            command.get("space"),
        )
        self._set_optional_choice_combo_value(
            self._move_camera_mode_field,
            command.get("mode"),
        )
        self._move_camera_duration_field.set_optional_value(command.get("duration"))
        self._move_camera_frames_needed_field.set_optional_value(
            command.get("frames_needed")
        )
        self._move_camera_speed_field.set_optional_value(
            command.get("speed_px_per_second")
        )

        try:
            self._teleport_camera_x_spin.setValue(float(command.get("x", 0.0)))
        except (TypeError, ValueError):
            self._teleport_camera_x_spin.setValue(0.0)
        try:
            self._teleport_camera_y_spin.setValue(float(command.get("y", 0.0)))
        except (TypeError, ValueError):
            self._teleport_camera_y_spin.setValue(0.0)
        self._set_optional_choice_combo_value(
            self._teleport_camera_space_field,
            command.get("space"),
        )
        self._set_optional_choice_combo_value(
            self._teleport_camera_mode_field,
            command.get("mode"),
        )

        self._play_audio_path_edit.setText(str(command.get("path", "")))
        self._play_audio_volume_field.set_optional_value(command.get("volume"))

        try:
            self._set_sound_volume_spin.setValue(max(0.0, float(command.get("volume", 1.0))))
        except (TypeError, ValueError):
            self._set_sound_volume_spin.setValue(1.0)

        self._play_music_path_edit.setText(str(command.get("path", "")))
        self._set_optional_bool_combo_value(
            self._play_music_loop_field,
            command.get("loop"),
        )
        self._play_music_volume_field.set_optional_value(command.get("volume"))
        self._set_optional_bool_combo_value(
            self._play_music_restart_if_same_field,
            command.get("restart_if_same"),
        )

        self._stop_music_fade_seconds_field.set_optional_value(
            command.get("fade_seconds")
        )

        try:
            self._set_music_volume_spin.setValue(max(0.0, float(command.get("volume", 1.0))))
        except (TypeError, ValueError):
            self._set_music_volume_spin.setValue(1.0)

        self._show_screen_image_element_id_edit.setText(
            str(command.get("element_id", ""))
        )
        self._show_screen_image_path_edit.setText(str(command.get("path", "")))
        try:
            self._show_screen_image_x_spin.setValue(float(command.get("x", 0.0)))
        except (TypeError, ValueError):
            self._show_screen_image_x_spin.setValue(0.0)
        try:
            self._show_screen_image_y_spin.setValue(float(command.get("y", 0.0)))
        except (TypeError, ValueError):
            self._show_screen_image_y_spin.setValue(0.0)
        self._show_screen_image_frame_width_field.set_optional_value(
            command.get("frame_width")
        )
        self._show_screen_image_frame_height_field.set_optional_value(
            command.get("frame_height")
        )
        self._show_screen_image_frame_field.set_optional_value(command.get("frame"))
        self._show_screen_image_layer_field.set_optional_value(command.get("layer"))
        self._set_optional_choice_combo_value(
            self._show_screen_image_anchor_field,
            command.get("anchor"),
        )
        self._set_optional_bool_combo_value(
            self._show_screen_image_flip_x_field,
            command.get("flip_x"),
        )
        self._show_screen_image_tint_field.set_optional_value(
            _rgb_to_text(command.get("tint"))
        )
        self._set_optional_bool_combo_value(
            self._show_screen_image_visible_field,
            command.get("visible"),
        )

        self._show_screen_text_element_id_edit.setText(
            str(command.get("element_id", ""))
        )
        self._show_screen_text_text_edit.setText(str(command.get("text", "")))
        try:
            self._show_screen_text_x_spin.setValue(float(command.get("x", 0.0)))
        except (TypeError, ValueError):
            self._show_screen_text_x_spin.setValue(0.0)
        try:
            self._show_screen_text_y_spin.setValue(float(command.get("y", 0.0)))
        except (TypeError, ValueError):
            self._show_screen_text_y_spin.setValue(0.0)
        self._show_screen_text_layer_field.set_optional_value(command.get("layer"))
        self._set_optional_choice_combo_value(
            self._show_screen_text_anchor_field,
            command.get("anchor"),
        )
        self._show_screen_text_color_field.set_optional_value(
            _rgb_to_text(command.get("color"))
        )
        self._show_screen_text_font_id_field.set_optional_value(command.get("font_id"))
        self._show_screen_text_max_width_field.set_optional_value(
            command.get("max_width")
        )
        self._set_optional_bool_combo_value(
            self._show_screen_text_visible_field,
            command.get("visible"),
        )

        self._set_screen_text_element_id_edit.setText(
            str(command.get("element_id", ""))
        )
        self._set_screen_text_text_edit.setText(str(command.get("text", "")))

        self._remove_screen_element_id_edit.setText(
            str(command.get("element_id", ""))
        )

        self._clear_screen_elements_layer_field.set_optional_value(command.get("layer"))

        self._play_screen_animation_element_id_edit.setText(
            str(command.get("element_id", ""))
        )
        self._play_screen_animation_frame_sequence_edit.setText(
            _int_list_to_text(command.get("frame_sequence"))
        )
        self._play_screen_animation_ticks_per_frame_field.set_optional_value(
            command.get("ticks_per_frame")
        )
        self._set_optional_bool_combo_value(
            self._play_screen_animation_hold_last_frame_field,
            command.get("hold_last_frame"),
        )
        self._set_optional_bool_combo_value(
            self._play_screen_animation_wait_field,
            command.get("wait"),
        )

        self._wait_for_screen_animation_element_id_edit.setText(
            str(command.get("element_id", ""))
        )

        self._play_animation_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._play_animation_visual_id_field.set_optional_value(command.get("visual_id"))
        self._play_animation_name_edit.setText(str(command.get("animation", "")))
        self._play_animation_frame_count_field.set_optional_value(
            command.get("frame_count")
        )
        self._play_animation_duration_ticks_field.set_optional_value(
            command.get("duration_ticks")
        )
        self._set_optional_bool_combo_value(
            self._play_animation_wait_field,
            command.get("wait"),
        )

        self._wait_for_animation_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._wait_for_animation_visual_id_field.set_optional_value(
            command.get("visual_id")
        )

        self._stop_animation_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._stop_animation_visual_id_field.set_optional_value(command.get("visual_id"))
        self._set_optional_bool_combo_value(
            self._stop_animation_reset_field,
            command.get("reset_to_default"),
        )

        self._add_inventory_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._add_inventory_item_id_edit.setText(str(command.get("item_id", "")))
        self._add_inventory_quantity_field.set_optional_value(command.get("quantity"))
        self._set_optional_choice_combo_value(
            self._add_inventory_quantity_mode_field,
            command.get("quantity_mode"),
        )
        self._add_inventory_result_var_field.set_optional_value(
            command.get("result_var_name")
        )
        self._set_optional_bool_combo_value(
            self._add_inventory_persistent_field,
            command.get("persistent"),
        )

        self._remove_inventory_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._remove_inventory_item_id_edit.setText(str(command.get("item_id", "")))
        self._remove_inventory_quantity_field.set_optional_value(command.get("quantity"))
        self._set_optional_choice_combo_value(
            self._remove_inventory_quantity_mode_field,
            command.get("quantity_mode"),
        )
        self._remove_inventory_result_var_field.set_optional_value(
            command.get("result_var_name")
        )
        self._set_optional_bool_combo_value(
            self._remove_inventory_persistent_field,
            command.get("persistent"),
        )

        self._use_inventory_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._use_inventory_item_id_edit.setText(str(command.get("item_id", "")))
        self._use_inventory_quantity_field.set_optional_value(command.get("quantity"))
        self._use_inventory_result_var_field.set_optional_value(
            command.get("result_var_name")
        )
        self._set_optional_bool_combo_value(
            self._use_inventory_persistent_field,
            command.get("persistent"),
        )

        self._set_inventory_max_entity_id_edit.setText(str(command.get("entity_id", "")))
        try:
            self._set_inventory_max_stacks_spin.setValue(
                max(0, int(command.get("max_stacks", 0)))
            )
        except (TypeError, ValueError):
            self._set_inventory_max_stacks_spin.setValue(0)
        self._set_optional_bool_combo_value(
            self._set_inventory_max_persistent_field,
            command.get("persistent"),
        )

        self._open_inventory_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._open_inventory_ui_preset_field.set_optional_value(command.get("ui_preset"))
        self._set_optional_bool_combo_value(
            self._open_inventory_wait_field,
            command.get("wait"),
        )

        self._set_current_area_var_name_edit.setText(str(command.get("name", "")))
        if "value" in command:
            self._set_current_area_var_value_edit.setPlainText(
                json.dumps(command.get("value"), indent=2, ensure_ascii=False)
            )
        else:
            self._set_current_area_var_value_edit.clear()
        self._set_optional_bool_combo_value(
            self._set_current_area_var_persistent_field,
            command.get("persistent"),
        )
        self._set_optional_choice_combo_value(
            self._set_current_area_var_value_mode_field,
            command.get("value_mode"),
        )

        self._add_current_area_var_name_edit.setText(str(command.get("name", "")))
        self._add_current_area_var_amount_field.set_optional_value(command.get("amount"))
        self._set_optional_bool_combo_value(
            self._add_current_area_var_persistent_field,
            command.get("persistent"),
        )

        self._add_entity_var_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._add_entity_var_name_edit.setText(str(command.get("name", "")))
        self._add_entity_var_amount_field.set_optional_value(command.get("amount"))
        self._set_optional_bool_combo_value(
            self._add_entity_var_persistent_field,
            command.get("persistent"),
        )

        self._toggle_current_area_var_name_edit.setText(str(command.get("name", "")))
        self._set_optional_bool_combo_value(
            self._toggle_current_area_var_persistent_field,
            command.get("persistent"),
        )

        self._toggle_entity_var_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._toggle_entity_var_name_edit.setText(str(command.get("name", "")))
        self._set_optional_bool_combo_value(
            self._toggle_entity_var_persistent_field,
            command.get("persistent"),
        )

        self._set_current_area_var_length_name_edit.setText(str(command.get("name", "")))
        if "value" in command:
            self._set_current_area_var_length_value_edit.setPlainText(
                json.dumps(command.get("value"), indent=2, ensure_ascii=False)
            )
        else:
            self._set_current_area_var_length_value_edit.clear()
        self._set_optional_bool_combo_value(
            self._set_current_area_var_length_persistent_field,
            command.get("persistent"),
        )

        self._set_entity_var_length_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_entity_var_length_name_edit.setText(str(command.get("name", "")))
        if "value" in command:
            self._set_entity_var_length_value_edit.setPlainText(
                json.dumps(command.get("value"), indent=2, ensure_ascii=False)
            )
        else:
            self._set_entity_var_length_value_edit.clear()
        self._set_optional_bool_combo_value(
            self._set_entity_var_length_persistent_field,
            command.get("persistent"),
        )

        self._append_current_area_var_name_edit.setText(str(command.get("name", "")))
        if "value" in command:
            self._append_current_area_var_value_edit.setPlainText(
                json.dumps(command.get("value"), indent=2, ensure_ascii=False)
            )
        else:
            self._append_current_area_var_value_edit.clear()
        self._set_optional_bool_combo_value(
            self._append_current_area_var_persistent_field,
            command.get("persistent"),
        )
        self._set_optional_choice_combo_value(
            self._append_current_area_var_value_mode_field,
            command.get("value_mode"),
        )

        self._append_entity_var_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._append_entity_var_name_edit.setText(str(command.get("name", "")))
        if "value" in command:
            self._append_entity_var_value_edit.setPlainText(
                json.dumps(command.get("value"), indent=2, ensure_ascii=False)
            )
        else:
            self._append_entity_var_value_edit.clear()
        self._set_optional_bool_combo_value(
            self._append_entity_var_persistent_field,
            command.get("persistent"),
        )
        self._set_optional_choice_combo_value(
            self._append_entity_var_value_mode_field,
            command.get("value_mode"),
        )

        self._pop_current_area_var_name_edit.setText(str(command.get("name", "")))
        self._pop_current_area_var_store_var_field.set_optional_value(command.get("store_var"))
        if "default" in command:
            self._pop_current_area_var_default_edit.setPlainText(
                json.dumps(command.get("default"), indent=2, ensure_ascii=False)
            )
        else:
            self._pop_current_area_var_default_edit.clear()
        self._set_optional_bool_combo_value(
            self._pop_current_area_var_persistent_field,
            command.get("persistent"),
        )

        self._pop_entity_var_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._pop_entity_var_name_edit.setText(str(command.get("name", "")))
        self._pop_entity_var_store_var_field.set_optional_value(command.get("store_var"))
        if "default" in command:
            self._pop_entity_var_default_edit.setPlainText(
                json.dumps(command.get("default"), indent=2, ensure_ascii=False)
            )
        else:
            self._pop_entity_var_default_edit.clear()
        self._set_optional_bool_combo_value(
            self._pop_entity_var_persistent_field,
            command.get("persistent"),
        )

        self._set_entity_field_entity_id_edit.setText(str(command.get("entity_id", "")))
        field_name = command.get("field_name")
        self._set_editable_combo_value(self._set_entity_field_name_combo, field_name)
        if "value" in command:
            self._set_entity_field_value_edit.setPlainText(
                json.dumps(command.get("value"), indent=2, ensure_ascii=False)
            )
        else:
            self._set_entity_field_value_edit.clear()
        self._set_optional_bool_combo_value(
            self._set_entity_field_persistent_field,
            command.get("persistent"),
        )

        self._set_entity_fields_entity_id_edit.setText(str(command.get("entity_id", "")))
        if "set" in command:
            self._set_entity_fields_payload_edit.setPlainText(
                json.dumps(command.get("set"), indent=2, ensure_ascii=False)
            )
        else:
            self._set_entity_fields_payload_edit.clear()
        self._set_optional_bool_combo_value(
            self._set_entity_fields_persistent_field,
            command.get("persistent"),
        )

        entity_payload = command.get("entity")
        if isinstance(entity_payload, dict):
            self._set_optional_choice_combo_value(self._spawn_entity_mode_combo, "full")
            self._spawn_entity_full_edit.setPlainText(
                json.dumps(entity_payload, indent=2, ensure_ascii=False)
            )
        else:
            self._set_optional_choice_combo_value(self._spawn_entity_mode_combo, "partial")
            self._spawn_entity_full_edit.clear()
        self._spawn_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._spawn_entity_template_field.set_optional_value(command.get("template"))
        self._spawn_entity_kind_field.set_optional_value(command.get("kind"))
        try:
            self._spawn_entity_x_spin.setValue(int(command.get("x", 0)))
        except (TypeError, ValueError):
            self._spawn_entity_x_spin.setValue(0)
        try:
            self._spawn_entity_y_spin.setValue(int(command.get("y", 0)))
        except (TypeError, ValueError):
            self._spawn_entity_y_spin.setValue(0)
        if "parameters" in command:
            self._spawn_entity_parameters_edit.setPlainText(
                json.dumps(command.get("parameters"), indent=2, ensure_ascii=False)
            )
        else:
            self._spawn_entity_parameters_edit.clear()
        self._set_optional_bool_combo_value(
            self._spawn_entity_present_field,
            command.get("present"),
        )
        self._set_optional_bool_combo_value(
            self._spawn_entity_persistent_field,
            command.get("persistent"),
        )
        self._sync_spawn_entity_mode_visibility()

        self._set_area_var_area_id_edit.setText(str(command.get("area_id", "")))
        self._set_area_var_name_edit.setText(str(command.get("name", "")))
        if "value" in command:
            self._set_area_var_value_edit.setPlainText(
                json.dumps(command.get("value"), indent=2, ensure_ascii=False)
            )
        else:
            self._set_area_var_value_edit.clear()

        self._set_area_entity_var_area_id_edit.setText(str(command.get("area_id", "")))
        self._set_area_entity_var_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_area_entity_var_name_edit.setText(str(command.get("name", "")))
        if "value" in command:
            self._set_area_entity_var_value_edit.setPlainText(
                json.dumps(command.get("value"), indent=2, ensure_ascii=False)
            )
        else:
            self._set_area_entity_var_value_edit.clear()

        self._set_area_entity_field_area_id_edit.setText(str(command.get("area_id", "")))
        self._set_area_entity_field_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_editable_combo_value(
            self._set_area_entity_field_name_combo,
            command.get("field_name"),
        )
        if "value" in command:
            self._set_area_entity_field_value_edit.setPlainText(
                json.dumps(command.get("value"), indent=2, ensure_ascii=False)
            )
        else:
            self._set_area_entity_field_value_edit.clear()

        self._reset_transient_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._reset_transient_entity_ids_field.set_optional_value(
            ", ".join(command.get("entity_ids", []))
            if isinstance(command.get("entity_ids"), list)
            else command.get("entity_ids")
        )
        self._reset_transient_include_tags_field.set_optional_value(
            ", ".join(command.get("include_tags", []))
            if isinstance(command.get("include_tags"), list)
            else command.get("include_tags")
        )
        self._reset_transient_exclude_tags_field.set_optional_value(
            ", ".join(command.get("exclude_tags", []))
            if isinstance(command.get("exclude_tags"), list)
            else command.get("exclude_tags")
        )
        self._set_optional_choice_combo_value(
            self._reset_transient_apply_field,
            command.get("apply"),
        )

        self._reset_persistent_include_tags_field.set_optional_value(
            ", ".join(command.get("include_tags", []))
            if isinstance(command.get("include_tags"), list)
            else command.get("include_tags")
        )
        self._reset_persistent_exclude_tags_field.set_optional_value(
            ", ".join(command.get("exclude_tags", []))
            if isinstance(command.get("exclude_tags"), list)
            else command.get("exclude_tags")
        )
        self._set_optional_choice_combo_value(
            self._reset_persistent_apply_field,
            command.get("apply"),
        )

        self._set_var_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_var_name_edit.setText(str(command.get("name", "")))
        if "value" in command:
            self._set_var_value_edit.setPlainText(
                json.dumps(command.get("value"), indent=2, ensure_ascii=False)
            )
        else:
            self._set_var_value_edit.clear()
        self._set_optional_bool_combo_value(
            self._set_var_persistent_field,
            command.get("persistent"),
        )
        self._set_optional_choice_combo_value(
            self._set_var_value_mode_field,
            command.get("value_mode"),
        )

        self._set_visible_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_optional_bool_combo_value(
            self._set_visible_value_field,
            command.get("visible"),
        )
        self._set_optional_bool_combo_value(
            self._set_visible_persistent_field,
            command.get("persistent"),
        )

        self._set_present_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_optional_bool_combo_value(
            self._set_present_value_field,
            command.get("present"),
        )
        self._set_optional_bool_combo_value(
            self._set_present_persistent_field,
            command.get("persistent"),
        )

        self._set_color_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_color_value_edit.setText(_rgb_to_text(command.get("color")))
        self._set_optional_bool_combo_value(
            self._set_color_persistent_field,
            command.get("persistent"),
        )

        self._destroy_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_optional_bool_combo_value(
            self._destroy_entity_persistent_field,
            command.get("persistent"),
        )

        self._set_visual_frame_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_visual_frame_visual_id_field.set_optional_value(
            command.get("visual_id")
        )
        try:
            self._set_visual_frame_spin.setValue(max(0, int(command.get("frame", 0))))
        except (TypeError, ValueError):
            self._set_visual_frame_spin.setValue(0)

        self._set_visual_flip_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_visual_flip_visual_id_field.set_optional_value(
            command.get("visual_id")
        )
        self._set_optional_bool_combo_value(
            self._set_visual_flip_x_value_field,
            command.get("flip_x"),
        )

        self._set_entity_command_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_entity_command_id_edit.setText(str(command.get("command_id", "")))
        self._set_optional_bool_combo_value(
            self._set_entity_command_enabled_field,
            command.get("enabled"),
        )
        self._set_optional_bool_combo_value(
            self._set_entity_command_persistent_field,
            command.get("persistent"),
        )

        self._set_entity_commands_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_optional_bool_combo_value(
            self._set_entity_commands_enabled_field,
            command.get("enabled"),
        )
        self._set_optional_bool_combo_value(
            self._set_entity_commands_persistent_field,
            command.get("persistent"),
        )

        self._set_input_target_action_edit.setText(str(command.get("action", "")))
        self._set_input_target_entity_id_field.set_optional_value(
            command.get("entity_id")
        )

        self._route_inputs_entity_id_field.set_optional_value(command.get("entity_id"))
        self._route_inputs_actions_field.set_optional_value(
            _string_list_to_text(command.get("actions"))
        )

        self._push_input_routes_actions_field.set_optional_value(
            _string_list_to_text(command.get("actions"))
        )

        try:
            self._wait_frames_spin.setValue(max(0, int(command.get("frames", 1))))
        except (TypeError, ValueError):
            self._wait_frames_spin.setValue(1)

        try:
            self._wait_seconds_spin.setValue(max(0.0, float(command.get("seconds", 1.0))))
        except (TypeError, ValueError):
            self._wait_seconds_spin.setValue(1.0)

        self._interact_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_optional_choice_combo_value(
            self._interact_direction_field,
            command.get("direction"),
        )

        self._set_active_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._set_active_dialogue_id_edit.setText(str(command.get("dialogue_id", "")))
        self._set_optional_bool_combo_value(
            self._set_active_persistent_field,
            command.get("persistent"),
        )

        self._step_entity_id_edit.setText(str(command.get("entity_id", "")))
        self._step_delta_field.set_optional_value(command.get("delta"))
        self._set_optional_bool_combo_value(
            self._step_wrap_field,
            command.get("wrap"),
        )
        self._set_optional_bool_combo_value(
            self._step_persistent_field,
            command.get("persistent"),
        )

        self._set_active_by_order_entity_id_edit.setText(str(command.get("entity_id", "")))
        order = command.get("order")
        try:
            self._set_active_by_order_spin.setValue(max(1, int(order)))
        except (TypeError, ValueError):
            self._set_active_by_order_spin.setValue(1)
        self._set_optional_bool_combo_value(
            self._set_active_by_order_wrap_field,
            command.get("wrap"),
        )
        self._set_optional_bool_combo_value(
            self._set_active_by_order_persistent_field,
            command.get("persistent"),
        )

        if command_type != "open_dialogue_session":
            self._sync_open_dialogue_advanced_state(expanded=False)
        if command_type != "run_project_command":
            self._sync_run_project_advanced_state(expanded=False)
        if command_type != "run_entity_command":
            self._sync_run_entity_advanced_state(expanded=False)
        if command_type != "change_area":
            self._sync_change_area_advanced_state(expanded=False)
        if command_type != "open_entity_dialogue":
            self._sync_open_entity_advanced_state(expanded=False)

    def _entity_picker_request(self, *, parameter_name: str, current_value: str) -> EntityReferencePickerRequest:
        return EntityReferencePickerRequest(
            parameter_name=parameter_name,
            current_value=current_value,
            parameter_spec={"type": "entity_id"},
            current_area_id=self._current_area_id,
            entity_id=self._current_entity_id,
            entity_template_id=None,
            parameter_values=None,
        )

    def _area_picker_request(
        self,
        *,
        parameter_name: str,
        current_value: str,
    ) -> EntityReferencePickerRequest:
        return EntityReferencePickerRequest(
            parameter_name=parameter_name,
            current_value=current_value,
            parameter_spec={"type": "area_id"},
            current_area_id=self._current_area_id,
            entity_id=self._current_entity_id,
            entity_template_id=None,
            parameter_values=None,
        )

    def _entity_dialogue_picker_request(
        self,
        *,
        current_value: str,
        entity_id_value: str,
    ) -> EntityReferencePickerRequest:
        return EntityReferencePickerRequest(
            parameter_name="dialogue_id",
            current_value=current_value,
            parameter_spec={
                "type": "entity_dialogue_id",
                "entity_parameter": "entity_id",
            },
            current_area_id=self._current_area_id,
            entity_id=self._current_entity_id,
            entity_template_id=None,
            parameter_values={
                "entity_id": entity_id_value,
                "dialogue_id": current_value,
            },
            entity_dialogue_names_override=(
                self._current_entity_dialogue_names or None
            ),
        )

    def _entity_command_picker_request(
        self,
        *,
        current_value: str,
        entity_id_value: str,
    ) -> EntityReferencePickerRequest:
        return EntityReferencePickerRequest(
            parameter_name="command_id",
            current_value=current_value,
            parameter_spec={
                "type": "entity_command_id",
                "entity_parameter": "entity_id",
            },
            current_area_id=self._current_area_id,
            entity_id=self._current_entity_id,
            entity_template_id=None,
            parameter_values={
                "entity_id": entity_id_value,
                "command_id": current_value,
            },
            entity_command_names_override=(
                self._current_entity_command_names or None
            ),
        )

    def _pick_entity_into_edit(self, edit: QLineEdit, *, parameter_name: str) -> None:
        selected = call_reference_picker_callback(
            self._entity_picker,
            edit.text().strip(),
            request=self._entity_picker_request(
                parameter_name=parameter_name,
                current_value=edit.text().strip(),
            ),
        )
        if selected:
            edit.setText(selected)

    def _pick_area_into_edit(self, edit: QLineEdit, *, parameter_name: str) -> None:
        selected = call_reference_picker_callback(
            self._area_picker,
            edit.text().strip(),
            request=self._area_picker_request(
                parameter_name=parameter_name,
                current_value=edit.text().strip(),
            ),
        )
        if selected:
            edit.setText(selected)

    def _browse_asset_into_edit(self, edit: QLineEdit) -> None:
        selected = call_reference_picker_callback(
            self._asset_picker,
            edit.text().strip(),
        )
        if selected:
            edit.setText(selected)

    def _pick_item_into_edit(self, edit: QLineEdit) -> None:
        selected = call_reference_picker_callback(
            self._item_picker,
            edit.text().strip(),
        )
        if selected:
            edit.setText(selected)

    def _pick_entity_into_optional_field(
        self,
        field: _OptionalTextField,
        *,
        parameter_name: str,
    ) -> None:
        current_value = field.optional_value() or field.edit.text().strip()
        selected = call_reference_picker_callback(
            self._entity_picker,
            current_value,
            request=self._entity_picker_request(
                parameter_name=parameter_name,
                current_value=current_value,
            ),
        )
        if selected:
            field.set_optional_value(selected)

    def _pick_entity_into_ref_value_edit(
        self,
        edit: QLineEdit,
        ref_name: str,
    ) -> None:
        current_value = edit.text().strip()
        selected = call_reference_picker_callback(
            self._entity_picker,
            current_value,
            request=self._entity_picker_request(
                parameter_name=f"entity_refs.{ref_name or 'value'}",
                current_value=current_value,
            ),
        )
        if selected:
            edit.setText(selected)

    def _show_entity_token_menu_for_edit(
        self,
        edit: QLineEdit,
        anchor: QWidget,
    ) -> None:
        menu = QMenu(self)
        for token, label in _COMMON_ENTITY_REFERENCE_TOKENS:
            action = menu.addAction(f"{label} ({token})")
            action.triggered.connect(
                lambda _checked=False, value=token: self._apply_entity_reference_token_to_edit(
                    edit,
                    value,
                )
            )
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    def _show_entity_token_menu_for_optional_field(
        self,
        field: _OptionalTextField,
        anchor: QWidget,
    ) -> None:
        menu = QMenu(self)
        for token, label in _COMMON_ENTITY_REFERENCE_TOKENS:
            action = menu.addAction(f"{label} ({token})")
            action.triggered.connect(
                lambda _checked=False, value=token: self._apply_entity_reference_token_to_optional_field(
                    field,
                    value,
                )
            )
        menu.exec(anchor.mapToGlobal(anchor.rect().bottomLeft()))

    @staticmethod
    def _apply_entity_reference_token_to_edit(
        edit: QLineEdit,
        token: str,
    ) -> None:
        edit.setText(str(token).strip())

    @staticmethod
    def _apply_entity_reference_token_to_optional_field(
        field: _OptionalTextField,
        token: str,
    ) -> None:
        field.set_optional_value(str(token).strip())

    def _sync_entity_picker_button_state(self) -> None:
        enabled = self._entity_picker is not None
        for button in (
            getattr(self, "_open_entity_entity_pick", None),
            getattr(self, "_set_grid_entity_pick", None),
            getattr(self, "_set_world_entity_pick", None),
            getattr(self, "_set_screen_entity_pick", None),
            getattr(self, "_move_world_entity_pick", None),
            getattr(self, "_move_screen_entity_pick", None),
            getattr(self, "_push_facing_entity_pick", None),
            getattr(self, "_wait_for_move_entity_pick", None),
            getattr(self, "_step_in_direction_entity_pick", None),
            getattr(self, "_run_entity_entity_pick", None),
            getattr(self, "_interact_entity_pick", None),
            getattr(self, "_set_var_entity_pick", None),
            getattr(self, "_set_visible_entity_pick", None),
            getattr(self, "_set_present_entity_pick", None),
            getattr(self, "_set_color_entity_pick", None),
            getattr(self, "_destroy_entity_pick", None),
            getattr(self, "_play_animation_entity_pick", None),
            getattr(self, "_wait_for_animation_entity_pick", None),
            getattr(self, "_stop_animation_entity_pick", None),
            getattr(self, "_add_inventory_entity_pick", None),
            getattr(self, "_remove_inventory_entity_pick", None),
            getattr(self, "_use_inventory_entity_pick", None),
            getattr(self, "_set_inventory_max_entity_pick", None),
            getattr(self, "_open_inventory_entity_pick", None),
            getattr(self, "_set_visual_frame_entity_pick", None),
            getattr(self, "_set_visual_flip_entity_pick", None),
            getattr(self, "_set_entity_command_entity_pick", None),
            getattr(self, "_set_entity_commands_entity_pick", None),
            getattr(self, "_set_entity_field_entity_pick", None),
            getattr(self, "_set_entity_fields_entity_pick", None),
            getattr(self, "_set_camera_follow_entity_pick", None),
            getattr(self, "_reset_transient_entity_pick", None),
            getattr(self, "_set_active_entity_pick", None),
            getattr(self, "_step_entity_pick", None),
            getattr(self, "_set_active_by_order_entity_pick", None),
        ):
            if button is not None:
                button.setEnabled(enabled)
        for field in (
            getattr(self, "_open_dialogue_entity_refs_field", None),
            getattr(self, "_run_project_entity_refs_field", None),
            getattr(self, "_run_entity_entity_refs_field", None),
            getattr(self, "_change_area_entity_refs_field", None),
            getattr(self, "_open_entity_entity_refs_field", None),
        ):
            if isinstance(field, _NamedEntityRefsField):
                field.set_picker_enabled(enabled)
        for field in (
            getattr(self, "_change_area_camera_follow_field", None),
            getattr(self, "_new_game_camera_follow_field", None),
            getattr(self, "_set_camera_policy_follow_field", None),
        ):
            if isinstance(field, _CameraFollowPatchField):
                field.set_picker_enabled(enabled)
            elif isinstance(field, _CameraFollowEditor):
                field.set_picker_enabled(enabled)

    def _sync_area_picker_button_state(self) -> None:
        enabled = self._area_picker is not None
        for button in (
            getattr(self, "_change_area_area_pick", None),
            getattr(self, "_new_game_area_pick", None),
            getattr(self, "_set_area_var_area_pick", None),
            getattr(self, "_set_area_entity_var_area_pick", None),
            getattr(self, "_set_area_entity_field_area_pick", None),
        ):
            if button is not None:
                button.setEnabled(enabled)

    def _sync_asset_picker_button_state(self) -> None:
        enabled = self._asset_picker is not None
        for button in (
            getattr(self, "_play_audio_browse", None),
            getattr(self, "_play_music_browse", None),
            getattr(self, "_show_screen_image_path_browse", None),
        ):
            if button is not None:
                button.setEnabled(enabled)

    def _sync_item_picker_button_state(self) -> None:
        enabled = self._item_picker is not None
        for button in (
            getattr(self, "_add_inventory_item_pick", None),
            getattr(self, "_remove_inventory_item_pick", None),
            getattr(self, "_use_inventory_item_pick", None),
        ):
            if button is not None:
                button.setEnabled(enabled)

    def _pick_entity_command_id_into_edit(
        self,
        edit: QLineEdit,
        *,
        entity_id_edit: QLineEdit,
    ) -> None:
        current_value = edit.text().strip()
        entity_id_value = entity_id_edit.text().strip()
        selected = call_reference_picker_callback(
            self._entity_command_picker,
            current_value,
            request=self._entity_command_picker_request(
                current_value=current_value,
                entity_id_value=entity_id_value,
            ),
        )
        if selected:
            edit.setText(selected)

    def _sync_entity_command_picker_button_state(self) -> None:
        picker_enabled = self._entity_command_picker is not None
        run_entity_enabled = picker_enabled and bool(
            self._run_entity_entity_id_edit.text().strip()
        )
        if getattr(self, "_run_entity_command_pick", None) is not None:
            self._run_entity_command_pick.setEnabled(run_entity_enabled)
        set_entity_command_enabled = picker_enabled and bool(
            self._set_entity_command_entity_id_edit.text().strip()
        )
        if getattr(self, "_set_entity_command_pick", None) is not None:
            self._set_entity_command_pick.setEnabled(set_entity_command_enabled)

    def _pick_dialogue_id_into_edit(
        self,
        edit: QLineEdit,
        *,
        entity_id_edit: QLineEdit,
    ) -> None:
        current_value = edit.text().strip()
        entity_id_value = entity_id_edit.text().strip()
        selected = call_reference_picker_callback(
            self._entity_dialogue_picker,
            current_value,
            request=self._entity_dialogue_picker_request(
                current_value=current_value,
                entity_id_value=entity_id_value,
            ),
        )
        if selected:
            edit.setText(selected)

    def _pick_dialogue_id_into_optional_field(
        self,
        field: _OptionalTextField,
        *,
        entity_id_edit: QLineEdit,
    ) -> None:
        current_value = field.optional_value() or field.edit.text().strip()
        entity_id_value = entity_id_edit.text().strip()
        selected = call_reference_picker_callback(
            self._entity_dialogue_picker,
            current_value,
            request=self._entity_dialogue_picker_request(
                current_value=current_value,
                entity_id_value=entity_id_value,
            ),
        )
        if selected:
            field.set_optional_value(selected)

    def _sync_entity_dialogue_picker_button_state(self) -> None:
        picker_enabled = self._entity_dialogue_picker is not None
        open_entity_enabled = picker_enabled and bool(
            self._open_entity_entity_id_edit.text().strip()
        )
        if self._open_entity_dialogue_id_field.button is not None:
            self._open_entity_dialogue_id_field.button.setEnabled(open_entity_enabled)
        set_active_enabled = picker_enabled and bool(
            self._set_active_entity_id_edit.text().strip()
        )
        if getattr(self, "_set_active_dialogue_pick", None) is not None:
            self._set_active_dialogue_pick.setEnabled(set_active_enabled)

    def _ensure_command_type_visible(self, command_type: str) -> None:
        if not command_type:
            return
        if self._command_type_combo.findText(command_type) >= 0:
            return
        self._command_type_combo.insertItem(0, command_type)

    def _sync_structured_page(self, command_type: str) -> None:
        page_by_type = {
            "open_dialogue_session": self._open_dialogue_page,
            "run_project_command": self._run_project_command_page,
            "run_entity_command": self._run_entity_command_page,
            "run_sequence": self._run_sequence_page,
            "spawn_flow": self._spawn_flow_page,
            "run_parallel": self._run_parallel_page,
            "run_commands_for_collection": self._run_commands_for_collection_page,
            "if": self._if_page,
            "change_area": self._change_area_page,
            "new_game": self._new_game_page,
            "load_game": self._load_game_page,
            "save_game": self._save_game_page,
            "quit_game": self._quit_game_page,
            "set_simulation_paused": self._set_simulation_paused_page,
            "toggle_simulation_paused": self._toggle_simulation_paused_page,
            "step_simulation_tick": self._step_simulation_tick_page,
            "adjust_output_scale": self._adjust_output_scale_page,
            "open_entity_dialogue": self._open_entity_dialogue_page,
            "set_entity_grid_position": self._set_entity_grid_position_page,
            "set_entity_world_position": self._set_entity_world_position_page,
            "set_entity_screen_position": self._set_entity_screen_position_page,
            "move_entity_world_position": self._move_entity_world_position_page,
            "move_entity_screen_position": self._move_entity_screen_position_page,
            "push_facing": self._push_facing_page,
            "wait_for_move": self._wait_for_move_page,
            "step_in_direction": self._step_in_direction_page,
            "set_camera_follow_entity": self._set_camera_follow_entity_page,
            "set_camera_follow_input_target": self._set_camera_follow_input_target_page,
            "clear_camera_follow": self._clear_camera_follow_page,
            "set_camera_policy": self._set_camera_policy_page,
            "push_camera_state": self._push_camera_state_page,
            "pop_camera_state": self._pop_camera_state_page,
            "set_camera_bounds": self._set_camera_bounds_page,
            "clear_camera_bounds": self._clear_camera_bounds_page,
            "set_camera_deadzone": self._set_camera_deadzone_page,
            "clear_camera_deadzone": self._clear_camera_deadzone_page,
            "move_camera": self._move_camera_page,
            "teleport_camera": self._teleport_camera_page,
            "play_audio": self._play_audio_page,
            "set_sound_volume": self._set_sound_volume_page,
            "play_music": self._play_music_page,
            "stop_music": self._stop_music_page,
            "pause_music": self._pause_music_page,
            "resume_music": self._resume_music_page,
            "set_music_volume": self._set_music_volume_page,
            "show_screen_image": self._show_screen_image_page,
            "show_screen_text": self._show_screen_text_page,
            "set_screen_text": self._set_screen_text_page,
            "remove_screen_element": self._remove_screen_element_page,
            "clear_screen_elements": self._clear_screen_elements_page,
            "play_screen_animation": self._play_screen_animation_page,
            "wait_for_screen_animation": self._wait_for_screen_animation_page,
            "play_animation": self._play_animation_page,
            "wait_for_animation": self._wait_for_animation_page,
            "stop_animation": self._stop_animation_page,
            "add_inventory_item": self._add_inventory_item_page,
            "remove_inventory_item": self._remove_inventory_item_page,
            "use_inventory_item": self._use_inventory_item_page,
            "set_inventory_max_stacks": self._set_inventory_max_stacks_page,
            "open_inventory_session": self._open_inventory_session_page,
            "close_inventory_session": self._close_inventory_session_page,
            "set_current_area_var": self._set_current_area_var_page,
            "add_current_area_var": self._add_current_area_var_page,
            "add_entity_var": self._add_entity_var_page,
            "toggle_current_area_var": self._toggle_current_area_var_page,
            "toggle_entity_var": self._toggle_entity_var_page,
            "set_current_area_var_length": self._set_current_area_var_length_page,
            "set_entity_var_length": self._set_entity_var_length_page,
            "append_current_area_var": self._append_current_area_var_page,
            "append_entity_var": self._append_entity_var_page,
            "pop_current_area_var": self._pop_current_area_var_page,
            "pop_entity_var": self._pop_entity_var_page,
            "set_entity_field": self._set_entity_field_page,
            "set_entity_fields": self._set_entity_fields_page,
            "spawn_entity": self._spawn_entity_page,
            "set_area_var": self._set_area_var_page,
            "set_area_entity_var": self._set_area_entity_var_page,
            "set_area_entity_field": self._set_area_entity_field_page,
            "reset_transient_state": self._reset_transient_state_page,
            "reset_persistent_state": self._reset_persistent_state_page,
            "set_entity_var": self._set_entity_var_page,
            "set_visible": self._set_visible_page,
            "set_present": self._set_present_page,
            "set_color": self._set_color_page,
            "destroy_entity": self._destroy_entity_page,
            "set_visual_frame": self._set_visual_frame_page,
            "set_visual_flip_x": self._set_visual_flip_x_page,
            "set_entity_command_enabled": self._set_entity_command_enabled_page,
            "set_entity_commands_enabled": self._set_entity_commands_enabled_page,
            "set_input_target": self._set_input_target_page,
            "route_inputs_to_entity": self._route_inputs_to_entity_page,
            "push_input_routes": self._push_input_routes_page,
            "pop_input_routes": self._pop_input_routes_page,
            "wait_frames": self._wait_frames_page,
            "wait_seconds": self._wait_seconds_page,
            "close_dialogue_session": self._close_dialogue_session_page,
            "interact_facing": self._interact_facing_page,
            "set_entity_active_dialogue": self._set_active_dialogue_page,
            "step_entity_active_dialogue": self._step_active_dialogue_page,
            "set_entity_active_dialogue_by_order": self._set_active_by_order_page,
        }
        self._command_stack.setCurrentWidget(
            page_by_type.get(command_type, self._generic_page)
        )

    def _sync_open_dialogue_source_visibility(self) -> None:
        source = self._dialogue_source_combo.currentText().strip()
        is_file = source == "Dialogue File"
        self._dialogue_path_edit.parentWidget().setVisible(is_file)
        self._inline_dialogue_summary.parentWidget().setVisible(not is_file)

    def _open_nested_command_list_dialog(
        self,
        title: str,
        commands: object,
        *,
        command_spec_id_label: str | None = None,
    ) -> list[dict[str, Any]] | None:
        dialog = CommandListDialog(
            self,
            area_picker=self._area_picker,
            asset_picker=self._asset_picker,
            entity_picker=self._entity_picker,
            entity_command_picker=self._entity_command_picker,
            entity_dialogue_picker=self._entity_dialogue_picker,
            item_picker=self._item_picker,
            dialogue_picker=self._dialogue_picker,
            command_picker=self._command_picker,
            command_spec_id_label=command_spec_id_label,
            current_entity_id=self._current_entity_id,
            current_area_id=self._current_area_id,
            current_entity_command_names=self._current_entity_command_names,
            current_entity_dialogue_names=self._current_entity_dialogue_names,
        )
        dialog.setWindowTitle(title)
        dialog.load_commands(commands)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.commands()

    @staticmethod
    def _flow_advanced_field_count(
        source_field: _OptionalTextField,
        refs_mode_field: QComboBox,
        entity_refs_field: _NamedEntityRefsField,
    ) -> int:
        count = 0
        if source_field.optional_value() is not None:
            count += 1
        if CommandEditorDialog._optional_choice_combo_value(refs_mode_field) is not None:
            count += 1
        count += entity_refs_field.ref_count()
        return count

    @staticmethod
    def _sync_flow_advanced_state(
        toggle: QToolButton,
        widget: QWidget,
        advanced_count: int,
        *,
        expanded: bool | None = None,
    ) -> None:
        label = "Advanced"
        if advanced_count > 0:
            label = f"Advanced ({advanced_count} set)"
        toggle.setText(label)
        if expanded is not None:
            blockers = [QSignalBlocker(toggle)]
            toggle.setChecked(expanded)
            del blockers
        expanded_state = toggle.isChecked()
        widget.setVisible(expanded_state)
        toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded_state else Qt.ArrowType.RightArrow
        )

    def _set_flow_context_fields(
        self,
        target: dict[str, Any],
        *,
        source_entity_id_field: _OptionalTextField,
        refs_mode_field: QComboBox,
        entity_refs_field: _NamedEntityRefsField,
        show_message: bool,
    ) -> bool:
        self._set_optional_text_field(
            target,
            "source_entity_id",
            source_entity_id_field,
        )
        refs_mode = self._optional_choice_combo_value(refs_mode_field)
        if isinstance(refs_mode, str) and refs_mode.strip():
            target["refs_mode"] = refs_mode.strip()
        else:
            target.pop("refs_mode", None)
        return self._set_entity_refs_field(
            target,
            "entity_refs",
            entity_refs_field,
            show_message=show_message,
        )

    def _on_edit_run_sequence_commands(self) -> None:
        updated = self._open_nested_command_list_dialog(
            "Edit Child Commands - run_sequence",
            self._run_sequence_commands_field.commands(),
        )
        if updated is None:
            return
        self._run_sequence_commands_field.set_commands(updated)

    def _on_edit_spawn_flow_commands(self) -> None:
        updated = self._open_nested_command_list_dialog(
            "Edit Child Commands - spawn_flow",
            self._spawn_flow_commands_field.commands(),
        )
        if updated is None:
            return
        self._spawn_flow_commands_field.set_commands(updated)

    def _on_edit_run_parallel_commands(self) -> None:
        updated = self._open_nested_command_list_dialog(
            "Edit Parallel Branches - run_parallel",
            self._run_parallel_commands_field.commands(),
            command_spec_id_label="branch_id",
        )
        if updated is None:
            return
        self._run_parallel_commands_field.set_commands(updated)
        self._refresh_run_parallel_child_id_choices()

    def _on_edit_run_commands_for_collection_commands(self) -> None:
        updated = self._open_nested_command_list_dialog(
            "Edit Child Commands - run_commands_for_collection",
            self._run_for_each_commands_field.commands(),
        )
        if updated is None:
            return
        self._run_for_each_commands_field.set_commands(updated)

    def _on_edit_if_then_commands(self) -> None:
        updated = self._open_nested_command_list_dialog(
            "Edit Then Commands - if",
            self._if_then_commands_field.commands(),
        )
        if updated is None:
            return
        self._if_then_commands_field.set_commands(updated)

    def _on_edit_if_else_commands(self) -> None:
        updated = self._open_nested_command_list_dialog(
            "Edit Else Commands - if",
            self._if_else_commands_field.commands(),
        )
        if updated is None:
            return
        self._if_else_commands_field.set_commands(updated)

    def _refresh_run_parallel_child_id_choices(self) -> None:
        current_text = self._run_parallel_child_id_combo.currentText().strip()
        branch_ids: list[str] = []
        for branch in self._run_parallel_commands_field.commands():
            branch_id = str(branch.get("id", "")).strip()
            if branch_id and branch_id not in branch_ids:
                branch_ids.append(branch_id)
        blockers = [QSignalBlocker(self._run_parallel_child_id_combo)]
        self._run_parallel_child_id_combo.clear()
        for branch_id in branch_ids:
            self._run_parallel_child_id_combo.addItem(branch_id, branch_id)
        del blockers
        self._set_editable_combo_value(
            self._run_parallel_child_id_combo,
            current_text or None,
        )

    def _sync_run_parallel_completion_visibility(self) -> None:
        mode = self._optional_choice_combo_value(self._run_parallel_completion_mode_field)
        show_child = mode == "child"
        self._run_parallel_child_id_row.setVisible(show_child)
        self._run_parallel_completion_note.setVisible(mode in {"any", "child"})

    def _open_dialogue_advanced_field_count(self) -> int:
        count = 0
        for field in (
            self._ui_preset_field,
            self._actor_id_field,
            self._caller_id_field,
        ):
            if field.optional_value() is not None:
                count += 1
        count += self._open_dialogue_entity_refs_field.ref_count()
        return count

    def _sync_open_dialogue_advanced_state(
        self, *args: Any, expanded: bool | None = None
    ) -> None:
        advanced_count = self._open_dialogue_advanced_field_count()
        label = "Advanced"
        if advanced_count > 0:
            label = f"Advanced ({advanced_count} set)"
        self._open_dialogue_advanced_toggle.setText(label)
        if expanded is not None:
            blockers = [QSignalBlocker(self._open_dialogue_advanced_toggle)]
            self._open_dialogue_advanced_toggle.setChecked(expanded)
            del blockers
        expanded_state = self._open_dialogue_advanced_toggle.isChecked()
        self._open_dialogue_advanced_widget.setVisible(expanded_state)
        self._open_dialogue_advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded_state else Qt.ArrowType.RightArrow
        )

    def _on_open_dialogue_advanced_toggled(self, checked: bool) -> None:
        self._sync_open_dialogue_advanced_state(expanded=bool(checked))

    def _run_project_advanced_field_count(self) -> int:
        count = 0
        if self._run_project_source_entity_id_field.optional_value() is not None:
            count += 1
        if self._optional_choice_combo_value(self._run_project_refs_mode_field) is not None:
            count += 1
        count += self._run_project_entity_refs_field.ref_count()
        return count

    def _sync_run_project_advanced_state(
        self, *args: Any, expanded: bool | None = None
    ) -> None:
        advanced_count = self._run_project_advanced_field_count()
        label = "Advanced"
        if advanced_count > 0:
            label = f"Advanced ({advanced_count} set)"
        self._run_project_advanced_toggle.setText(label)
        if expanded is not None:
            blockers = [QSignalBlocker(self._run_project_advanced_toggle)]
            self._run_project_advanced_toggle.setChecked(expanded)
            del blockers
        expanded_state = self._run_project_advanced_toggle.isChecked()
        self._run_project_advanced_widget.setVisible(expanded_state)
        self._run_project_advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded_state else Qt.ArrowType.RightArrow
        )

    def _on_run_project_advanced_toggled(self, checked: bool) -> None:
        self._sync_run_project_advanced_state(expanded=bool(checked))

    def _run_entity_advanced_field_count(self) -> int:
        count = 0
        if self._run_entity_source_entity_id_field.optional_value() is not None:
            count += 1
        if self._optional_choice_combo_value(self._run_entity_refs_mode_field) is not None:
            count += 1
        count += self._run_entity_entity_refs_field.ref_count()
        return count

    def _sync_run_entity_advanced_state(
        self, *args: Any, expanded: bool | None = None
    ) -> None:
        advanced_count = self._run_entity_advanced_field_count()
        label = "Advanced"
        if advanced_count > 0:
            label = f"Advanced ({advanced_count} set)"
        self._run_entity_advanced_toggle.setText(label)
        if expanded is not None:
            blockers = [QSignalBlocker(self._run_entity_advanced_toggle)]
            self._run_entity_advanced_toggle.setChecked(expanded)
            del blockers
        expanded_state = self._run_entity_advanced_toggle.isChecked()
        self._run_entity_advanced_widget.setVisible(expanded_state)
        self._run_entity_advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded_state else Qt.ArrowType.RightArrow
        )

    def _on_run_entity_advanced_toggled(self, checked: bool) -> None:
        self._sync_run_entity_advanced_state(expanded=bool(checked))

    def _run_sequence_advanced_field_count(self) -> int:
        return self._flow_advanced_field_count(
            self._run_sequence_source_entity_id_field,
            self._run_sequence_refs_mode_field,
            self._run_sequence_entity_refs_field,
        )

    def _sync_run_sequence_advanced_state(
        self, *args: Any, expanded: bool | None = None
    ) -> None:
        self._sync_flow_advanced_state(
            self._run_sequence_advanced_toggle,
            self._run_sequence_advanced_widget,
            self._run_sequence_advanced_field_count(),
            expanded=expanded,
        )

    def _on_run_sequence_advanced_toggled(self, checked: bool) -> None:
        self._sync_run_sequence_advanced_state(expanded=bool(checked))

    def _spawn_flow_advanced_field_count(self) -> int:
        return self._flow_advanced_field_count(
            self._spawn_flow_source_entity_id_field,
            self._spawn_flow_refs_mode_field,
            self._spawn_flow_entity_refs_field,
        )

    def _sync_spawn_flow_advanced_state(
        self, *args: Any, expanded: bool | None = None
    ) -> None:
        self._sync_flow_advanced_state(
            self._spawn_flow_advanced_toggle,
            self._spawn_flow_advanced_widget,
            self._spawn_flow_advanced_field_count(),
            expanded=expanded,
        )

    def _on_spawn_flow_advanced_toggled(self, checked: bool) -> None:
        self._sync_spawn_flow_advanced_state(expanded=bool(checked))

    def _run_parallel_advanced_field_count(self) -> int:
        return self._flow_advanced_field_count(
            self._run_parallel_source_entity_id_field,
            self._run_parallel_refs_mode_field,
            self._run_parallel_entity_refs_field,
        )

    def _sync_run_parallel_advanced_state(
        self, *args: Any, expanded: bool | None = None
    ) -> None:
        self._sync_flow_advanced_state(
            self._run_parallel_advanced_toggle,
            self._run_parallel_advanced_widget,
            self._run_parallel_advanced_field_count(),
            expanded=expanded,
        )

    def _on_run_parallel_advanced_toggled(self, checked: bool) -> None:
        self._sync_run_parallel_advanced_state(expanded=bool(checked))

    def _run_for_each_advanced_field_count(self) -> int:
        return self._flow_advanced_field_count(
            self._run_for_each_source_entity_id_field,
            self._run_for_each_refs_mode_field,
            self._run_for_each_entity_refs_field,
        )

    def _sync_run_for_each_advanced_state(
        self, *args: Any, expanded: bool | None = None
    ) -> None:
        self._sync_flow_advanced_state(
            self._run_for_each_advanced_toggle,
            self._run_for_each_advanced_widget,
            self._run_for_each_advanced_field_count(),
            expanded=expanded,
        )

    def _on_run_for_each_advanced_toggled(self, checked: bool) -> None:
        self._sync_run_for_each_advanced_state(expanded=bool(checked))

    def _change_area_advanced_field_count(self) -> int:
        count = 0
        if self._change_area_allowed_instigator_kinds_field.optional_value() is not None:
            count += 1
        if self._change_area_source_entity_id_field.optional_value() is not None:
            count += 1
        count += self._change_area_entity_refs_field.ref_count()
        return count

    def _sync_change_area_advanced_state(
        self, *args: Any, expanded: bool | None = None
    ) -> None:
        advanced_count = self._change_area_advanced_field_count()
        label = "Advanced"
        if advanced_count > 0:
            label = f"Advanced ({advanced_count} set)"
        self._change_area_advanced_toggle.setText(label)
        if expanded is not None:
            blockers = [QSignalBlocker(self._change_area_advanced_toggle)]
            self._change_area_advanced_toggle.setChecked(expanded)
            del blockers
        expanded_state = self._change_area_advanced_toggle.isChecked()
        self._change_area_advanced_widget.setVisible(expanded_state)
        self._change_area_advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded_state else Qt.ArrowType.RightArrow
        )

    def _on_change_area_advanced_toggled(self, checked: bool) -> None:
        self._sync_change_area_advanced_state(expanded=bool(checked))

    def _open_entity_advanced_field_count(self) -> int:
        count = 0
        for field in (
            self._open_entity_ui_preset_field,
            self._open_entity_actor_id_field,
            self._open_entity_caller_id_field,
        ):
            if field.optional_value() is not None:
                count += 1
        count += self._open_entity_entity_refs_field.ref_count()
        return count

    def _sync_open_entity_advanced_state(
        self, *args: Any, expanded: bool | None = None
    ) -> None:
        advanced_count = self._open_entity_advanced_field_count()
        label = "Advanced"
        if advanced_count > 0:
            label = f"Advanced ({advanced_count} set)"
        self._open_entity_advanced_toggle.setText(label)
        if expanded is not None:
            blockers = [QSignalBlocker(self._open_entity_advanced_toggle)]
            self._open_entity_advanced_toggle.setChecked(expanded)
            del blockers
        expanded_state = self._open_entity_advanced_toggle.isChecked()
        self._open_entity_advanced_widget.setVisible(expanded_state)
        self._open_entity_advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded_state else Qt.ArrowType.RightArrow
        )

    def _on_open_entity_advanced_toggled(self, checked: bool) -> None:
        self._sync_open_entity_advanced_state(expanded=bool(checked))

    def _build_structured_command(self, *, show_message: bool) -> dict[str, Any] | None:
        command_type = self._command_type_combo.currentText().strip()
        if not command_type:
            if show_message:
                QMessageBox.warning(self, "Invalid Command", "Command type cannot be blank.")
            return None
        if command_type not in _SUPPORTED_COMMAND_TYPES:
            return self._build_generic_command(command_type, show_message=show_message)

        if str(self._loaded_command.get("type", "")).strip() == command_type:
            base = copy.deepcopy(self._loaded_command)
        else:
            base = {"type": command_type}
        base["type"] = command_type
        for key in _OWNED_FIELDS_BY_COMMAND_TYPE.get(command_type, set()):
            base.pop(key, None)
        if self._command_spec_id_label is not None:
            self._set_optional_text_field(base, "id", self._command_spec_id_field)

        if command_type == "open_dialogue_session":
            source = self._dialogue_source_combo.currentText().strip()
            if source == "Dialogue File":
                dialogue_path = self._dialogue_path_edit.text().strip()
                if not dialogue_path:
                    if show_message:
                        QMessageBox.warning(
                            self,
                            "Invalid Command",
                            "dialogue_path cannot be blank when using Dialogue File.",
                        )
                    return None
                base["dialogue_path"] = dialogue_path
            else:
                base["dialogue_definition"] = copy.deepcopy(
                    self._inline_dialogue_definition or {"segments": []}
                )
            self._set_optional_bool_field(base, "allow_cancel", self._allow_cancel_field)
            self._set_optional_text_field(base, "ui_preset", self._ui_preset_field)
            self._set_optional_text_field(base, "actor_id", self._actor_id_field)
            self._set_optional_text_field(base, "caller_id", self._caller_id_field)
            if not self._set_entity_refs_field(
                base,
                "entity_refs",
                self._open_dialogue_entity_refs_field,
                show_message=show_message,
            ):
                return None
            return base

        if command_type == "run_project_command":
            command_id = self._project_command_id_edit.text().strip()
            if not command_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "command_id cannot be blank.",
                    )
                return None
            base["command_id"] = command_id
            self._set_optional_text_field(
                base,
                "source_entity_id",
                self._run_project_source_entity_id_field,
            )
            refs_mode = self._optional_choice_combo_value(self._run_project_refs_mode_field)
            if isinstance(refs_mode, str) and refs_mode.strip():
                base["refs_mode"] = refs_mode.strip()
            if not self._set_entity_refs_field(
                base,
                "entity_refs",
                self._run_project_entity_refs_field,
                show_message=show_message,
            ):
                return None
            if base.get("refs_mode") is None:
                base.pop("refs_mode", None)
            return base

        if command_type == "run_entity_command":
            entity_id = self._run_entity_entity_id_edit.text().strip()
            command_id = self._run_entity_command_id_edit.text().strip()
            if not entity_id or not command_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id and command_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["command_id"] = command_id
            self._set_optional_text_field(
                base,
                "source_entity_id",
                self._run_entity_source_entity_id_field,
            )
            refs_mode = self._optional_choice_combo_value(self._run_entity_refs_mode_field)
            if isinstance(refs_mode, str) and refs_mode.strip():
                base["refs_mode"] = refs_mode.strip()
            if not self._set_entity_refs_field(
                base,
                "entity_refs",
                self._run_entity_entity_refs_field,
                show_message=show_message,
            ):
                return None
            if base.get("refs_mode") is None:
                base.pop("refs_mode", None)
            return base

        if command_type == "run_sequence":
            commands = self._run_sequence_commands_field.commands()
            if commands:
                base["commands"] = commands
            else:
                base.pop("commands", None)
            if not self._set_flow_context_fields(
                base,
                source_entity_id_field=self._run_sequence_source_entity_id_field,
                refs_mode_field=self._run_sequence_refs_mode_field,
                entity_refs_field=self._run_sequence_entity_refs_field,
                show_message=show_message,
            ):
                return None
            return base

        if command_type == "spawn_flow":
            commands = self._spawn_flow_commands_field.commands()
            if commands:
                base["commands"] = commands
            else:
                base.pop("commands", None)
            if not self._set_flow_context_fields(
                base,
                source_entity_id_field=self._spawn_flow_source_entity_id_field,
                refs_mode_field=self._spawn_flow_refs_mode_field,
                entity_refs_field=self._spawn_flow_entity_refs_field,
                show_message=show_message,
            ):
                return None
            return base

        if command_type == "run_parallel":
            commands = self._run_parallel_commands_field.commands()
            if commands:
                base["commands"] = commands
            else:
                base.pop("commands", None)
            completion_mode = self._optional_choice_combo_value(
                self._run_parallel_completion_mode_field
            )
            if completion_mode is None:
                base.pop("completion", None)
            else:
                completion: dict[str, Any] = {"mode": completion_mode}
                if completion_mode == "child":
                    child_id = self._editable_combo_text(
                        self._run_parallel_child_id_combo
                    )
                    if not child_id:
                        if show_message:
                            QMessageBox.warning(
                                self,
                                "Invalid Command",
                                "completion.child_id cannot be blank when completion.mode is child.",
                            )
                        return None
                    completion["child_id"] = child_id
                base["completion"] = completion
            if not self._set_flow_context_fields(
                base,
                source_entity_id_field=self._run_parallel_source_entity_id_field,
                refs_mode_field=self._run_parallel_refs_mode_field,
                entity_refs_field=self._run_parallel_entity_refs_field,
                show_message=show_message,
            ):
                return None
            return base

        if command_type == "run_commands_for_collection":
            value_text = self._run_for_each_value_edit.toPlainText().strip()
            if value_text:
                try:
                    base["value"] = _parse_json_text_value(value_text)
                except (ValueError, json.JSONDecodeError) as exc:
                    if show_message:
                        QMessageBox.warning(
                            self,
                            "Invalid Command",
                            f"value must be valid JSON.\n{exc}",
                        )
                    return None
            else:
                base.pop("value", None)
            self._set_optional_text_field(
                base,
                "item_param",
                self._run_for_each_item_param_field,
            )
            self._set_optional_text_field(
                base,
                "index_param",
                self._run_for_each_index_param_field,
            )
            commands = self._run_for_each_commands_field.commands()
            if commands:
                base["commands"] = commands
            else:
                base.pop("commands", None)
            if not self._set_flow_context_fields(
                base,
                source_entity_id_field=self._run_for_each_source_entity_id_field,
                refs_mode_field=self._run_for_each_refs_mode_field,
                entity_refs_field=self._run_for_each_entity_refs_field,
                show_message=show_message,
            ):
                return None
            return base

        if command_type == "if":
            left_text = self._if_left_edit.toPlainText().strip()
            if left_text:
                try:
                    base["left"] = _parse_json_text_value(left_text)
                except (ValueError, json.JSONDecodeError) as exc:
                    if show_message:
                        QMessageBox.warning(
                            self,
                            "Invalid Command",
                            f"left must be valid JSON.\n{exc}",
                        )
                    return None
            else:
                base.pop("left", None)
            op = self._optional_choice_combo_value(self._if_op_field)
            if isinstance(op, str) and op.strip() and op.strip() != "eq":
                base["op"] = op.strip()
            else:
                base.pop("op", None)
            right_text = self._if_right_edit.toPlainText().strip()
            if right_text:
                try:
                    base["right"] = _parse_json_text_value(right_text)
                except (ValueError, json.JSONDecodeError) as exc:
                    if show_message:
                        QMessageBox.warning(
                            self,
                            "Invalid Command",
                            f"right must be valid JSON.\n{exc}",
                        )
                    return None
            else:
                base.pop("right", None)
            then_commands = self._if_then_commands_field.commands()
            if then_commands:
                base["then"] = then_commands
            else:
                base.pop("then", None)
            else_commands = self._if_else_commands_field.commands()
            if else_commands:
                base["else"] = else_commands
            else:
                base.pop("else", None)
            return base

        if command_type == "change_area":
            area_id = self._change_area_area_id_edit.text().strip()
            if not area_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "area_id cannot be blank.",
                    )
                return None
            base["area_id"] = area_id
            self._set_optional_text_field(base, "entry_id", self._change_area_entry_id_field)
            self._set_optional_text_field(
                base,
                "destination_entity_id",
                self._change_area_destination_entity_id_field,
            )
            self._set_optional_text_field(
                base,
                "transfer_entity_id",
                self._change_area_transfer_entity_id_field,
            )
            transfer_entity_ids = _parse_string_list_text(
                self._change_area_transfer_entity_ids_field.optional_value() or ""
            )
            if transfer_entity_ids:
                base["transfer_entity_ids"] = transfer_entity_ids
            else:
                base.pop("transfer_entity_ids", None)
            if not self._set_camera_follow_patch_field(
                base,
                "camera_follow",
                self._change_area_camera_follow_field,
                show_message=show_message,
            ):
                return None
            allowed_instigator_kinds = _parse_string_list_text(
                self._change_area_allowed_instigator_kinds_field.optional_value() or ""
            )
            if allowed_instigator_kinds:
                base["allowed_instigator_kinds"] = allowed_instigator_kinds
            else:
                base.pop("allowed_instigator_kinds", None)
            self._set_optional_text_field(
                base,
                "source_entity_id",
                self._change_area_source_entity_id_field,
            )
            if not self._set_entity_refs_field(
                base,
                "entity_refs",
                self._change_area_entity_refs_field,
                show_message=show_message,
            ):
                return None
            return base

        if command_type == "new_game":
            area_id = self._new_game_area_id_edit.text().strip()
            if not area_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "area_id cannot be blank.",
                    )
                return None
            base["area_id"] = area_id
            self._set_optional_text_field(base, "entry_id", self._new_game_entry_id_field)
            self._set_optional_text_field(
                base,
                "destination_entity_id",
                self._new_game_destination_entity_id_field,
            )
            self._set_optional_text_field(
                base,
                "source_entity_id",
                self._new_game_source_entity_id_field,
            )
            if not self._set_camera_follow_patch_field(
                base,
                "camera_follow",
                self._new_game_camera_follow_field,
                show_message=show_message,
            ):
                return None
            return base

        if command_type == "load_game":
            self._set_optional_text_field(
                base,
                "save_path",
                self._load_game_save_path_field,
            )
            return base

        if command_type == "save_game":
            self._set_optional_text_field(
                base,
                "save_path",
                self._save_game_save_path_field,
            )
            return base

        if command_type == "quit_game":
            return base

        if command_type == "set_simulation_paused":
            paused = self._optional_bool_combo_value(self._set_simulation_paused_field)
            if paused is None:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "paused must be set to True or False.",
                    )
                return None
            base["paused"] = paused
            return base

        if command_type == "toggle_simulation_paused":
            return base

        if command_type == "step_simulation_tick":
            return base

        if command_type == "adjust_output_scale":
            base["delta"] = int(self._adjust_output_scale_delta_spin.value())
            return base

        if command_type == "open_entity_dialogue":
            entity_id = self._open_entity_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            self._set_optional_text_field(
                base,
                "dialogue_id",
                self._open_entity_dialogue_id_field,
            )
            self._set_optional_bool_field(
                base,
                "allow_cancel",
                self._open_entity_allow_cancel_field,
            )
            self._set_optional_text_field(
                base,
                "ui_preset",
                self._open_entity_ui_preset_field,
            )
            self._set_optional_text_field(
                base,
                "actor_id",
                self._open_entity_actor_id_field,
            )
            self._set_optional_text_field(
                base,
                "caller_id",
                self._open_entity_caller_id_field,
            )
            if not self._set_entity_refs_field(
                base,
                "entity_refs",
                self._open_entity_entity_refs_field,
                show_message=show_message,
            ):
                return None
            return base

        if command_type == "set_entity_grid_position":
            entity_id = self._set_grid_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["x"] = int(self._set_grid_x_spin.value())
            base["y"] = int(self._set_grid_y_spin.value())
            mode = self._optional_choice_combo_value(self._set_grid_mode_field)
            if isinstance(mode, str) and mode.strip():
                base["mode"] = mode.strip()
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_grid_persistent_field,
            )
            return base

        if command_type == "set_entity_world_position":
            entity_id = self._set_world_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["x"] = float(self._set_world_x_spin.value())
            base["y"] = float(self._set_world_y_spin.value())
            mode = self._optional_choice_combo_value(self._set_world_mode_field)
            if isinstance(mode, str) and mode.strip():
                base["mode"] = mode.strip()
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_world_persistent_field,
            )
            return base

        if command_type == "set_entity_screen_position":
            entity_id = self._set_screen_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["x"] = float(self._set_screen_x_spin.value())
            base["y"] = float(self._set_screen_y_spin.value())
            mode = self._optional_choice_combo_value(self._set_screen_mode_field)
            if isinstance(mode, str) and mode.strip():
                base["mode"] = mode.strip()
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_screen_persistent_field,
            )
            return base

        if command_type == "move_entity_world_position":
            entity_id = self._move_world_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["x"] = float(self._move_world_x_spin.value())
            base["y"] = float(self._move_world_y_spin.value())
            mode = self._optional_choice_combo_value(self._move_world_mode_field)
            if isinstance(mode, str) and mode.strip():
                base["mode"] = mode.strip()
            self._set_optional_float_field(
                base,
                "duration",
                self._move_world_duration_field,
            )
            self._set_optional_int_field(
                base,
                "frames_needed",
                self._move_world_frames_needed_field,
            )
            self._set_optional_float_field(
                base,
                "speed_px_per_second",
                self._move_world_speed_field,
            )
            self._set_optional_bool_field(
                base,
                "wait",
                self._move_world_wait_field,
            )
            self._set_optional_bool_field(
                base,
                "persistent",
                self._move_world_persistent_field,
            )
            return base

        if command_type == "move_entity_screen_position":
            entity_id = self._move_screen_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["x"] = float(self._move_screen_x_spin.value())
            base["y"] = float(self._move_screen_y_spin.value())
            mode = self._optional_choice_combo_value(self._move_screen_mode_field)
            if isinstance(mode, str) and mode.strip():
                base["mode"] = mode.strip()
            self._set_optional_float_field(
                base,
                "duration",
                self._move_screen_duration_field,
            )
            self._set_optional_int_field(
                base,
                "frames_needed",
                self._move_screen_frames_needed_field,
            )
            self._set_optional_float_field(
                base,
                "speed_px_per_second",
                self._move_screen_speed_field,
            )
            self._set_optional_bool_field(
                base,
                "wait",
                self._move_screen_wait_field,
            )
            self._set_optional_bool_field(
                base,
                "persistent",
                self._move_screen_persistent_field,
            )
            return base

        if command_type == "push_facing":
            entity_id = self._push_facing_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            direction = self._optional_choice_combo_value(self._push_facing_direction_field)
            if isinstance(direction, str) and direction.strip():
                base["direction"] = direction.strip()
            self._set_optional_int_field(
                base,
                "push_strength",
                self._push_facing_push_strength_field,
            )
            self._set_optional_float_field(
                base,
                "duration",
                self._push_facing_duration_field,
            )
            self._set_optional_int_field(
                base,
                "frames_needed",
                self._push_facing_frames_needed_field,
            )
            self._set_optional_float_field(
                base,
                "speed_px_per_second",
                self._push_facing_speed_field,
            )
            self._set_optional_bool_field(
                base,
                "wait",
                self._push_facing_wait_field,
            )
            self._set_optional_bool_field(
                base,
                "persistent",
                self._push_facing_persistent_field,
            )
            return base

        if command_type == "wait_for_move":
            entity_id = self._wait_for_move_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            return base

        if command_type == "step_in_direction":
            entity_id = self._step_in_direction_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            direction = self._optional_choice_combo_value(
                self._step_in_direction_direction_field
            )
            if isinstance(direction, str) and direction.strip():
                base["direction"] = direction.strip()
            self._set_optional_int_field(
                base,
                "push_strength",
                self._step_in_direction_push_strength_field,
            )
            self._set_optional_int_field(
                base,
                "frames_needed",
                self._step_in_direction_frames_needed_field,
            )
            self._set_optional_bool_field(
                base,
                "wait",
                self._step_in_direction_wait_field,
            )
            self._set_optional_bool_field(
                base,
                "persistent",
                self._step_in_direction_persistent_field,
            )
            return base

        if command_type == "set_camera_follow_entity":
            entity_id = self._set_camera_follow_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            offset_x = float(self._set_camera_follow_entity_offset_x_spin.value())
            offset_y = float(self._set_camera_follow_entity_offset_y_spin.value())
            if offset_x != 0.0:
                base["offset_x"] = offset_x
            if offset_y != 0.0:
                base["offset_y"] = offset_y
            return base

        if command_type == "set_camera_follow_input_target":
            action = self._set_camera_follow_input_action_edit.text().strip()
            if not action:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "action cannot be blank.",
                    )
                return None
            base["action"] = action
            offset_x = float(self._set_camera_follow_input_offset_x_spin.value())
            offset_y = float(self._set_camera_follow_input_offset_y_spin.value())
            if offset_x != 0.0:
                base["offset_x"] = offset_x
            if offset_y != 0.0:
                base["offset_y"] = offset_y
            return base

        if command_type == "clear_camera_follow":
            return base

        if command_type == "set_camera_policy":
            if not self._set_camera_follow_patch_field(
                base,
                "follow",
                self._set_camera_policy_follow_field,
                show_message=show_message,
            ):
                return None
            if not self._set_camera_rect_patch_field(
                base,
                "bounds",
                self._set_camera_policy_bounds_field,
                show_message=show_message,
            ):
                return None
            if not self._set_camera_rect_patch_field(
                base,
                "deadzone",
                self._set_camera_policy_deadzone_field,
                show_message=show_message,
            ):
                return None
            return base

        if command_type == "push_camera_state":
            return base

        if command_type == "pop_camera_state":
            return base

        if command_type == "set_camera_bounds":
            try:
                base.update(self._set_camera_bounds_editor.rect_value())
            except ValueError as exc:
                if show_message:
                    QMessageBox.warning(self, "Invalid Command", str(exc))
                return None
            return base

        if command_type == "clear_camera_bounds":
            return base

        if command_type == "set_camera_deadzone":
            try:
                base.update(self._set_camera_deadzone_editor.rect_value())
            except ValueError as exc:
                if show_message:
                    QMessageBox.warning(self, "Invalid Command", str(exc))
                return None
            return base

        if command_type == "clear_camera_deadzone":
            return base

        if command_type == "move_camera":
            base["x"] = float(self._move_camera_x_spin.value())
            base["y"] = float(self._move_camera_y_spin.value())
            space = self._optional_choice_combo_value(self._move_camera_space_field)
            if isinstance(space, str) and space.strip():
                base["space"] = space.strip()
            mode = self._optional_choice_combo_value(self._move_camera_mode_field)
            if isinstance(mode, str) and mode.strip():
                base["mode"] = mode.strip()
            self._set_optional_float_field(
                base,
                "duration",
                self._move_camera_duration_field,
            )
            self._set_optional_int_field(
                base,
                "frames_needed",
                self._move_camera_frames_needed_field,
            )
            self._set_optional_float_field(
                base,
                "speed_px_per_second",
                self._move_camera_speed_field,
            )
            return base

        if command_type == "teleport_camera":
            base["x"] = float(self._teleport_camera_x_spin.value())
            base["y"] = float(self._teleport_camera_y_spin.value())
            space = self._optional_choice_combo_value(self._teleport_camera_space_field)
            if isinstance(space, str) and space.strip():
                base["space"] = space.strip()
            mode = self._optional_choice_combo_value(self._teleport_camera_mode_field)
            if isinstance(mode, str) and mode.strip():
                base["mode"] = mode.strip()
            return base

        if command_type == "play_audio":
            path = self._play_audio_path_edit.text().strip()
            if not path:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "path cannot be blank.",
                    )
                return None
            base["path"] = path
            self._set_optional_float_field(
                base,
                "volume",
                self._play_audio_volume_field,
            )
            return base

        if command_type == "set_sound_volume":
            base["volume"] = float(self._set_sound_volume_spin.value())
            return base

        if command_type == "play_music":
            path = self._play_music_path_edit.text().strip()
            if not path:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "path cannot be blank.",
                    )
                return None
            base["path"] = path
            self._set_optional_bool_field(base, "loop", self._play_music_loop_field)
            self._set_optional_float_field(
                base,
                "volume",
                self._play_music_volume_field,
            )
            self._set_optional_bool_field(
                base,
                "restart_if_same",
                self._play_music_restart_if_same_field,
            )
            return base

        if command_type == "stop_music":
            self._set_optional_float_field(
                base,
                "fade_seconds",
                self._stop_music_fade_seconds_field,
            )
            return base

        if command_type == "pause_music":
            return base

        if command_type == "resume_music":
            return base

        if command_type == "set_music_volume":
            base["volume"] = float(self._set_music_volume_spin.value())
            return base

        if command_type == "show_screen_image":
            element_id = self._show_screen_image_element_id_edit.text().strip()
            path = self._show_screen_image_path_edit.text().strip()
            if not element_id or not path:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "element_id and path cannot be blank.",
                    )
                return None
            base["element_id"] = element_id
            base["path"] = path
            base["x"] = float(self._show_screen_image_x_spin.value())
            base["y"] = float(self._show_screen_image_y_spin.value())
            self._set_optional_int_field(
                base,
                "frame_width",
                self._show_screen_image_frame_width_field,
            )
            self._set_optional_int_field(
                base,
                "frame_height",
                self._show_screen_image_frame_height_field,
            )
            self._set_optional_int_field(
                base,
                "frame",
                self._show_screen_image_frame_field,
            )
            self._set_optional_int_field(
                base,
                "layer",
                self._show_screen_image_layer_field,
            )
            anchor = self._optional_choice_combo_value(self._show_screen_image_anchor_field)
            if isinstance(anchor, str) and anchor.strip():
                base["anchor"] = anchor.strip()
            tint_text = self._show_screen_image_tint_field.optional_value()
            if isinstance(tint_text, str) and tint_text.strip():
                try:
                    base["tint"] = list(_parse_rgb_text(tint_text))
                except ValueError as exc:
                    if show_message:
                        QMessageBox.warning(self, "Invalid Command", str(exc))
                    return None
            else:
                base.pop("tint", None)
            self._set_optional_bool_field(
                base,
                "flip_x",
                self._show_screen_image_flip_x_field,
            )
            self._set_optional_bool_field(
                base,
                "visible",
                self._show_screen_image_visible_field,
            )
            return base

        if command_type == "show_screen_text":
            element_id = self._show_screen_text_element_id_edit.text().strip()
            text = self._show_screen_text_text_edit.text()
            if not element_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "element_id cannot be blank.",
                    )
                return None
            base["element_id"] = element_id
            base["text"] = text
            base["x"] = float(self._show_screen_text_x_spin.value())
            base["y"] = float(self._show_screen_text_y_spin.value())
            self._set_optional_int_field(
                base,
                "layer",
                self._show_screen_text_layer_field,
            )
            anchor = self._optional_choice_combo_value(self._show_screen_text_anchor_field)
            if isinstance(anchor, str) and anchor.strip():
                base["anchor"] = anchor.strip()
            color_text = self._show_screen_text_color_field.optional_value()
            if isinstance(color_text, str) and color_text.strip():
                try:
                    base["color"] = list(_parse_rgb_text(color_text))
                except ValueError as exc:
                    if show_message:
                        QMessageBox.warning(self, "Invalid Command", str(exc))
                    return None
            else:
                base.pop("color", None)
            self._set_optional_text_field(
                base,
                "font_id",
                self._show_screen_text_font_id_field,
            )
            self._set_optional_int_field(
                base,
                "max_width",
                self._show_screen_text_max_width_field,
            )
            self._set_optional_bool_field(
                base,
                "visible",
                self._show_screen_text_visible_field,
            )
            return base

        if command_type == "set_screen_text":
            element_id = self._set_screen_text_element_id_edit.text().strip()
            text = self._set_screen_text_text_edit.text()
            if not element_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "element_id cannot be blank.",
                    )
                return None
            base["element_id"] = element_id
            base["text"] = text
            return base

        if command_type == "remove_screen_element":
            element_id = self._remove_screen_element_id_edit.text().strip()
            if not element_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "element_id cannot be blank.",
                    )
                return None
            base["element_id"] = element_id
            return base

        if command_type == "clear_screen_elements":
            self._set_optional_int_field(
                base,
                "layer",
                self._clear_screen_elements_layer_field,
            )
            return base

        if command_type == "play_screen_animation":
            element_id = self._play_screen_animation_element_id_edit.text().strip()
            frame_sequence_text = self._play_screen_animation_frame_sequence_edit.text().strip()
            if not element_id or not frame_sequence_text:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "element_id and frame_sequence cannot be blank.",
                    )
                return None
            try:
                frame_sequence = _parse_int_list_text(frame_sequence_text)
            except ValueError as exc:
                if show_message:
                    QMessageBox.warning(self, "Invalid Command", str(exc))
                return None
            if not frame_sequence:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "frame_sequence must contain at least one frame number.",
                    )
                return None
            base["element_id"] = element_id
            base["frame_sequence"] = frame_sequence
            self._set_optional_int_field(
                base,
                "ticks_per_frame",
                self._play_screen_animation_ticks_per_frame_field,
            )
            self._set_optional_bool_field(
                base,
                "hold_last_frame",
                self._play_screen_animation_hold_last_frame_field,
            )
            self._set_optional_bool_field(
                base,
                "wait",
                self._play_screen_animation_wait_field,
            )
            return base

        if command_type == "wait_for_screen_animation":
            element_id = self._wait_for_screen_animation_element_id_edit.text().strip()
            if not element_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "element_id cannot be blank.",
                    )
                return None
            base["element_id"] = element_id
            return base

        if command_type == "play_animation":
            entity_id = self._play_animation_entity_id_edit.text().strip()
            animation = self._play_animation_name_edit.text().strip()
            if not entity_id or not animation:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id and animation cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["animation"] = animation
            self._set_optional_text_field(
                base,
                "visual_id",
                self._play_animation_visual_id_field,
            )
            self._set_optional_int_field(
                base,
                "frame_count",
                self._play_animation_frame_count_field,
            )
            self._set_optional_int_field(
                base,
                "duration_ticks",
                self._play_animation_duration_ticks_field,
            )
            self._set_optional_bool_field(
                base,
                "wait",
                self._play_animation_wait_field,
            )
            return base

        if command_type == "wait_for_animation":
            entity_id = self._wait_for_animation_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            self._set_optional_text_field(
                base,
                "visual_id",
                self._wait_for_animation_visual_id_field,
            )
            return base

        if command_type == "stop_animation":
            entity_id = self._stop_animation_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            self._set_optional_text_field(
                base,
                "visual_id",
                self._stop_animation_visual_id_field,
            )
            self._set_optional_bool_field(
                base,
                "reset_to_default",
                self._stop_animation_reset_field,
            )
            return base

        if command_type == "add_inventory_item":
            entity_id = self._add_inventory_entity_id_edit.text().strip()
            item_id = self._add_inventory_item_id_edit.text().strip()
            quantity_mode = self._optional_choice_combo_value(
                self._add_inventory_quantity_mode_field
            )
            if (
                not entity_id
                or not item_id
                or not isinstance(quantity_mode, str)
                or not quantity_mode.strip()
            ):
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id, item_id, and quantity_mode must be set.",
                    )
                return None
            base["entity_id"] = entity_id
            base["item_id"] = item_id
            base["quantity_mode"] = quantity_mode.strip()
            self._set_optional_int_field(
                base,
                "quantity",
                self._add_inventory_quantity_field,
            )
            self._set_optional_text_field(
                base,
                "result_var_name",
                self._add_inventory_result_var_field,
            )
            self._set_optional_bool_field(
                base,
                "persistent",
                self._add_inventory_persistent_field,
            )
            return base

        if command_type == "remove_inventory_item":
            entity_id = self._remove_inventory_entity_id_edit.text().strip()
            item_id = self._remove_inventory_item_id_edit.text().strip()
            quantity_mode = self._optional_choice_combo_value(
                self._remove_inventory_quantity_mode_field
            )
            if (
                not entity_id
                or not item_id
                or not isinstance(quantity_mode, str)
                or not quantity_mode.strip()
            ):
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id, item_id, and quantity_mode must be set.",
                    )
                return None
            base["entity_id"] = entity_id
            base["item_id"] = item_id
            base["quantity_mode"] = quantity_mode.strip()
            self._set_optional_int_field(
                base,
                "quantity",
                self._remove_inventory_quantity_field,
            )
            self._set_optional_text_field(
                base,
                "result_var_name",
                self._remove_inventory_result_var_field,
            )
            self._set_optional_bool_field(
                base,
                "persistent",
                self._remove_inventory_persistent_field,
            )
            return base

        if command_type == "use_inventory_item":
            entity_id = self._use_inventory_entity_id_edit.text().strip()
            item_id = self._use_inventory_item_id_edit.text().strip()
            if not entity_id or not item_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id and item_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["item_id"] = item_id
            self._set_optional_int_field(
                base,
                "quantity",
                self._use_inventory_quantity_field,
            )
            self._set_optional_text_field(
                base,
                "result_var_name",
                self._use_inventory_result_var_field,
            )
            self._set_optional_bool_field(
                base,
                "persistent",
                self._use_inventory_persistent_field,
            )
            return base

        if command_type == "set_inventory_max_stacks":
            entity_id = self._set_inventory_max_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["max_stacks"] = int(self._set_inventory_max_stacks_spin.value())
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_inventory_max_persistent_field,
            )
            return base

        if command_type == "open_inventory_session":
            entity_id = self._open_inventory_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            self._set_optional_text_field(
                base,
                "ui_preset",
                self._open_inventory_ui_preset_field,
            )
            self._set_optional_bool_field(
                base,
                "wait",
                self._open_inventory_wait_field,
            )
            return base

        if command_type == "close_inventory_session":
            return base

        if command_type == "set_entity_command_enabled":
            entity_id = self._set_entity_command_entity_id_edit.text().strip()
            command_id = self._set_entity_command_id_edit.text().strip()
            enabled = self._optional_bool_combo_value(self._set_entity_command_enabled_field)
            if not entity_id or not command_id or enabled is None:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id and command_id must be set, and enabled must be True or False.",
                    )
                return None
            base["entity_id"] = entity_id
            base["command_id"] = command_id
            base["enabled"] = enabled
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_entity_command_persistent_field,
            )
            return base

        if command_type == "set_entity_commands_enabled":
            entity_id = self._set_entity_commands_entity_id_edit.text().strip()
            enabled = self._optional_bool_combo_value(self._set_entity_commands_enabled_field)
            if not entity_id or enabled is None:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id must be set, and enabled must be True or False.",
                    )
                return None
            base["entity_id"] = entity_id
            base["enabled"] = enabled
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_entity_commands_persistent_field,
            )
            return base

        if command_type == "set_entity_active_dialogue":
            entity_id = self._set_active_entity_id_edit.text().strip()
            dialogue_id = self._set_active_dialogue_id_edit.text().strip()
            if not entity_id or not dialogue_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id and dialogue_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["dialogue_id"] = dialogue_id
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_active_persistent_field,
            )
            return base

        if command_type == "set_current_area_var":
            name = self._set_current_area_var_name_edit.text().strip()
            value_text = self._set_current_area_var_value_edit.toPlainText().strip()
            if not name or not value_text:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "name and value cannot be blank.",
                    )
                return None
            try:
                value = _parse_json_text_value(value_text)
            except (ValueError, json.JSONDecodeError) as exc:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        f"Value must be valid JSON.\n{exc}",
                    )
                return None
            base["name"] = name
            base["value"] = value
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_current_area_var_persistent_field,
            )
            value_mode = self._optional_choice_combo_value(
                self._set_current_area_var_value_mode_field
            )
            if isinstance(value_mode, str) and value_mode.strip():
                base["value_mode"] = value_mode.strip()
            return base

        if command_type == "add_current_area_var":
            name = self._add_current_area_var_name_edit.text().strip()
            if not name:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "name cannot be blank.",
                    )
                return None
            base["name"] = name
            amount = self._add_current_area_var_amount_field.optional_value()
            if amount is not None:
                base["amount"] = _coerce_numeric_literal(amount)
            self._set_optional_bool_field(
                base,
                "persistent",
                self._add_current_area_var_persistent_field,
            )
            return base

        if command_type == "add_entity_var":
            entity_id = self._add_entity_var_entity_id_edit.text().strip()
            name = self._add_entity_var_name_edit.text().strip()
            if not entity_id or not name:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id and name cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["name"] = name
            amount = self._add_entity_var_amount_field.optional_value()
            if amount is not None:
                base["amount"] = _coerce_numeric_literal(amount)
            self._set_optional_bool_field(
                base,
                "persistent",
                self._add_entity_var_persistent_field,
            )
            return base

        if command_type == "toggle_current_area_var":
            name = self._toggle_current_area_var_name_edit.text().strip()
            if not name:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "name cannot be blank.",
                    )
                return None
            base["name"] = name
            self._set_optional_bool_field(
                base,
                "persistent",
                self._toggle_current_area_var_persistent_field,
            )
            return base

        if command_type == "toggle_entity_var":
            entity_id = self._toggle_entity_var_entity_id_edit.text().strip()
            name = self._toggle_entity_var_name_edit.text().strip()
            if not entity_id or not name:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id and name cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["name"] = name
            self._set_optional_bool_field(
                base,
                "persistent",
                self._toggle_entity_var_persistent_field,
            )
            return base

        if command_type == "set_current_area_var_length":
            name = self._set_current_area_var_length_name_edit.text().strip()
            if not name:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "name cannot be blank.",
                    )
                return None
            base["name"] = name
            value_text = self._set_current_area_var_length_value_edit.toPlainText().strip()
            if value_text:
                try:
                    base["value"] = _parse_json_text_value(value_text)
                except (ValueError, json.JSONDecodeError) as exc:
                    if show_message:
                        QMessageBox.warning(
                            self,
                            "Invalid Command",
                            f"Value must be valid JSON.\n{exc}",
                        )
                    return None
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_current_area_var_length_persistent_field,
            )
            return base

        if command_type == "set_entity_var_length":
            entity_id = self._set_entity_var_length_entity_id_edit.text().strip()
            name = self._set_entity_var_length_name_edit.text().strip()
            if not entity_id or not name:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id and name cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["name"] = name
            value_text = self._set_entity_var_length_value_edit.toPlainText().strip()
            if value_text:
                try:
                    base["value"] = _parse_json_text_value(value_text)
                except (ValueError, json.JSONDecodeError) as exc:
                    if show_message:
                        QMessageBox.warning(
                            self,
                            "Invalid Command",
                            f"Value must be valid JSON.\n{exc}",
                        )
                    return None
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_entity_var_length_persistent_field,
            )
            return base

        if command_type == "append_current_area_var":
            name = self._append_current_area_var_name_edit.text().strip()
            value_text = self._append_current_area_var_value_edit.toPlainText().strip()
            if not name or not value_text:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "name and value cannot be blank.",
                    )
                return None
            try:
                value = _parse_json_text_value(value_text)
            except (ValueError, json.JSONDecodeError) as exc:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        f"Value must be valid JSON.\n{exc}",
                    )
                return None
            base["name"] = name
            base["value"] = value
            self._set_optional_bool_field(
                base,
                "persistent",
                self._append_current_area_var_persistent_field,
            )
            value_mode = self._optional_choice_combo_value(
                self._append_current_area_var_value_mode_field
            )
            if isinstance(value_mode, str) and value_mode.strip():
                base["value_mode"] = value_mode.strip()
            return base

        if command_type == "append_entity_var":
            entity_id = self._append_entity_var_entity_id_edit.text().strip()
            name = self._append_entity_var_name_edit.text().strip()
            value_text = self._append_entity_var_value_edit.toPlainText().strip()
            if not entity_id or not name or not value_text:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id, name, and value cannot be blank.",
                    )
                return None
            try:
                value = _parse_json_text_value(value_text)
            except (ValueError, json.JSONDecodeError) as exc:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        f"Value must be valid JSON.\n{exc}",
                    )
                return None
            base["entity_id"] = entity_id
            base["name"] = name
            base["value"] = value
            self._set_optional_bool_field(
                base,
                "persistent",
                self._append_entity_var_persistent_field,
            )
            value_mode = self._optional_choice_combo_value(
                self._append_entity_var_value_mode_field
            )
            if isinstance(value_mode, str) and value_mode.strip():
                base["value_mode"] = value_mode.strip()
            return base

        if command_type == "pop_current_area_var":
            name = self._pop_current_area_var_name_edit.text().strip()
            if not name:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "name cannot be blank.",
                    )
                return None
            base["name"] = name
            self._set_optional_text_field(
                base,
                "store_var",
                self._pop_current_area_var_store_var_field,
            )
            default_text = self._pop_current_area_var_default_edit.toPlainText().strip()
            if default_text:
                try:
                    base["default"] = _parse_json_text_value(default_text)
                except (ValueError, json.JSONDecodeError) as exc:
                    if show_message:
                        QMessageBox.warning(
                            self,
                            "Invalid Command",
                            f"Default must be valid JSON.\n{exc}",
                        )
                    return None
            self._set_optional_bool_field(
                base,
                "persistent",
                self._pop_current_area_var_persistent_field,
            )
            return base

        if command_type == "pop_entity_var":
            entity_id = self._pop_entity_var_entity_id_edit.text().strip()
            name = self._pop_entity_var_name_edit.text().strip()
            if not entity_id or not name:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id and name cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["name"] = name
            self._set_optional_text_field(
                base,
                "store_var",
                self._pop_entity_var_store_var_field,
            )
            default_text = self._pop_entity_var_default_edit.toPlainText().strip()
            if default_text:
                try:
                    base["default"] = _parse_json_text_value(default_text)
                except (ValueError, json.JSONDecodeError) as exc:
                    if show_message:
                        QMessageBox.warning(
                            self,
                            "Invalid Command",
                            f"Default must be valid JSON.\n{exc}",
                        )
                    return None
            self._set_optional_bool_field(
                base,
                "persistent",
                self._pop_entity_var_persistent_field,
            )
            return base

        if command_type == "set_entity_field":
            entity_id = self._set_entity_field_entity_id_edit.text().strip()
            field_name = self._editable_combo_text(self._set_entity_field_name_combo)
            value_text = self._set_entity_field_value_edit.toPlainText().strip()
            if not entity_id or not field_name or not value_text:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id, field_name, and value cannot be blank.",
                    )
                return None
            try:
                value = _parse_json_text_value(value_text)
            except (ValueError, json.JSONDecodeError) as exc:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        f"Value must be valid JSON.\n{exc}",
                    )
                return None
            base["entity_id"] = entity_id
            base["field_name"] = field_name
            base["value"] = value
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_entity_field_persistent_field,
            )
            return base

        if command_type == "set_entity_fields":
            entity_id = self._set_entity_fields_entity_id_edit.text().strip()
            payload_text = self._set_entity_fields_payload_edit.toPlainText().strip()
            if not entity_id or not payload_text:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id and set payload cannot be blank.",
                    )
                return None
            try:
                payload = _parse_json_object_text_value(payload_text)
            except (ValueError, json.JSONDecodeError) as exc:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        f"set must be a JSON object.\n{exc}",
                    )
                return None
            base["entity_id"] = entity_id
            base["set"] = payload
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_entity_fields_persistent_field,
            )
            return base

        if command_type == "spawn_entity":
            mode = self._optional_choice_combo_value(self._spawn_entity_mode_combo)
            if mode == "full":
                payload_text = self._spawn_entity_full_edit.toPlainText().strip()
                if not payload_text:
                    if show_message:
                        QMessageBox.warning(
                            self,
                            "Invalid Command",
                            "entity cannot be blank when using Full Entity JSON mode.",
                        )
                    return None
                try:
                    base["entity"] = _parse_json_object_text_value(payload_text)
                except (ValueError, json.JSONDecodeError) as exc:
                    if show_message:
                        QMessageBox.warning(
                            self,
                            "Invalid Command",
                            f"entity must be a JSON object.\n{exc}",
                        )
                    return None
            else:
                entity_id = self._spawn_entity_id_edit.text().strip()
                if not entity_id:
                    if show_message:
                        QMessageBox.warning(
                            self,
                            "Invalid Command",
                            "entity_id cannot be blank in Template / Partial mode.",
                        )
                    return None
                base["entity_id"] = entity_id
                base["x"] = int(self._spawn_entity_x_spin.value())
                base["y"] = int(self._spawn_entity_y_spin.value())
                self._set_optional_text_field(
                    base,
                    "template",
                    self._spawn_entity_template_field,
                )
                self._set_optional_text_field(
                    base,
                    "kind",
                    self._spawn_entity_kind_field,
                )
                parameters_text = self._spawn_entity_parameters_edit.toPlainText().strip()
                if parameters_text:
                    try:
                        base["parameters"] = _parse_json_object_text_value(parameters_text)
                    except (ValueError, json.JSONDecodeError) as exc:
                        if show_message:
                            QMessageBox.warning(
                                self,
                                "Invalid Command",
                                f"parameters must be a JSON object.\n{exc}",
                            )
                        return None
            self._set_optional_bool_field(
                base,
                "present",
                self._spawn_entity_present_field,
            )
            self._set_optional_bool_field(
                base,
                "persistent",
                self._spawn_entity_persistent_field,
            )
            return base

        if command_type == "set_area_var":
            area_id = self._set_area_var_area_id_edit.text().strip()
            name = self._set_area_var_name_edit.text().strip()
            value_text = self._set_area_var_value_edit.toPlainText().strip()
            if not area_id or not name or not value_text:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "area_id, name, and value cannot be blank.",
                    )
                return None
            try:
                value = _parse_json_text_value(value_text)
            except (ValueError, json.JSONDecodeError) as exc:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        f"Value must be valid JSON.\n{exc}",
                    )
                return None
            base["area_id"] = area_id
            base["name"] = name
            base["value"] = value
            return base

        if command_type == "set_area_entity_var":
            area_id = self._set_area_entity_var_area_id_edit.text().strip()
            entity_id = self._set_area_entity_var_entity_id_edit.text().strip()
            name = self._set_area_entity_var_name_edit.text().strip()
            value_text = self._set_area_entity_var_value_edit.toPlainText().strip()
            if not area_id or not entity_id or not name or not value_text:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "area_id, entity_id, name, and value cannot be blank.",
                    )
                return None
            try:
                value = _parse_json_text_value(value_text)
            except (ValueError, json.JSONDecodeError) as exc:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        f"Value must be valid JSON.\n{exc}",
                    )
                return None
            base["area_id"] = area_id
            base["entity_id"] = entity_id
            base["name"] = name
            base["value"] = value
            return base

        if command_type == "set_area_entity_field":
            area_id = self._set_area_entity_field_area_id_edit.text().strip()
            entity_id = self._set_area_entity_field_entity_id_edit.text().strip()
            field_name = self._editable_combo_text(self._set_area_entity_field_name_combo)
            value_text = self._set_area_entity_field_value_edit.toPlainText().strip()
            if not area_id or not entity_id or not field_name or not value_text:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "area_id, entity_id, field_name, and value cannot be blank.",
                    )
                return None
            try:
                value = _parse_json_text_value(value_text)
            except (ValueError, json.JSONDecodeError) as exc:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        f"Value must be valid JSON.\n{exc}",
                    )
                return None
            base["area_id"] = area_id
            base["entity_id"] = entity_id
            base["field_name"] = field_name
            base["value"] = value
            return base

        if command_type == "reset_transient_state":
            entity_id = self._reset_transient_entity_id_edit.text().strip()
            if entity_id:
                base["entity_id"] = entity_id
            entity_ids = _parse_string_list_text(
                self._reset_transient_entity_ids_field.optional_value() or ""
            )
            if entity_ids:
                base["entity_ids"] = entity_ids
            include_tags = _parse_string_list_text(
                self._reset_transient_include_tags_field.optional_value() or ""
            )
            if include_tags:
                base["include_tags"] = include_tags
            exclude_tags = _parse_string_list_text(
                self._reset_transient_exclude_tags_field.optional_value() or ""
            )
            if exclude_tags:
                base["exclude_tags"] = exclude_tags
            apply_mode = self._optional_choice_combo_value(self._reset_transient_apply_field)
            if isinstance(apply_mode, str) and apply_mode.strip():
                base["apply"] = apply_mode.strip()
            return base

        if command_type == "reset_persistent_state":
            include_tags = _parse_string_list_text(
                self._reset_persistent_include_tags_field.optional_value() or ""
            )
            if include_tags:
                base["include_tags"] = include_tags
            exclude_tags = _parse_string_list_text(
                self._reset_persistent_exclude_tags_field.optional_value() or ""
            )
            if exclude_tags:
                base["exclude_tags"] = exclude_tags
            apply_mode = self._optional_choice_combo_value(self._reset_persistent_apply_field)
            if isinstance(apply_mode, str) and apply_mode.strip():
                base["apply"] = apply_mode.strip()
            return base

        if command_type == "set_entity_var":
            entity_id = self._set_var_entity_id_edit.text().strip()
            name = self._set_var_name_edit.text().strip()
            value_text = self._set_var_value_edit.toPlainText().strip()
            if not entity_id or not name or not value_text:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id, name, and value cannot be blank.",
                    )
                return None
            try:
                value = json.loads(value_text)
            except json.JSONDecodeError as exc:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        f"Value must be valid JSON.\n{exc}",
                    )
                return None
            base["entity_id"] = entity_id
            base["name"] = name
            base["value"] = value
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_var_persistent_field,
            )
            value_mode = self._optional_choice_combo_value(self._set_var_value_mode_field)
            if isinstance(value_mode, str) and value_mode.strip():
                base["value_mode"] = value_mode.strip()
            return base

        if command_type == "set_visible":
            entity_id = self._set_visible_entity_id_edit.text().strip()
            visible = self._optional_bool_combo_value(self._set_visible_value_field)
            if not entity_id or visible is None:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id must be set and visible must be True or False.",
                    )
                return None
            base["entity_id"] = entity_id
            base["visible"] = visible
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_visible_persistent_field,
            )
            return base

        if command_type == "set_present":
            entity_id = self._set_present_entity_id_edit.text().strip()
            present = self._optional_bool_combo_value(self._set_present_value_field)
            if not entity_id or present is None:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id must be set and present must be True or False.",
                    )
                return None
            base["entity_id"] = entity_id
            base["present"] = present
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_present_persistent_field,
            )
            return base

        if command_type == "set_color":
            entity_id = self._set_color_entity_id_edit.text().strip()
            color_text = self._set_color_value_edit.text().strip()
            if not entity_id or not color_text:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id and color cannot be blank.",
                    )
                return None
            try:
                base["color"] = list(_parse_rgb_text(color_text))
            except ValueError as exc:
                if show_message:
                    QMessageBox.warning(self, "Invalid Command", str(exc))
                return None
            base["entity_id"] = entity_id
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_color_persistent_field,
            )
            return base

        if command_type == "destroy_entity":
            entity_id = self._destroy_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            self._set_optional_bool_field(
                base,
                "persistent",
                self._destroy_entity_persistent_field,
            )
            return base

        if command_type == "set_visual_frame":
            entity_id = self._set_visual_frame_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            self._set_optional_text_field(
                base,
                "visual_id",
                self._set_visual_frame_visual_id_field,
            )
            base["frame"] = int(self._set_visual_frame_spin.value())
            return base

        if command_type == "set_visual_flip_x":
            entity_id = self._set_visual_flip_entity_id_edit.text().strip()
            flip_x = self._optional_bool_combo_value(self._set_visual_flip_x_value_field)
            if not entity_id or flip_x is None:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id must be set and flip_x must be True or False.",
                    )
                return None
            base["entity_id"] = entity_id
            self._set_optional_text_field(
                base,
                "visual_id",
                self._set_visual_flip_visual_id_field,
            )
            base["flip_x"] = flip_x
            return base

        if command_type == "set_input_target":
            action = self._set_input_target_action_edit.text().strip()
            if not action:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "action cannot be blank.",
                    )
                return None
            base["action"] = action
            self._set_optional_text_field(
                base,
                "entity_id",
                self._set_input_target_entity_id_field,
            )
            return base

        if command_type == "route_inputs_to_entity":
            self._set_optional_text_field(
                base,
                "entity_id",
                self._route_inputs_entity_id_field,
            )
            actions = _parse_string_list_text(
                self._route_inputs_actions_field.optional_value() or ""
            )
            if actions:
                base["actions"] = actions
            else:
                base.pop("actions", None)
            return base

        if command_type == "push_input_routes":
            actions = _parse_string_list_text(
                self._push_input_routes_actions_field.optional_value() or ""
            )
            if actions:
                base["actions"] = actions
            else:
                base.pop("actions", None)
            return base

        if command_type == "pop_input_routes":
            return base

        if command_type == "wait_frames":
            base["frames"] = int(self._wait_frames_spin.value())
            return base

        if command_type == "wait_seconds":
            base["seconds"] = float(self._wait_seconds_spin.value())
            return base

        if command_type == "close_dialogue_session":
            return base

        if command_type == "interact_facing":
            entity_id = self._interact_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            direction = self._optional_choice_combo_value(self._interact_direction_field)
            if isinstance(direction, str) and direction.strip():
                base["direction"] = direction.strip()
            return base

        if command_type == "step_entity_active_dialogue":
            entity_id = self._step_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            self._set_optional_int_field(base, "delta", self._step_delta_field)
            self._set_optional_bool_field(base, "wrap", self._step_wrap_field)
            self._set_optional_bool_field(base, "persistent", self._step_persistent_field)
            return base

        if command_type == "set_entity_active_dialogue_by_order":
            entity_id = self._set_active_by_order_entity_id_edit.text().strip()
            if not entity_id:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command",
                        "entity_id cannot be blank.",
                    )
                return None
            base["entity_id"] = entity_id
            base["order"] = int(self._set_active_by_order_spin.value())
            self._set_optional_bool_field(
                base,
                "wrap",
                self._set_active_by_order_wrap_field,
            )
            self._set_optional_bool_field(
                base,
                "persistent",
                self._set_active_by_order_persistent_field,
            )
            return base

        return base

    def _build_generic_command(self, command_type: str, *, show_message: bool) -> dict[str, Any] | None:
        params_text = self._generic_params_edit.toPlainText().strip()
        if not params_text:
            parsed_params: dict[str, Any] = {}
        else:
            try:
                parsed = loads_json_data(
                    params_text,
                    source_name="Command parameters",
                )
            except JsonDataDecodeError as exc:
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command Parameters",
                        f"Could not parse command parameters:\n{exc}",
                    )
                return None
            if not isinstance(parsed, dict):
                if show_message:
                    QMessageBox.warning(
                        self,
                        "Invalid Command Parameters",
                        "Command parameters must be a JSON object.",
                    )
                return None
            parsed_params = copy.deepcopy(parsed)
        parsed_params.pop("type", None)
        if self._command_spec_id_label is not None:
            spec_id = self._command_spec_id_field.optional_value()
            if spec_id is not None:
                parsed_params["id"] = spec_id
            else:
                parsed_params.pop("id", None)
        return {"type": command_type, **parsed_params}

    @staticmethod
    def _set_optional_text_field(
        target: dict[str, Any],
        key: str,
        field: _OptionalTextField,
    ) -> None:
        value = field.optional_value()
        if value is not None:
            target[key] = value
        else:
            target.pop(key, None)

    def _set_entity_refs_field(
        self,
        target: dict[str, Any],
        key: str,
        field: _NamedEntityRefsField,
        *,
        show_message: bool,
    ) -> bool:
        try:
            refs = field.refs()
        except ValueError as exc:
            if show_message:
                QMessageBox.warning(
                    self,
                    "Invalid Named Entity Refs",
                    str(exc),
                )
            return False
        if refs:
            target[key] = refs
        else:
            target.pop(key, None)
        return True

    @staticmethod
    def _set_optional_int_field(
        target: dict[str, Any],
        key: str,
        field: _OptionalIntField,
    ) -> None:
        value = field.optional_value()
        if value is not None:
            target[key] = value
        else:
            target.pop(key, None)

    @staticmethod
    def _set_optional_float_field(
        target: dict[str, Any],
        key: str,
        field: _OptionalFloatField,
    ) -> None:
        value = field.optional_value()
        if value is not None:
            target[key] = value
        else:
            target.pop(key, None)

    @staticmethod
    def _set_optional_bool_field(
        target: dict[str, Any],
        key: str,
        combo: QComboBox,
    ) -> None:
        value = CommandEditorDialog._optional_bool_combo_value(combo)
        if value is None:
            target.pop(key, None)
        else:
            target[key] = value

    def _set_camera_follow_patch_field(
        self,
        target: dict[str, Any],
        key: str,
        field: _CameraFollowPatchField,
        *,
        show_message: bool,
    ) -> bool:
        mode = field.patch_mode()
        if mode == "omit":
            target.pop(key, None)
            return True
        if mode == "clear":
            target[key] = None
            return True
        try:
            target[key] = field.patch_value()
        except ValueError as exc:
            if show_message:
                QMessageBox.warning(self, "Invalid Camera Follow", str(exc))
            return False
        return True

    def _set_camera_rect_patch_field(
        self,
        target: dict[str, Any],
        key: str,
        field: _CameraRectPatchField,
        *,
        show_message: bool,
    ) -> bool:
        mode = field.patch_mode()
        if mode == "omit":
            target.pop(key, None)
            return True
        if mode == "clear":
            target[key] = None
            return True
        try:
            target[key] = field.patch_value()
        except ValueError as exc:
            if show_message:
                QMessageBox.warning(self, "Invalid Camera Rectangle", str(exc))
            return False
        return True

    def _command_from_json_tab(self, *, show_message: bool) -> dict[str, Any]:
        try:
            parsed = loads_json_data(
                self._command_json_edit.toPlainText(),
                source_name="Command JSON",
            )
        except JsonDataDecodeError as exc:
            if show_message:
                QMessageBox.warning(self, "Invalid Command JSON", str(exc))
            raise ValueError("Invalid command JSON") from exc
        if not isinstance(parsed, dict):
            if show_message:
                QMessageBox.warning(
                    self,
                    "Invalid Command JSON",
                    "Command JSON must be a JSON object.",
                )
            raise ValueError("Command JSON must be an object.")
        if not str(parsed.get("type", "")).strip():
            if show_message:
                QMessageBox.warning(
                    self,
                    "Invalid Command JSON",
                    "Command JSON must include a non-empty 'type'.",
                )
            raise ValueError("Command JSON missing type.")
        return copy.deepcopy(parsed)

    def _on_tab_changed(self, index: int) -> None:
        if self._syncing_tabs or self._loading:
            return
        self._syncing_tabs = True
        try:
            if index == 1:
                command = self._build_structured_command(show_message=True)
                if command is None:
                    self._tabs.setCurrentIndex(0)
                    return
                self._command_json_edit.setPlainText(
                    json.dumps(command, indent=2, ensure_ascii=False)
                )
            else:
                try:
                    command = self._command_from_json_tab(show_message=True)
                except ValueError:
                    self._tabs.setCurrentIndex(1)
                    return
                self.load_command(command)
        finally:
            self._syncing_tabs = False

    def _on_command_type_changed(self, command_type: str) -> None:
        if self._loading:
            return
        self._command_header.setText(command_type or "Command")
        self._sync_structured_page(command_type)
        if command_type not in _SUPPORTED_COMMAND_TYPES:
            self._generic_params_edit.setPlainText("{}")

    def _on_browse_dialogue_path(self) -> None:
        if self._dialogue_picker is None:
            return
        selected = self._dialogue_picker(self._dialogue_path_edit.text().strip())
        if selected:
            self._dialogue_path_edit.setText(selected)

    def _on_browse_project_command_id(self) -> None:
        if self._command_picker is None:
            return
        selected = self._command_picker(self._project_command_id_edit.text().strip())
        if selected:
            self._project_command_id_edit.setText(selected)

    def _on_edit_inline_dialogue(self) -> None:
        updated = self._open_inline_dialogue_definition_dialog(
            self._inline_dialogue_definition or {"segments": []}
        )
        if updated is None:
            return
        self._inline_dialogue_definition = copy.deepcopy(updated)
        self._inline_dialogue_summary.setText(
            _summarize_dialogue_definition(self._inline_dialogue_definition)
        )

    def _open_inline_dialogue_definition_dialog(
        self,
        definition: object,
    ) -> dict[str, Any] | None:
        from area_editor.widgets.dialogue_definition_dialog import DialogueDefinitionDialog

        dialog = DialogueDefinitionDialog(
            self,
            area_picker=self._area_picker,
            asset_picker=self._asset_picker,
            entity_picker=self._entity_picker,
            entity_command_picker=self._entity_command_picker,
            entity_dialogue_picker=self._entity_dialogue_picker,
            item_picker=self._item_picker,
            dialogue_picker=self._dialogue_picker,
            command_picker=self._command_picker,
            current_entity_id=self._current_entity_id,
            current_area_id=self._current_area_id,
            current_entity_command_names=self._current_entity_command_names,
            current_entity_dialogue_names=self._current_entity_dialogue_names,
        )
        dialog.setWindowTitle("Edit Inline Dialogue")
        dialog.load_definition(definition)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.definition()


class CommandListDialog(QDialog):
    """Popup manager for one authored command list."""

    def __init__(
        self,
        parent=None,
        *,
        area_picker: Callable[..., str | None] | None = None,
        asset_picker: Callable[..., str | None] | None = None,
        entity_picker: Callable[..., str | None] | None = None,
        entity_command_picker: Callable[..., str | None] | None = None,
        entity_dialogue_picker: Callable[..., str | None] | None = None,
        item_picker: Callable[..., str | None] | None = None,
        dialogue_picker: Callable[[str], str | None] | None = None,
        command_picker: Callable[[str], str | None] | None = None,
        suggested_command_names: list[str] | tuple[str, ...] | None = None,
        command_spec_id_label: str | None = None,
        current_entity_id: str | None = None,
        current_area_id: str | None = None,
        current_entity_command_names: list[str] | tuple[str, ...] | None = None,
        current_entity_dialogue_names: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("CommandListDialog")
        self.setWindowTitle("Edit Commands")
        self.resize(900, 620)

        self._area_picker = area_picker
        self._asset_picker = asset_picker
        self._entity_picker = entity_picker
        self._entity_command_picker = entity_command_picker
        self._entity_dialogue_picker = entity_dialogue_picker
        self._item_picker = item_picker
        self._dialogue_picker = dialogue_picker
        self._command_picker = command_picker
        self._suggested_command_names = tuple(
            str(name).strip()
            for name in (suggested_command_names or ())
            if str(name).strip()
        )
        self._command_spec_id_label = (
            str(command_spec_id_label).strip() or None
            if command_spec_id_label is not None
            else None
        )
        self._current_entity_id = (
            str(current_entity_id).strip() or None if current_entity_id is not None else None
        )
        self._current_area_id = (
            str(current_area_id).strip() or None if current_area_id is not None else None
        )
        self._current_entity_command_names = tuple(
            str(name).strip()
            for name in (current_entity_command_names or ())
            if str(name).strip()
        )
        self._current_entity_dialogue_names = tuple(
            str(name).strip()
            for name in (current_entity_dialogue_names or ())
            if str(name).strip()
        )
        self._commands: list[dict[str, Any]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        note = QLabel(
            "Manage one command list here. Right-click to add or delete commands, drag to reorder, "
            "and double-click or use Edit to modify the selected command."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #666;")
        outer.addWidget(note)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("Commands"))
        hint = QLabel("Right-click to add or delete. Drag to reorder.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        left_layout.addWidget(hint)
        self._command_list = _ReorderListWidget()
        self._command_list.setMinimumWidth(280)
        left_layout.addWidget(self._command_list, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._selection_header = QLabel("No command selected")
        header_font = self._selection_header.font()
        header_font.setBold(True)
        self._selection_header.setFont(header_font)
        right_layout.addWidget(self._selection_header)

        self._selection_summary = QLabel("Select a command to edit it.")
        self._selection_summary.setWordWrap(True)
        right_layout.addWidget(self._selection_summary)

        self._selection_note = QLabel(
            "The command editor opens in a separate popup and keeps unsupported fields through JSON fallback."
        )
        self._selection_note.setWordWrap(True)
        self._selection_note.setStyleSheet("color: #666;")
        right_layout.addWidget(self._selection_note)

        buttons_row = QHBoxLayout()
        buttons_row.setContentsMargins(0, 0, 0, 0)
        self._edit_button = QPushButton("Edit...")
        self._edit_button.setAutoDefault(False)
        self._edit_button.setDefault(False)
        self._edit_button.clicked.connect(self._on_edit_selected)
        buttons_row.addWidget(self._edit_button)
        buttons_row.addStretch(1)
        right_layout.addLayout(buttons_row)
        right_layout.addStretch(1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([320, 520])

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        outer.addWidget(self._buttons)

        self._command_list.currentRowChanged.connect(self._on_command_row_changed)
        self._command_list.itemDoubleClicked.connect(lambda _item: self._on_edit_selected())
        self._command_list.customContextMenuRequested.connect(
            self._on_command_context_menu_requested
        )
        self._command_list.visual_order_changed.connect(self._on_command_visual_order_changed)
        self._sync_selection_state()

    def load_commands(self, commands: object) -> None:
        self._commands = _normalize_command_list(commands)
        self._refresh_command_list()
        if self._command_list.count() > 0:
            self._command_list.setCurrentRow(0)
        self._sync_selection_state()

    def commands(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._commands)

    def _command_at_row(self, row: int) -> dict[str, Any] | None:
        if row < 0 or row >= len(self._commands):
            return None
        return self._commands[row]

    def _refresh_command_list(self) -> None:
        current_row = self._command_list.currentRow()
        self._command_list.blockSignals(True)
        try:
            self._command_list.clear()
            for index, command in enumerate(self._commands):
                item = QListWidgetItem(self._command_summary_text(command, index))
                item.setData(Qt.ItemDataRole.UserRole, index)
                self._command_list.addItem(item)
        finally:
            self._command_list.blockSignals(False)
        if self._command_list.count() > 0:
            self._command_list.setCurrentRow(min(max(current_row, 0), self._command_list.count() - 1))

    def _command_summary_text(self, command: object, index: int) -> str:
        summary = _command_summary(command, index)
        if self._command_spec_id_label is None or not isinstance(command, dict):
            return summary
        spec_id = str(command.get("id", "")).strip()
        if not spec_id:
            return summary
        return f"{summary} [{self._command_spec_id_label}: {spec_id}]"

    def _default_command_for_type(self, command_type: str) -> dict[str, Any]:
        if command_type == "open_dialogue_session":
            return {
                "type": command_type,
                "dialogue_definition": {
                    "segments": [],
                },
            }
        return {"type": command_type}

    def _prompt_command_type(self) -> str | None:
        dialog = _CommandTypePickerDialog(
            self,
            command_names=_known_command_names(),
            suggested_command_names=self._suggested_command_names,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.selected_command_type()

    def _sync_selection_state(self) -> None:
        row = self._command_list.currentRow()
        command = self._command_at_row(row)
        has_selection = command is not None
        self._edit_button.setEnabled(has_selection)
        if command is None:
            self._selection_header.setText("No command selected")
            self._selection_summary.setText("Select a command to edit it.")
            return
        command_type = str(command.get("type", "")).strip() or "(no type)"
        self._selection_header.setText(f"Command {row + 1}: {command_type}")
        self._selection_summary.setText(self._command_summary_text(command, row))

    def _edit_command_at(self, row: int) -> bool:
        command = self._command_at_row(row)
        if command is None:
            return False
        dialog = CommandEditorDialog(
            self,
            area_picker=self._area_picker,
            asset_picker=self._asset_picker,
            entity_picker=self._entity_picker,
            entity_command_picker=self._entity_command_picker,
            entity_dialogue_picker=self._entity_dialogue_picker,
            item_picker=self._item_picker,
            dialogue_picker=self._dialogue_picker,
            command_picker=self._command_picker,
            command_spec_id_label=self._command_spec_id_label,
            current_entity_id=self._current_entity_id,
            current_area_id=self._current_area_id,
            current_entity_command_names=self._current_entity_command_names,
            current_entity_dialogue_names=self._current_entity_dialogue_names,
        )
        dialog.load_command(command)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        self._commands[row] = dialog.command()
        self._refresh_command_list()
        self._command_list.setCurrentRow(row)
        self._sync_selection_state()
        return True

    def _add_command_after(self, after_row: int | None) -> None:
        command_type = self._prompt_command_type()
        if command_type is None:
            return
        dialog = CommandEditorDialog(
            self,
            area_picker=self._area_picker,
            asset_picker=self._asset_picker,
            entity_picker=self._entity_picker,
            entity_command_picker=self._entity_command_picker,
            entity_dialogue_picker=self._entity_dialogue_picker,
            item_picker=self._item_picker,
            dialogue_picker=self._dialogue_picker,
            command_picker=self._command_picker,
            command_spec_id_label=self._command_spec_id_label,
            current_entity_id=self._current_entity_id,
            current_area_id=self._current_area_id,
            current_entity_command_names=self._current_entity_command_names,
            current_entity_dialogue_names=self._current_entity_dialogue_names,
        )
        dialog.load_command(self._default_command_for_type(command_type))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        insert_row = len(self._commands)
        if after_row is not None and 0 <= after_row < len(self._commands):
            insert_row = after_row + 1
        self._commands.insert(insert_row, dialog.command())
        self._refresh_command_list()
        self._command_list.setCurrentRow(insert_row)
        self._sync_selection_state()

    def _delete_command_at(self, row: int) -> None:
        if row < 0 or row >= len(self._commands):
            return
        del self._commands[row]
        self._refresh_command_list()
        if self._command_list.count() > 0:
            self._command_list.setCurrentRow(min(row, self._command_list.count() - 1))
        self._sync_selection_state()

    def _on_command_context_menu_requested(self, position) -> None:
        item = self._command_list.itemAt(position)
        target_row = self._command_list.row(item) if item is not None else -1
        menu = QMenu(self)
        add_action = menu.addAction("Add Command...")
        edit_action = None
        delete_action = None
        if target_row >= 0:
            edit_action = menu.addAction("Edit...")
            menu.addSeparator()
            delete_action = menu.addAction("Delete")
        chosen = menu.exec(self._command_list.viewport().mapToGlobal(position))
        if chosen == add_action:
            self._add_command_after(target_row if target_row >= 0 else None)
        elif edit_action is not None and chosen == edit_action:
            self._edit_command_at(target_row)
        elif delete_action is not None and chosen == delete_action:
            self._delete_command_at(target_row)

    def _on_command_visual_order_changed(self, visual_order: list[int]) -> None:
        if len(visual_order) != len(self._commands):
            self._refresh_command_list()
            self._sync_selection_state()
            return
        current_command = self._command_at_row(self._command_list.currentRow())
        reordered = [
            self._commands[index]
            for index in visual_order
            if 0 <= index < len(self._commands)
        ]
        if len(reordered) != len(self._commands):
            self._refresh_command_list()
            self._sync_selection_state()
            return
        self._commands[:] = reordered
        self._refresh_command_list()
        if current_command is not None and current_command in self._commands:
            self._command_list.setCurrentRow(self._commands.index(current_command))
        self._sync_selection_state()

    def _on_command_row_changed(self, _row: int) -> None:
        self._sync_selection_state()

    def _on_edit_selected(self) -> None:
        self._edit_command_at(self._command_list.currentRow())

    def accept(self) -> None:  # noqa: D401
        super().accept()
