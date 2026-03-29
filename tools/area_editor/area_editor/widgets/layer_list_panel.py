"""Dock panel listing tile layers and entity visibility toggles.

Each row has a checkbox that shows/hides the corresponding
``QGraphicsItemGroup`` on the canvas.  Clicking a layer row (not the
checkbox) selects it as the active paint target.  A virtual *Entities*
row at the bottom controls entity-marker visibility but cannot be
selected as a paint target.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDockWidget,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from area_editor.documents.area_document import TileLayerDocument

# Special sentinel index for the virtual "Entities" row.
_ENTITIES_INDEX = -1


class LayerListPanel(QDockWidget):
    """Right dock: per-layer visibility checkboxes and active-layer selection."""

    layer_visibility_changed = Signal(int, bool)       # (layer_index, visible)
    entities_visibility_changed = Signal(bool)          # (visible)
    active_layer_changed = Signal(int)                  # layer_index

    def __init__(self, parent=None) -> None:
        super().__init__("Layers", parent)
        self.setObjectName("LayerListPanel")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)

        self._list = QListWidget()
        self._list.itemChanged.connect(self._on_item_changed)
        self._list.currentItemChanged.connect(self._on_current_item_changed)
        layout.addWidget(self._list)

        self.setWidget(container)
        self.setMinimumWidth(120)

        self._active_layer: int = 0
        self._bold_font = QFont()
        self._bold_font.setBold(True)
        self._normal_font = QFont()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_layers(self, layers: list[TileLayerDocument]) -> None:
        """Rebuild the list from the given tile layers."""
        self._list.blockSignals(True)
        self._list.clear()

        for idx, layer in enumerate(layers):
            suffix = "  [above]" if layer.draw_above_entities else ""
            item = QListWidgetItem(f"{layer.name}{suffix}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            self._list.addItem(item)

        # Virtual "Entities" row
        ent_item = QListWidgetItem("Entities")
        ent_item.setFlags(ent_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        ent_item.setCheckState(Qt.CheckState.Checked)
        ent_item.setData(Qt.ItemDataRole.UserRole, _ENTITIES_INDEX)
        self._list.addItem(ent_item)

        # Select first layer as active by default
        if layers:
            self._active_layer = 0
            self._list.setCurrentRow(0)
            first = self._list.item(0)
            if first is not None:
                first.setFont(self._bold_font)

        self._list.blockSignals(False)

    def clear_layers(self) -> None:
        self._list.clear()
        self._active_layer = 0

    @property
    def active_layer(self) -> int:
        return self._active_layer

    def active_layer_name(self) -> str:
        """Return the display name of the active layer, or empty string."""
        item = self._list.item(self._active_layer)
        if item is None:
            return ""
        return item.text().split("  [")[0]  # strip "[above]" suffix

    def set_active_layer(self, index: int) -> None:
        """Programmatically restore the active paint target layer."""
        if index < 0 or index >= self._list.count():
            return
        item = self._list.item(index)
        if item is None:
            return
        row_index = item.data(Qt.ItemDataRole.UserRole)
        if row_index == _ENTITIES_INDEX:
            return

        previous = self._list.item(self._active_layer)
        if previous is not None and previous is not item:
            previous.setFont(self._normal_font)

        self._list.blockSignals(True)
        self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        item.setFont(self._bold_font)
        self._active_layer = index

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        visible = item.checkState() == Qt.CheckState.Checked
        if index == _ENTITIES_INDEX:
            self.entities_visibility_changed.emit(visible)
        else:
            self.layer_visibility_changed.emit(index, visible)

    def _on_current_item_changed(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        index = current.data(Qt.ItemDataRole.UserRole)
        if index == _ENTITIES_INDEX:
            # Don't allow selecting the entities row as paint target;
            # revert to the previous selection.
            if previous is not None:
                self._list.blockSignals(True)
                self._list.setCurrentItem(previous)
                self._list.blockSignals(False)
            return

        # Update bold styling
        if previous is not None:
            previous.setFont(self._normal_font)
        current.setFont(self._bold_font)

        self._active_layer = index
        self.active_layer_changed.emit(index)
