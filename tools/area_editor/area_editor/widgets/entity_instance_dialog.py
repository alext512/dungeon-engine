"""Floating entity-instance editor dialog."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QVBoxLayout

from area_editor.widgets.entity_instance_json_panel import EntityInstanceEditorWidget


class EntityInstanceDialog(QDialog):
    """Pinned modeless dialog hosting the entity-instance editor widget."""

    close_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("EntityInstanceDialog")
        self.setWindowTitle("Edit Entity Instance")
        self.setModal(False)

        self._allow_close = False
        self._target_area_id: str | None = None
        self._target_entity_id: str | None = None

        self._editor_widget = EntityInstanceEditorWidget()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self._editor_widget)
        self.resize(460, 520)

    @property
    def editor_widget(self) -> EntityInstanceEditorWidget:
        return self._editor_widget

    @property
    def target_area_id(self) -> str | None:
        return self._target_area_id

    @property
    def target_entity_id(self) -> str | None:
        return self._target_entity_id

    @property
    def has_dirty_changes(self) -> bool:
        return self._editor_widget.is_dirty or self._editor_widget.fields_dirty

    def set_target(self, area_id: str, entity_id: str) -> None:
        self._target_area_id = area_id
        self._target_entity_id = entity_id
        self.setWindowTitle(f"Edit Entity Instance: {entity_id}")

    def force_close(self) -> None:
        self._allow_close = True
        try:
            self.close()
        finally:
            self._allow_close = False

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._allow_close:
            super().closeEvent(event)
            return
        event.ignore()
        self.close_requested.emit()

