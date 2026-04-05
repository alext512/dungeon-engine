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
from PySide6.QtWidgets import QApplication, QTabBar

from area_editor.app.main_window import MainWindow
from area_editor.widgets.document_tab_widget import ContentType
from area_editor.widgets.browser_workspace_dock import BrowserWorkspaceDock
from area_editor.widgets.entity_template_editor_widget import EntityTemplateEditorWidget
from area_editor.widgets.global_entities_editor_widget import GlobalEntitiesEditorWidget
from area_editor.widgets.item_editor_widget import ItemEditorWidget
from area_editor.widgets.json_viewer_widget import JsonViewerWidget
from area_editor.widgets.project_manifest_editor_widget import ProjectManifestEditorWidget
from area_editor.widgets.shared_variables_editor_widget import SharedVariablesEditorWidget

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

    def _create_reference_rich_project(self, root: Path) -> Path:
        project = root / "project"
        assets = project / "assets"
        areas = project / "areas"
        items = project / "items"
        dialogues = project / "dialogues" / "system"
        commands = project / "commands" / "system"
        assets.mkdir(parents=True)
        areas.mkdir()
        items.mkdir()
        dialogues.mkdir(parents=True)
        commands.mkdir(parents=True)

        base = QPixmap(16, 16)
        base.fill(QColor("blue"))
        self.assertTrue(base.save(str(assets / "base.png")))

        (project / "project.json").write_text(
            (
                '{\n'
                '  "startup_area": "areas/demo",\n'
                '  "item_paths": ["items/"],\n'
                '  "dialogue_paths": ["dialogues/"],\n'
                '  "command_paths": ["commands/"]\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        (areas / "demo.json").write_text(
            (
                '{\n'
                '  "name": "Demo",\n'
                '  "tile_size": 16,\n'
                '  "tilesets": [],\n'
                '  "tile_layers": [],\n'
                '  "entities": [\n'
                '    {\n'
                '      "id": "terminal",\n'
                '      "grid_x": 0,\n'
                '      "grid_y": 0,\n'
                '      "item_id": "items/apple",\n'
                '      "required_item_id": "items/apple",\n'
                '      "dialogue_path": "dialogues/system/prompt",\n'
                '      "success_dialogue_path": "dialogues/system/prompt",\n'
                '      "command_id": "commands/system/do_thing"\n'
                '    }\n'
                '  ],\n'
                '  "variables": {}\n'
                '}\n'
            ),
            encoding="utf-8",
        )
        (items / "apple.json").write_text(
            '{\n  "name": "Apple",\n  "max_stack": 9\n}\n',
            encoding="utf-8",
        )
        (dialogues / "prompt.json").write_text(
            '{\n  "segments": []\n}\n',
            encoding="utf-8",
        )
        (commands / "do_thing.json").write_text(
            '{\n  "commands": []\n}\n',
            encoding="utf-8",
        )
        return project / "project.json"

    def _create_entity_reference_project(self, root: Path) -> Path:
        project = root / "project"
        assets = project / "assets"
        areas = project / "areas"
        assets.mkdir(parents=True)
        areas.mkdir()

        base = QPixmap(16, 16)
        base.fill(QColor("darkGreen"))
        self.assertTrue(base.save(str(assets / "base.png")))

        (project / "project.json").write_text(
            (
                '{\n'
                '  "startup_area": "areas/demo",\n'
                '  "global_entities": [\n'
                '    {\n'
                '      "id": "dialogue_controller"\n'
                '    }\n'
                '  ],\n'
                '  "input_targets": {\n'
                '    "confirm": "switch_a"\n'
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
                '  "tilesets": [],\n'
                '  "tile_layers": [\n'
                '    {\n'
                '      "name": "ground",\n'
                '      "render_order": 0,\n'
                '      "y_sort": false,\n'
                '      "stack_order": 0,\n'
                '      "grid": [[0, 0]]\n'
                '    }\n'
                '  ],\n'
                '  "camera": {\n'
                '    "follow": {\n'
                '      "mode": "entity",\n'
                '      "entity_id": "switch_a"\n'
                '    }\n'
                '  },\n'
                '  "input_targets": {\n'
                '    "interact": "switch_a"\n'
                '  },\n'
                '  "entities": [\n'
                '    {\n'
                '      "id": "switch_a",\n'
                '      "grid_x": 0,\n'
                '      "grid_y": 0,\n'
                '      "kind": "switch"\n'
                '    },\n'
                '    {\n'
                '      "id": "relay",\n'
                '      "grid_x": 1,\n'
                '      "grid_y": 0,\n'
                '      "kind": "relay",\n'
                '      "target_id": "switch_a",\n'
                '      "source_entity_id": "switch_a",\n'
                '      "entity_ids": ["switch_a", "dialogue_controller"]\n'
                '    }\n'
                '  ],\n'
                '  "variables": {}\n'
                '}\n'
            ),
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
            self.assertIsInstance(window._browser_workspace, BrowserWorkspaceDock)
            self.assertEqual(
                window.dockWidgetArea(window._browser_workspace),
                Qt.DockWidgetArea.LeftDockWidgetArea,
            )
            self.assertEqual(window._entity_instance_panel.windowTitle(), "Entity Instance")
            self.assertEqual(window._entity_instance_panel.tab_count, 2)
            self.assertEqual(
                window._entity_instance_panel.tab_titles(),
                ["Entity Instance JSON", "Entity Instance Editor"],
            )
            self.assertEqual(
                window._browser_workspace.row_titles(1),
                ["Areas", "Entity Templates", "Items", "Global Entities"],
            )
            self.assertEqual(
                window._browser_workspace.row_titles(2),
                ["Dialogues", "Commands", "Assets"],
            )
            self.assertEqual(window._browser_workspace.active_key(), "areas")
            self.assertEqual(window._browser_workspace.row_visual_current_index(1), 0)
            self.assertEqual(window._browser_workspace.row_visual_current_index(2), -1)

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
            with patch.object(
                window,
                "_confirm_entity_rename_preview",
                return_value=True,
            ):
                window._on_apply_entity_instance_json()

            doc = window._area_docs["areas/demo"]
            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None
            entity = next(entity for entity in doc.entities if entity.id == "npc_custom")
            self.assertEqual((entity.x, entity.y), (1, 1))
            self.assertEqual(entity.render_order, 12)
            self.assertFalse(entity.y_sort)
            self.assertEqual(entity.sort_y_offset, 2.5)
            self.assertEqual(entity.stack_order, 9)
            self.assertEqual(canvas.selected_entity_id, "npc_custom")
            self.assertEqual(window._entity_instance_panel.entity_id, "npc_custom")
            self.assertFalse(window._tab_widget.is_dirty("areas/demo"))
            self.assertTrue(window._enable_json_editing_action.isChecked())

            window._on_clear_selection()
            self.assertTrue(window._enable_json_editing_action.isChecked())

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
            fields._kind_edit.setText("door")
            fields._tags_edit.setText("front, locked")
            fields._facing_combo.setCurrentText("left")
            fields._interactable_check.setChecked(True)
            fields._interaction_priority_spin.setValue(4)
            fields._variables_text.setPlainText('{\n  "opened": false,\n  "key": "copper"\n}')
            fields._visuals_text.setPlainText(
                '[\n'
                '  {\n'
                '    "id": "main",\n'
                '    "path": "assets/project/sprites/front_door.png",\n'
                '    "frame_width": 16,\n'
                '    "frame_height": 16\n'
                '  }\n'
                ']'
            )
            fields._parameter_edits["target_area"].setText("areas/updated_house")
            QApplication.processEvents()

            self.assertTrue(window._entity_instance_panel.fields_dirty)
            self.assertFalse(window._entity_instance_panel._json_editor.isEnabled())

            window._render_panel._render_order_spin.setValue(14)
            QApplication.processEvents()

            with patch.object(
                window,
                "_confirm_entity_rename_preview",
                return_value=True,
            ):
                window._on_apply_entity_instance_fields()

            doc = window._area_docs["areas/demo"]
            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None
            entity = next(entity for entity in doc.entities if entity.id == "front_door")
            self.assertEqual(entity.x, 1)
            self.assertEqual(entity.parameters, {
                "target_area": "areas/updated_house",
                "target_entry": "from_square",
            })
            self.assertEqual(entity._extra["kind"], "door")
            self.assertEqual(entity._extra["tags"], ["front", "locked"])
            self.assertEqual(entity._extra["facing"], "left")
            self.assertTrue(entity._extra["interactable"])
            self.assertEqual(entity._extra["interaction_priority"], 4)
            self.assertEqual(entity._extra["variables"], {"opened": False, "key": "copper"})
            self.assertEqual(
                entity._extra["visuals"],
                [
                    {
                        "id": "main",
                        "path": "assets/project/sprites/front_door.png",
                        "frame_width": 16,
                        "frame_height": 16,
                    }
                ],
            )
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
            self.assertIsInstance(widget, EntityTemplateEditorWidget)
            assert isinstance(widget, EntityTemplateEditorWidget)
            self.assertTrue(widget.raw_json_widget.isReadOnly())
            self.assertFalse(window._enable_json_editing_action.isChecked())

            window._enable_json_editing_action.setChecked(True)
            self.assertFalse(widget.raw_json_widget.isReadOnly())

            text = widget.raw_json_widget.toPlainText()
            self.assertIn('"render_order": 10', text)
            widget.raw_json_widget.setPlainText(
                text.replace('"render_order": 10', '"render_order": 11')
            )
            QApplication.processEvents()

            self.assertTrue(window._tab_widget.is_dirty("entity_templates/npc"))
            window._on_save_active()

            saved = template_path.read_text(encoding="utf-8")
            self.assertIn('"render_order": 11', saved)
            self.assertFalse(window._tab_widget.is_dirty("entity_templates/npc"))
            self.assertTrue(window._enable_json_editing_action.isChecked())

    def test_template_fields_editor_updates_visuals_and_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_paint_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window._enable_json_editing_action.setChecked(False)
            window.open_project(project_file)

            template_path = project_file.parent / "entity_templates" / "npc.json"
            window._open_content("entity_templates/npc", template_path, ContentType.ENTITY_TEMPLATE)

            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, EntityTemplateEditorWidget)
            assert isinstance(widget, EntityTemplateEditorWidget)

            window._enable_json_editing_action.setChecked(True)
            widget.fields_editor._visuals_text.setPlainText(
                (
                    '[\n'
                    '  {\n'
                    '    "id": "main",\n'
                    '    "path": "assets/base.png",\n'
                    '    "frame_width": 16,\n'
                    '    "frame_height": 16\n'
                    "  }\n"
                    "]"
                )
            )
            QApplication.processEvents()

            self.assertTrue(window._tab_widget.is_dirty("entity_templates/npc"))
            window._on_save_active()

            saved = template_path.read_text(encoding="utf-8")
            self.assertIn('"id": "main"', saved)
            self.assertIn('"path": "assets/base.png"', saved)
            self.assertFalse(window._tab_widget.is_dirty("entity_templates/npc"))

    def test_template_fields_editor_updates_persistence_and_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_paint_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window._enable_json_editing_action.setChecked(False)
            window.open_project(project_file)

            template_path = project_file.parent / "entity_templates" / "npc.json"
            window._open_content("entity_templates/npc", template_path, ContentType.ENTITY_TEMPLATE)

            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, EntityTemplateEditorWidget)
            assert isinstance(widget, EntityTemplateEditorWidget)

            window._enable_json_editing_action.setChecked(True)
            widget.fields_editor._entity_state_check.setChecked(True)
            widget.fields_editor._persistence_variables_text.setPlainText(
                '{\n  "shake_timer": false,\n  "times_pushed": true\n}'
            )
            QApplication.processEvents()

            self.assertTrue(window._tab_widget.is_dirty("entity_templates/npc"))
            window._on_save_active()

            saved = template_path.read_text(encoding="utf-8")
            self.assertIn('"persistence"', saved)
            self.assertIn('"entity_state": true', saved)
            self.assertIn('"times_pushed": true', saved)
            self.assertFalse(window._tab_widget.is_dirty("entity_templates/npc"))

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

    def test_create_new_area_file_refreshes_and_opens_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            area_id, file_path = window._create_new_area_file(
                area_id="title_screen",
                display_name="Title Screen",
                width=6,
                height=4,
                tile_size=16,
            )

            self.assertEqual(area_id, "areas/title_screen")
            self.assertTrue(file_path.is_file())

            window._refresh_area_panel()
            entries = [content_id for content_id, _path in self._panel_file_entries(window._area_panel)]
            self.assertIn("areas/title_screen", entries)

            window._open_area(area_id, file_path)
            info = window._tab_widget.active_info()
            self.assertIsNotNone(info)
            assert info is not None
            self.assertEqual(info.content_id, "areas/title_screen")
            self.assertEqual(info.content_type, ContentType.AREA)

            doc = window._area_docs["areas/title_screen"]
            self.assertEqual(doc.width, 6)
            self.assertEqual(doc.height, 4)
            self.assertEqual(doc.tile_size, 16)
            self.assertEqual(doc.name, "Title Screen")

    def test_area_extent_operation_shifts_world_entities_but_not_screen_entities(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_fields_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            doc = window._area_docs["areas/demo"]
            screen_ids = window._screen_space_entity_ids(doc)

            succeeded, blocked = window._apply_area_extent_operation(
                doc,
                "add_columns_left",
                2,
                screen_entity_ids=screen_ids,
            )

            self.assertTrue(succeeded)
            self.assertIsNone(blocked)
            door = next(entity for entity in doc.entities if entity.id == "house_door")
            backdrop = next(entity for entity in doc.entities if entity.id == "title_backdrop")
            self.assertEqual(door.grid_x, 2)
            self.assertEqual(backdrop.pixel_x, 12)

    def test_area_extent_remove_blocks_when_world_entity_would_fall_out_of_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_fields_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            doc = window._area_docs["areas/demo"]
            screen_ids = window._screen_space_entity_ids(doc)

            succeeded, blocked = window._apply_area_extent_operation(
                doc,
                "remove_left_columns",
                1,
                screen_entity_ids=screen_ids,
            )

            self.assertFalse(succeeded)
            self.assertIsNotNone(blocked)
            self.assertIn("outside the area bounds", blocked)

    def test_screen_space_template_brush_places_entities_in_screen_pane(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_fields_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None

            window._on_template_brush_selected("entity_templates/display_sprite")
            self.assertTrue(window._paint_tiles_action.isChecked())
            self.assertTrue(canvas.tile_paint_mode)
            self.assertEqual(window._active_brush_type.value, "entity")
            self.assertTrue(window._entity_brush_supported)
            self.assertIn("Paint: entity display_sprite", window._status_gid.text())

            canvas.entity_screen_paint_requested.emit("entity_templates/display_sprite", 40, 28)

            doc = window._area_docs["areas/demo"]
            created = next(entity for entity in doc.entities if entity.id == "display_sprite_1")
            self.assertEqual(created.template, "entity_templates/display_sprite")
            self.assertEqual(created.space, "screen")
            self.assertEqual((created.pixel_x, created.pixel_y), (40, 28))
            self.assertTrue(window._tab_widget.is_dirty("areas/demo"))
            self.assertEqual(canvas.selected_entity_id, "display_sprite_1")
            window._tab_widget.set_dirty("areas/demo", False)

    def test_entity_validation_rejects_duplicate_id_in_other_area(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_fields_project(Path(tmp))
            other_area = project_file.parent / "areas" / "other.json"
            other_area.write_text(
                (
                    '{\n'
                    '  "name": "Other",\n'
                    '  "tile_size": 16,\n'
                    '  "tilesets": [],\n'
                    '  "tile_layers": [\n'
                    '    {\n'
                    '      "name": "ground",\n'
                    '      "render_order": 0,\n'
                    '      "y_sort": false,\n'
                    '      "stack_order": 0,\n'
                    '      "grid": [[0]]\n'
                    '    }\n'
                    '  ],\n'
                    '  "entities": [\n'
                    '    {\n'
                    '      "id": "shared_actor",\n'
                    '      "grid_x": 0,\n'
                    '      "grid_y": 0\n'
                    '    }\n'
                    '  ],\n'
                    '  "variables": {}\n'
                    '}\n'
                ),
                encoding="utf-8",
            )

            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            doc = window._area_docs["areas/demo"]
            current = next(entity for entity in doc.entities if entity.id == "house_door")
            updated = type(current).from_dict(current.to_dict())
            updated.id = "shared_actor"

            error = window._validate_entity_update("areas/demo", doc, current, updated)

            self.assertIsNotNone(error)
            assert error is not None
            self.assertEqual(error[0], "Duplicate Entity ID")
            self.assertIn("areas/other", error[1])

    def test_entity_validation_rejects_duplicate_id_with_project_global(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_fields_project(Path(tmp))
            project_file.write_text(
                (
                    '{\n'
                    '  "startup_area": "areas/demo",\n'
                    '  "entity_template_paths": ["entity_templates/"],\n'
                    '  "shared_variables_path": "shared_variables.json",\n'
                    '  "global_entities": [\n'
                    '    {\n'
                    '      "id": "pause_controller",\n'
                    '      "template": "entity_templates/display_sprite"\n'
                    '    }\n'
                    '  ]\n'
                    '}\n'
                ),
                encoding="utf-8",
            )

            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            doc = window._area_docs["areas/demo"]
            current = next(entity for entity in doc.entities if entity.id == "house_door")
            updated = type(current).from_dict(current.to_dict())
            updated.id = "pause_controller"

            error = window._validate_entity_update("areas/demo", doc, current, updated)

            self.assertIsNotNone(error)
            assert error is not None
            self.assertEqual(error[0], "Duplicate Entity ID")
            self.assertIn("project global entity", error[1])

    def test_screen_space_template_brush_uses_project_wide_unique_id_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_fields_project(Path(tmp))
            project_file.write_text(
                (
                    '{\n'
                    '  "startup_area": "areas/demo",\n'
                    '  "entity_template_paths": ["entity_templates/"],\n'
                    '  "shared_variables_path": "shared_variables.json",\n'
                    '  "global_entities": [\n'
                    '    {\n'
                    '      "id": "display_sprite_2",\n'
                    '      "template": "entity_templates/display_sprite"\n'
                    '    }\n'
                    '  ]\n'
                    '}\n'
                ),
                encoding="utf-8",
            )
            other_area = project_file.parent / "areas" / "other.json"
            other_area.write_text(
                (
                    '{\n'
                    '  "name": "Other",\n'
                    '  "tile_size": 16,\n'
                    '  "tilesets": [],\n'
                    '  "tile_layers": [\n'
                    '    {\n'
                    '      "name": "ground",\n'
                    '      "render_order": 0,\n'
                    '      "y_sort": false,\n'
                    '      "stack_order": 0,\n'
                    '      "grid": [[0]]\n'
                    '    }\n'
                    '  ],\n'
                    '  "entities": [\n'
                    '    {\n'
                    '      "id": "display_sprite_1",\n'
                    '      "pixel_x": 0,\n'
                    '      "pixel_y": 0,\n'
                    '      "space": "screen"\n'
                    '    }\n'
                    '  ],\n'
                    '  "variables": {}\n'
                    '}\n'
                ),
                encoding="utf-8",
            )

            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None

            window._on_template_brush_selected("entity_templates/display_sprite")
            canvas.entity_screen_paint_requested.emit("entity_templates/display_sprite", 40, 28)

            doc = window._area_docs["areas/demo"]
            created = next(entity for entity in doc.entities if entity.id == "display_sprite_3")
            self.assertEqual(created.template, "entity_templates/display_sprite")
            window._tab_widget.set_dirty("areas/demo", False)

    def test_open_project_populates_items_panel_and_project_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            self.assertTrue(window._open_project_manifest_action.isEnabled())
            self.assertTrue(window._open_shared_variables_action.isEnabled())
            self.assertTrue(window._open_global_entities_action.isEnabled())

            entries = self._panel_file_entries(window._item_panel)
            self.assertEqual(
                [content_id for content_id, _path in entries],
                ["items/apple", "items/keys/silver_key"],
            )
            self.assertEqual(window._global_entities_panel._tree.topLevelItemCount(), 1)
            self.assertEqual(
                window._global_entities_panel._tree.topLevelItem(0).text(0),
                "pause_controller",
            )

    def test_all_visible_tab_bars_prefer_scrolling_without_eliding(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            tab_bars = window.findChildren(QTabBar)
            self.assertTrue(tab_bars)
            for tab_bar in tab_bars:
                self.assertTrue(tab_bar.usesScrollButtons())
                self.assertEqual(tab_bar.elideMode(), Qt.TextElideMode.ElideNone)
                self.assertFalse(tab_bar.expanding())

    def test_item_panel_signal_opens_item_json_tab(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window._enable_json_editing_action.setChecked(False)
            window.open_project(project_file)

            entries = self._panel_file_entries(window._item_panel)
            item_content_id, item_path = entries[0]
            window._item_panel.file_open_requested.emit(item_content_id, item_path)

            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, ItemEditorWidget)
            assert isinstance(widget, ItemEditorWidget)
            self.assertEqual(window._tab_widget.active_info().content_type, ContentType.ITEM)
            self.assertEqual(window._tab_widget.active_info().content_id, item_content_id)
            self.assertTrue(widget.raw_json_widget.isReadOnly())

    def test_item_fields_editor_updates_basic_fields_and_art_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window._enable_json_editing_action.setChecked(False)
            window.open_project(project_file)

            item_path = project_file.parent / "items" / "apple.json"
            window._open_content("items/apple", item_path, ContentType.ITEM)

            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, ItemEditorWidget)
            assert isinstance(widget, ItemEditorWidget)

            window._enable_json_editing_action.setChecked(True)
            widget.fields_editor._name_edit.setText("Green Apple")
            widget.fields_editor._description_edit.setPlainText("Fresh and tart.")
            widget.fields_editor._max_stack_spin.setValue(12)
            widget.fields_editor._consume_spin.setValue(1)
            widget.fields_editor._icon_editor._path_edit.setText("assets/base.png")
            widget.fields_editor._icon_editor._frame_width_spin.setValue(16)
            widget.fields_editor._icon_editor._frame_height_spin.setValue(16)
            widget.fields_editor._icon_editor._frame_spin.setValue(0)
            widget.fields_editor._portrait_editor._path_edit.setText("assets/base.png")
            widget.fields_editor._portrait_editor._frame_width_spin.setValue(32)
            widget.fields_editor._portrait_editor._frame_height_spin.setValue(32)
            widget.fields_editor._portrait_editor._frame_spin.setValue(0)
            QApplication.processEvents()

            self.assertTrue(window._tab_widget.is_dirty("items/apple"))
            window._on_save_active()

            saved = item_path.read_text(encoding="utf-8")
            self.assertIn('"name": "Green Apple"', saved)
            self.assertIn('"description": "Fresh and tart."', saved)
            self.assertIn('"max_stack": 12', saved)
            self.assertIn('"consume_quantity_on_use": 1', saved)
            self.assertIn('"icon"', saved)
            self.assertIn('"portrait"', saved)
            self.assertFalse(window._tab_widget.is_dirty("items/apple"))

    def test_project_and_shared_variables_tabs_open_and_save_through_focused_surfaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window._enable_json_editing_action.setChecked(False)
            window.open_project(project_file)

            window._open_project_manifest_tab()
            project_widget = window._tab_widget.active_widget()
            self.assertIsInstance(project_widget, ProjectManifestEditorWidget)
            assert isinstance(project_widget, ProjectManifestEditorWidget)
            self.assertEqual(
                window._tab_widget.active_info().content_type,
                ContentType.PROJECT_MANIFEST,
            )
            self.assertTrue(project_widget.raw_json_widget.isReadOnly())

            window._open_shared_variables_tab()
            shared_widget = window._tab_widget.active_widget()
            self.assertIsInstance(shared_widget, SharedVariablesEditorWidget)
            assert isinstance(shared_widget, SharedVariablesEditorWidget)
            self.assertEqual(
                window._tab_widget.active_info().content_type,
                ContentType.SHARED_VARIABLES,
            )
            self.assertTrue(shared_widget.raw_json_widget.isReadOnly())

            window._open_project_manifest_tab()
            window._enable_json_editing_action.setChecked(True)
            self.assertFalse(project_widget.raw_json_widget.isReadOnly())

            project_widget.fields_editor._save_dir_edit.setText("slot_data")
            startup_index = project_widget.fields_editor._startup_area_combo.findData("areas/demo")
            self.assertGreaterEqual(startup_index, 0)
            project_widget.fields_editor._startup_area_combo.setCurrentIndex(startup_index)
            QApplication.processEvents()

            self.assertTrue(window._tab_widget.is_dirty("project/project"))
            window._on_save_active()

            saved_project = project_file.read_text(encoding="utf-8")
            self.assertIn('"save_dir": "slot_data"', saved_project)
            self.assertIn('"startup_area": "areas/demo"', saved_project)
            self.assertFalse(window._tab_widget.is_dirty("project/project"))

            window._open_shared_variables_tab()
            self.assertFalse(shared_widget.raw_json_widget.isReadOnly())
            shared_widget.fields_editor._width_spin.setValue(400)
            shared_widget.fields_editor._height_spin.setValue(224)
            shared_widget.fields_editor._ticks_spin.setValue(20)
            QApplication.processEvents()

            self.assertTrue(window._tab_widget.is_dirty("project/shared_variables"))
            window._on_save_active()

            saved = (project_file.parent / "shared_variables.json").read_text(encoding="utf-8")
            self.assertIn('"internal_width": 400', saved)
            self.assertIn('"internal_height": 224', saved)
            self.assertIn('"ticks_per_tile": 20', saved)
            self.assertFalse(window._tab_widget.is_dirty("project/shared_variables"))

    def test_area_rename_moves_file_and_updates_startup_area(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            old_path = project_file.parent / "areas" / "demo.json"
            with patch.object(
                window,
                "_prompt_content_relative_name",
                return_value="rooms/demo_renamed",
            ), patch.object(
                window,
                "_confirm_content_rename_preview",
                return_value=True,
            ):
                window._on_rename_project_content(
                    ContentType.AREA,
                    "areas/demo",
                    old_path,
                )

            new_path = project_file.parent / "areas" / "rooms" / "demo_renamed.json"
            self.assertFalse(old_path.exists())
            self.assertTrue(new_path.is_file())
            saved_project = project_file.read_text(encoding="utf-8")
            self.assertIn('"startup_area": "areas/rooms/demo_renamed"', saved_project)
            self.assertEqual(
                window._tab_widget.active_info().content_id,
                "areas/rooms/demo_renamed",
            )
            entries = self._panel_file_entries(window._area_panel)
            self.assertIn(("areas/rooms/demo_renamed", new_path), entries)

    def test_template_rename_moves_file_and_updates_known_template_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            assets = project / "assets"
            areas = project / "areas"
            templates = project / "entity_templates"
            assets.mkdir(parents=True)
            areas.mkdir()
            templates.mkdir()

            base = QPixmap(16, 16)
            base.fill(QColor("magenta"))
            self.assertTrue(base.save(str(assets / "base.png")))

            (project / "project.json").write_text(
                (
                    '{\n'
                    '  "startup_area": "areas/demo",\n'
                    '  "entity_template_paths": ["entity_templates/"],\n'
                    '  "global_entities": [\n'
                    '    {\n'
                    '      "id": "pause_controller",\n'
                    '      "template": "entity_templates/old_controller"\n'
                    '    }\n'
                    '  ]\n'
                    '}\n'
                ),
                encoding="utf-8",
            )
            (areas / "demo.json").write_text(
                (
                    '{\n'
                    '  "name": "Demo",\n'
                    '  "tile_size": 16,\n'
                    '  "tilesets": [],\n'
                    '  "tile_layers": [],\n'
                    '  "entities": [\n'
                    '    {\n'
                    '      "id": "switch_a",\n'
                    '      "template": "entity_templates/old_controller",\n'
                    '      "grid_x": 0,\n'
                    '      "grid_y": 0\n'
                    '    }\n'
                    '  ],\n'
                    '  "variables": {}\n'
                    '}\n'
                ),
                encoding="utf-8",
            )
            (templates / "old_controller.json").write_text(
                (
                    '{\n'
                    '  "space": "world",\n'
                    '  "visuals": [\n'
                    '    {\n'
                    '      "id": "main",\n'
                    '      "path": "assets/base.png",\n'
                    '      "frame_width": 16,\n'
                    '      "frame_height": 16\n'
                    '    }\n'
                    '  ]\n'
                    '}\n'
                ),
                encoding="utf-8",
            )

            project_file = project / "project.json"
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)
            old_path = templates / "old_controller.json"
            window._open_content(
                "entity_templates/old_controller",
                old_path,
                ContentType.ENTITY_TEMPLATE,
            )

            with patch.object(
                window,
                "_prompt_content_relative_name",
                return_value="systems/new_controller",
            ), patch.object(
                window,
                "_confirm_content_rename_preview",
                return_value=True,
            ):
                window._on_rename_project_content(
                    ContentType.ENTITY_TEMPLATE,
                    "entity_templates/old_controller",
                    old_path,
                )

            new_path = templates / "systems" / "new_controller.json"
            self.assertFalse(old_path.exists())
            self.assertTrue(new_path.is_file())
            saved_project = project_file.read_text(encoding="utf-8")
            self.assertIn(
                '"template": "entity_templates/systems/new_controller"',
                saved_project,
            )
            saved_area = (areas / "demo.json").read_text(encoding="utf-8")
            self.assertIn(
                '"template": "entity_templates/systems/new_controller"',
                saved_area,
            )
            self.assertEqual(
                window._tab_widget.active_info().content_id,
                "entity_templates/systems/new_controller",
            )
            entries = self._panel_file_entries(window._template_panel)
            self.assertIn(
                ("entity_templates/systems/new_controller", new_path),
                entries,
            )

    def test_item_rename_moves_file_and_updates_known_item_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_reference_rich_project(Path(tmp))
            project = project_file.parent
            items = project / "items"
            areas = project / "areas"
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            old_path = items / "apple.json"
            window._open_content("items/apple", old_path, ContentType.ITEM)

            with patch.object(
                window,
                "_prompt_content_relative_name",
                return_value="keys/silver_apple",
            ), patch.object(
                window,
                "_confirm_content_rename_preview",
                return_value=True,
            ):
                window._on_rename_project_content(
                    ContentType.ITEM,
                    "items/apple",
                    old_path,
                )

            new_path = items / "keys" / "silver_apple.json"
            self.assertFalse(old_path.exists())
            self.assertTrue(new_path.is_file())
            saved_area = (areas / "demo.json").read_text(encoding="utf-8")
            self.assertIn('"item_id": "items/keys/silver_apple"', saved_area)
            self.assertIn('"required_item_id": "items/keys/silver_apple"', saved_area)
            self.assertEqual(
                window._tab_widget.active_info().content_id,
                "items/keys/silver_apple",
            )
            entries = self._panel_file_entries(window._item_panel)
            self.assertIn(("items/keys/silver_apple", new_path), entries)

    def test_dialogue_rename_moves_file_and_updates_known_dialogue_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_reference_rich_project(Path(tmp))
            project = project_file.parent
            dialogues = project / "dialogues" / "system"
            areas = project / "areas"
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            old_path = dialogues / "prompt.json"
            window._open_content(
                "dialogues/system/prompt",
                old_path,
                ContentType.DIALOGUE,
            )

            with patch.object(
                window,
                "_prompt_content_relative_name",
                return_value="system/prompt_v2",
            ), patch.object(
                window,
                "_confirm_content_rename_preview",
                return_value=True,
            ):
                window._on_rename_project_content(
                    ContentType.DIALOGUE,
                    "dialogues/system/prompt",
                    old_path,
                )

            new_path = dialogues / "prompt_v2.json"
            self.assertFalse(old_path.exists())
            self.assertTrue(new_path.is_file())
            saved_area = (areas / "demo.json").read_text(encoding="utf-8")
            self.assertIn('"dialogue_path": "dialogues/system/prompt_v2"', saved_area)
            self.assertIn(
                '"success_dialogue_path": "dialogues/system/prompt_v2"',
                saved_area,
            )
            self.assertEqual(
                window._tab_widget.active_info().content_id,
                "dialogues/system/prompt_v2",
            )
            entries = self._panel_file_entries(window._dialogue_panel)
            self.assertIn(("dialogues/system/prompt_v2", new_path), entries)

    def test_command_rename_moves_file_and_updates_known_command_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_reference_rich_project(Path(tmp))
            project = project_file.parent
            commands = project / "commands" / "system"
            areas = project / "areas"
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            old_path = commands / "do_thing.json"
            window._open_content(
                "commands/system/do_thing",
                old_path,
                ContentType.NAMED_COMMAND,
            )

            with patch.object(
                window,
                "_prompt_content_relative_name",
                return_value="system/do_better_thing",
            ), patch.object(
                window,
                "_confirm_content_rename_preview",
                return_value=True,
            ):
                window._on_rename_project_content(
                    ContentType.NAMED_COMMAND,
                    "commands/system/do_thing",
                    old_path,
                )

            new_path = commands / "do_better_thing.json"
            self.assertFalse(old_path.exists())
            self.assertTrue(new_path.is_file())
            saved_area = (areas / "demo.json").read_text(encoding="utf-8")
            self.assertIn(
                '"command_id": "commands/system/do_better_thing"',
                saved_area,
            )
            self.assertEqual(
                window._tab_widget.active_info().content_id,
                "commands/system/do_better_thing",
            )
            entries = self._panel_file_entries(window._command_panel)
            self.assertIn(("commands/system/do_better_thing", new_path), entries)

    def test_entity_instance_rename_updates_known_entity_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_reference_project(Path(tmp))
            project = project_file.parent
            area_path = project / "areas" / "demo.json"
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            window._active_instance_entity_id = "switch_a"
            window._refresh_entity_instance_panel()
            fields = window._entity_instance_panel._fields_editor
            fields._id_edit.setText("switch_b")

            with patch.object(
                window,
                "_confirm_entity_rename_preview",
                return_value=True,
            ):
                window._on_apply_entity_instance_fields()

            saved_project = project_file.read_text(encoding="utf-8")
            self.assertIn('"confirm": "switch_b"', saved_project)
            saved_area = area_path.read_text(encoding="utf-8")
            self.assertIn('"id": "switch_b"', saved_area)
            self.assertIn('"entity_id": "switch_b"', saved_area)
            self.assertIn('"interact": "switch_b"', saved_area)
            self.assertIn('"target_id": "switch_b"', saved_area)
            self.assertIn('"source_entity_id": "switch_b"', saved_area)
            self.assertIn('"entity_ids": [\n        "switch_b",', saved_area)
            self.assertEqual(window._active_instance_entity_id, "switch_b")
            self.assertEqual(
                window._entity_instance_panel.entity_id,
                "switch_b",
            )

    def test_global_entities_panel_opens_focused_editor_and_saves_back_to_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window._enable_json_editing_action.setChecked(False)
            window.open_project(project_file)

            window._global_entities_panel.global_entity_open_requested.emit("pause_controller")

            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, GlobalEntitiesEditorWidget)
            assert isinstance(widget, GlobalEntitiesEditorWidget)
            self.assertEqual(
                window._tab_widget.active_info().content_type,
                ContentType.GLOBAL_ENTITIES,
            )
            self.assertIn("pause_controller", widget.toPlainText())
            self.assertIn("pause_controller", widget._target_label.text())

            window._enable_json_editing_action.setChecked(True)
            updated_text = widget.toPlainText().replace(
                '"pause_controller"',
                '"pause_controller_v2"',
            )
            widget.setPlainText(updated_text)
            QApplication.processEvents()

            self.assertTrue(window._tab_widget.is_dirty("project/global_entities"))
            window._on_save_active()

            saved = project_file.read_text(encoding="utf-8")
            self.assertIn('"pause_controller_v2"', saved)
            self.assertFalse(window._tab_widget.is_dirty("project/global_entities"))
            self.assertEqual(
                window._global_entities_panel._tree.topLevelItem(0).text(0),
                "pause_controller_v2",
            )

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
