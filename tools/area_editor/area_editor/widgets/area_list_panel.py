"""Dock panel that lists all discovered areas in a folder tree.

Thin wrapper around ``FileTreePanel`` that emits ``area_selected``
with the typed ``AreaEntry`` data.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal

from area_editor.project_io.manifest import AREA_ID_PREFIX, AreaEntry
from area_editor.widgets.file_tree_panel import FileTreePanel


class AreaListPanel(FileTreePanel):
    """Left dock: browsable folder tree of area files."""

    area_selected = Signal(str, Path)  # (area_id, file_path) — single-click
    area_open_requested = Signal(str, Path)  # (area_id, file_path) — double-click

    def __init__(self, parent=None) -> None:
        super().__init__(
            "Areas",
            object_name="AreaListPanel",
            parent=parent,
        )
        self.file_selected.connect(self._on_file_selected)
        self.file_open_requested.connect(self._on_file_open_requested)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_areas(self, entries: list[AreaEntry], root_dirs: list[Path] | None = None) -> None:
        """Populate the tree from area entries."""
        self._entry_map: dict[str, AreaEntry] = {e.area_id: e for e in entries}
        self._tree.blockSignals(True)
        self._tree.clear()
        self._tree.blockSignals(False)
        self._content_prefix = AREA_ID_PREFIX
        self.populate(root_dirs or [], icon_provider=None)
        self._tree.blockSignals(True)
        for item in self._iter_tree_items():
            data = item.data(0, self._FILE_ROLE)
            if data is None:
                continue
            content_id, file_path = data
            item.setData(0, self._FILE_ROLE, (content_id, Path(file_path)))
            item.setToolTip(0, content_id)
        self._tree.blockSignals(False)

    def highlight_area(self, area_id: str) -> None:
        """Select the item matching *area_id* without emitting a signal."""
        self.select_by_id(area_id)

    def clear_areas(self) -> None:
        self.clear_tree()

    def _iter_tree_items(self):
        stack = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item is None:
                continue
            yield item
            for index in range(item.childCount()):
                stack.append(item.child(index))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_file_selected(self, content_id: str, file_path: Path) -> None:
        self.area_selected.emit(content_id, file_path)

    def _on_file_open_requested(self, content_id: str, file_path: Path) -> None:
        self.area_open_requested.emit(content_id, file_path)
