"""Dock panel listing tile layers and entity visibility toggles.

Each row has a checkbox that shows/hides the corresponding
``QGraphicsItemGroup`` on the canvas.  Clicking a layer row (not the
checkbox) selects it as the active paint target.  A virtual *Entities*
row at the bottom controls entity-marker visibility but cannot be
selected as a paint target.
"""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from area_editor.documents.area_document import TileLayerDocument

# Special sentinel index for the virtual "Entities" row.
_ENTITIES_INDEX = -1
_LAYER_NAME_ROLE = Qt.ItemDataRole.UserRole + 1


class LayerListPanel(QDockWidget):
    """Right dock: per-layer visibility checkboxes and active-layer selection."""

    layer_visibility_changed = Signal(int, bool)       # (layer_index, visible)
    entities_visibility_changed = Signal(bool)          # (visible)
    active_layer_changed = Signal(int)                  # layer_index
    layer_properties_changed = Signal(int, int, bool, float, int)

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

        self._properties_group = QGroupBox("Render Properties")
        properties_layout = QFormLayout(self._properties_group)
        properties_layout.setContentsMargins(8, 8, 8, 8)

        self._render_order_spin = QSpinBox()
        self._render_order_spin.setRange(-9999, 9999)
        properties_layout.addRow("Render order", self._render_order_spin)

        self._y_sort_check = QCheckBox()
        properties_layout.addRow("Y-sort", self._y_sort_check)

        self._sort_y_offset_spin = QDoubleSpinBox()
        self._sort_y_offset_spin.setRange(-4096.0, 4096.0)
        self._sort_y_offset_spin.setDecimals(2)
        self._sort_y_offset_spin.setSingleStep(1.0)
        properties_layout.addRow("Sort Y offset", self._sort_y_offset_spin)

        self._stack_order_spin = QSpinBox()
        self._stack_order_spin.setRange(-9999, 9999)
        properties_layout.addRow("Stack order", self._stack_order_spin)
        layout.addWidget(self._properties_group)

        self.setWidget(container)
        self.setMinimumWidth(220)

        self._active_layer: int = 0
        self._bold_font = QFont()
        self._bold_font.setBold(True)
        self._normal_font = QFont()
        self._layers: list[TileLayerDocument] = []
        self._syncing_controls = False

        self._render_order_spin.valueChanged.connect(self._emit_layer_properties_changed)
        self._y_sort_check.toggled.connect(self._emit_layer_properties_changed)
        self._sort_y_offset_spin.valueChanged.connect(self._emit_layer_properties_changed)
        self._stack_order_spin.valueChanged.connect(self._emit_layer_properties_changed)
        self._set_property_controls_enabled(False)

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
        self._sync_property_controls()

    def clear_layers(self) -> None:
        self._list.clear()
        self._active_layer = 0
        self._layers = []
        self._sync_property_controls()

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
        self._sync_property_controls()

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
        if index == self._active_layer:
            self._sync_property_controls()

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
        self._sync_property_controls()
        self.active_layer_changed.emit(index)

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

    def _set_property_controls_enabled(self, enabled: bool) -> None:
        self._properties_group.setEnabled(enabled)

    def _sync_property_controls(self) -> None:
        layer = self._layer_for_index(self._active_layer)
        self._syncing_controls = True
        try:
            blockers = [
                QSignalBlocker(self._render_order_spin),
                QSignalBlocker(self._y_sort_check),
                QSignalBlocker(self._sort_y_offset_spin),
                QSignalBlocker(self._stack_order_spin),
            ]
            if layer is None:
                self._set_property_controls_enabled(False)
                self._render_order_spin.setValue(0)
                self._y_sort_check.setChecked(False)
                self._sort_y_offset_spin.setValue(0.0)
                self._stack_order_spin.setValue(0)
            else:
                self._set_property_controls_enabled(True)
                self._render_order_spin.setValue(layer.render_order)
                self._y_sort_check.setChecked(layer.y_sort)
                self._sort_y_offset_spin.setValue(layer.sort_y_offset)
                self._stack_order_spin.setValue(layer.stack_order)
            del blockers
        finally:
            self._syncing_controls = False

    def _emit_layer_properties_changed(self, *_args) -> None:
        if self._syncing_controls:
            return
        layer = self._layer_for_index(self._active_layer)
        if layer is None:
            return
        self.layer_properties_changed.emit(
            self._active_layer,
            self._render_order_spin.value(),
            self._y_sort_check.isChecked(),
            self._sort_y_offset_spin.value(),
            self._stack_order_spin.value(),
        )
