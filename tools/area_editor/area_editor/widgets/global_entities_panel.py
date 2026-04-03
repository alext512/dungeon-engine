"""Dock panel listing global entities authored in ``project.json``."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from area_editor.project_io.manifest import GlobalEntityEntry


class GlobalEntitiesPanel(QDockWidget):
    """Left-dock browser for project-level global entities."""

    global_entity_selected = Signal(str)  # entity_id
    global_entity_open_requested = Signal(str)  # entity_id

    def __init__(self, parent=None) -> None:
        super().__init__("Global Entities", parent)
        self.setObjectName("GlobalEntitiesPanel")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.currentItemChanged.connect(self._on_item_changed)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._tree)

        self.setWidget(container)
        self.setMinimumWidth(140)

    def populate(self, entries: list[GlobalEntityEntry]) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        for entry in entries:
            item = QTreeWidgetItem(self._tree, [entry.entity_id])
            item.setData(0, Qt.ItemDataRole.UserRole, entry.entity_id)
            if entry.template_id:
                item.setToolTip(0, f"{entry.entity_id}\n{entry.template_id}")
            else:
                item.setToolTip(0, entry.entity_id)
        self._tree.blockSignals(False)

    def clear_entities(self) -> None:
        self._tree.clear()

    def select_entity(self, entity_id: str) -> None:
        self._tree.blockSignals(True)
        for index in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(index)
            if item is not None and item.data(0, Qt.ItemDataRole.UserRole) == entity_id:
                self._tree.setCurrentItem(item)
                break
        self._tree.blockSignals(False)

    def _on_item_changed(self, current: QTreeWidgetItem | None, _previous) -> None:
        if current is None:
            return
        entity_id = current.data(0, Qt.ItemDataRole.UserRole)
        if entity_id:
            self.global_entity_selected.emit(str(entity_id))

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        entity_id = item.data(0, Qt.ItemDataRole.UserRole)
        if entity_id:
            self.global_entity_open_requested.emit(str(entity_id))
