"""Dockable shared render-properties editor for layers and entities."""

from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class RenderPropertiesPanel(QDockWidget):
    """Shared dock widget for editing render properties of one target."""

    properties_changed = Signal(int, bool, float, int)

    def __init__(self, parent=None) -> None:
        super().__init__("Render Properties", parent)
        self.setObjectName("RenderPropertiesPanel")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)

        self._target_label = QLabel("Editing: None")
        layout.addWidget(self._target_label)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)

        self._render_order_spin = QSpinBox()
        self._render_order_spin.setRange(-9999, 9999)
        form.addRow("Render order", self._render_order_spin)

        self._y_sort_check = QCheckBox()
        form.addRow("Y-sort", self._y_sort_check)

        self._sort_y_offset_spin = QDoubleSpinBox()
        self._sort_y_offset_spin.setRange(-4096.0, 4096.0)
        self._sort_y_offset_spin.setDecimals(2)
        self._sort_y_offset_spin.setSingleStep(1.0)
        form.addRow("Sort Y offset", self._sort_y_offset_spin)

        self._stack_order_spin = QSpinBox()
        self._stack_order_spin.setRange(-9999, 9999)
        form.addRow("Stack order", self._stack_order_spin)

        layout.addLayout(form)
        layout.addStretch(1)

        self.setWidget(container)
        self.setMinimumWidth(220)

        self._syncing = False
        self._set_controls_enabled(False)

        self._render_order_spin.valueChanged.connect(self._emit_properties_changed)
        self._y_sort_check.toggled.connect(self._emit_properties_changed)
        self._sort_y_offset_spin.valueChanged.connect(self._emit_properties_changed)
        self._stack_order_spin.valueChanged.connect(self._emit_properties_changed)

    def clear_target(self) -> None:
        self._syncing = True
        try:
            blockers = [
                QSignalBlocker(self._render_order_spin),
                QSignalBlocker(self._y_sort_check),
                QSignalBlocker(self._sort_y_offset_spin),
                QSignalBlocker(self._stack_order_spin),
            ]
            self._target_label.setText("Editing: None")
            self._render_order_spin.setValue(0)
            self._y_sort_check.setChecked(False)
            self._sort_y_offset_spin.setValue(0.0)
            self._stack_order_spin.setValue(0)
            self._set_controls_enabled(False)
            del blockers
        finally:
            self._syncing = False

    def set_target(
        self,
        *,
        label: str,
        render_order: int,
        y_sort: bool,
        sort_y_offset: float,
        stack_order: int,
    ) -> None:
        self._syncing = True
        try:
            blockers = [
                QSignalBlocker(self._render_order_spin),
                QSignalBlocker(self._y_sort_check),
                QSignalBlocker(self._sort_y_offset_spin),
                QSignalBlocker(self._stack_order_spin),
            ]
            self._target_label.setText(f"Editing: {label}")
            self._render_order_spin.setValue(render_order)
            self._y_sort_check.setChecked(y_sort)
            self._sort_y_offset_spin.setValue(sort_y_offset)
            self._stack_order_spin.setValue(stack_order)
            self._set_controls_enabled(True)
            del blockers
        finally:
            self._syncing = False

    def _set_controls_enabled(self, enabled: bool) -> None:
        self._render_order_spin.setEnabled(enabled)
        self._y_sort_check.setEnabled(enabled)
        self._sort_y_offset_spin.setEnabled(enabled)
        self._stack_order_spin.setEnabled(enabled)

    def _emit_properties_changed(self, *_args) -> None:
        if self._syncing:
            return
        self.properties_changed.emit(
            self._render_order_spin.value(),
            self._y_sort_check.isChecked(),
            self._sort_y_offset_spin.value(),
            self._stack_order_spin.value(),
        )
