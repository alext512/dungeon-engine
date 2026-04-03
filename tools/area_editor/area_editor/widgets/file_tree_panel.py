"""Reusable dock panel that displays a folder tree for a project content root.

Used by all content browser tabs (areas, templates, dialogues, named
commands, assets).  Scans one or more root directories and builds a
tree mirroring the filesystem hierarchy.

Subclasses or callers can optionally provide icons per item and connect
to selection signals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QDockWidget,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class FileTreePanel(QDockWidget):
    """Generic dock panel showing a folder tree of project files."""

    file_selected = Signal(str, Path)  # (content_id, file_path) — single-click
    file_open_requested = Signal(str, Path)  # (content_id, file_path) — double-click / context menu

    def __init__(
        self,
        title: str,
        *,
        object_name: str | None = None,
        icon_size: int = 0,
        file_extensions: tuple[str, ...] = (".json",),
        content_prefix: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(title, parent)
        self.setObjectName(object_name or title.replace(" ", ""))
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self._file_extensions = file_extensions
        self._content_prefix = (
            content_prefix.strip("/").replace("\\", "/") if content_prefix else None
        )
        self._context_menu_builder: Callable[[QMenu, str, Path], None] | None = None

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        if icon_size > 0:
            self._tree.setIconSize(QSize(icon_size, icon_size))
        self._tree.currentItemChanged.connect(self._on_item_changed)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self._tree)

        self.setWidget(container)
        self.setMinimumWidth(140)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def populate(
        self,
        root_dirs: list[Path],
        *,
        icon_provider: Callable[[str, Path], QIcon | None] | None = None,
    ) -> None:
        """Scan *root_dirs* and build the folder tree.

        *icon_provider* is called with ``(content_id, file_path)`` and
        may return a ``QIcon`` for the item, or ``None``.
        """
        self._tree.blockSignals(True)
        self._tree.clear()

        folder_nodes: dict[str, QTreeWidgetItem] = {}

        entries = self._discover(root_dirs)
        for content_id, file_path in entries:
            parts = self._display_parts_for_content_id(content_id)

            # Build folder nodes
            if len(parts) == 1:
                parent = self._tree.invisibleRootItem()
                leaf_name = parts[0]
            else:
                parent = self._tree.invisibleRootItem()
                for depth, folder_name in enumerate(parts[:-1]):
                    folder_key = "/".join(parts[: depth + 1])
                    if folder_key not in folder_nodes:
                        folder_item = QTreeWidgetItem(parent, [folder_name])
                        folder_item.setData(0, 256, None)
                        folder_item.setExpanded(True)
                        folder_nodes[folder_key] = folder_item
                    parent = folder_nodes[folder_key]
                leaf_name = parts[-1]

            item = QTreeWidgetItem(parent, [leaf_name])
            item.setData(0, 256, (content_id, file_path))
            item.setToolTip(0, content_id)

            if icon_provider is not None:
                icon = icon_provider(content_id, file_path)
                if icon is not None:
                    item.setIcon(0, icon)

        self._tree.blockSignals(False)

    def clear_tree(self) -> None:
        self._tree.clear()

    def set_context_menu_builder(
        self,
        builder: Callable[[QMenu, str, Path], None] | None,
    ) -> None:
        """Install an optional callback that can add file-specific actions."""
        self._context_menu_builder = builder

    def select_by_id(self, content_id: str) -> None:
        """Select the item with matching id without emitting a signal."""
        self._tree.blockSignals(True)
        item = self._find_item(content_id)
        if item is not None:
            self._tree.setCurrentItem(item)
        self._tree.blockSignals(False)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_item_changed(self, current: QTreeWidgetItem | None, _prev) -> None:
        if current is None:
            return
        data = current.data(0, 256)
        if data is not None:
            content_id, file_path = data
            self.file_selected.emit(content_id, file_path)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, 256)
        if data is not None:
            content_id, file_path = data
            self.file_open_requested.emit(content_id, file_path)

    def _on_context_menu(self, position) -> None:
        item = self._tree.itemAt(position)
        if item is None:
            return
        data = item.data(0, 256)
        if data is None:
            return  # folder node, no action
        content_id, file_path = data
        menu = QMenu(self)
        open_action = QAction("Open", self)
        open_action.triggered.connect(
            lambda: self.file_open_requested.emit(content_id, file_path)
        )
        menu.addAction(open_action)
        if self._context_menu_builder is not None:
            self._context_menu_builder(menu, content_id, file_path)
        if menu.actions():
            menu.exec(self._tree.viewport().mapToGlobal(position))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _discover(self, root_dirs: list[Path]) -> list[tuple[str, Path]]:
        """Scan root directories and return (content_id, path) pairs."""
        entries: list[tuple[str, Path]] = []
        seen: set[Path] = set()
        for directory in root_dirs:
            if not directory.is_dir():
                continue
            for f in sorted(directory.rglob("*")):
                if not f.is_file():
                    continue
                if self._file_extensions and f.suffix.lower() not in self._file_extensions:
                    continue
                resolved = f.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                # Derive content id from relative path
                try:
                    relative = resolved.relative_to(directory.resolve())
                    content_id = str(relative.with_suffix("")).replace("\\", "/")
                except ValueError:
                    content_id = f.stem
                if self._content_prefix:
                    content_id = f"{self._content_prefix}/{content_id}"
                entries.append((content_id, f))
        return sorted(entries, key=lambda e: e[0])

    def _display_parts_for_content_id(self, content_id: str) -> list[str]:
        display_id = content_id
        if self._content_prefix:
            prefix = f"{self._content_prefix}/"
            if display_id.startswith(prefix):
                display_id = display_id[len(prefix) :]
        return [part for part in display_id.split("/") if part]

    def _find_item(self, content_id: str) -> QTreeWidgetItem | None:
        stack = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item is None:
                continue
            data = item.data(0, 256)
            if data is not None and data[0] == content_id:
                return item
            for i in range(item.childCount()):
                stack.append(item.child(i))
        return None
