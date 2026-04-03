"""Integration tests for main-window editor state restoration."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

from area_editor.app.main_window import MainWindow
from area_editor.widgets.document_tab_widget import ContentType
from area_editor.widgets.json_viewer_widget import JsonViewerWidget

_TEST_PROJECT = (
    Path(__file__).resolve().parent.parent.parent.parent / "projects" / "test_project"
)
_PROJECT_FILE = _TEST_PROJECT / "project.json"
_VILLAGE_SQUARE = _TEST_PROJECT / "areas" / "village_square.json"
_VILLAGE_HOUSE = _TEST_PROJECT / "areas" / "village_house.json"


@unittest.skipUnless(_PROJECT_FILE.is_file(), "test_project fixture not found")
class TestMainWindowPaintState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.open_project(_PROJECT_FILE)

    def tearDown(self):
        self.window.close()

    def test_open_project_dialog_starts_in_last_project_directory(self):
        last_project_dir = _PROJECT_FILE.parent
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
            self.window._settings.setValue("last_project_path", str(_PROJECT_FILE))
            self.window._on_open_project()

        self.assertEqual(dialog.call_args.args[2], str(_PROJECT_FILE.parent))

    def test_paint_mode_state_restores_per_area_tab(self):
        self.window._open_area("areas/village_square", _VILLAGE_SQUARE)
        self.window._layer_panel.set_active_layer(1)
        self.window._on_active_layer_changed(1)
        self.window._tileset_panel.select_gid(6)
        self.window._on_tile_selected(6)
        self.window._on_paint_tiles_toggled(True)

        self.window._open_area("areas/village_house", _VILLAGE_HOUSE)
        self.window._layer_panel.set_active_layer(2)
        self.window._on_active_layer_changed(2)
        self.window._tileset_panel.select_gid(3)
        self.window._on_tile_selected(3)
        self.window._on_paint_tiles_toggled(True)

        self.window._open_area("areas/village_square", _VILLAGE_SQUARE)

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

        self.window._open_area("areas/village_house", _VILLAGE_HOUSE)

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


class TestMainWindowTilesetEditing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def _create_project(self, root: Path) -> Path:
        project = root / "project"
        assets = project / "assets"
        areas = project / "areas"
        assets.mkdir(parents=True)
        areas.mkdir()

        base = QPixmap(32, 16)
        base.fill(QColor("green"))
        self.assertTrue(base.save(str(assets / "base.png")))

        extra = QPixmap(16, 16)
        extra.fill(QColor("yellow"))
        self.assertTrue(extra.save(str(assets / "extra.png")))

        (project / "project.json").write_text(
            '{\n  "startup_area": "areas/demo"\n}\n',
            encoding="utf-8",
        )
        (areas / "demo.json").write_text(
            (
                '{\n'
                '  "name": "Demo",\n'
                '  "tile_size": 16,\n'
                '  "tilesets": [\n'
                '    {\n'
                '      "firstgid": 1,\n'
                '      "path": "assets/base.png",\n'
                '      "tile_width": 16,\n'
                '      "tile_height": 16\n'
                '    }\n'
                '  ],\n'
                '  "tile_layers": [\n'
                '    {\n'
                '      "name": "ground",\n'
                '      "render_order": 0,\n'
                '      "y_sort": false,\n'
                '      "stack_order": 0,\n'
                '      "grid": [[1, 2]]\n'
                '    }\n'
                '  ],\n'
                '  "entities": [],\n'
                '  "variables": {}\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        return project / "project.json"

    def _create_layering_project(self, root: Path) -> Path:
        project = root / "project"
        assets = project / "assets"
        areas = project / "areas"
        assets.mkdir(parents=True)
        areas.mkdir()

        base = QPixmap(16, 16)
        base.fill(QColor("cyan"))
        self.assertTrue(base.save(str(assets / "base.png")))

        (project / "project.json").write_text(
            '{\n  "startup_area": "areas/demo"\n}\n',
            encoding="utf-8",
        )
        (areas / "demo.json").write_text(
            (
                '{\n'
                '  "name": "Demo",\n'
                '  "tile_size": 16,\n'
                '  "tilesets": [\n'
                '    {\n'
                '      "firstgid": 1,\n'
                '      "path": "assets/base.png",\n'
                '      "tile_width": 16,\n'
                '      "tile_height": 16\n'
                '    }\n'
                '  ],\n'
                '  "tile_layers": [\n'
                '    {\n'
                '      "name": "ground",\n'
                '      "render_order": 0,\n'
                '      "y_sort": false,\n'
                '      "stack_order": 0,\n'
                '      "grid": [[1]]\n'
                '    }\n'
                '  ],\n'
                '  "entities": [\n'
                '    {\n'
                '      "id": "actor",\n'
                '      "grid_x": 0,\n'
                '      "grid_y": 0,\n'
                '      "render_order": 10,\n'
                '      "y_sort": false,\n'
                '      "stack_order": 0\n'
                '    }\n'
                '  ],\n'
                '  "variables": {}\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        return project / "project.json"

    def _create_entity_paint_project(self, root: Path) -> Path:
        project = root / "project"
        assets = project / "assets"
        areas = project / "areas"
        templates = project / "entity_templates"
        assets.mkdir(parents=True)
        areas.mkdir()
        templates.mkdir()

        base = QPixmap(16, 16)
        base.fill(QColor("white"))
        self.assertTrue(base.save(str(assets / "base.png")))

        (project / "project.json").write_text(
            (
                '{\n'
                '  "startup_area": "areas/demo",\n'
                '  "entity_template_paths": ["entity_templates/"]\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        (areas / "demo.json").write_text(
            (
                '{\n'
                '  "name": "Demo",\n'
                '  "tile_size": 16,\n'
                '  "tilesets": [\n'
                '    {\n'
                '      "firstgid": 1,\n'
                '      "path": "assets/base.png",\n'
                '      "tile_width": 16,\n'
                '      "tile_height": 16\n'
                '    }\n'
                '  ],\n'
                '  "tile_layers": [\n'
                '    {\n'
                '      "name": "ground",\n'
                '      "render_order": 0,\n'
                '      "y_sort": false,\n'
                '      "stack_order": 0,\n'
                '      "grid": [[1, 1], [1, 1]]\n'
                '    }\n'
                '  ],\n'
                '  "entities": [],\n'
                '  "variables": {}\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        (templates / "npc.json").write_text(
            (
                '{\n'
                '  "render_order": 10,\n'
                '  "y_sort": true,\n'
                '  "visuals": []\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        return project / "project.json"

    def _create_entity_select_project(self, root: Path) -> Path:
        project = root / "project"
        assets = project / "assets"
        areas = project / "areas"
        assets.mkdir(parents=True)
        areas.mkdir()

        base = QPixmap(16, 16)
        base.fill(QColor("magenta"))
        self.assertTrue(base.save(str(assets / "base.png")))

        (project / "project.json").write_text(
            '{\n  "startup_area": "areas/demo"\n}\n',
            encoding="utf-8",
        )
        (areas / "demo.json").write_text(
            (
                '{\n'
                '  "name": "Demo",\n'
                '  "tile_size": 16,\n'
                '  "tilesets": [\n'
                '    {\n'
                '      "firstgid": 1,\n'
                '      "path": "assets/base.png",\n'
                '      "tile_width": 16,\n'
                '      "tile_height": 16\n'
                '    }\n'
                '  ],\n'
                '  "tile_layers": [\n'
                '    {\n'
                '      "name": "ground",\n'
                '      "render_order": 0,\n'
                '      "y_sort": false,\n'
                '      "stack_order": 0,\n'
                '      "grid": [[1, 1], [1, 1]]\n'
                '    }\n'
                '  ],\n'
                '  "entities": [\n'
                '    {\n'
                '      "id": "npc_1",\n'
                '      "grid_x": 0,\n'
                '      "grid_y": 0,\n'
                '      "render_order": 10,\n'
                '      "y_sort": true,\n'
                '      "stack_order": 0\n'
                '    },\n'
                '    {\n'
                '      "id": "npc_2",\n'
                '      "grid_x": 0,\n'
                '      "grid_y": 0,\n'
                '      "render_order": 10,\n'
                '      "y_sort": true,\n'
                '      "stack_order": 2\n'
                '    }\n'
                '  ],\n'
                '  "variables": {}\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        return project / "project.json"

    def _create_entity_fields_project(self, root: Path) -> Path:
        project = root / "project"
        assets = project / "assets"
        areas = project / "areas"
        templates = project / "entity_templates"
        assets.mkdir(parents=True)
        areas.mkdir()
        templates.mkdir()

        base = QPixmap(16, 16)
        base.fill(QColor("blue"))
        self.assertTrue(base.save(str(assets / "base.png")))

        (project / "project.json").write_text(
            (
                '{\n'
                '  "startup_area": "areas/demo",\n'
                '  "entity_template_paths": ["entity_templates/"],\n'
                '  "shared_variables_path": "shared_variables.json"\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        (project / "shared_variables.json").write_text(
            (
                '{\n'
                '  "display": {\n'
                '    "internal_width": 256,\n'
                '    "internal_height": 192\n'
                '  }\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        (areas / "demo.json").write_text(
            (
                '{\n'
                '  "name": "Demo",\n'
                '  "tile_size": 16,\n'
                '  "tilesets": [\n'
                '    {\n'
                '      "firstgid": 1,\n'
                '      "path": "assets/base.png",\n'
                '      "tile_width": 16,\n'
                '      "tile_height": 16\n'
                '    }\n'
                '  ],\n'
                '  "tile_layers": [\n'
                '    {\n'
                '      "name": "ground",\n'
                '      "render_order": 0,\n'
                '      "y_sort": false,\n'
                '      "stack_order": 0,\n'
                '      "grid": [[1, 1], [1, 1]]\n'
                '    }\n'
                '  ],\n'
                '  "entities": [\n'
                '    {\n'
                '      "id": "house_door",\n'
                '      "grid_x": 0,\n'
                '      "grid_y": 0,\n'
                '      "template": "entity_templates/area_door",\n'
                '      "parameters": {\n'
                '        "target_area": "areas/village_house",\n'
                '        "target_entry": "from_square"\n'
                '      },\n'
                '      "render_order": 10,\n'
                '      "y_sort": true,\n'
                '      "stack_order": 0\n'
                '    },\n'
                '    {\n'
                '      "id": "title_backdrop",\n'
                '      "pixel_x": 12,\n'
                '      "pixel_y": 18,\n'
                '      "template": "entity_templates/display_sprite",\n'
                '      "parameters": {\n'
                '        "sprite_path": "assets/base.png"\n'
                '      },\n'
                '      "render_order": 0,\n'
                '      "y_sort": false,\n'
                '      "stack_order": 0\n'
                '    }\n'
                '  ],\n'
                '  "variables": {}\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        (templates / "area_door.json").write_text(
            (
                '{\n'
                '  "entity_commands": {\n'
                '    "interact": {\n'
                '      "enabled": true,\n'
                '      "commands": [\n'
                '        {\n'
                '          "type": "change_area",\n'
                '          "area_id": "$target_area",\n'
                '          "entry_id": "$target_entry"\n'
                '        }\n'
                '      ]\n'
                '    }\n'
                '  },\n'
                '  "render_order": 10\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        (templates / "display_sprite.json").write_text(
            (
                '{\n'
                '  "space": "screen",\n'
                '  "render_order": 0,\n'
                '  "y_sort": false,\n'
                '  "visuals": [\n'
                '    {\n'
                '      "path": "$sprite_path"\n'
                '    }\n'
                '  ]\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        return project / "project.json"

    def _create_dialogue_project(self, root: Path) -> Path:
        project = root / "project"
        assets = project / "assets"
        areas = project / "areas"
        dialogues = project / "dialogues"
        assets.mkdir(parents=True)
        areas.mkdir()
        dialogues.mkdir()

        base = QPixmap(16, 16)
        base.fill(QColor("orange"))
        self.assertTrue(base.save(str(assets / "base.png")))

        (project / "project.json").write_text(
            (
                '{\n'
                '  "startup_area": "areas/demo",\n'
                '  "dialogue_paths": ["dialogues/"]\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        (areas / "demo.json").write_text(
            (
                '{\n'
                '  "name": "Demo",\n'
                '  "tile_size": 16,\n'
                '  "tilesets": [\n'
                '    {\n'
                '      "firstgid": 1,\n'
                '      "path": "assets/base.png",\n'
                '      "tile_width": 16,\n'
                '      "tile_height": 16\n'
                '    }\n'
                '  ],\n'
                '  "tile_layers": [\n'
                '    {\n'
                '      "name": "ground",\n'
                '      "render_order": 0,\n'
                '      "y_sort": false,\n'
                '      "stack_order": 0,\n'
                '      "grid": [[1]]\n'
                '    }\n'
                '  ],\n'
                '  "entities": [],\n'
                '  "variables": {}\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        (dialogues / "intro.json").write_text(
            '{\n  "text": "Hello"\n}\n',
            encoding="utf-8",
        )
        return project / "project.json"

    def _create_project_content_project(self, root: Path) -> Path:
        project = root / "project"
        assets = project / "assets"
        areas = project / "areas"
        items = project / "items"
        nested_items = items / "keys"
        assets.mkdir(parents=True)
        areas.mkdir()
        nested_items.mkdir(parents=True)

        base = QPixmap(16, 16)
        base.fill(QColor("red"))
        self.assertTrue(base.save(str(assets / "base.png")))

        (project / "project.json").write_text(
            (
                '{\n'
                '  "startup_area": "areas/demo",\n'
                '  "item_paths": ["items/"],\n'
                '  "shared_variables_path": "shared_variables.json",\n'
                '  "global_entities": [\n'
                '    {\n'
                '      "id": "pause_controller",\n'
                '      "template": "entity_templates/pause_controller"\n'
                '    }\n'
                '  ]\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        (project / "shared_variables.json").write_text(
            (
                '{\n'
                '  "display": {\n'
                '    "internal_width": 320,\n'
                '    "internal_height": 240\n'
                '  },\n'
                '  "inventory_ui": {\n'
                '    "preset": "standard"\n'
                '  }\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        (areas / "demo.json").write_text(
            (
                '{\n'
                '  "name": "Demo",\n'
                '  "tile_size": 16,\n'
                '  "tilesets": [\n'
                '    {\n'
                '      "firstgid": 1,\n'
                '      "path": "assets/base.png",\n'
                '      "tile_width": 16,\n'
                '      "tile_height": 16\n'
                '    }\n'
                '  ],\n'
                '  "tile_layers": [\n'
                '    {\n'
                '      "name": "ground",\n'
                '      "render_order": 0,\n'
                '      "y_sort": false,\n'
                '      "stack_order": 0,\n'
                '      "grid": [[1]]\n'
                '    }\n'
                '  ],\n'
                '  "entities": [],\n'
                '  "variables": {}\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        (items / "apple.json").write_text(
            '{\n  "name": "Apple",\n  "max_stack": 9\n}\n',
            encoding="utf-8",
        )
        (nested_items / "silver_key.json").write_text(
            '{\n  "name": "Silver Key",\n  "max_stack": 1\n}\n',
            encoding="utf-8",
        )
        return project / "project.json"

    def _panel_file_entries(self, panel) -> list[tuple[str, Path]]:
        entries: list[tuple[str, Path]] = []
        stack = [panel._tree.topLevelItem(i) for i in range(panel._tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item is None:
                continue
            data = item.data(0, 256)
            if data is not None:
                entries.append(data)
            for index in range(item.childCount()):
                stack.append(item.child(index))
        return sorted(entries, key=lambda pair: pair[0])

    def test_add_tileset_appends_safe_firstgid(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            with patch.object(
                window,
                "_show_tileset_details_dialog",
                return_value=("assets/extra.png", 16, 16),
            ):
                window._add_tileset_to_active_area(project_file.parent / "assets" / "extra.png")

            doc = window._area_docs["areas/demo"]
            self.assertEqual(len(doc.tilesets), 2)
            self.assertEqual(doc.tilesets[1].firstgid, 3)
            self.assertEqual(doc.tilesets[1].path, "assets/extra.png")
            self.assertTrue(window._tab_widget.is_dirty("areas/demo"))
            window._tab_widget.set_dirty("areas/demo", False)

    def test_edit_tileset_updates_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            with patch.object(
                window,
                "_show_tileset_details_dialog",
                return_value=("assets/base.png", 32, 16),
            ):
                window._edit_tileset_in_active_area(0)

            doc = window._area_docs["areas/demo"]
            self.assertEqual(doc.tilesets[0].tile_width, 32)
            self.assertEqual(doc.tilesets[0].tile_height, 16)
            self.assertTrue(window._tab_widget.is_dirty("areas/demo"))
            window._tab_widget.set_dirty("areas/demo", False)

    def test_layer_property_controls_update_document_and_canvas(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_layering_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            doc = window._area_docs["areas/demo"]
            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None

            self.assertLess(
                canvas._layer_items[0][0].zValue(),
                canvas._entity_items[0].zValue(),
            )

            self.assertEqual(window._render_panel._target_label.text(), "Editing: Layer ground")

            window._render_panel._render_order_spin.setValue(15)
            window._render_panel._y_sort_check.setChecked(True)
            window._render_panel._sort_y_offset_spin.setValue(-4.0)
            window._render_panel._stack_order_spin.setValue(3)
            QApplication.processEvents()

            self.assertEqual(doc.tile_layers[0].render_order, 15)
            self.assertTrue(doc.tile_layers[0].y_sort)
            self.assertEqual(doc.tile_layers[0].sort_y_offset, -4.0)
            self.assertEqual(doc.tile_layers[0].stack_order, 3)
            self.assertTrue(window._tab_widget.is_dirty("areas/demo"))
            self.assertIn("z:15", window._layer_panel._list.item(0).text())
            self.assertIn("y-sort", window._layer_panel._list.item(0).text())
            self.assertIn("stack:3", window._layer_panel._list.item(0).text())
            self.assertIn("offset:-4", window._layer_panel._list.item(0).text())
            self.assertGreater(
                canvas._layer_items[0][0].zValue(),
                canvas._entity_items[0].zValue(),
            )
            window._tab_widget.set_dirty("areas/demo", False)

    def test_render_properties_panel_updates_selected_entity(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window._json_editing_enabled = False
            window._set_json_editing_action_state(False)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None

            window._select_action.setChecked(True)
            canvas.select_entities_at_cell(0, 0)
            QApplication.processEvents()

            self.assertEqual(canvas.selected_entity_id, "npc_2")
            self.assertEqual(
                window._render_panel._target_label.text(),
                "Editing: Entity npc_2",
            )

            window._render_panel._render_order_spin.setValue(14)
            window._render_panel._y_sort_check.setChecked(False)
            window._render_panel._sort_y_offset_spin.setValue(3.5)
            window._render_panel._stack_order_spin.setValue(7)
            QApplication.processEvents()

            doc = window._area_docs["areas/demo"]
            entity = next(entity for entity in doc.entities if entity.id == "npc_2")
            self.assertEqual(entity.render_order, 14)
            self.assertFalse(entity.y_sort)
            self.assertEqual(entity.sort_y_offset, 3.5)
            self.assertEqual(entity.stack_order, 7)
            self.assertTrue(window._tab_widget.is_dirty("areas/demo"))
            self.assertEqual(canvas.selected_entity_id, "npc_2")
            window._tab_widget.set_dirty("areas/demo", False)

    def test_entity_instance_panel_uses_its_own_left_dock_with_internal_tabs(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            self.assertEqual(
                window.dockWidgetArea(window._entity_instance_panel),
                Qt.DockWidgetArea.LeftDockWidgetArea,
            )
            self.assertNotIn(
                window._entity_instance_panel,
                window.tabifiedDockWidgets(window._area_panel),
            )
            self.assertEqual(window._entity_instance_panel.windowTitle(), "Entity Instance")
            self.assertEqual(window._entity_instance_panel.tab_count, 2)
            self.assertEqual(
                window._entity_instance_panel.tab_titles(),
                ["Entity Instance JSON", "Entity Instance Editor"],
            )

    def test_entity_instance_json_panel_applies_selected_entity_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None

            window._select_action.setChecked(True)
            canvas.select_entities_at_cell(0, 0)
            QApplication.processEvents()

            self.assertEqual(window._entity_instance_panel.entity_id, "npc_2")

            window._enable_json_editing_action.setChecked(True)
            raw = (
                '{\n'
                '  "id": "npc_custom",\n'
                '  "grid_x": 1,\n'
                '  "grid_y": 1,\n'
                '  "render_order": 12,\n'
                '  "y_sort": false,\n'
                '  "sort_y_offset": 2.5,\n'
                '  "stack_order": 9\n'
                '}'
            )
            window._entity_instance_panel._editor.setPlainText(raw)
            window._on_apply_entity_instance_json()

            doc = window._area_docs["areas/demo"]
            entity = next(entity for entity in doc.entities if entity.id == "npc_custom")
            self.assertEqual((entity.x, entity.y), (1, 1))
            self.assertEqual(entity.render_order, 12)
            self.assertFalse(entity.y_sort)
            self.assertEqual(entity.sort_y_offset, 2.5)
            self.assertEqual(entity.stack_order, 9)
            self.assertEqual(canvas.selected_entity_id, "npc_custom")
            self.assertEqual(window._entity_instance_panel.entity_id, "npc_custom")
            self.assertTrue(window._tab_widget.is_dirty("areas/demo"))
            self.assertTrue(window._enable_json_editing_action.isChecked())

            window._on_clear_selection()
            self.assertTrue(window._enable_json_editing_action.isChecked())
            window._tab_widget.set_dirty("areas/demo", False)

    def test_entity_instance_fields_panel_applies_changes_without_reverting_render_properties(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_fields_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)
            window._enable_json_editing_action.setChecked(True)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None

            window._select_action.setChecked(True)
            canvas.select_entities_at_cell(0, 0)
            QApplication.processEvents()

            fields = window._entity_instance_panel._fields_editor
            self.assertEqual(fields._id_edit.text(), "house_door")
            self.assertEqual(
                fields._parameter_edits["target_area"].text(),
                "areas/village_house",
            )

            fields._id_edit.setText("front_door")
            fields._x_spin.setValue(1)
            fields._parameter_edits["target_area"].setText("areas/updated_house")
            QApplication.processEvents()

            self.assertTrue(window._entity_instance_panel.fields_dirty)
            self.assertFalse(window._entity_instance_panel._json_editor.isEnabled())

            window._render_panel._render_order_spin.setValue(14)
            QApplication.processEvents()

            window._on_apply_entity_instance_fields()

            doc = window._area_docs["areas/demo"]
            entity = next(entity for entity in doc.entities if entity.id == "front_door")
            self.assertEqual(entity.x, 1)
            self.assertEqual(entity.parameters, {
                "target_area": "areas/updated_house",
                "target_entry": "from_square",
            })
            self.assertEqual(entity.render_order, 14)
            self.assertEqual(canvas.selected_entity_id, "front_door")
            self.assertFalse(window._entity_instance_panel.fields_dirty)
            self.assertTrue(window._entity_instance_panel._json_editor.isEnabled())
            window._tab_widget.set_dirty("areas/demo", False)

    def test_entity_instance_fields_panel_uses_effective_space_from_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_fields_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            window._active_instance_entity_id = "title_backdrop"
            window._refresh_entity_instance_panel()

            fields = window._entity_instance_panel._fields_editor
            self.assertEqual(fields._space_label.text(), "screen")
            self.assertTrue(fields._x_spin.isHidden())
            self.assertTrue(fields._y_spin.isHidden())
            self.assertFalse(fields._pixel_x_row.isHidden())
            self.assertFalse(fields._pixel_y_row.isHidden())

    def test_open_project_passes_display_size_into_screen_pane(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_fields_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None

            self.assertEqual(window._display_width, 256)
            self.assertEqual(window._display_height, 192)
            self.assertEqual(canvas._screen_pane_size, (256, 192))

    def test_screen_entity_selection_and_pixel_nudge_use_screen_space_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_fields_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None

            window._select_action.setChecked(True)
            canvas.set_selected_entity("title_backdrop", cycle_position=1, cycle_total=1)
            QApplication.processEvents()

            self.assertEqual(window._entity_instance_panel.entity_id, "title_backdrop")

            window._on_nudge_selected_entity(1, 0)
            doc = window._area_docs["areas/demo"]
            entity = next(entity for entity in doc.entities if entity.id == "title_backdrop")
            self.assertEqual((entity.pixel_x, entity.pixel_y), (13, 18))
            self.assertIn("pixel (13, 18)", window.statusBar().currentMessage())

            window._on_nudge_screen_entity(8, 0)
            entity = next(entity for entity in doc.entities if entity.id == "title_backdrop")
            self.assertEqual((entity.pixel_x, entity.pixel_y), (21, 18))

            canvas.select_entities_at_cell(0, 0)
            QApplication.processEvents()
            door = next(entity for entity in doc.entities if entity.id == "house_door")
            before = (door.x, door.y)
            window._on_nudge_screen_entity(8, 0)
            self.assertEqual((door.x, door.y), before)
            window._tab_widget.set_dirty("areas/demo", False)

    def test_template_json_tab_is_guarded_and_saveable(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_paint_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window._enable_json_editing_action.setChecked(False)
            window.open_project(project_file)

            template_path = project_file.parent / "entity_templates" / "npc.json"
            window._open_content("entity_templates/npc", template_path, ContentType.ENTITY_TEMPLATE)

            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, JsonViewerWidget)
            assert isinstance(widget, JsonViewerWidget)
            self.assertTrue(widget.isReadOnly())
            self.assertFalse(window._enable_json_editing_action.isChecked())

            window._enable_json_editing_action.setChecked(True)
            self.assertFalse(widget.isReadOnly())

            text = widget.toPlainText()
            self.assertIn('"render_order": 10', text)
            widget.setPlainText(text.replace('"render_order": 10', '"render_order": 11'))
            QApplication.processEvents()

            self.assertTrue(window._tab_widget.is_dirty("entity_templates/npc"))
            window._on_save_active()

            saved = template_path.read_text(encoding="utf-8")
            self.assertIn('"render_order": 11', saved)
            self.assertFalse(window._tab_widget.is_dirty("entity_templates/npc"))
            self.assertTrue(window._enable_json_editing_action.isChecked())

    def test_dialogue_json_tab_is_guarded_and_saveable(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_dialogue_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window._enable_json_editing_action.setChecked(False)
            window.open_project(project_file)

            dialogue_path = project_file.parent / "dialogues" / "intro.json"
            window._open_content("dialogues/intro", dialogue_path, ContentType.DIALOGUE)

            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, JsonViewerWidget)
            assert isinstance(widget, JsonViewerWidget)
            self.assertTrue(widget.isReadOnly())

            window._enable_json_editing_action.setChecked(True)
            self.assertFalse(widget.isReadOnly())

            widget.setPlainText('{\n  "text": "Updated hello"\n}')
            QApplication.processEvents()

            self.assertTrue(window._tab_widget.is_dirty("dialogues/intro"))
            window._on_save_active()

            saved = dialogue_path.read_text(encoding="utf-8")
            self.assertIn('"text": "Updated hello"', saved)
            self.assertFalse(window._tab_widget.is_dirty("dialogues/intro"))

    def test_open_project_populates_items_panel_and_project_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            self.assertTrue(window._open_project_manifest_action.isEnabled())
            self.assertTrue(window._open_shared_variables_action.isEnabled())

            entries = self._panel_file_entries(window._item_panel)
            self.assertEqual(
                [content_id for content_id, _path in entries],
                ["items/apple", "items/keys/silver_key"],
            )

    def test_item_panel_signal_opens_item_json_tab(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            entries = self._panel_file_entries(window._item_panel)
            item_content_id, item_path = entries[0]
            window._item_panel.file_open_requested.emit(item_content_id, item_path)

            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, JsonViewerWidget)
            assert isinstance(widget, JsonViewerWidget)
            self.assertEqual(window._tab_widget.active_info().content_type, ContentType.ITEM)
            self.assertEqual(window._tab_widget.active_info().content_id, item_content_id)

    def test_project_and_shared_variables_tabs_open_and_shared_variables_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window._enable_json_editing_action.setChecked(False)
            window.open_project(project_file)

            window._open_project_manifest_tab()
            project_widget = window._tab_widget.active_widget()
            self.assertIsInstance(project_widget, JsonViewerWidget)
            assert isinstance(project_widget, JsonViewerWidget)
            self.assertEqual(
                window._tab_widget.active_info().content_type,
                ContentType.PROJECT_MANIFEST,
            )

            window._open_shared_variables_tab()
            shared_widget = window._tab_widget.active_widget()
            self.assertIsInstance(shared_widget, JsonViewerWidget)
            assert isinstance(shared_widget, JsonViewerWidget)
            self.assertEqual(
                window._tab_widget.active_info().content_type,
                ContentType.SHARED_VARIABLES,
            )
            self.assertTrue(shared_widget.isReadOnly())

            window._enable_json_editing_action.setChecked(True)
            self.assertFalse(shared_widget.isReadOnly())

            updated_text = shared_widget.toPlainText().replace('"preset": "standard"', '"preset": "compact"')
            shared_widget.setPlainText(updated_text)
            QApplication.processEvents()

            self.assertTrue(window._tab_widget.is_dirty("project/shared_variables"))
            window._on_save_active()

            saved = (project_file.parent / "shared_variables.json").read_text(encoding="utf-8")
            self.assertIn('"preset": "compact"', saved)
            self.assertFalse(window._tab_widget.is_dirty("project/shared_variables"))

    def test_template_brush_switches_active_paint_target_and_places_entities(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_paint_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None

            window._on_template_brush_selected("entity_templates/npc")
            self.assertTrue(window._paint_tiles_action.isChecked())
            self.assertTrue(canvas.tile_paint_mode)
            self.assertEqual(window._active_brush_type.value, "entity")
            self.assertFalse(window._tileset_panel.brush_active)
            self.assertEqual(canvas.active_brush_type.value, "entity")
            self.assertIn("Paint: entity npc", window._status_gid.text())

            canvas.entity_paint_requested.emit("entity_templates/npc", 1, 1)

            doc = window._area_docs["areas/demo"]
            self.assertEqual(len(doc.entities), 1)
            self.assertEqual(doc.entities[0].id, "npc_1")
            self.assertEqual(doc.entities[0].x, 1)
            self.assertEqual(doc.entities[0].y, 1)
            self.assertTrue(window._tab_widget.is_dirty("areas/demo"))

            canvas.entity_delete_requested.emit(1, 1)
            self.assertEqual(len(doc.entities), 0)
            window._tab_widget.set_dirty("areas/demo", False)

    def test_tile_brush_selection_enables_shared_paint_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None
            self.assertFalse(window._paint_tiles_action.isChecked())

            window._tileset_panel.select_gid(1)
            QApplication.processEvents()

            self.assertTrue(window._paint_tiles_action.isChecked())
            self.assertTrue(canvas.tile_paint_mode)
            self.assertEqual(window._active_brush_type.value, "tile")

    def test_select_mode_cycles_entities_and_supports_nudge_delete_and_clear(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None

            window._select_action.setChecked(True)
            self.assertTrue(canvas.select_mode)
            self.assertFalse(canvas.tile_paint_mode)

            self.assertTrue(canvas.select_entities_at_cell(0, 0))
            self.assertEqual(canvas.selected_entity_id, "npc_2")
            self.assertIn("Select: npc_2", window._status_gid.text())
            self.assertIn("(1 of 2)", window._status_gid.text())

            self.assertTrue(canvas.select_entities_at_cell(0, 0))
            self.assertEqual(canvas.selected_entity_id, "npc_1")
            self.assertIn("(2 of 2)", window._status_gid.text())

            window._on_nudge_selected_entity(1, 0)
            doc = window._area_docs["areas/demo"]
            self.assertTrue(window._tab_widget.is_dirty("areas/demo"))
            self.assertEqual(canvas.selected_entity_id, "npc_1")
            moved = next(entity for entity in doc.entities if entity.id == "npc_1")
            self.assertEqual((moved.x, moved.y), (1, 0))

            window._on_delete_selected_entity()
            self.assertEqual([entity.id for entity in doc.entities], ["npc_2"])
            self.assertIsNone(canvas.selected_entity_id)

            canvas.select_entities_at_cell(0, 0)
            self.assertEqual(canvas.selected_entity_id, "npc_2")
            window._on_clear_selection()
            self.assertIsNone(canvas.selected_entity_id)
            self.assertEqual(window._status_gid.text(), "Select: none")
            window._tab_widget.set_dirty("areas/demo", False)
