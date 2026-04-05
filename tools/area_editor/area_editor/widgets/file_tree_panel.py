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

    _FILE_ROLE = 256
    _FOLDER_ROLE = 257

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
        preserve_file_extensions: bool = False,
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
        self._preserve_file_extensions = preserve_file_extensions
        self._context_menu_builder: Callable[[QMenu, str, Path], None] | None = None
        self._folder_context_menu_builder: (
            Callable[[QMenu, str, Path, Path], None] | None
        ) = None
        self._empty_space_context_menu_builder: (
            Callable[[QMenu, list[Path], str | None, Path | None, Path | None], None] | None
        ) = None
        self._root_dirs: list[Path] = []
        self._expanded_folder_paths: set[str] = set()
        self._root_signature: tuple[str, ...] = ()

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        if icon_size > 0:
            self._tree.setIconSize(QSize(icon_size, icon_size))
        self._tree.currentItemChanged.connect(self._on_item_changed)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.itemExpanded.connect(self._on_item_expanded)
        self._tree.itemCollapsed.connect(self._on_item_collapsed)
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
        self._root_dirs = [directory.resolve() for directory in root_dirs if directory.is_dir()]
        root_signature = tuple(str(directory) for directory in self._root_dirs)
        if root_signature != self._root_signature:
            self._expanded_folder_paths.clear()
            self._root_signature = root_signature

        folder_nodes: dict[tuple[Path, str], QTreeWidgetItem] = {}

        def ensure_folder_node(root_dir: Path, relative_parts: list[str]) -> QTreeWidgetItem:
            parent = self._tree.invisibleRootItem()
            current_item: QTreeWidgetItem | None = None
            current_relative: list[str] = []
            for folder_name in relative_parts:
                current_relative.append(folder_name)
                relative_path = "/".join(current_relative)
                folder_key = (root_dir, relative_path)
                if folder_key not in folder_nodes:
                    folder_item = QTreeWidgetItem(parent, [folder_name])
                    folder_item.setData(
                        0,
                        self._FOLDER_ROLE,
                        (relative_path, root_dir / Path(*current_relative), root_dir),
                    )
                    folder_item.setToolTip(0, relative_path)
                    folder_item.setExpanded(relative_path in self._expanded_folder_paths)
                    folder_nodes[folder_key] = folder_item
                current_item = folder_nodes[folder_key]
                parent = current_item
            if current_item is None:
                raise RuntimeError("Folder node creation requires at least one relative part.")
            return current_item

        for root_dir, relative_path, _folder_path in self._discover_folders(root_dirs):
            parts = [part for part in relative_path.split("/") if part]
            if parts:
                ensure_folder_node(root_dir, parts)

        entries = self._discover(root_dirs)
        for content_id, file_path, root_dir in entries:
            parts = self._display_parts_for_content_id(content_id)

            if len(parts) == 1:
                parent = self._tree.invisibleRootItem()
                leaf_name = parts[0]
            else:
                parent = ensure_folder_node(root_dir, parts[:-1])
                leaf_name = parts[-1]

            item = QTreeWidgetItem(parent, [leaf_name])
            item.setData(0, self._FILE_ROLE, (content_id, file_path))
            item.setToolTip(0, content_id)

            if icon_provider is not None:
                icon = icon_provider(content_id, file_path)
                if icon is not None:
                    item.setIcon(0, icon)

        self._tree.blockSignals(False)

    def clear_tree(self) -> None:
        self._tree.clear()
        self._expanded_folder_paths.clear()
        self._root_signature = ()

    def set_context_menu_builder(
        self,
        builder: Callable[[QMenu, str, Path], None] | None,
    ) -> None:
        """Install an optional callback that can add file-specific actions."""
        self._context_menu_builder = builder

    def set_folder_context_menu_builder(
        self,
        builder: Callable[[QMenu, str, Path, Path], None] | None,
    ) -> None:
        self._folder_context_menu_builder = builder

    def set_empty_space_context_menu_builder(
        self,
        builder: Callable[[QMenu, list[Path], str | None, Path | None, Path | None], None]
        | None,
    ) -> None:
        self._empty_space_context_menu_builder = builder

    def select_by_id(self, content_id: str) -> None:
        """Select the item with matching id without emitting a signal."""
        self._tree.blockSignals(True)
        item = self._find_item(content_id)
        if item is not None:
            parent = item.parent()
            while parent is not None:
                parent.setExpanded(True)
                folder_data = parent.data(0, self._FOLDER_ROLE)
                if folder_data is not None:
                    relative_path, _folder_path, _root_dir = folder_data
                    self._expanded_folder_paths.add(str(relative_path))
                parent = parent.parent()
            self._tree.setCurrentItem(item)
        self._tree.blockSignals(False)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_item_changed(self, current: QTreeWidgetItem | None, _prev) -> None:
        if current is None:
            return
        data = current.data(0, self._FILE_ROLE)
        if data is not None:
            content_id, file_path = data
            self.file_selected.emit(content_id, file_path)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, self._FILE_ROLE)
        if data is not None:
            content_id, file_path = data
            self.file_open_requested.emit(content_id, file_path)

    def _on_context_menu(self, position) -> None:
        item = self._tree.itemAt(position)
        menu = QMenu(self)
        if item is None:
            if self._empty_space_context_menu_builder is not None:
                current_relative_path, current_folder_path, current_root_dir = (
                    self._current_folder_context()
                )
                self._empty_space_context_menu_builder(
                    menu,
                    list(self._root_dirs),
                    current_relative_path,
                    current_folder_path,
                    current_root_dir,
                )
        else:
            data = item.data(0, self._FILE_ROLE)
            if data is not None:
                content_id, file_path = data
                open_action = QAction("Open", self)
                open_action.triggered.connect(
                    lambda: self.file_open_requested.emit(content_id, file_path)
                )
                menu.addAction(open_action)
                if self._context_menu_builder is not None:
                    self._context_menu_builder(menu, content_id, file_path)
            else:
                folder_data = item.data(0, self._FOLDER_ROLE)
                if folder_data is not None and self._folder_context_menu_builder is not None:
                    relative_path, folder_path, root_dir = folder_data
                    self._folder_context_menu_builder(
                        menu,
                        str(relative_path),
                        Path(folder_path),
                        Path(root_dir),
                    )
        if menu.actions():
            menu.exec(self._tree.viewport().mapToGlobal(position))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _discover(self, root_dirs: list[Path]) -> list[tuple[str, Path, Path]]:
        """Scan root directories and return (content_id, path) pairs."""
        entries: list[tuple[str, Path, Path]] = []
        seen: set[Path] = set()
        for directory in root_dirs:
            if not directory.is_dir():
                continue
            resolved_root = directory.resolve()
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
                    relative = resolved.relative_to(resolved_root)
                    if self._preserve_file_extensions:
                        content_id = str(relative).replace("\\", "/")
                    else:
                        content_id = str(relative.with_suffix("")).replace("\\", "/")
                except ValueError:
                    content_id = f.name if self._preserve_file_extensions else f.stem
                if self._content_prefix:
                    content_id = f"{self._content_prefix}/{content_id}"
                entries.append((content_id, f, resolved_root))
        return sorted(entries, key=lambda e: e[0])

    def _discover_folders(self, root_dirs: list[Path]) -> list[tuple[Path, str, Path]]:
        folders: list[tuple[Path, str, Path]] = []
        seen: set[tuple[Path, str]] = set()
        for directory in root_dirs:
            if not directory.is_dir():
                continue
            resolved_root = directory.resolve()
            for folder_path in sorted(
                (path for path in directory.rglob("*") if path.is_dir()),
                key=lambda path: str(path).lower(),
            ):
                resolved = folder_path.resolve()
                try:
                    relative = resolved.relative_to(resolved_root)
                except ValueError:
                    continue
                relative_path = str(relative).replace("\\", "/").strip("/")
                if not relative_path:
                    continue
                folder_key = (resolved_root, relative_path)
                if folder_key in seen:
                    continue
                seen.add(folder_key)
                folders.append((resolved_root, relative_path, resolved))
        return folders

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
            data = item.data(0, self._FILE_ROLE)
            if data is not None and data[0] == content_id:
                return item
            for i in range(item.childCount()):
                stack.append(item.child(i))
        return None

    def _current_folder_context(self) -> tuple[str | None, Path | None, Path | None]:
        item = self._tree.currentItem()
        while item is not None:
            folder_data = item.data(0, self._FOLDER_ROLE)
            if folder_data is not None:
                relative_path, folder_path, root_dir = folder_data
                return str(relative_path), Path(folder_path), Path(root_dir)
            item = item.parent()
        return None, None, None

    def _on_item_expanded(self, item: QTreeWidgetItem) -> None:
        folder_data = item.data(0, self._FOLDER_ROLE)
        if folder_data is None:
            return
        relative_path, _folder_path, _root_dir = folder_data
        self._expanded_folder_paths.add(str(relative_path))

    def _on_item_collapsed(self, item: QTreeWidgetItem) -> None:
        folder_data = item.data(0, self._FOLDER_ROLE)
        if folder_data is None:
            return
        relative_path, _folder_path, _root_dir = folder_data
        self._expanded_folder_paths.discard(str(relative_path))
