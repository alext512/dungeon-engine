"""Structured editor for authored entity visuals."""

from __future__ import annotations

import copy
import json
import re
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from area_editor.json_io import JsonDataDecodeError, dumps_for_clone, loads_json_data
from area_editor.widgets.reference_picker_support import call_reference_picker_callback

_INT_RE = re.compile(r"^[+-]?\d+$")
_NUMBER_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")
_FACINGS = ("up", "down", "left", "right")


def parse_visuals(raw_visuals: object) -> list[dict[str, Any]]:
    """Return a structured-editor-safe copy of a visuals array."""
    if raw_visuals is None:
        return []
    if not isinstance(raw_visuals, list):
        raise ValueError("Visuals must be a JSON array.")
    visuals: list[dict[str, Any]] = []
    for index, raw_visual in enumerate(raw_visuals):
        if not isinstance(raw_visual, dict):
            raise ValueError(f"visuals[{index}] must be a JSON object.")
        raw_animations = raw_visual.get("animations")
        if raw_animations is not None:
            _parse_animations(raw_animations)
        visuals.append(copy.deepcopy(raw_visual))
    return visuals


def summarize_visuals(visuals: list[dict[str, Any]]) -> str:
    if not visuals:
        return "No visuals"
    if len(visuals) == 1:
        return "1 visual"
    return f"{len(visuals)} visuals"


def _parse_animations(raw_animations: object) -> dict[str, dict[str, Any]]:
    if raw_animations is None:
        return {}
    if not isinstance(raw_animations, dict):
        raise ValueError("Visual animations must be a JSON object.")
    animations: dict[str, dict[str, Any]] = {}
    for raw_name, raw_clip in raw_animations.items():
        name = str(raw_name).strip()
        if not name:
            raise ValueError("Visual animation names must not be blank.")
        if not isinstance(raw_clip, dict):
            raise ValueError(f"Visual animation '{name}' must be a JSON object.")
        animations[name] = copy.deepcopy(raw_clip)
    return animations


def _format_edit_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _format_list_value(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list) and all(
        isinstance(item, (str, int, float)) and not isinstance(item, bool)
        for item in value
    ):
        return ", ".join(str(item) for item in value)
    return _format_edit_value(value)


def _parse_scalar_text(text: str, *, source_name: str) -> object | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith(("{", "[", '"')):
        try:
            return loads_json_data(stripped, source_name=source_name)
        except JsonDataDecodeError as exc:
            raise ValueError(f"{source_name} must be valid JSON.\n{exc}") from exc
    lower = stripped.lower()
    if lower in {"true", "false", "null"}:
        try:
            return loads_json_data(lower, source_name=source_name)
        except JsonDataDecodeError as exc:
            raise ValueError(f"{source_name} must be valid JSON.\n{exc}") from exc
    if _INT_RE.match(stripped):
        return int(stripped)
    if _NUMBER_RE.match(stripped):
        return float(stripped)
    return stripped


def _parse_intish_text(text: str, *, source_name: str) -> object | None:
    value = _parse_scalar_text(text, source_name=source_name)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{source_name} must be a number or token.")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, (dict, str)):
        return value
    raise ValueError(f"{source_name} must be a number or token.")


def _parse_numberish_text(text: str, *, source_name: str) -> object | None:
    value = _parse_scalar_text(text, source_name=source_name)
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{source_name} must be a number or token.")
    if isinstance(value, (int, float, dict, str)):
        return value
    raise ValueError(f"{source_name} must be a number or token.")


def _parse_sequence_text(text: str, *, source_name: str) -> object | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith(("[", "{", '"')) or stripped.startswith("$"):
        value = _parse_scalar_text(stripped, source_name=source_name)
        if isinstance(value, list) or isinstance(value, dict) or isinstance(value, str):
            return value
        raise ValueError(f"{source_name} must be an array or token.")
    values: list[object] = []
    for raw_part in stripped.split(","):
        part = raw_part.strip()
        if not part:
            continue
        values.append(int(part) if _INT_RE.match(part) else part)
    return values


def _parse_rgb_text(text: str, *, source_name: str) -> object | None:
    stripped = text.strip()
    if not stripped:
        return None
    if stripped.startswith("$"):
        return stripped
    if stripped.startswith("["):
        try:
            value = loads_json_data(stripped, source_name=source_name)
        except JsonDataDecodeError as exc:
            raise ValueError(f"{source_name} must be valid JSON.\n{exc}") from exc
    else:
        parts = [part.strip() for part in stripped.split(",") if part.strip()]
        value = [int(part) if _INT_RE.match(part) else part for part in parts]
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{source_name} must be three RGB values.")
    return value


def _set_optional_key(target: dict[str, Any], key: str, value: object | None) -> None:
    if value is None:
        target.pop(key, None)
    else:
        target[key] = value


def _set_tristate_value(check: QCheckBox, value: object) -> None:
    if value is None:
        check.setCheckState(Qt.CheckState.PartiallyChecked)
    elif bool(value):
        check.setCheckState(Qt.CheckState.Checked)
    else:
        check.setCheckState(Qt.CheckState.Unchecked)


