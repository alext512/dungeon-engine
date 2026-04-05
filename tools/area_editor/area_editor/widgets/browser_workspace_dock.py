"""Dock widget that hosts the project browser in two tab rows."""

from __future__ import annotations

from PySide6.QtCore import QRect, Signal
from PySide6.QtWidgets import (
    QDockWidget,
    QStackedWidget,
    QStyle,
    QStyleOptionTab,
    QStylePainter,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from area_editor.widgets.tab_overflow import configure_tab_bar_overflow


class _VisualTabBar(QTabBar):
    """A real tab bar whose highlighted tab can be visually suppressed."""

    tab_requested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        configure_tab_bar_overflow(self)
        self.setDrawBase(True)
        self.setMovable(False)
        self._visual_current_index = -1
        self.tabBarClicked.connect(self._on_tab_clicked)

    def set_visual_current_index(self, index: int) -> None:
        self._visual_current_index = index
        self.update()

    def visual_current_index(self) -> int:
        return self._visual_current_index

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt override
        painter = QStylePainter(self)
        option = QStyleOptionTab()
        for index in range(self.count()):
            self.initStyleOption(option, index)
            if index != self._visual_current_index:
                option.state &= ~QStyle.StateFlag.State_Selected
                option.state &= ~QStyle.StateFlag.State_HasFocus
            painter.drawControl(QStyle.ControlElement.CE_TabBarTabShape, option)
            painter.drawControl(QStyle.ControlElement.CE_TabBarTabLabel, option)
        if self.drawBase():
            base_option = QStyleOptionTab()
            base_option.rect = QRect(0, 0, self.width(), self.height())
            painter.drawPrimitive(QStyle.PrimitiveElement.PE_FrameTabBarBase, base_option)

    def _on_tab_clicked(self, index: int) -> None:
        if index >= 0:
            self.tab_requested.emit(index)


class BrowserWorkspaceDock(QDockWidget):
    """Left dock with two independent tab rows controlling one content stack."""

    page_changed = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__("Project Browser", parent)
        self.setObjectName("BrowserWorkspaceDock")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._row1 = _VisualTabBar()
        self._row1.tab_requested.connect(lambda index: self._on_row_requested(1, index))
        layout.addWidget(self._row1)

        self._row2 = _VisualTabBar()
        self._row2.tab_requested.connect(lambda index: self._on_row_requested(2, index))
        layout.addWidget(self._row2)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)
        self.setWidget(container)
        self.setMinimumWidth(220)

        self._row1_keys: list[str] = []
        self._row2_keys: list[str] = []
        self._page_indices: dict[str, int] = {}
        self._active_key: str | None = None
        self._syncing = False

    def add_page(self, *, row: int, key: str, title: str, widget: QWidget) -> None:
        self._page_indices[key] = self._stack.addWidget(widget)
        if row == 1:
            self._row1.addTab(title)
            self._row1_keys.append(key)
        elif row == 2:
            self._row2.addTab(title)
            self._row2_keys.append(key)
        else:
            raise ValueError("row must be 1 or 2")

        if self._stack.count() == 1:
            self.set_current_page(key)

    def set_current_page(self, key: str) -> None:
        index = self._page_indices[key]
        self._active_key = key
        self._stack.setCurrentIndex(index)
        self._syncing = True
        try:
            self._set_row_state(self._row1, self._row1_keys, key)
            self._set_row_state(self._row2, self._row2_keys, key)
        finally:
            self._syncing = False
        self.page_changed.emit(key)

    def row_titles(self, row: int) -> list[str]:
        tab_bar = self._row1 if row == 1 else self._row2
        return [tab_bar.tabText(index) for index in range(tab_bar.count())]

    def active_key(self) -> str | None:
        return self._active_key

    def row_visual_current_index(self, row: int) -> int:
        tab_bar = self._row1 if row == 1 else self._row2
        return tab_bar.visual_current_index()

    def _set_row_state(self, tab_bar: _VisualTabBar, keys: list[str], active_key: str) -> None:
        if active_key in keys:
            index = keys.index(active_key)
            tab_bar.setCurrentIndex(index)
            tab_bar.set_visual_current_index(index)
        else:
            tab_bar.set_visual_current_index(-1)
            if tab_bar.currentIndex() < 0 and tab_bar.count() > 0:
                tab_bar.setCurrentIndex(0)

    def _on_row_requested(self, row: int, index: int) -> None:
        if self._syncing or index < 0:
            return
        keys = self._row1_keys if row == 1 else self._row2_keys
        if index < len(keys):
            self.set_current_page(keys[index])
