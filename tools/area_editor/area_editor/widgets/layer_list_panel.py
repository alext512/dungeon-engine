"""Dock panel listing tile layers plus lightweight management actions.

Each row has a checkbox that shows or hides the corresponding tile-layer
items on the canvas. Clicking a row selects it as the active paint
target. Context-menu actions provide small layer-management workflows.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QDockWidget,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
    QWidget,
)

from area_editor.documents.area_document import TileLayerDocument

_LAYER_NAME_ROLE = Qt.ItemDataRole.UserRole + 1


class LayerListPanel(QDockWidget):
    """Right dock: per-layer visibility checkboxes and active-layer selection."""

    layer_visibility_changed = Signal(int, bool)       # (layer_index, visible)
    active_layer_changed = Signal(int)                  # layer_index
    add_layer_requested = Signal()
    rename_layer_requested = Signal(int)
    delete_layer_requested = Signal(int)
    move_layer_up_requested = Signal(int)
    move_layer_down_requested = Signal(int)

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
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._list)

        self.setWidget(container)
        self.setMinimumWidth(220)

        self._active_layer: int = 0
        self._bold_font = QFont()
        self._bold_font.setBold(True)
        self._normal_font = QFont()
        self._layers: list[TileLayerDocument] = []

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_layers(self, layers: list[TileLayerDocument]) -> None:
        """Rebuild the list from the given tile layers."""
        self._layers = list(layers)
        self._list.blockSignals(True)
        self._list.clear()

        for idx, layer in enumerate(layers):
            item = QListWidgetItem(self._format_layer_label(layer))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, idx)
            item.setData(_LAYER_NAME_ROLE, layer.name)
            self._list.addItem(item)

        # Select first layer as active by default
        if layers:
            self._active_layer = 0
            self._list.setCurrentRow(0)
            first = self._list.item(0)
            if first is not None:
                first.setFont(self._bold_font)
        else:
            self._active_layer = 0

        self._list.blockSignals(False)

    def clear_layers(self) -> None:
        self._list.clear()
        self._active_layer = 0
        self._layers = []

    @property
    def active_layer(self) -> int:
        return self._active_layer

    def active_layer_name(self) -> str:
        """Return the display name of the active layer, or empty string."""
        item = self._list.item(self._active_layer)
        if item is None:
            return ""
        return str(item.data(_LAYER_NAME_ROLE) or item.text())

    def set_active_layer(self, index: int) -> None:
        """Programmatically restore the active paint target layer."""
        if index < 0 or index >= self._list.count():
            return
        item = self._list.item(index)
        if item is None:
            return

        previous = self._list.item(self._active_layer)
        if previous is not None and previous is not item:
            previous.setFont(self._normal_font)

        self._list.blockSignals(True)
        self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        item.setFont(self._bold_font)
        self._active_layer = index

    def update_layer(self, index: int, layer: TileLayerDocument) -> None:
        """Refresh one visible row after layer properties change."""
        if not (0 <= index < len(self._layers)):
            return
        self._layers[index] = layer
        item = self._item_for_layer(index)
        if item is None:
            return
        item.setText(self._format_layer_label(layer))
        item.setData(_LAYER_NAME_ROLE, layer.name)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        visible = item.checkState() == Qt.CheckState.Checked
        self.layer_visibility_changed.emit(index, visible)

    def _on_current_item_changed(
        self, current: QListWidgetItem | None, previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        index = current.data(Qt.ItemDataRole.UserRole)

        # Update bold styling
        if previous is not None:
            previous.setFont(self._normal_font)
        current.setFont(self._bold_font)

        self._active_layer = index
        self.active_layer_changed.emit(index)

    def _on_context_menu(self, pos) -> None:
        menu = QMenu(self)
        clicked_item = self._list.itemAt(pos)
        index = None
        if clicked_item is not None:
            index = int(clicked_item.data(Qt.ItemDataRole.UserRole))

        add_action = QAction("Add Layer...", self)
        add_action.triggered.connect(lambda _checked=False: self.add_layer_requested.emit())
        menu.addAction(add_action)

        if index is not None:
            menu.addSeparator()

            rename_action = QAction("Rename Layer...", self)
            rename_action.triggered.connect(lambda _checked=False, idx=index: self.rename_layer_requested.emit(idx))
            menu.addAction(rename_action)

            delete_action = QAction("Delete Layer...", self)
            delete_action.triggered.connect(lambda _checked=False, idx=index: self.delete_layer_requested.emit(idx))
            menu.addAction(delete_action)

            menu.addSeparator()

            move_up_action = QAction("Move Layer Up", self)
            move_up_action.setEnabled(index > 0)
            move_up_action.triggered.connect(lambda _checked=False, idx=index: self.move_layer_up_requested.emit(idx))
            menu.addAction(move_up_action)

            move_down_action = QAction("Move Layer Down", self)
            move_down_action.setEnabled(index < (len(self._layers) - 1))
            move_down_action.triggered.connect(lambda _checked=False, idx=index: self.move_layer_down_requested.emit(idx))
            menu.addAction(move_down_action)

        menu.exec(self._list.viewport().mapToGlobal(pos))

    def _format_layer_label(self, layer: TileLayerDocument) -> str:
        """Return one compact layer-list label for the unified render model."""
        badges = [f"z:{layer.render_order}"]
        if layer.y_sort:
            badges.append("y-sort")
        if layer.stack_order:
            badges.append(f"stack:{layer.stack_order}")
        if layer.sort_y_offset:
            badges.append(f"offset:{layer.sort_y_offset:g}")
        return f"{layer.name}  [{' | '.join(badges)}]"

    def _item_for_layer(self, index: int) -> QListWidgetItem | None:
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == index:
                return item
        return None

    def _layer_for_index(self, index: int) -> TileLayerDocument | None:
        if 0 <= index < len(self._layers):
            return self._layers[index]
        return None
