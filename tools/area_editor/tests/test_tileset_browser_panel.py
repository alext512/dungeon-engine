"""Widget tests for the tileset browser panel."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from area_editor.catalogs.tileset_catalog import TilesetCatalog
from area_editor.documents.area_document import TilesetRef
from area_editor.project_io.asset_resolver import AssetResolver
from area_editor.widgets.tileset_browser_panel import TilesetBrowserPanel


class TestTilesetBrowserPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_select_gid_switches_to_owning_tileset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            assets.mkdir()

            first = QPixmap(16, 16)
            first.fill(QColor("red"))
            self.assertTrue(first.save(str(assets / "one.png")))

            second = QPixmap(16, 16)
            second.fill(QColor("blue"))
            self.assertTrue(second.save(str(assets / "two.png")))

            catalog = TilesetCatalog(AssetResolver([assets]))
            panel = TilesetBrowserPanel()
            panel.set_tilesets(
                [
                    TilesetRef(1, "assets/one.png", 16, 16),
                    TilesetRef(9, "assets/two.png", 16, 16),
                ],
                catalog,
            )

            panel.select_gid(9)

            self.assertEqual(panel.selected_gid, 9)
            self.assertEqual(panel.current_tileset_index, 1)
            self.assertEqual(panel._status.text(), "GID: 9")
