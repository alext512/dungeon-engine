"""Structured table editor for entity variable JSON objects."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def _copy_name(base_name: str, existing_names: set[str]) -> str:
    stem = f"{base_name}_copy" if base_name else "variable"
    candidate = stem
    suffix = 2
    while candidate in existing_names:
        candidate = f"{stem}_{suffix}"
        suffix += 1
    return candidate


def _format_variable_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _parse_variable_value(raw_text: str, *, variable_name: str) -> Any:
    text = raw_text.strip()
    if not text:
        return ""
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        if text.startswith(("{", "[", '"')):
            raise ValueError(
                f"Variable '{variable_name}' value must be valid JSON or plain text."
            ) from exc
        return raw_text


class EntityVariablesTable(QWidget):
    """Table surface for a JSON object of entity variables."""

    changed = Signal()

    def __init__(
        self,
        parent=None,
        *,
        empty_message: str = "No variables defined.",
    ) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        self._add_button = QPushButton("Add Variable")
        self._duplicate_button = QPushButton("Duplicate")
        self._remove_button = QPushButton("Remove")
        self._add_button.clicked.connect(lambda _checked=False: self.add_variable())
        self._duplicate_button.clicked.connect(
            lambda _checked=False: self.duplicate_selected_variable()
        )
        self._remove_button.clicked.connect(
            lambda _checked=False: self.remove_selected_variable()
        )
        buttons.addWidget(self._add_button)
        buttons.addWidget(self._duplicate_button)
        buttons.addWidget(self._remove_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(["Variable", "Value"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.cellChanged.connect(lambda *_args: self.changed.emit())
        self._table.currentCellChanged.connect(
            lambda *_args: self._sync_button_state()
        )
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self._table, 1)

        self._empty_label = QLabel(empty_message)
        self._empty_label.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(self._empty_label)

        self._sync_button_state()

    @property
    def table(self) -> QTableWidget:
        return self._table

    def set_editing_enabled(self, enabled: bool) -> None:
        self._table.setEnabled(enabled)
        self._add_button.setEnabled(enabled)
        self._duplicate_button.setEnabled(enabled and self._table.currentRow() >= 0)
        self._remove_button.setEnabled(enabled and self._table.currentRow() >= 0)

    def set_variables(self, variables: object) -> None:
        if variables is None:
            variables = {}
        if not isinstance(variables, dict):
            raise ValueError("Variables must be a JSON object.")
        self._table.blockSignals(True)
        try:
            self._table.setRowCount(0)
            for raw_name, value in variables.items():
                self._insert_row(str(raw_name), _format_variable_value(value))
        finally:
            self._table.blockSignals(False)
        self._sync_button_state()

    def variables(self) -> dict[str, Any]:
        variables: dict[str, Any] = {}
        for row in range(self._table.rowCount()):
            name_item = self._table.item(row, 0)
            value_item = self._table.item(row, 1)
            name = name_item.text().strip() if name_item is not None else ""
            raw_value = value_item.text() if value_item is not None else ""
            if not name and not raw_value.strip():
                continue
            if not name:
                raise ValueError("Variable names must not be blank.")
            if name in variables:
                raise ValueError(f"Duplicate variable '{name}'.")
            variables[name] = _parse_variable_value(raw_value, variable_name=name)
        return variables

    def add_variable(self, name: str = "", value: object = "") -> int:
        row = self._insert_row(str(name), _format_variable_value(value))
        self._table.setCurrentCell(row, 0)
        self._sync_button_state()
        self.changed.emit()
        return row

    def duplicate_selected_variable(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        name_item = self._table.item(row, 0)
        value_item = self._table.item(row, 1)
        existing_names = {
            self._table.item(index, 0).text().strip()
            for index in range(self._table.rowCount())
            if self._table.item(index, 0) is not None
        }
        name = _copy_name(
            name_item.text().strip() if name_item is not None else "",
            existing_names,
        )
        value = value_item.text() if value_item is not None else ""
        new_row = self._insert_row(name, value)
        self._table.setCurrentCell(new_row, 0)
        self._sync_button_state()
        self.changed.emit()

    def remove_selected_variable(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        self._table.removeRow(row)
        self._sync_button_state()
        self.changed.emit()

    def _insert_row(self, name: str, value: str) -> int:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(name))
        self._table.setItem(row, 1, QTableWidgetItem(value))
        return row

    def _show_context_menu(self, pos) -> None:
        if not self._table.isEnabled():
            return
        row = self._table.rowAt(pos.y())
        if row >= 0:
            self._table.setCurrentCell(row, 0)

        menu = QMenu(self)
        add_action = menu.addAction("Add Variable")
        duplicate_action = None
        remove_action = None
        if self._table.currentRow() >= 0:
            duplicate_action = menu.addAction("Duplicate")
            remove_action = menu.addAction("Remove")

        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen == add_action:
            self.add_variable()
        elif duplicate_action is not None and chosen == duplicate_action:
            self.duplicate_selected_variable()
        elif remove_action is not None and chosen == remove_action:
            self.remove_selected_variable()

    def _sync_button_state(self) -> None:
        has_selection = self._table.currentRow() >= 0
        enabled = self._table.isEnabled()
        self._duplicate_button.setEnabled(enabled and has_selection)
        self._remove_button.setEnabled(enabled and has_selection)
        self._empty_label.setVisible(self._table.rowCount() == 0)
