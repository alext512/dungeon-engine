"""Focused main-window tests for per-project open state and paint restoration."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.app.main_window import MainWindow
from fixture_project import create_editor_fixture_project


class TestMainWindowPaintState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])
        cls._fixture_temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._fixture_temp.cleanup)
        cls._fixture = create_editor_fixture_project(Path(cls._fixture_temp.name))

    def setUp(self):
        self.window = MainWindow()
        self.window.open_project(self._fixture.project_file)

    def tearDown(self):
        self.window.close()

    def test_open_project_dialog_starts_in_last_project_directory(self):
        last_project_dir = self._fixture.project_file.parent
        self.window._settings.setValue("last_project_path", str(last_project_dir))

        with patch(
            "area_editor.app.main_window.QFileDialog.getOpenFileName",
            return_value=("", ""),
        ) as dialog:
            self.window._on_open_project()

        self.assertEqual(dialog.call_args.args[2], str(last_project_dir))

    def test_open_project_dialog_uses_parent_when_last_path_is_project_file(self):
        with patch(
            "area_editor.app.main_window.QFileDialog.getOpenFileName",
            return_value=("", ""),
        ) as dialog:
            self.window._settings.setValue("last_project_path", str(self._fixture.project_file))
            self.window._on_open_project()

        self.assertEqual(dialog.call_args.args[2], str(self._fixture.project_file.parent))

    def test_paint_mode_state_restores_per_area_tab(self):
        self.window._open_area("areas/village_square", self._fixture.village_square)
        self.window._layer_panel.set_active_layer(1)
        self.window._on_active_layer_changed(1)
        self.window._tileset_panel.select_gid(6)
        self.window._on_tile_selected(6)
        self.window._on_paint_tiles_toggled(True)

        self.window._open_area("areas/village_house", self._fixture.village_house)
        self.window._layer_panel.set_active_layer(2)
        self.window._on_active_layer_changed(2)
        self.window._tileset_panel.select_gid(3)
        self.window._on_tile_selected(3)
        self.window._on_paint_tiles_toggled(True)

        self.window._open_area("areas/village_square", self._fixture.village_square)

        active_canvas = self.window._active_canvas()
        self.assertIsNotNone(active_canvas)
        assert active_canvas is not None
        self.assertEqual(self.window._tab_widget.active_info().content_id, "areas/village_square")
        self.assertTrue(self.window._paint_tiles_action.isChecked())
        self.assertEqual(self.window._layer_panel.active_layer, 1)
        self.assertEqual(self.window._layer_panel.active_layer_name(), "structure")
        self.assertEqual(self.window._tileset_panel.selected_gid, 6)
        self.assertEqual(active_canvas.active_layer, 1)
        self.assertEqual(active_canvas.selected_gid, 6)
        self.assertTrue(active_canvas.tile_paint_mode)

        self.window._open_area("areas/village_house", self._fixture.village_house)

        active_canvas = self.window._active_canvas()
        self.assertIsNotNone(active_canvas)
        assert active_canvas is not None
        self.assertEqual(self.window._tab_widget.active_info().content_id, "areas/village_house")
        self.assertTrue(self.window._paint_tiles_action.isChecked())
        self.assertEqual(self.window._layer_panel.active_layer, 2)
        self.assertEqual(self.window._layer_panel.active_layer_name(), "overlay")
        self.assertEqual(self.window._tileset_panel.selected_gid, 3)
        self.assertEqual(active_canvas.active_layer, 2)
        self.assertEqual(active_canvas.selected_gid, 3)
        self.assertTrue(active_canvas.tile_paint_mode)
