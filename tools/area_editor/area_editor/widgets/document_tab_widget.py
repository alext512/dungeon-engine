"""Central tabbed document area.

Manages open document tabs — areas render in TileCanvas, JSON files
in a read-only viewer, images in a zoomable preview.  Tracks open
documents by content_id to prevent duplicates.
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QFont, QMouseEvent
from PySide6.QtWidgets import (
    QLabel,
    QStackedWidget,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from area_editor.widgets.image_viewer_widget import ImageViewerWidget
from area_editor.widgets.json_viewer_widget import JsonViewerWidget
from area_editor.widgets.tab_overflow import configure_tab_widget_overflow
from area_editor.widgets.tile_canvas import TileCanvas

log = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


class ContentType(Enum):
    AREA = auto()
    AREA_JSON = auto()
    ENTITY_TEMPLATE = auto()
    ITEM = auto()
    DIALOGUE = auto()
    NAMED_COMMAND = auto()
    ASSET = auto()
    SHARED_VARIABLES = auto()
    PROJECT_MANIFEST = auto()
    GLOBAL_ENTITIES = auto()
    DOCUMENTATION = auto()


class _TabInfo:
    """Metadata stored per open tab."""

    __slots__ = ("content_id", "file_path", "content_type", "dirty")

    def __init__(
        self, content_id: str, file_path: Path, content_type: ContentType
    ) -> None:
        self.content_id = content_id
        self.file_path = file_path
        self.content_type = content_type
        self.dirty = False


class DocumentTabWidget(QStackedWidget):
    """Stacked widget: either an empty welcome page or the tab widget."""

    # Emitted when the active tab changes. content_id is "" when no tabs.
    active_tab_changed = Signal(str, object)  # (content_id, ContentType | None)
    tab_close_requested = Signal(str, object)  # (content_id, ContentType)
    tab_closed = Signal(str)  # content_id

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Welcome page (shown when no tabs are open)
        self._welcome = QLabel("Open a file from the side panels")
        self._welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome_font = QFont()
        welcome_font.setPointSize(14)
        self._welcome.setFont(welcome_font)
        self._welcome.setStyleSheet("color: #888;")
        self.addWidget(self._welcome)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.setDocumentMode(True)
        configure_tab_widget_overflow(self._tabs)
        self._tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tabs.currentChanged.connect(self._on_current_changed)
        self.addWidget(self._tabs)

        # Install event filter on the tab bar for middle-click close
        self._tabs.tabBar().installEventFilter(self)

        # Open tab registry: content_id -> tab index
        self._tab_infos: list[_TabInfo] = []

        # Start on welcome page
        self.setCurrentWidget(self._welcome)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open_tab(
        self,
        content_id: str,
        file_path: Path,
        content_type: ContentType,
        *,
        widget: QWidget | None = None,
    ) -> QWidget:
        """Open a document tab, or focus it if already open.

        For areas, the caller should pass a pre-configured ``TileCanvas``
        as *widget*.  For other types, the appropriate viewer is created
        automatically.

        Returns the tab's widget.
        """
        # Check for existing tab
        for i, info in enumerate(self._tab_infos):
            if info.content_id == content_id:
                self._tabs.setCurrentIndex(i)
                self.setCurrentWidget(self._tabs)
                return self._tabs.widget(i)

        # Create widget if not provided
        if widget is None:
            widget = self._create_viewer(file_path, content_type)

        info = _TabInfo(content_id, file_path, content_type)
        self._tab_infos.append(info)

        index = self._tabs.addTab(widget, self._tab_label(info))
        self._tabs.setTabToolTip(index, content_id)
        self._tabs.setCurrentIndex(index)
        self.setCurrentWidget(self._tabs)

        return widget

    def close_all(self) -> None:
        """Close all tabs (e.g. when loading a new project)."""
        while self._tabs.count() > 0:
            self._close_tab(0)

    def close_content(self, content_id: str) -> None:
        """Close the tab for *content_id* if it is open."""
        index = self._index_for_content(content_id)
        if index is not None:
            self._close_tab(index)

    def active_content_id(self) -> str | None:
        """Return the content_id of the active tab, or None."""
        idx = self._tabs.currentIndex()
        if 0 <= idx < len(self._tab_infos):
            return self._tab_infos[idx].content_id
        return None

    def active_widget(self) -> QWidget | None:
        """Return the widget of the active tab."""
        return self._tabs.currentWidget()

    def active_info(self) -> _TabInfo | None:
        """Return the _TabInfo for the active tab."""
        idx = self._tabs.currentIndex()
        if 0 <= idx < len(self._tab_infos):
            return self._tab_infos[idx]
        return None

    def content_info(self, content_id: str) -> _TabInfo | None:
        """Return the tab info for a known content id."""
        index = self._index_for_content(content_id)
        if index is None:
            return None
        return self._tab_infos[index]

    def widget_for_content(self, content_id: str) -> QWidget | None:
        """Return the widget for a known content id, if open."""
        index = self._index_for_content(content_id)
        if index is None:
            return None
        return self._tabs.widget(index)

    def is_dirty(self, content_id: str) -> bool:
        info = self.content_info(content_id)
        return False if info is None else info.dirty

    def dirty_content_ids(self) -> list[str]:
        return [info.content_id for info in self._tab_infos if info.dirty]

    def set_dirty(self, content_id: str, dirty: bool) -> None:
        index = self._index_for_content(content_id)
        if index is None:
            return
        info = self._tab_infos[index]
        if info.dirty == dirty:
            return
        info.dirty = dirty
        self._tabs.setTabText(index, self._tab_label(info))

    # ------------------------------------------------------------------
    # Event filter (middle-click close)
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._tabs.tabBar() and event.type() == QEvent.Type.MouseButtonRelease:
            me: QMouseEvent = event
            if me.button() == Qt.MouseButton.MiddleButton:
                idx = self._tabs.tabBar().tabAt(me.position().toPoint())
                if idx >= 0:
                    self._on_tab_close_requested(idx)
                    return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_tab_close_requested(self, index: int) -> None:
        if index < 0 or index >= len(self._tab_infos):
            return
        info = self._tab_infos[index]
        self.tab_close_requested.emit(info.content_id, info.content_type)

    def _close_tab(self, index: int) -> None:
        if index < 0 or index >= len(self._tab_infos):
            return
        info = self._tab_infos.pop(index)
        widget = self._tabs.widget(index)
        self._tabs.removeTab(index)
        widget.deleteLater()
        self.tab_closed.emit(info.content_id)

        if self._tabs.count() == 0:
            self.setCurrentWidget(self._welcome)
            self.active_tab_changed.emit("", None)

    def _on_current_changed(self, index: int) -> None:
        if 0 <= index < len(self._tab_infos):
            info = self._tab_infos[index]
            self.active_tab_changed.emit(info.content_id, info.content_type)
        else:
            self.active_tab_changed.emit("", None)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_viewer(
        self, file_path: Path, content_type: ContentType
    ) -> QWidget:
        if content_type == ContentType.ASSET:
            if file_path.suffix.lower() in _IMAGE_EXTENSIONS:
                return ImageViewerWidget(file_path)
        return JsonViewerWidget(file_path)

    def _index_for_content(self, content_id: str) -> int | None:
        for index, info in enumerate(self._tab_infos):
            if info.content_id == content_id:
                return index
        return None

    @staticmethod
    def _tab_label(info: _TabInfo) -> str:
        if info.content_type == ContentType.AREA_JSON:
            base = info.file_path.name
        elif info.content_type == ContentType.PROJECT_MANIFEST:
            base = info.file_path.stem
        elif info.content_type == ContentType.SHARED_VARIABLES:
            base = info.file_path.stem
        elif info.content_type == ContentType.GLOBAL_ENTITIES:
            base = "global_entities"
        elif info.content_type == ContentType.DOCUMENTATION:
            base = "Docs"
        else:
            base = info.content_id.rsplit("/", 1)[-1]
        return f"*{base}" if info.dirty else base
