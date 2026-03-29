"""Dockable entity-instance editor with JSON and future UI tabs."""

from __future__ import annotations

import json

from PySide6.QtCore import Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from area_editor.documents.area_document import EntityDocument


class _EntityInstanceJsonEditor(QWidget):
    """Shows one selected entity instance as editable JSON."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)
    editing_enabled_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self._target_label = QLabel("Selected Entity: None")
        layout.addWidget(self._target_label)

        self._editor = QPlainTextEdit()
        self._editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._editor.setFont(font)
        self._editor.setReadOnly(True)
        self._editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._editor, 1)

        buttons = QHBoxLayout()
        self._apply_button = QPushButton("Apply")
        self._apply_button.clicked.connect(self.apply_requested.emit)
        buttons.addWidget(self._apply_button)
        self._revert_button = QPushButton("Revert")
        self._revert_button.clicked.connect(self.revert_requested.emit)
        buttons.addWidget(self._revert_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self._entity_id: str | None = None
        self._editing_enabled = False
        self._dirty = False
        self._loading = False
        self._set_buttons_enabled(False)

    @property
    def entity_id(self) -> str | None:
        return self._entity_id

    @property
    def editing_enabled(self) -> bool:
        return self._editing_enabled

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def json_text(self) -> str:
        return self._editor.toPlainText()

    @property
    def editor(self) -> QPlainTextEdit:
        return self._editor

    def set_editing_enabled(self, enabled: bool) -> None:
        self._editing_enabled = enabled and self._entity_id is not None
        self._editor.setReadOnly(not self._editing_enabled)
        self._set_buttons_enabled(self._entity_id is not None)
        self.editing_enabled_changed.emit(self._editing_enabled)

    def clear_entity(self) -> None:
        self._entity_id = None
        self._editing_enabled = False
        self._loading = True
        try:
            self._editor.setPlainText("")
        finally:
            self._loading = False
        self._target_label.setText("Selected Entity: None")
        self._set_dirty(False)
        self._editor.setReadOnly(True)
        self._set_buttons_enabled(False)

    def load_entity(self, entity: EntityDocument) -> None:
        self._entity_id = entity.id
        text = json.dumps(entity.to_dict(), indent=2, ensure_ascii=False)
        self._loading = True
        try:
            self._editor.setPlainText(text)
        finally:
            self._loading = False
        self._target_label.setText(f"Selected Entity: {entity.id}")
        self._set_dirty(False)
        self._editor.setReadOnly(not self._editing_enabled)
        self._set_buttons_enabled(True)

    def set_json_text(self, text: str) -> None:
        self._loading = True
        try:
            self._editor.setPlainText(text)
        finally:
            self._loading = False
        self._set_dirty(False)

    def _on_text_changed(self) -> None:
        if self._loading or not self._editing_enabled:
            return
        self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        if self._dirty == dirty:
            return
        self._dirty = dirty
        self.dirty_changed.emit(dirty)

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self._apply_button.setEnabled(enabled)
        self._revert_button.setEnabled(enabled)


class _EntityInstanceFieldsPlaceholder(QWidget):
    """Placeholder for future structured entity-instance editing."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self._target_label = QLabel("Selected Entity: None")
        layout.addWidget(self._target_label)

        hint = QLabel(
            "Structured entity instance editing is not implemented yet.\n"
            "For now, use the JSON tab to edit x, y, parameters, and other instance fields."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)

    def clear_entity(self) -> None:
        self._target_label.setText("Selected Entity: None")

    def load_entity(self, entity: EntityDocument) -> None:
        self._target_label.setText(f"Selected Entity: {entity.id}")


class EntityInstanceJsonPanel(QDockWidget):
    """Dockable entity-instance editor with internal tabs."""

    apply_requested = Signal()
    revert_requested = Signal()
    dirty_changed = Signal(bool)
    editing_enabled_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__("Entity Instance", parent)
        self.setObjectName("EntityInstanceJsonPanel")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._json_editor = _EntityInstanceJsonEditor()
        self._fields_placeholder = _EntityInstanceFieldsPlaceholder()

        self._tabs.addTab(self._json_editor, "Entity Instance JSON")
        self._tabs.addTab(self._fields_placeholder, "Entity Instance Editor")
        self.setWidget(self._tabs)
        self.setMinimumWidth(300)
        self._editor = self._json_editor.editor

        self._json_editor.apply_requested.connect(self.apply_requested.emit)
        self._json_editor.revert_requested.connect(self.revert_requested.emit)
        self._json_editor.dirty_changed.connect(self.dirty_changed.emit)
        self._json_editor.editing_enabled_changed.connect(
            self.editing_enabled_changed.emit
        )

    @property
    def entity_id(self) -> str | None:
        return self._json_editor.entity_id

    @property
    def editing_enabled(self) -> bool:
        return self._json_editor.editing_enabled

    @property
    def is_dirty(self) -> bool:
        return self._json_editor.is_dirty

    @property
    def json_text(self) -> str:
        return self._json_editor.json_text

    @property
    def editor(self) -> QPlainTextEdit:
        return self._json_editor.editor

    @property
    def tab_count(self) -> int:
        return self._tabs.count()

    def tab_titles(self) -> list[str]:
        return [self._tabs.tabText(index) for index in range(self._tabs.count())]

    def set_editing_enabled(self, enabled: bool) -> None:
        self._json_editor.set_editing_enabled(enabled)

    def clear_entity(self) -> None:
        self._json_editor.clear_entity()
        self._fields_placeholder.clear_entity()

    def load_entity(self, entity: EntityDocument) -> None:
        self._json_editor.load_entity(entity)
        self._fields_placeholder.load_entity(entity)

    def set_json_text(self, text: str) -> None:
        self._json_editor.set_json_text(text)