def _tristate_value(check: QCheckBox) -> bool | None:
    state = check.checkState()
    if state == Qt.CheckState.PartiallyChecked:
        return None
    return state == Qt.CheckState.Checked


class _ReorderListWidget(QListWidget):
    """List widget that emits one stable visual-order snapshot after drops."""

    visual_order_change_started = Signal()
    visual_order_changed = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        self.visual_order_change_started.emit()
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


class VisualAnimationsDialog(QDialog):
    """Small structured editor for a visual's named animation clips."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Animation Clips")
        self.resize(620, 360)
        self._clips: list[dict[str, Any]] = []
        self._loading = False
        self._current_row = -1
        self._reordering = False

        layout = QVBoxLayout(self)
        body = QHBoxLayout()
        layout.addLayout(body, 1)

        left = QVBoxLayout()
        left.addWidget(QLabel("Clips"))
        hint = QLabel("Right-click to add, duplicate, or remove. Drag to reorder.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        left.addWidget(hint)
        self._list = _ReorderListWidget()
        self._list.currentRowChanged.connect(self._on_current_row_changed)
        self._list.customContextMenuRequested.connect(
            self._on_clip_context_menu_requested
        )
        self._list.visual_order_change_started.connect(
            self._on_clip_order_change_started
        )
        self._list.visual_order_changed.connect(self._on_clip_visual_order_changed)
        self._list.itemDoubleClicked.connect(lambda _item: self._name_edit.setFocus())
        left.addWidget(self._list, 1)
        body.addLayout(left, 1)

        right = QWidget()
        form = QFormLayout(right)
        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(self._on_form_changed)
        form.addRow("name", self._name_edit)

        self._frames_edit = QLineEdit()
        self._frames_edit.setPlaceholderText("0, 1, 2")
        self._frames_edit.textChanged.connect(self._on_form_changed)
        form.addRow("frames", self._frames_edit)

        self._flip_x_check = QCheckBox("Use horizontal flip")
        self._flip_x_check.setTristate(True)
        self._flip_x_check.setToolTip("Mixed state omits the clip-level field.")
        self._flip_x_check.stateChanged.connect(self._on_form_changed)
        form.addRow("flip_x", self._flip_x_check)

        self._preserve_phase_check = QCheckBox("Preserve animation phase")
        self._preserve_phase_check.setTristate(True)
        self._preserve_phase_check.setToolTip(
            "Mixed state omits the clip-level field."
        )
        self._preserve_phase_check.stateChanged.connect(self._on_form_changed)
        form.addRow("preserve_phase", self._preserve_phase_check)
        body.addWidget(right, 2)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_animations(self, animations: object) -> None:
        parsed = _parse_animations(animations)
        self._clips = [
            {"name": name, "data": copy.deepcopy(data)}
            for name, data in parsed.items()
        ]
        self._refresh_list(select_row=0 if self._clips else -1)

    def animations(self) -> dict[str, dict[str, Any]]:
        self._apply_form_to_current()
        output: dict[str, dict[str, Any]] = {}
        for clip in self._clips:
            name = str(clip.get("name", "")).strip()
            output[name] = copy.deepcopy(clip.get("data", {}))
        return output

    def accept(self) -> None:
        try:
            self._apply_form_to_current()
            self._validate_names()
            self.animations()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Animation Clip", str(exc))
            return
        super().accept()

    def _validate_names(self) -> None:
        seen: set[str] = set()
        for clip in self._clips:
            name = str(clip.get("name", "")).strip()
            if not name:
                raise ValueError("Animation clip names must not be blank.")
            if name in seen:
                raise ValueError(f"Duplicate animation clip '{name}'.")
            seen.add(name)

    def _refresh_list(self, *, select_row: int | None = None) -> None:
        self._loading = True
        try:
            self._list.clear()
            for index, clip in enumerate(self._clips):
                item = QListWidgetItem(str(clip.get("name", "")).strip() or "clip")
                item.setData(Qt.ItemDataRole.UserRole, index)
                self._list.addItem(item)
            if select_row is not None:
                if 0 <= select_row < len(self._clips):
                    self._list.setCurrentRow(select_row)
                    self._load_form_from_row(select_row)
                else:
                    self._list.setCurrentRow(-1)
                    self._load_form_from_row(-1)
        finally:
            self._loading = False
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        has_clip = 0 <= self._list.currentRow() < len(self._clips)
        self._set_form_enabled(has_clip)

    def _set_form_enabled(self, enabled: bool) -> None:
        for widget in (
            self._name_edit,
            self._frames_edit,
            self._flip_x_check,
            self._preserve_phase_check,
        ):
            widget.setEnabled(enabled)

    def _load_form_from_row(self, row: int) -> None:
        self._loading = True
        try:
            self._current_row = row
            if not (0 <= row < len(self._clips)):
                self._name_edit.clear()
                self._frames_edit.clear()
                _set_tristate_value(self._flip_x_check, None)
                _set_tristate_value(self._preserve_phase_check, None)
                return
            clip = self._clips[row]
            data = clip.get("data", {})
            self._name_edit.setText(str(clip.get("name", "")))
            self._frames_edit.setText(_format_list_value(data.get("frames")))
            _set_tristate_value(
                self._flip_x_check,
                data.get("flip_x") if "flip_x" in data else None,
            )
            _set_tristate_value(
                self._preserve_phase_check,
                data.get("preserve_phase") if "preserve_phase" in data else None,
            )
        finally:
            self._loading = False
        self._sync_buttons()

    def _apply_form_to_current(self) -> None:
        row = self._current_row
        if not (0 <= row < len(self._clips)):
            return
        clip = self._clips[row]
        data = copy.deepcopy(clip.get("data", {}))
        name = self._name_edit.text().strip()
        clip["name"] = name
        frames_value = _parse_sequence_text(
            self._frames_edit.text(),
            source_name="Animation frames",
        )
        _set_optional_key(data, "frames", frames_value)
        _set_optional_key(data, "flip_x", _tristate_value(self._flip_x_check))
        _set_optional_key(
            data,
            "preserve_phase",
            _tristate_value(self._preserve_phase_check),
        )
        clip["data"] = data
        item = self._list.item(row)
        if item is not None:
            item.setText(name or "clip")
            item.setData(Qt.ItemDataRole.UserRole, row)

    def _on_current_row_changed(self, row: int) -> None:
        if self._loading or self._reordering:
            return
        try:
            self._apply_form_to_current()
        except ValueError:
            pass
        self._load_form_from_row(row)

    def _on_form_changed(self, *_args: object) -> None:
        if self._loading:
            return
        try:
            self._apply_form_to_current()
        except ValueError:
            pass

    def _on_add_clicked(self) -> None:
        self._add_clip_after(None)

    def _add_clip_after(self, after_row: int | None) -> None:
        names = {str(clip.get("name", "")).strip() for clip in self._clips}
        base = "idle"
        name = base
        index = 2
        while name in names:
            name = f"{base}_{index}"
            index += 1
        insert_row = len(self._clips)
        if after_row is not None and 0 <= after_row < len(self._clips):
            insert_row = after_row + 1
        self._clips.insert(insert_row, {"name": name, "data": {"frames": [0]}})
        self._refresh_list(select_row=insert_row)

    def _on_duplicate_clicked(self) -> None:
        self._duplicate_clip_at(self._list.currentRow())

    def _duplicate_clip_at(self, row: int) -> None:
        if not (0 <= row < len(self._clips)):
            return
        self._apply_form_to_current()
        names = {str(clip.get("name", "")).strip() for clip in self._clips}
        source_name = str(self._clips[row].get("name", "")).strip() or "clip"
        name = f"{source_name}_copy"
        index = 2
        while name in names:
            name = f"{source_name}_copy_{index}"
            index += 1
        copied = copy.deepcopy(self._clips[row])
        copied["name"] = name
        self._clips.insert(row + 1, copied)
        self._refresh_list(select_row=row + 1)

    def _on_remove_clicked(self) -> None:
        self._remove_clip_at(self._list.currentRow())

    def _remove_clip_at(self, row: int) -> None:
        if not (0 <= row < len(self._clips)):
            return
        self._clips.pop(row)
        self._refresh_list(select_row=min(row, len(self._clips) - 1))

    def _move_clip(self, row: int, delta: int) -> None:
        target = row + delta
        if not (0 <= row < len(self._clips)) or not (0 <= target < len(self._clips)):
            return
        self._apply_form_to_current()
        self._clips[row], self._clips[target] = self._clips[target], self._clips[row]
        self._refresh_list(select_row=target)

    def _on_clip_context_menu_requested(self, position) -> None:
        item = self._list.itemAt(position)
        target_row = self._list.row(item) if item is not None else -1
        if target_row >= 0:
            self._list.setCurrentRow(target_row)
        menu = QMenu(self)
        add_action = menu.addAction("Add Clip")
        duplicate_action = None
        remove_action = None
        move_up_action = None
        move_down_action = None
        if target_row >= 0:
            duplicate_action = menu.addAction("Duplicate")
            remove_action = menu.addAction("Remove")
            menu.addSeparator()
            move_up_action = menu.addAction("Move Up")
            move_up_action.setEnabled(target_row > 0)
            move_down_action = menu.addAction("Move Down")
            move_down_action.setEnabled(target_row < len(self._clips) - 1)
        chosen = menu.exec(self._list.viewport().mapToGlobal(position))
        if chosen == add_action:
            self._add_clip_after(target_row if target_row >= 0 else None)
        elif duplicate_action is not None and chosen == duplicate_action:
            self._duplicate_clip_at(target_row)
        elif remove_action is not None and chosen == remove_action:
            self._remove_clip_at(target_row)
        elif move_up_action is not None and chosen == move_up_action:
            self._move_clip(target_row, -1)
        elif move_down_action is not None and chosen == move_down_action:
            self._move_clip(target_row, 1)

    def _on_clip_order_change_started(self) -> None:
        self._apply_form_to_current()
        self._reordering = True

    def _on_clip_visual_order_changed(self, visual_order: list[int]) -> None:
        selected_item = self._list.currentItem()
        selected_source = (
            selected_item.data(Qt.ItemDataRole.UserRole)
            if selected_item is not None
            else None
        )
        self._reordering = False
        if sorted(visual_order) != list(range(len(self._clips))):
            self._refresh_list()
            return
        self._clips[:] = [self._clips[index] for index in visual_order]
        selected_row = (
            visual_order.index(selected_source)
            if isinstance(selected_source, int) and selected_source in visual_order
            else min(self._list.currentRow(), len(self._clips) - 1)
        )
        self._refresh_list(select_row=selected_row)


class VisualDefinitionDialog(QDialog):
    """Popup editor for one authored visual definition."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        asset_picker: Callable[..., str | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit Visual")
        self.resize(660, 560)
        self._asset_picker = asset_picker
        self._visual: dict[str, Any] = {}
        self._loading = False

        layout = QVBoxLayout(self)

        self._warning_label = QLabel("")
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #a25b00;")
        self._warning_label.hide()
        layout.addWidget(self._warning_label)

        form_host = QWidget()
        form = QFormLayout(form_host)

        self._id_edit = QLineEdit()
        self._id_edit.textChanged.connect(self._on_form_changed)
        form.addRow("id", self._id_edit)

        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.textChanged.connect(self._on_form_changed)
        path_row.addWidget(self._path_edit, 1)
        self._browse_path_button = QPushButton("Browse...")
        self._browse_path_button.clicked.connect(self._on_browse_path_clicked)
        self._browse_path_button.setEnabled(self._asset_picker is not None)
        path_row.addWidget(self._browse_path_button)
        path_widget = QWidget()
        path_widget.setLayout(path_row)
        form.addRow("path", path_widget)

        self._frame_width_edit = QLineEdit()
        self._frame_width_edit.setPlaceholderText("16")
        self._frame_width_edit.textChanged.connect(self._on_form_changed)
        form.addRow("frame_width", self._frame_width_edit)

        self._frame_height_edit = QLineEdit()
        self._frame_height_edit.setPlaceholderText("16")
        self._frame_height_edit.textChanged.connect(self._on_form_changed)
        form.addRow("frame_height", self._frame_height_edit)

        self._frames_edit = QLineEdit()
        self._frames_edit.setPlaceholderText("0, 1, 2")
        self._frames_edit.textChanged.connect(self._on_form_changed)
        form.addRow("frames", self._frames_edit)

        self._default_animation_edit = QLineEdit()
        self._default_animation_edit.textChanged.connect(self._on_form_changed)
        form.addRow("default_animation", self._default_animation_edit)

        self._facing_edits: dict[str, QLineEdit] = {}
        facing_widget = QWidget()
        facing_layout = QFormLayout(facing_widget)
        facing_layout.setContentsMargins(0, 0, 0, 0)
        for facing in _FACINGS:
            edit = QLineEdit()
            edit.textChanged.connect(self._on_form_changed)
            self._facing_edits[facing] = edit
            facing_layout.addRow(facing, edit)
        form.addRow("default_animation_by_facing", facing_widget)

        self._animation_fps_edit = QLineEdit()
        self._animation_fps_edit.setPlaceholderText("8")
        self._animation_fps_edit.textChanged.connect(self._on_form_changed)
        form.addRow("animation_fps", self._animation_fps_edit)

        self._animate_when_moving_check = QCheckBox("Animate only while moving")
        self._animate_when_moving_check.setTristate(True)
        self._animate_when_moving_check.setToolTip("Mixed state omits the field.")
        self._animate_when_moving_check.stateChanged.connect(self._on_form_changed)
        form.addRow("animate_when_moving", self._animate_when_moving_check)

        self._flip_x_check = QCheckBox("Flip horizontally")
        self._flip_x_check.setTristate(True)
        self._flip_x_check.setToolTip("Mixed state omits the field.")
        self._flip_x_check.stateChanged.connect(self._on_form_changed)
        form.addRow("flip_x", self._flip_x_check)

        self._visible_check = QCheckBox("Visible")
        self._visible_check.setTristate(True)
        self._visible_check.setToolTip("Mixed state omits the field.")
        self._visible_check.stateChanged.connect(self._on_form_changed)
        form.addRow("visible", self._visible_check)

        self._tint_edit = QLineEdit()
        self._tint_edit.setPlaceholderText("255, 255, 255")
        self._tint_edit.textChanged.connect(self._on_form_changed)
        form.addRow("tint", self._tint_edit)

        self._offset_x_edit = QLineEdit()
        self._offset_x_edit.setPlaceholderText("0")
        self._offset_x_edit.textChanged.connect(self._on_form_changed)
        form.addRow("offset_x", self._offset_x_edit)

        self._offset_y_edit = QLineEdit()
        self._offset_y_edit.setPlaceholderText("0")
        self._offset_y_edit.textChanged.connect(self._on_form_changed)
        form.addRow("offset_y", self._offset_y_edit)

        self._draw_order_edit = QLineEdit()
        self._draw_order_edit.setPlaceholderText("0")
        self._draw_order_edit.textChanged.connect(self._on_form_changed)
        form.addRow("draw_order", self._draw_order_edit)

        clips_row = QHBoxLayout()
        self._animations_summary = QLabel("No clips")
        clips_row.addWidget(self._animations_summary, 1)
        self._edit_animations_button = QPushButton("Edit Clips...")
        self._edit_animations_button.clicked.connect(self._on_edit_animations_clicked)
        clips_row.addWidget(self._edit_animations_button)
        clips_widget = QWidget()
        clips_widget.setLayout(clips_row)
        form.addRow("animations", clips_widget)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(form_host)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_visual(self, visual: dict[str, Any]) -> None:
        self._visual = copy.deepcopy(visual)
        self._load_form()

    def visual(self) -> dict[str, Any]:
        self._apply_form(raise_errors=True)
        return copy.deepcopy(self._visual)

    def accept(self) -> None:
        try:
            self._apply_form(raise_errors=True)
            parse_visuals([self._visual])
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Visual", str(exc))
            return
        super().accept()

    def _load_form(self) -> None:
        self._loading = True
        try:
            visual = self._visual
            self._id_edit.setText(_format_edit_value(visual.get("id")))
            self._path_edit.setText(_format_edit_value(visual.get("path")))
            self._frame_width_edit.setText(_format_edit_value(visual.get("frame_width")))
            self._frame_height_edit.setText(
                _format_edit_value(visual.get("frame_height"))
            )
            self._frames_edit.setText(_format_list_value(visual.get("frames")))
            self._default_animation_edit.setText(
                _format_edit_value(visual.get("default_animation"))
            )
            raw_facing = visual.get("default_animation_by_facing")
            facing_map = raw_facing if isinstance(raw_facing, dict) else {}
            for facing, edit in self._facing_edits.items():
                edit.setText(_format_edit_value(facing_map.get(facing)))
            self._animation_fps_edit.setText(
                _format_edit_value(visual.get("animation_fps"))
            )
            _set_tristate_value(
                self._animate_when_moving_check,
                visual.get("animate_when_moving")
                if "animate_when_moving" in visual
                else None,
            )
            _set_tristate_value(
                self._flip_x_check,
                visual.get("flip_x") if "flip_x" in visual else None,
            )
            _set_tristate_value(
                self._visible_check,
                visual.get("visible") if "visible" in visual else None,
            )
            self._tint_edit.setText(_format_list_value(visual.get("tint")))
            self._offset_x_edit.setText(_format_edit_value(visual.get("offset_x")))
            self._offset_y_edit.setText(_format_edit_value(visual.get("offset_y")))
            self._draw_order_edit.setText(_format_edit_value(visual.get("draw_order")))
            self._sync_animations_summary()
        finally:
            self._loading = False

    def _sync_animations_summary(self) -> None:
        try:
            animations = _parse_animations(self._visual.get("animations"))
        except ValueError:
            self._animations_summary.setText("Raw JSON only")
            return
        count = len(animations)
        if count == 0:
            self._animations_summary.setText("No clips")
        elif count == 1:
            self._animations_summary.setText("1 clip")
        else:
            self._animations_summary.setText(f"{count} clips")

    def _apply_form(self, *, raise_errors: bool = False) -> None:
        visual = self._visual
        try:
            _set_optional_key(
                visual,
                "id",
                _parse_scalar_text(self._id_edit.text(), source_name="Visual id"),
            )
            _set_optional_key(
                visual,
                "path",
                _parse_scalar_text(self._path_edit.text(), source_name="Visual path"),
            )
            _set_optional_key(
                visual,
                "frame_width",
                _parse_intish_text(
                    self._frame_width_edit.text(),
                    source_name="Visual frame_width",
                ),
            )
            _set_optional_key(
                visual,
                "frame_height",
                _parse_intish_text(
                    self._frame_height_edit.text(),
                    source_name="Visual frame_height",
                ),
            )
            _set_optional_key(
                visual,
                "frames",
                _parse_sequence_text(
                    self._frames_edit.text(),
                    source_name="Visual frames",
                ),
            )
            _set_optional_key(
                visual,
                "default_animation",
                _parse_scalar_text(
                    self._default_animation_edit.text(),
                    source_name="Visual default_animation",
                ),
            )
            facing_map: dict[str, object] = {}
            for facing, edit in self._facing_edits.items():
                value = _parse_scalar_text(
                    edit.text(),
                    source_name=f"Visual default_animation_by_facing.{facing}",
                )
                if value is not None:
                    facing_map[facing] = value
            _set_optional_key(visual, "default_animation_by_facing", facing_map or None)
            _set_optional_key(
                visual,
                "animation_fps",
                _parse_numberish_text(
                    self._animation_fps_edit.text(),
                    source_name="Visual animation_fps",
                ),
            )
            _set_optional_key(
                visual,
                "animate_when_moving",
                _tristate_value(self._animate_when_moving_check),
            )
            _set_optional_key(visual, "flip_x", _tristate_value(self._flip_x_check))
            _set_optional_key(visual, "visible", _tristate_value(self._visible_check))
            _set_optional_key(
                visual,
                "tint",
                _parse_rgb_text(self._tint_edit.text(), source_name="Visual tint"),
            )
            _set_optional_key(
                visual,
                "offset_x",
                _parse_numberish_text(
                    self._offset_x_edit.text(),
                    source_name="Visual offset_x",
                ),
            )
            _set_optional_key(
                visual,
                "offset_y",
                _parse_numberish_text(
                    self._offset_y_edit.text(),
                    source_name="Visual offset_y",
                ),
            )
            _set_optional_key(
                visual,
                "draw_order",
                _parse_numberish_text(
                    self._draw_order_edit.text(),
                    source_name="Visual draw_order",
                ),
            )
        except ValueError as exc:
            self._warning_label.setText(str(exc))
            self._warning_label.show()
            if raise_errors:
                raise
            return
        self._warning_label.hide()
        self._sync_animations_summary()

    def _on_form_changed(self, *_args: object) -> None:
        if self._loading:
            return
        self._apply_form()

    def _on_browse_path_clicked(self) -> None:
        selected = call_reference_picker_callback(
            self._asset_picker,
            self._path_edit.text().strip(),
        )
        if selected:
            self._path_edit.setText(selected)

    def _on_edit_animations_clicked(self) -> None:
        self._apply_form()
        try:
            _parse_animations(self._visual.get("animations"))
        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Animation Clips",
                f"Animations are not using the supported object shape.\n{exc}",
            )
            return
        dialog = VisualAnimationsDialog(self)
        dialog.load_animations(self._visual.get("animations"))
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return
        animations = dialog.animations()
        if animations:
            self._visual["animations"] = animations
        else:
            self._visual.pop("animations", None)
        self._sync_animations_summary()


