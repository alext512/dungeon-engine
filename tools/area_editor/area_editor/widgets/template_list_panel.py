"""Dock panel listing available entity templates in a folder tree.

Uses ``FileTreePanel`` with an icon provider that extracts the first
visual frame from each template as a sprite preview.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon

from area_editor.catalogs.template_catalog import TemplateCatalog
from area_editor.catalogs.tileset_catalog import TilesetCatalog
from area_editor.project_io.manifest import (
    TEMPLATE_ID_PREFIX,
    ProjectManifest,
    discover_entity_templates,
)
from area_editor.widgets.file_tree_panel import FileTreePanel


class TemplateListPanel(FileTreePanel):
    """Dock panel: folder tree of entity templates with sprite icons."""

    def __init__(self, parent=None) -> None:
        super().__init__(
            "Entity Templates",
            object_name="TemplateListPanel",
            icon_size=24,
            parent=parent,
        )

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
                    scaled = pm.scaled(
                        QSize(24, 24),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.FastTransformation,
                    )
                    item.setIcon(0, QIcon(scaled))

        self._tree.blockSignals(False)

    def clear_templates(self) -> None:
        self.clear_tree()
