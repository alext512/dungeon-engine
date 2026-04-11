"""Dock panel listing available entity templates in a folder tree.

Uses ``FileTreePanel`` with an icon provider that extracts the first
visual frame from each template as a sprite preview.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QTransform

from area_editor.catalogs.template_catalog import TemplateCatalog
from area_editor.catalogs.tileset_catalog import TilesetCatalog
from area_editor.project_io.project_manifest import (
    TEMPLATE_ID_PREFIX,
    ProjectManifest,
    discover_entity_templates,
)
from area_editor.widgets.file_tree_panel import FileTreePanel


class TemplateListPanel(FileTreePanel):
    """Dock panel: folder tree of entity templates with sprite icons."""

    template_brush_selected = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(
            "Entity Templates",
            object_name="TemplateListPanel",
            icon_size=24,
            parent=parent,
        )
        self.file_selected.connect(self._on_file_selected)
        self._active_brush_template_id: str | None = None
        self._active_brush_font = QFont()
        self._active_brush_font.setBold(True)
        self._normal_font = QFont()
        self._active_brush_background = QBrush(QColor(40, 90, 120, 90))

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_templates(
        self,
        manifest: ProjectManifest,
        templates: TemplateCatalog,
        catalog: TilesetCatalog,
    ) -> None:
        """Populate from template paths with sprite icons."""
        self._tree.blockSignals(True)
        self._tree.clear()

        folder_nodes: dict[str, object] = {}
        from PySide6.QtWidgets import QTreeWidgetItem

        for entry in discover_entity_templates(manifest):
            content_id = entry.template_id
            display_id = content_id.removeprefix(f"{TEMPLATE_ID_PREFIX}/")
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
            item.setData(0, 256, (content_id, entry.file_path))
            item.setToolTip(0, content_id)

            visual = templates.get_first_visual(content_id)
            if visual is not None:
                frame_index = visual.frames[0] if visual.frames else 0
                pm = catalog.get_sprite_frame(
                    visual.path,
                    visual.frame_width,
                    visual.frame_height,
                    frame_index,
                )
                if pm is not None:
                    if visual.flip_x:
                        pm = pm.transformed(QTransform().scale(-1, 1))
                    scaled = pm.scaled(
                        QSize(24, 24),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.FastTransformation,
                    )
                    item.setIcon(0, QIcon(scaled))

        self._tree.blockSignals(False)
        self._refresh_brush_highlight()

    def clear_templates(self) -> None:
        self.clear_tree()
        self._active_brush_template_id = None

    def set_brush_active(self, template_id: str | None) -> None:
        """Highlight the active entity brush without clearing remembered selection."""
        self._active_brush_template_id = template_id
        self._refresh_brush_highlight()

    def _on_file_selected(self, content_id: str, _file_path: Path) -> None:
        self.template_brush_selected.emit(content_id)

    def _refresh_brush_highlight(self) -> None:
        stack = [self._tree.topLevelItem(i) for i in range(self._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item is None:
                continue
            data = item.data(0, 256)
            if data is not None:
                content_id = data[0]
                if content_id == self._active_brush_template_id:
                    item.setFont(0, self._active_brush_font)
                    item.setBackground(0, self._active_brush_background)
                else:
                    item.setFont(0, self._normal_font)
                    item.setBackground(0, QBrush())
            for index in range(item.childCount()):
                stack.append(item.child(index))