class EntityVisualsEditor(QWidget):
    """List manager for an entity template's visuals array."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._visuals: list[dict[str, Any]] = []
        self._loading = False
        self._editing_enabled = False
        self._asset_picker: Callable[..., str | None] | None = None
        self._reordering = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._warning_label = QLabel("")
        self._warning_label.setWordWrap(True)
        self._warning_label.setStyleSheet("color: #a25b00;")
        self._warning_label.hide()
        layout.addWidget(self._warning_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self._summary_label = QLabel("No visuals")
        left_layout.addWidget(self._summary_label)
        hint = QLabel("Right-click to add or delete. Drag to reorder.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        left_layout.addWidget(hint)
        self._list = _ReorderListWidget()
        self._list.setMinimumWidth(260)
        self._list.currentRowChanged.connect(self._on_current_row_changed)
        self._list.customContextMenuRequested.connect(
            self._on_visual_context_menu_requested
        )
        self._list.visual_order_change_started.connect(
            self._on_visual_order_change_started
        )
        self._list.visual_order_changed.connect(self._on_visual_order_changed)
        self._list.itemDoubleClicked.connect(
            lambda item: self._edit_visual_at(self._list.row(item))
        )
        left_layout.addWidget(self._list, 1)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._selection_header = QLabel("No visual selected")
        header_font = self._selection_header.font()
        header_font.setBold(True)
        self._selection_header.setFont(header_font)
        right_layout.addWidget(self._selection_header)

        self._selection_summary = QLabel("Select a visual to edit it.")
        self._selection_summary.setWordWrap(True)
        right_layout.addWidget(self._selection_summary)

        self._selection_details = QLabel("")
        self._selection_details.setWordWrap(True)
        self._selection_details.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        right_layout.addWidget(self._selection_details)

        edit_row = QHBoxLayout()
        self._edit_button = QPushButton("Edit...")
        self._edit_button.clicked.connect(lambda: self._edit_visual_at(self._list.currentRow()))
        edit_row.addWidget(self._edit_button)
        edit_row.addStretch(1)
        right_layout.addLayout(edit_row)
        right_layout.addStretch(1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 520])

        self.set_editing_enabled(False)

    def set_asset_picker(
        self,
        picker: Callable[..., str | None] | None,
    ) -> None:
        self._asset_picker = picker

    def load_visuals(self, visuals: list[dict[str, Any]]) -> None:
        self._warning_label.hide()
        self._visuals = dumps_for_clone(visuals)
        self._refresh_list(select_row=0 if self._visuals else -1)

    def visuals(self) -> list[dict[str, Any]]:
        return dumps_for_clone(self._visuals)

    def visuals_text(self) -> str:
        return json.dumps(self.visuals(), indent=2, ensure_ascii=False)

    def set_editing_enabled(self, enabled: bool) -> None:
        self._editing_enabled = enabled
        self._sync_selection_state()

    def _refresh_list(self, *, select_row: int | None = None) -> None:
        self._loading = True
        try:
            self._list.clear()
            for index, visual in enumerate(self._visuals):
                item = QListWidgetItem(self._visual_label(index, visual))
                item.setData(Qt.ItemDataRole.UserRole, index)
                self._list.addItem(item)
            if select_row is not None:
                if 0 <= select_row < len(self._visuals):
                    self._list.setCurrentRow(select_row)
                else:
                    self._list.setCurrentRow(-1)
        finally:
            self._loading = False
        self._sync_selection_state()

    def _visual_label(self, index: int, visual: dict[str, Any]) -> str:
        visual_id = str(visual.get("id", "")).strip()
        path = str(visual.get("path", "")).strip()
        label = visual_id or path.rsplit("/", 1)[-1] or "visual"
        return f"{index + 1}. {label}"

    def _visual_at_row(self, row: int) -> dict[str, Any] | None:
        if 0 <= row < len(self._visuals):
            return self._visuals[row]
        return None

    def _sync_selection_state(self) -> None:
        self._summary_label.setText(summarize_visuals(self._visuals))
        self._list.setEnabled(True)
        self._list.setDragEnabled(self._editing_enabled)
        self._list.setAcceptDrops(self._editing_enabled)
        row = self._list.currentRow()
        visual = self._visual_at_row(row)
        has_visual = visual is not None
        self._edit_button.setEnabled(self._editing_enabled and has_visual)
        if visual is None:
            self._selection_header.setText("No visual selected")
            self._selection_summary.setText("Select a visual to edit it.")
            self._selection_details.clear()
            return
        visual_id = str(visual.get("id", "")).strip() or "(no id)"
        self._selection_header.setText(f"Visual {row + 1}: {visual_id}")
        self._selection_summary.setText(self._visual_summary_text(visual))
        self._selection_details.setText(self._visual_detail_text(visual))

    def _visual_summary_text(self, visual: dict[str, Any]) -> str:
        path = str(visual.get("path", "")).strip()
        size_parts = [
            _format_edit_value(visual.get("frame_width")),
            _format_edit_value(visual.get("frame_height")),
        ]
        size = " x ".join(part for part in size_parts if part)
        details: list[str] = []
        if path:
            details.append(path)
        if size:
            details.append(size)
        animation = str(visual.get("default_animation", "")).strip()
        if animation:
            details.append(f"default: {animation}")
        return " | ".join(details) if details else "Visual has no path yet."

    def _visual_detail_text(self, visual: dict[str, Any]) -> str:
        try:
            animation_count = len(_parse_animations(visual.get("animations")))
            animation_text = (
                "No clips"
                if animation_count == 0
                else "1 clip"
                if animation_count == 1
                else f"{animation_count} clips"
            )
        except ValueError:
            animation_text = "Raw JSON only"
        rows = [
            ("path", _format_edit_value(visual.get("path"))),
            ("frames", _format_list_value(visual.get("frames"))),
            ("default_animation", _format_edit_value(visual.get("default_animation"))),
            ("animation_fps", _format_edit_value(visual.get("animation_fps"))),
            ("animations", animation_text),
            ("visible", _format_edit_value(visual.get("visible"))),
            ("flip_x", _format_edit_value(visual.get("flip_x"))),
            ("tint", _format_list_value(visual.get("tint"))),
            ("offset", self._offset_summary(visual)),
            ("draw_order", _format_edit_value(visual.get("draw_order"))),
        ]
        return "\n".join(
            f"{name}: {value}" for name, value in rows if str(value).strip()
        )

    def _offset_summary(self, visual: dict[str, Any]) -> str:
        offset_x = _format_edit_value(visual.get("offset_x"))
        offset_y = _format_edit_value(visual.get("offset_y"))
        if offset_x or offset_y:
            return f"{offset_x or 0}, {offset_y or 0}"
        return ""

    def _default_visual(self) -> dict[str, Any]:
        ids = {str(visual.get("id", "")).strip() for visual in self._visuals}
        visual_id = "main" if "main" not in ids else f"visual_{len(self._visuals) + 1}"
        while visual_id in ids:
            visual_id = f"visual_{len(ids) + 1}"
        return {
            "id": visual_id,
            "path": "",
            "frame_width": 16,
            "frame_height": 16,
            "frames": [0],
        }

    def _open_visual_dialog(
        self,
        *,
        title: str,
        visual: dict[str, Any],
    ) -> dict[str, Any] | None:
        dialog = VisualDefinitionDialog(self, asset_picker=self._asset_picker)
        dialog.setWindowTitle(title)
        dialog.load_visual(visual)
        if dialog.exec() != int(QDialog.DialogCode.Accepted):
            return None
        return dialog.visual()

    def _insert_visual_after(self, after_row: int | None, visual: dict[str, Any]) -> None:
        parse_visuals([visual])
        insert_row = len(self._visuals)
        if after_row is not None and 0 <= after_row < len(self._visuals):
            insert_row = after_row + 1
        self._visuals.insert(insert_row, copy.deepcopy(visual))
        self._refresh_list(select_row=insert_row)
        self.changed.emit()

    def _on_add_clicked(self) -> None:
        self._add_visual_after(None)

    def _add_visual_after(self, after_row: int | None) -> None:
        visual = self._open_visual_dialog(
            title="Add Visual",
            visual=self._default_visual(),
        )
        if visual is None:
            return
        self._insert_visual_after(after_row, visual)

    def _on_duplicate_clicked(self) -> None:
        self._duplicate_visual_at(self._list.currentRow())

    def _duplicate_visual_at(self, row: int) -> None:
        visual = self._visual_at_row(row)
        if visual is None:
            return
        copied = copy.deepcopy(visual)
        ids = {str(item.get("id", "")).strip() for item in self._visuals}
        source_id = str(copied.get("id", "")).strip() or "visual"
        visual_id = f"{source_id}_copy"
        index = 2
        while visual_id in ids:
            visual_id = f"{source_id}_copy_{index}"
            index += 1
        copied["id"] = visual_id
        self._insert_visual_after(row, copied)

    def _on_remove_clicked(self) -> None:
        self._remove_visual_at(self._list.currentRow())

    def _remove_visual_at(self, row: int) -> None:
        if not (0 <= row < len(self._visuals)):
            return
        self._visuals.pop(row)
        self._refresh_list(select_row=min(row, len(self._visuals) - 1))
        self.changed.emit()

    def _move_current(self, delta: int) -> None:
        self._move_visual(self._list.currentRow(), delta)

    def _move_visual(self, row: int, delta: int) -> None:
        target = row + delta
        if not (0 <= row < len(self._visuals)) or not (0 <= target < len(self._visuals)):
            return
        self._visuals[row], self._visuals[target] = self._visuals[target], self._visuals[row]
        self._refresh_list(select_row=target)
        self.changed.emit()

    def _edit_visual_at(self, row: int) -> None:
        visual = self._visual_at_row(row)
        if visual is None or not self._editing_enabled:
            return
        updated = self._open_visual_dialog(
            title=f"Edit Visual - {str(visual.get('id', '')).strip() or row + 1}",
            visual=visual,
        )
        if updated is None:
            return
        parse_visuals([updated])
        self._visuals[row] = copy.deepcopy(updated)
        self._refresh_list(select_row=row)
        self.changed.emit()

    def _on_visual_context_menu_requested(self, position) -> None:
        item = self._list.itemAt(position)
        target_row = self._list.row(item) if item is not None else -1
        if target_row >= 0:
            self._list.setCurrentRow(target_row)
        menu = QMenu(self)
        add_action = menu.addAction("Add Visual...")
        add_action.setEnabled(self._editing_enabled)
        edit_action = None
        duplicate_action = None
        remove_action = None
        move_up_action = None
        move_down_action = None
        if target_row >= 0:
            edit_action = menu.addAction("Edit...")
            edit_action.setEnabled(self._editing_enabled)
            duplicate_action = menu.addAction("Duplicate")
            duplicate_action.setEnabled(self._editing_enabled)
            remove_action = menu.addAction("Remove")
            remove_action.setEnabled(self._editing_enabled)
            menu.addSeparator()
            move_up_action = menu.addAction("Move Up")
            move_up_action.setEnabled(self._editing_enabled and target_row > 0)
            move_down_action = menu.addAction("Move Down")
            move_down_action.setEnabled(
                self._editing_enabled and target_row < len(self._visuals) - 1
            )
        chosen = menu.exec(self._list.viewport().mapToGlobal(position))
        if chosen == add_action:
            self._add_visual_after(target_row if target_row >= 0 else None)
        elif edit_action is not None and chosen == edit_action:
            self._edit_visual_at(target_row)
        elif duplicate_action is not None and chosen == duplicate_action:
            self._duplicate_visual_at(target_row)
        elif remove_action is not None and chosen == remove_action:
            self._remove_visual_at(target_row)
        elif move_up_action is not None and chosen == move_up_action:
            self._move_visual(target_row, -1)
        elif move_down_action is not None and chosen == move_down_action:
            self._move_visual(target_row, 1)

    def _on_visual_order_change_started(self) -> None:
        self._reordering = True

    def _on_visual_order_changed(self, visual_order: list[int]) -> None:
        selected_item = self._list.currentItem()
        selected_source = (
            selected_item.data(Qt.ItemDataRole.UserRole)
            if selected_item is not None
            else None
        )
        self._reordering = False
        if sorted(visual_order) != list(range(len(self._visuals))):
            self._refresh_list()
            return
        self._visuals[:] = [self._visuals[index] for index in visual_order]
        selected_row = (
            visual_order.index(selected_source)
            if isinstance(selected_source, int) and selected_source in visual_order
            else min(self._list.currentRow(), len(self._visuals) - 1)
        )
        self._refresh_list(select_row=selected_row)
        self.changed.emit()

    def _on_current_row_changed(self, _row: int) -> None:
        if self._loading or self._reordering:
            return
        self._sync_selection_state()
