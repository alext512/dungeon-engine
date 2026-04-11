"""Main-window content-management workflow tests."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.app.main_window import MainWindow
from area_editor.json_io import DEFAULT_JSON5_FILE_HEADER, load_json_data
from area_editor.widgets.document_tab_widget import ContentType
from area_editor.widgets.json_viewer_widget import JsonViewerWidget
from main_window_test_support import (
    create_entity_reference_project,
    create_project_content_project,
    find_tree_item_by_folder_path,
    panel_file_entries,
    panel_folder_entries,
)


class TestMainWindowContentManagement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    _create_project_content_project = staticmethod(create_project_content_project)
    _create_entity_reference_project = staticmethod(create_entity_reference_project)
    _panel_file_entries = staticmethod(panel_file_entries)
    _panel_folder_entries = staticmethod(panel_folder_entries)
    _find_tree_item_by_folder_path = staticmethod(find_tree_item_by_folder_path)

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

    def test_duplicate_area_action_creates_and_opens_full_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            source_path = project_file.parent / "areas" / "demo.json"
            with patch.object(
                window,
                "_prompt_content_relative_name",
                return_value="rooms/demo_copy",
            ), patch.object(
                window,
                "_prompt_area_duplicate_mode",
                return_value="Full Copy",
            ):
                window._on_duplicate_area("areas/demo", source_path)

            new_path = project_file.parent / "areas" / "rooms" / "demo_copy.json5"
            self.assertTrue(new_path.is_file())
            self.assertTrue(new_path.read_text(encoding="utf-8").startswith(DEFAULT_JSON5_FILE_HEADER))
            self.assertEqual(
                window._tab_widget.active_info().content_id,
                "areas/rooms/demo_copy",
            )
            self.assertIn(
                ("areas/rooms/demo_copy", new_path),
                self._panel_file_entries(window._area_panel),
            )

    def test_area_context_menu_can_open_raw_json_tab(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            area_path = project_file.parent / "areas" / "demo.json"
            window._open_area_raw_json("areas/demo", area_path)

            info = window._tab_widget.active_info()
            self.assertIsNotNone(info)
            assert info is not None
            self.assertEqual(info.content_type, ContentType.AREA_JSON)
            self.assertEqual(info.file_path, area_path)

            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, JsonViewerWidget)
            assert isinstance(widget, JsonViewerWidget)
            self.assertIn('"tile_layers"', widget.toPlainText())

    def test_raw_json_viewer_does_not_inject_missing_json5_notes_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "template.json5"
            authored_text = "{name: 'plain json5'}\n"
            file_path.write_text(authored_text, encoding="utf-8")

            widget = JsonViewerWidget(file_path)
            self.addCleanup(widget.close)

            self.assertEqual(widget.toPlainText(), authored_text)
            self.assertFalse(widget.is_dirty)

    def test_file_tree_open_labels_match_surface_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            area_path = project_file.parent / "areas" / "demo.json"
            asset_png = project_file.parent / "assets" / "base.png"
            asset_json = project_file.parent / "assets" / "base.json"
            dialogue_path = project_file.parent / "dialogues" / "system" / "prompt.json"
            command_path = project_file.parent / "commands" / "system" / "do_thing.json"

            self.assertEqual(window._area_panel._open_action_label_provider("areas/demo", area_path), "Open Area")
            self.assertEqual(window._dialogue_panel._open_action_label_provider("dialogues/system/prompt", dialogue_path), "Open Raw JSON")
            self.assertEqual(window._command_panel._open_action_label_provider("commands/system/do_thing", command_path), "Open Raw JSON")
            self.assertEqual(window._asset_panel._open_action_label_provider("base.png", asset_png), "Open")
            self.assertEqual(window._asset_panel._open_action_label_provider("base.json", asset_json), "Open Raw JSON")

    def test_saving_area_raw_json_reload_updates_open_area_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window._enable_json_editing_action.setChecked(True)
            window.open_project(project_file)

            area_path = project_file.parent / "areas" / "demo.json"
            window._open_area("areas/demo", area_path)
            window._open_area_raw_json("areas/demo", area_path)

            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, JsonViewerWidget)
            assert isinstance(widget, JsonViewerWidget)
            data = json.loads(widget.toPlainText())
            data["tile_layers"][0]["grid"] = [[0]]
            widget.setPlainText(json.dumps(data))
            QApplication.processEvents()

            window._on_save_active()

            self.assertEqual(window._area_docs["areas/demo"].tile_layers[0].grid, [[0]])

    def test_duplicate_area_full_copy_remaps_entity_ids_and_intra_area_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_reference_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            new_content_id, new_path = window._duplicate_area_file(
                source_content_id="areas/demo",
                source_file_path=project_file.parent / "areas" / "demo.json",
                new_relative_name="copies/demo_full",
                duplicate_mode="Full Copy",
            )

            self.assertEqual(new_content_id, "areas/copies/demo_full")
            self.assertEqual(new_path.suffix, ".json5")
            self.assertTrue(new_path.read_text(encoding="utf-8").startswith(DEFAULT_JSON5_FILE_HEADER))
            saved = load_json_data(new_path)
            self.assertEqual(len(saved["entities"]), 2)
            switch = next(entity for entity in saved["entities"] if entity.get("kind") == "switch")
            relay = next(entity for entity in saved["entities"] if entity.get("kind") == "relay")
            self.assertNotEqual(switch["id"], "switch_a")
            self.assertNotEqual(relay["id"], "relay")
            self.assertEqual(saved["camera"]["follow"]["entity_id"], switch["id"])
            self.assertEqual(saved["input_targets"]["interact"], switch["id"])
            self.assertEqual(relay["target_id"], switch["id"])
            self.assertEqual(relay["source_entity_id"], switch["id"])
            self.assertEqual(relay["entity_ids"], [switch["id"], "dialogue_controller"])

    def test_duplicate_area_layout_copy_keeps_map_shell_and_strips_entity_logic(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_reference_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            new_content_id, new_path = window._duplicate_area_file(
                source_content_id="areas/demo",
                source_file_path=project_file.parent / "areas" / "demo.json",
                new_relative_name="copies/demo_layout",
                duplicate_mode="Layout Copy",
            )

            self.assertEqual(new_content_id, "areas/copies/demo_layout")
            self.assertEqual(new_path.suffix, ".json5")
            self.assertTrue(new_path.read_text(encoding="utf-8").startswith(DEFAULT_JSON5_FILE_HEADER))
            saved = load_json_data(new_path)
            self.assertEqual(saved["tile_size"], 16)
            self.assertIn("tile_layers", saved)
            self.assertEqual(saved["entities"], [])
            self.assertEqual(saved.get("variables"), {})
            self.assertNotIn("camera", saved)
            self.assertNotIn("input_targets", saved)
            self.assertNotIn("entry_points", saved)
            self.assertNotIn("enter_commands", saved)

    def test_area_delete_removes_file_and_leaves_known_references_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            old_path = project_file.parent / "areas" / "demo.json"
            with patch.object(
                window,
                "_confirm_content_delete_preview",
                return_value=True,
            ) as confirm_delete:
                window._on_delete_project_content(
                    ContentType.AREA,
                    "areas/demo",
                    old_path,
                )

            self.assertFalse(old_path.exists())
            self.assertIn('"startup_area": "areas/demo"', project_file.read_text(encoding="utf-8"))
            self.assertNotIn(("areas/demo", old_path), self._panel_file_entries(window._area_panel))
            usages = confirm_delete.call_args.kwargs["reference_usages"]
            self.assertTrue(any(usage.file_path == project_file for usage in usages))

    def test_empty_folders_are_visible_in_file_backed_panels(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            project = project_file.parent
            (project / "assets" / "empty_assets").mkdir()
            (project / "areas" / "rooms").mkdir()
            (project / "items" / "empty_items").mkdir()
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            self.assertIn(
                ("empty_assets", project / "assets" / "empty_assets"),
                self._panel_folder_entries(window._asset_panel),
            )
            self.assertIn(
                ("rooms", project / "areas" / "rooms"),
                self._panel_folder_entries(window._area_panel),
            )
            self.assertIn(
                ("empty_items", project / "items" / "empty_items"),
                self._panel_folder_entries(window._item_panel),
            )

    def test_new_and_delete_empty_folder_refreshes_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            project = project_file.parent
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            root_dir = project / "assets"
            window._apply_new_content_folder(
                root_dir=root_dir,
                relative_path="project/new_empty",
            )
            created_path = root_dir / "project" / "new_empty"
            self.assertTrue(created_path.is_dir())
            self.assertIn(
                ("project/new_empty", created_path),
                self._panel_folder_entries(window._asset_panel),
            )

            window._on_delete_empty_content_folder(
                folder_path=created_path,
                relative_path="project/new_empty",
            )
            self.assertFalse(created_path.exists())
            self.assertNotIn(
                ("project/new_empty", created_path),
                self._panel_folder_entries(window._asset_panel),
            )

    def test_file_tree_folders_start_collapsed_and_remember_manual_expansion(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            project = project_file.parent
            (project / "assets" / "ui" / "title").mkdir(parents=True)
            (project / "assets" / "ui" / "title" / "panel.png").write_bytes(b"png")
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            ui_item = self._find_tree_item_by_folder_path(window._asset_panel, "ui")
            self.assertIsNotNone(ui_item)
            assert ui_item is not None
            self.assertFalse(ui_item.isExpanded())

            ui_item.setExpanded(True)
            QApplication.processEvents()
            self.assertTrue(ui_item.isExpanded())

            window._refresh_project_metadata_surfaces()
            refreshed_item = self._find_tree_item_by_folder_path(window._asset_panel, "ui")
            self.assertIsNotNone(refreshed_item)
            assert refreshed_item is not None
            self.assertTrue(refreshed_item.isExpanded())
