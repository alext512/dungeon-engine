"""Cell-flag brush controls for area editing."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from area_editor.documents.area_document import AreaDocument
from area_editor.json_io import JsonDataDecodeError, loads_json_data
from area_editor.operations.cell_flags import CellFlagBrush

class CellFlagBrushPanel(QWidget):
    """Choose which cell-flag operation canvas clicks should paint."""

    brush_changed = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("CellFlagBrushPanel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self._target_label = QLabel("Cell Flags: none")
        layout.addWidget(self._target_label)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(form)

        self._preset_combo = QComboBox()
        self._preset_combo.addItem("Blocked", CellFlagBrush("blocked", True))
        self._preset_combo.addItem("Custom flag", None)
        self._preset_combo.currentIndexChanged.connect(self._on_controls_changed)
        form.addRow("Brush", self._preset_combo)

        self._key_combo = QComboBox()
        self._key_combo.setEditable(True)
        self._key_combo.addItems(["tags"])
        self._key_combo.currentTextChanged.connect(self._on_controls_changed)
        form.addRow("Flag", self._key_combo)

        self._value_edit = QLineEdit('["water"]')
        self._value_edit.setPlaceholderText('Value, e.g. ["water", "slow", "no_spawn"]')
        self._value_edit.textChanged.connect(self._on_controls_changed)
        form.addRow("Value", self._value_edit)

        self._help_label = QLabel(
            "Left-click places blocked/flags. Right-click removes blocked/flags."
        )
        self._help_label.setWordWrap(True)
        self._help_label.setStyleSheet("color: #666;")
        layout.addWidget(self._help_label)
        layout.addStretch(1)

        self._current_brush = CellFlagBrush("blocked", True)
        self._sync_custom_controls()

    @property
    def current_brush(self) -> CellFlagBrush:
        return self._current_brush

    def load_area(self, area_id: str, area: AreaDocument) -> None:
        self._target_label.setText(f"Cell Flags: {area_id}")
        self._refresh_known_keys(area)
        self._on_controls_changed()

    def clear(self) -> None:
        self._target_label.setText("Cell Flags: none")

    def _refresh_known_keys(self, area: AreaDocument) -> None:
        known_keys = {"tags"}
        for row in area.cell_flags:
            for cell in row:
                if isinstance(cell, dict):
                    known_keys.update(
                        str(key)
                        for key in cell.keys()
                        if str(key) != "blocked"
                    )

        current = self._key_combo.currentText().strip()
        self._key_combo.blockSignals(True)
        self._key_combo.clear()
        self._key_combo.addItems(sorted(known_keys))
        if current:
            index = self._key_combo.findText(current)
            if index < 0:
                self._key_combo.addItem(current)
                index = self._key_combo.findText(current)
            self._key_combo.setCurrentIndex(index)
        self._key_combo.blockSignals(False)

    def _on_controls_changed(self) -> None:
        self._ensure_tags_value()
        brush = self._build_brush()
        self._current_brush = brush
        self._sync_custom_controls()
        self.brush_changed.emit(brush)

    def _build_brush(self) -> CellFlagBrush:
        preset = self._preset_combo.currentData()
        if isinstance(preset, CellFlagBrush) and preset.key:
            return preset

        key = self._key_combo.currentText().strip()
        value = self._parse_value(self._value_edit.text())
        if key == "tags":
            if not isinstance(value, list):
                self._set_help_warning("Tags must be a JSON list like [\"water\", \"slow\"].")
                return CellFlagBrush(key, [])
            self._set_help_default()
        else:
            self._set_help_default()
        return CellFlagBrush(key, value)

    def _parse_value(self, text: str) -> Any:
        stripped = text.strip()
        if not stripped:
            return True
        try:
            return loads_json_data(stripped, source_name="Cell flag brush value")
        except JsonDataDecodeError:
            return stripped

    def _sync_custom_controls(self) -> None:
        preset = self._preset_combo.currentData()
        custom = not (isinstance(preset, CellFlagBrush) and preset.key)
        self._key_combo.setEnabled(custom)
        self._value_edit.setEnabled(custom)

    def _ensure_tags_value(self) -> None:
        key = self._key_combo.currentText().strip()
        if key != "tags":
            return
        current = self._value_edit.text().strip()
        if not current or current in {"true", "false"}:
            self._value_edit.blockSignals(True)
            self._value_edit.setText('["tag"]')
            self._value_edit.blockSignals(False)

    def _set_help_warning(self, message: str) -> None:
        self._help_label.setText(message)
        self._help_label.setStyleSheet("color: #a33;")

    def _set_help_default(self) -> None:
        self._help_label.setText(
            "Left-click places blocked/flags. Right-click removes blocked/flags."
        )
        self._help_label.setStyleSheet("color: #666;")
