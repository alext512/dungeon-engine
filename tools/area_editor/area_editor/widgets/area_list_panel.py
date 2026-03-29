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

    def set_areas(self, entries: list[AreaEntry]) -> None:
        """Populate the tree from area entries."""
        root_dirs: dict[str, Path] = {}
        # Collect unique parent dirs to pass as roots
        for entry in entries:
            for part in entry.file_path.resolve().parents:
                pass  # just need the structure
        # Use populate with the manifest's area_paths instead
        # Store entries for lookup
        self._entry_map: dict[str, AreaEntry] = {e.area_id: e for e in entries}

        # Build tree manually from entries (they already have correct ids)
        self._tree.blockSignals(True)
        self._tree.clear()

        folder_nodes: dict[str, object] = {}
        from PySide6.QtWidgets import QTreeWidgetItem

        for entry in sorted(entries, key=lambda e: e.area_id):
            display_id = entry.area_id.removeprefix(f"{AREA_ID_PREFIX}/")
            parts = display_id.split("/")
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
            item.setData(0, 256, (entry.area_id, entry.file_path))
            item.setToolTip(0, entry.area_id)

        self._tree.blockSignals(False)

    def highlight_area(self, area_id: str) -> None:
        """Select the item matching *area_id* without emitting a signal."""
        self.select_by_id(area_id)

    def clear_areas(self) -> None:
        self.clear_tree()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_file_selected(self, content_id: str, file_path: Path) -> None:
        self.area_selected.emit(content_id, file_path)

    def _on_file_open_requested(self, content_id: str, file_path: Path) -> None:
        self.area_open_requested.emit(content_id, file_path)
