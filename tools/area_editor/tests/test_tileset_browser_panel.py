"""Widget tests for the tileset browser panel."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
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

    def test_sprite_frame_cache_distinguishes_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            assets.mkdir()

            sheet = QPixmap(32, 32)
            sheet.fill(QColor("red"))
            self.assertTrue(sheet.save(str(assets / "sheet.png")))

            catalog = TilesetCatalog(AssetResolver([assets]))

            small = catalog.get_sprite_frame("assets/sheet.png", 16, 16, 0)
            large = catalog.get_sprite_frame("assets/sheet.png", 32, 32, 0)

            self.assertIsNotNone(small)
            self.assertIsNotNone(large)
            assert small is not None
            assert large is not None
            self.assertEqual((small.width(), small.height()), (16, 16))
            self.assertEqual((large.width(), large.height()), (32, 32))

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
            self.assertFalse(panel.brush_is_erase)
            self.assertIn("Paint GID 9", panel._status.text())

    def test_switching_tileset_resets_to_eraser(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            assets.mkdir()

            first = QPixmap(32, 16)
            first.fill(QColor("red"))
            self.assertTrue(first.save(str(assets / "one.png")))

            second = QPixmap(32, 16)
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

            panel.select_gid(2)
            panel._combo.setCurrentIndex(1)

            self.assertEqual(panel.current_tileset_index, 1)
            self.assertEqual(panel.selected_gid, 0)
            self.assertTrue(panel.brush_is_erase)
            self.assertIn("Erase", panel._status.text())

    def test_sheet_renders_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            assets.mkdir()

            sheet = QPixmap(32, 16)
            sheet.fill(QColor("green"))
            self.assertTrue(sheet.save(str(assets / "sheet.png")))

            catalog = TilesetCatalog(AssetResolver([assets]))
            panel = TilesetBrowserPanel()
            panel.resize(240, 240)
            panel.set_tilesets(
                [TilesetRef(1, "assets/sheet.png", 16, 16)],
                catalog,
            )

            target = QPixmap(QSize(240, 240))
            target.fill(QColor("black"))
            panel._sheet_widget.render(target)

            self.assertFalse(target.isNull())

    def test_inactive_tile_brush_is_dimmed_but_remembered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            assets.mkdir()

            sheet = QPixmap(16, 16)
            sheet.fill(QColor("magenta"))
            self.assertTrue(sheet.save(str(assets / "sheet.png")))

            catalog = TilesetCatalog(AssetResolver([assets]))
            panel = TilesetBrowserPanel()
            panel.set_tilesets(
                [TilesetRef(1, "assets/sheet.png", 16, 16)],
                catalog,
            )

            panel.select_gid(1)
            panel.set_brush_active(False)

            self.assertFalse(panel.brush_active)
            self.assertEqual(panel.selected_gid, 1)
            self.assertIn("Remembered GID 1", panel._status.text())

    def test_multi_tile_selection_becomes_stamp_brush(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets = root / "assets"
            assets.mkdir()

            sheet = QPixmap(32, 32)
            sheet.fill(QColor("yellow"))
            self.assertTrue(sheet.save(str(assets / "sheet.png")))

            catalog = TilesetCatalog(AssetResolver([assets]))
            panel = TilesetBrowserPanel()
            panel.set_tilesets(
                [TilesetRef(1, "assets/sheet.png", 16, 16)],
                catalog,
            )

            panel._on_tile_selected(1, ((1, 2), (3, 4)))

            self.assertEqual(panel.selected_gid, 1)
            self.assertEqual(panel.selected_brush_block, ((1, 2), (3, 4)))
            self.assertIn("2x2 stamp", panel._status.text())
