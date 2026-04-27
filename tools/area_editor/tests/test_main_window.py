"""Integration tests for main-window editor state restoration."""

from __future__ import annotations

import os
import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QTabBar

from area_editor.app.main_window import MainWindow
from area_editor.catalogs.template_catalog import TemplateCatalog
from area_editor.documents.area_document import EntityDocument
from area_editor.json_io import DEFAULT_JSON5_FILE_HEADER, load_json_data
from area_editor.widgets.document_tab_widget import ContentType
from area_editor.widgets.browser_workspace_dock import BrowserWorkspaceDock
from area_editor.widgets.canvas_tool_strip import CanvasToolStrip
from area_editor.widgets.entity_template_editor_widget import EntityTemplateEditorWidget
from area_editor.widgets.global_entities_editor_widget import GlobalEntitiesEditorWidget
from area_editor.widgets.item_editor_widget import ItemEditorWidget
from area_editor.widgets.json_viewer_widget import JsonViewerWidget
from area_editor.widgets.project_command_editor_widget import ProjectCommandEditorWidget
from area_editor.widgets.project_manifest_editor_widget import ProjectManifestEditorWidget
from area_editor.widgets.shared_variables_editor_widget import SharedVariablesEditorWidget
from area_editor.widgets.entity_instance_json_panel import EntityReferencePickerRequest
from area_editor.widgets.tile_canvas import BrushType
from main_window_test_support import (
    create_basic_project,
    create_dialogue_project,
    create_entity_fields_project,
    create_entity_paint_project,
    create_entity_reference_project,
    create_entity_select_project,
    create_layering_project,
    create_project_content_project,
    create_reference_rich_project,
    create_tile_selection_project,
    find_tree_item_by_folder_path,
    panel_file_entries,
    panel_folder_entries,
)


def _find_menu_action(menu, text: str):
    for action in menu.actions():
        if action.isSeparator():
            continue
        if action.text() == text:
            return action
    raise AssertionError(f"Menu action '{text}' was not found.")


class TestMainWindowTilesetEditing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    _create_project = staticmethod(create_basic_project)
    _create_layering_project = staticmethod(create_layering_project)
    _create_tile_selection_project = staticmethod(create_tile_selection_project)
    _create_entity_paint_project = staticmethod(create_entity_paint_project)
    _create_entity_select_project = staticmethod(create_entity_select_project)
    _create_entity_fields_project = staticmethod(create_entity_fields_project)
    _create_dialogue_project = staticmethod(create_dialogue_project)
    _create_project_content_project = staticmethod(create_project_content_project)
    _create_reference_rich_project = staticmethod(create_reference_rich_project)
    _create_entity_reference_project = staticmethod(create_entity_reference_project)
    _panel_file_entries = staticmethod(panel_file_entries)
    _panel_folder_entries = staticmethod(panel_folder_entries)
    _find_tree_item_by_folder_path = staticmethod(find_tree_item_by_folder_path)

    def test_entity_dialogue_picker_resolves_self_target_and_browses_dialogues(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window._templates = TemplateCatalog()
        window._templates._templates["entity_templates/sign"] = {
            "dialogues": {
                "starting_dialogue": {},
                "repeat_dialogue": {},
            }
        }
        entity = EntityDocument(
            id="sign_1",
            grid_x=1,
            grid_y=1,
            template="entity_templates/sign",
        )

        with (
            patch.object(window, "_resolve_project_entity_by_id", return_value=entity),
            patch.object(window, "_browse_known_reference", return_value="repeat_dialogue") as browse,
        ):
            selected = window._browse_project_entity_dialogue_id(
                "",
                EntityReferencePickerRequest(
                    parameter_name="dialogue_id",
                    current_value="",
                    parameter_spec={
                        "type": "entity_dialogue_id",
                        "of": "entity_id",
                    },
                    current_area_id=None,
                    entity_id="sign_1",
                    entity_template_id=None,
                    parameter_values={"entity_id": "$self_id"},
                ),
            )

        self.assertEqual(selected, "repeat_dialogue")
        browse.assert_called_once_with(
            title="Choose Dialogue for sign_1",
            label="Dialogue",
            values=["repeat_dialogue", "starting_dialogue"],
            current_value="",
        )

    def test_entity_dialogue_picker_prefers_live_self_override_names(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window._templates = TemplateCatalog()
        window._templates._templates["entity_templates/sign"] = {
            "dialogues": {
                "starting_dialogue": {},
                "repeat_dialogue": {},
            }
        }
        entity = EntityDocument(
            id="sign_1",
            grid_x=1,
            grid_y=1,
            template="entity_templates/sign",
        )

        with (
            patch.object(window, "_resolve_project_entity_by_id", return_value=entity),
            patch.object(window, "_browse_known_reference", return_value="dialogue_2") as browse,
        ):
            selected = window._browse_project_entity_dialogue_id(
                "dialogue_1",
                EntityReferencePickerRequest(
                    parameter_name="dialogue_id",
                    current_value="dialogue_1",
                    parameter_spec={
                        "type": "entity_dialogue_id",
                        "of": "entity_id",
                    },
                    current_area_id=None,
                    entity_id="sign_1",
                    entity_template_id=None,
                    parameter_values={"entity_id": "$self_id", "dialogue_id": "dialogue_1"},
                    entity_dialogue_names_override=("dialogue_1", "dialogue_2"),
                ),
            )

        self.assertEqual(selected, "dialogue_2")
        browse.assert_called_once_with(
            title="Choose Dialogue for sign_1",
            label="Dialogue",
            values=["dialogue_1", "dialogue_2"],
            current_value="dialogue_1",
        )

    def test_entity_command_picker_resolves_self_target_and_browses_commands(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window._templates = TemplateCatalog()
        window._templates._templates["entity_templates/gate"] = {
            "entity_commands": {
                "open": {"commands": []},
                "close": {"commands": []},
            }
        }
        entity = EntityDocument(
            id="gate_1",
            grid_x=1,
            grid_y=1,
            template="entity_templates/gate",
        )

        with (
            patch.object(window, "_resolve_project_entity_by_id", return_value=entity),
            patch.object(window, "_browse_known_reference", return_value="open") as browse,
        ):
            selected = window._browse_project_entity_command_id(
                "",
                EntityReferencePickerRequest(
                    parameter_name="command_id",
                    current_value="",
                    parameter_spec={
                        "type": "entity_command_id",
                        "of": "entity_id",
                    },
                    current_area_id=None,
                    entity_id="gate_1",
                    entity_template_id=None,
                    parameter_values={"entity_id": "$self_id"},
                ),
            )

        self.assertEqual(selected, "open")
        browse.assert_called_once_with(
            title="Choose Command for gate_1",
            label="Command",
            values=["close", "open"],
            current_value="",
        )

    def test_entity_command_picker_prefers_live_self_override_names(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window._templates = TemplateCatalog()
        window._templates._templates["entity_templates/gate"] = {
            "entity_commands": {
                "open": {"commands": []},
                "close": {"commands": []},
            }
        }
        entity = EntityDocument(
            id="gate_1",
            grid_x=1,
            grid_y=1,
            template="entity_templates/gate",
        )

        with (
            patch.object(window, "_resolve_project_entity_by_id", return_value=entity),
            patch.object(window, "_browse_known_reference", return_value="toggle") as browse,
        ):
            selected = window._browse_project_entity_command_id(
                "toggle",
                EntityReferencePickerRequest(
                    parameter_name="command_id",
                    current_value="toggle",
                    parameter_spec={
                        "type": "entity_command_id",
                        "of": "entity_id",
                    },
                    current_area_id=None,
                    entity_id="gate_1",
                    entity_template_id=None,
                    parameter_values={"entity_id": "$self_id", "command_id": "toggle"},
                    entity_command_names_override=("lock", "toggle"),
                ),
            )

        self.assertEqual(selected, "toggle")
        browse.assert_called_once_with(
            title="Choose Command for gate_1",
            label="Command",
            values=["lock", "toggle"],
            current_value="toggle",
        )

    def test_visual_and_animation_pickers_use_target_entity_visuals(self):
        window = MainWindow()
        self.addCleanup(window.close)
        window._templates = TemplateCatalog()
        window._templates._templates["entity_templates/npc"] = {
            "visuals": [
                {
                    "id": "body",
                    "animations": {
                        "idle": {"frames": [0]},
                        "wave": {"frames": [1, 2]},
                    },
                },
                {
                    "id": "shadow",
                    "animations": {
                        "pulse": {"frames": [0, 1]},
                    },
                },
            ],
        }
        entity = EntityDocument(
            id="npc_1",
            grid_x=1,
            grid_y=1,
            template="entity_templates/npc",
        )

        with (
            patch.object(window, "_resolve_project_entity_by_id", return_value=entity),
            patch.object(window, "_browse_known_reference", return_value="body") as browse,
        ):
            selected_visual = window._browse_project_visual_id(
                "",
                EntityReferencePickerRequest(
                    parameter_name="visual_id",
                    current_value="",
                    parameter_spec={
                        "type": "visual_id",
                        "of": "entity_id",
                    },
                    current_area_id=None,
                    entity_id="npc_1",
                    entity_template_id=None,
                    parameter_values={"entity_id": "$self_id"},
                ),
            )

        self.assertEqual(selected_visual, "body")
        browse.assert_called_once_with(
            title="Choose Visual for npc_1",
            label="Visual",
            values=["body", "shadow"],
            current_value="",
        )

        with (
            patch.object(window, "_resolve_project_entity_by_id", return_value=entity),
            patch.object(window, "_browse_known_reference", return_value="wave") as browse,
        ):
            selected_animation = window._browse_project_animation_id(
                "",
                EntityReferencePickerRequest(
                    parameter_name="animation",
                    current_value="",
                    parameter_spec={
                        "type": "animation_id",
                        "of": "visual_id",
                    },
                    current_area_id=None,
                    entity_id="npc_1",
                    entity_template_id=None,
                    parameter_values={
                        "entity_id": "$self_id",
                        "visual_id": "body",
                    },
                ),
            )

        self.assertEqual(selected_animation, "wave")
        browse.assert_called_once_with(
            title="Choose Animation for npc_1.body",
            label="Animation",
            values=["idle", "wave"],
            current_value="",
        )

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

    def test_area_workspace_exposes_layers_entities_and_cell_flags_tabs(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            self.assertEqual(window._area_workspace.row_titles(1), ["Layers", "Entities"])
            self.assertEqual(window._area_workspace.row_titles(2), ["Cell Flags"])

    def test_canvas_tool_strip_exposes_main_edit_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            strip = window.findChild(CanvasToolStrip, "CanvasToolStrip")
            self.assertIsNotNone(strip)
            assert strip is not None

            self.assertEqual(
                strip.section_labels(),
                ["Target", "Tool"],
            )
            self.assertEqual(
                strip.button_texts(),
                ["Tiles", "Entities", "Flags", "Select", "Pencil", "Eraser"],
            )
            self.assertTrue(window._select_action.isChecked())
            self.assertTrue(window._target_entities_action.isChecked())
            self.assertTrue(window._tool_select_mode_action.isChecked())
            self.assertTrue(window._active_canvas().select_mode)
            self.assertFalse(window._paint_tiles_action.isChecked())

    def test_canvas_tool_strip_target_and_tool_actions_drive_editor_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_paint_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None

            window._target_tiles_action.setChecked(True)
            window._tool_select_mode_action.setChecked(True)
            QApplication.processEvents()
            self.assertTrue(window._tile_select_action.isChecked())
            self.assertTrue(canvas.tile_select_mode)

            window._tool_pencil_action.setChecked(True)
            QApplication.processEvents()
            self.assertTrue(window._paint_tiles_action.isChecked())
            self.assertTrue(canvas.tile_paint_mode)
            self.assertEqual(canvas.active_brush_type, BrushType.TILE)

            window._target_flags_action.setChecked(True)
            window._tool_eraser_action.setChecked(True)
            QApplication.processEvents()
            self.assertTrue(window._cell_flags_action.isChecked())
            self.assertTrue(canvas.cell_flags_edit_mode)
            self.assertTrue(canvas.cell_flag_erase_mode)
            self.assertFalse(window._tool_select_mode_action.isEnabled())

            window._on_template_brush_selected("entity_templates/npc")
            window._tool_eraser_action.setChecked(True)
            QApplication.processEvents()
            self.assertTrue(window._paint_tiles_action.isChecked())
            self.assertTrue(canvas.tile_paint_mode)
            self.assertEqual(canvas.active_brush_type, BrushType.ENTITY)
            self.assertTrue(canvas.entity_brush_erase_mode)

    def test_entity_reference_picker_entries_include_globals_and_template_space(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            areas = project / "areas"
            templates = project / "entity_templates"
            project.mkdir()
            areas.mkdir()
            templates.mkdir()

            (project / "project.json").write_text(
                json.dumps(
                    {
                        "startup_area": "areas/demo",
                        "entity_template_paths": ["entity_templates/"],
                        "global_entities": [
                            {
                                "id": "hud_global",
                                "template": "entity_templates/display_sprite",
                                "pixel_x": 7,
                                "pixel_y": 9,
                            }
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (templates / "display_sprite.json").write_text(
                json.dumps({"space": "screen"}, indent=2),
                encoding="utf-8",
            )
            (areas / "demo.json").write_text(
                json.dumps(
                    {
                        "tile_size": 16,
                        "tilesets": [],
                        "tile_layers": [
                            {
                                "name": "ground",
                                "render_order": 0,
                                "y_sort": False,
                                "stack_order": 0,
                                "grid": [[0]],
                            }
                        ],
                        "entities": [
                            {
                                "id": "switch_a",
                                "grid_x": 0,
                                "grid_y": 0,
                            },
                            {
                                "id": "hud_local",
                                "template": "entity_templates/display_sprite",
                                "pixel_x": 3,
                                "pixel_y": 5,
                            },
                        ],
                        "variables": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (areas / "destination.json").write_text(
                json.dumps(
                    {
                        "tile_size": 16,
                        "tilesets": [],
                        "tile_layers": [
                            {
                                "name": "ground",
                                "render_order": 0,
                                "y_sort": False,
                                "stack_order": 0,
                                "grid": [[0]],
                            }
                        ],
                        "entities": [
                            {
                                "id": "arrival_marker",
                                "grid_x": 0,
                                "grid_y": 0,
                            }
                        ],
                        "variables": {},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project / "project.json")

            by_id = {
                entry.entity_id: entry
                for entry in window._build_entity_reference_picker_entries()
            }
            self.assertEqual(by_id["switch_a"].scope, "area")
            self.assertEqual(by_id["switch_a"].space, "world")
            self.assertEqual(by_id["switch_a"].area_key, "areas/demo")
            self.assertEqual(by_id["switch_a"].position_text, "world (0, 0)")
            self.assertEqual(by_id["hud_local"].scope, "area")
            self.assertEqual(by_id["hud_local"].space, "screen")
            self.assertEqual(by_id["hud_local"].position_text, "screen (3, 5)")
            self.assertEqual(by_id["hud_global"].scope, "global")
            self.assertEqual(by_id["hud_global"].space, "screen")

            filtered = window._entity_reference_picker_entries_for_request(
                EntityReferencePickerRequest(
                    parameter_name="target_entity_id",
                    current_value="",
                    parameter_spec={
                        "type": "entity_id",
                        "scope": "area",
                        "space": "screen",
                    },
                    current_area_id="areas/demo",
                    entity_id="caller",
                    entity_template_id="entity_templates/button_target",
                )
            )
            self.assertEqual([entry.entity_id for entry in filtered], ["hud_local"])

            filtered = window._entity_reference_picker_entries_for_request(
                EntityReferencePickerRequest(
                    parameter_name="destination_entity_id",
                    current_value="",
                    parameter_spec={
                        "type": "entity_id",
                        "scope": "area",
                        "space": "world",
                        "of": "target_area",
                    },
                    current_area_id="areas/demo",
                    entity_id="caller",
                    entity_template_id="entity_templates/area_transition",
                    parameter_values={"target_area": "areas/destination"},
                )
            )
            self.assertEqual([entry.entity_id for entry in filtered], ["arrival_marker"])

    def test_area_context_menu_includes_start_command_editor(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project(Path(tmp))
            area_path = project_file.parent / "areas" / "demo.json"
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            menu = QMenu()
            self.addCleanup(menu.close)
            window._populate_area_context_menu(menu, "areas/demo", area_path)

            action_texts = [
                action.text()
                for action in menu.actions()
                if not action.isSeparator()
            ]
            self.assertIn("Edit Area Start Commands...", action_texts)

    def test_area_context_start_command_editor_updates_area_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project(Path(tmp))
            area_path = project_file.parent / "areas" / "demo.json"
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            replacement_commands = [
                {
                    "type": "set_input_route",
                    "action": "interact",
                    "entity_id": "player_1",
                    "command_id": "interact",
                }
            ]

            class FakeCommandListDialog:
                loaded_commands: object = None
                kwargs: dict[str, object] = {}

                def __init__(self, *args, **kwargs) -> None:
                    FakeCommandListDialog.kwargs = dict(kwargs)
                    self.window_title = ""

                def setWindowTitle(self, title: str) -> None:
                    self.window_title = title

                def load_commands(self, commands: object) -> None:
                    FakeCommandListDialog.loaded_commands = commands

                def exec(self) -> QDialog.DialogCode:
                    return QDialog.DialogCode.Accepted

                def commands(self) -> list[dict[str, object]]:
                    return replacement_commands

            with patch(
                "area_editor.app.main_window.CommandListDialog",
                FakeCommandListDialog,
            ):
                window._edit_area_start_commands("areas/demo", area_path)

            self.assertEqual(FakeCommandListDialog.loaded_commands, [])
            self.assertEqual(
                FakeCommandListDialog.kwargs["current_area_id"],
                "areas/demo",
            )
            self.assertEqual(
                window._area_docs["areas/demo"].enter_commands,
                replacement_commands,
            )
            self.assertTrue(window._tab_widget.is_dirty("areas/demo"))
            window._tab_widget.set_dirty("areas/demo", False)

    def test_area_context_start_command_editor_save_preserves_other_area_json_surfaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_reference_project(Path(tmp))
            area_path = project_file.parent / "areas" / "demo.json"
            area_data = load_json_data(area_path)
            area_data["enter_commands"] = [
                {
                    "type": "set_input_route",
                    "action": "interact",
                    "entity_id": "switch_a",
                    "command_id": "interact",
                }
            ]
            area_data["custom_root"] = {"keep": True}
            area_path.write_text(json.dumps(area_data, indent=2), encoding="utf-8")

            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            replacement_commands = [
                {
                    "type": "set_input_route",
                    "action": "interact",
                    "entity_id": "switch_a",
                    "command_id": "interact",
                },
                {
                    "type": "set_input_route",
                    "action": "menu",
                    "entity_id": "relay",
                    "command_id": "open_menu",
                },
            ]

            class FakeCommandListDialog:
                loaded_commands: object = None

                def __init__(self, *args, **kwargs) -> None:
                    pass

                def setWindowTitle(self, title: str) -> None:
                    pass

                def load_commands(self, commands: object) -> None:
                    FakeCommandListDialog.loaded_commands = commands

                def exec(self) -> QDialog.DialogCode:
                    return QDialog.DialogCode.Accepted

                def commands(self) -> list[dict[str, object]]:
                    return replacement_commands

            with patch(
                "area_editor.app.main_window.CommandListDialog",
                FakeCommandListDialog,
            ):
                window._edit_area_start_commands("areas/demo", area_path)

            window._on_save_active()

            saved = load_json_data(area_path)

            self.assertEqual(FakeCommandListDialog.loaded_commands, area_data["enter_commands"])
            self.assertEqual(saved["enter_commands"], replacement_commands)
            self.assertEqual(
                saved["camera"],
                {
                    "follow": {
                        "mode": "entity",
                        "entity_id": "switch_a",
                    }
                },
            )
            self.assertEqual(
                saved["input_routes"],
                {
                    "interact": {
                        "entity_id": "switch_a",
                        "command_id": "interact",
                    }
                },
            )
            self.assertEqual(saved["custom_root"], {"keep": True})

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

    def test_layer_render_properties_save_preserves_other_layer_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_layering_project(Path(tmp))
            area_path = project_file.parent / "areas" / "demo.json"
            area_data = load_json_data(area_path)
            area_data["tile_layers"][0]["opacity"] = 0.5
            area_data["tile_layers"][0]["custom_tag"] = {"keep": "yes"}
            area_path.write_text(json.dumps(area_data, indent=2), encoding="utf-8")

            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            window._render_panel._render_order_spin.setValue(15)
            window._render_panel._y_sort_check.setChecked(True)
            window._render_panel._sort_y_offset_spin.setValue(-4.0)
            window._render_panel._stack_order_spin.setValue(3)
            QApplication.processEvents()
            window._on_save_active()

            saved = load_json_data(area_path)
            layer = saved["tile_layers"][0]

            self.assertEqual(layer["name"], "ground")
            self.assertEqual(layer["grid"], [[1]])
            self.assertEqual(layer["render_order"], 15)
            self.assertTrue(layer["y_sort"])
            self.assertEqual(layer["sort_y_offset"], -4.0)
            self.assertEqual(layer["stack_order"], 3)
            self.assertEqual(layer["opacity"], 0.5)
            self.assertEqual(layer["custom_tag"], {"keep": "yes"})

    def test_layer_panel_lists_only_real_tile_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_layering_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            labels = [
                window._layer_panel._list.item(index).text()
                for index in range(window._layer_panel._list.count())
            ]

            self.assertEqual(window._layer_panel._list.count(), 1)
            self.assertTrue(labels[0].startswith("ground"))
            self.assertFalse(any(label == "Entities" for label in labels))

    def test_entities_visibility_action_toggles_canvas_entities(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_layering_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None
            self.assertTrue(window._entities_visibility_action.isChecked())
            self.assertTrue(canvas._entities_visible)
            self.assertTrue(all(item.isVisible() for item in canvas._entity_items))

            window._entities_visibility_action.setChecked(False)
            QApplication.processEvents()

            self.assertFalse(canvas._entities_visible)
            self.assertTrue(all(not item.isVisible() for item in canvas._entity_items))

    def test_tile_layer_management_adds_renames_moves_and_deletes_layers(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_layering_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            doc = window._area_docs["areas/demo"]

            with patch.object(
                window,
                "_prompt_tile_layer_name",
                return_value="overlay",
            ):
                window._on_add_tile_layer_requested()

            self.assertEqual([layer.name for layer in doc.tile_layers], ["ground", "overlay"])
            self.assertEqual(doc.tile_layers[1].grid, [[0]])
            self.assertEqual(window._layer_panel.active_layer_name(), "overlay")

            window._on_move_tile_layer_requested(1, -1)
            self.assertEqual([layer.name for layer in doc.tile_layers], ["overlay", "ground"])
            self.assertEqual(window._layer_panel.active_layer_name(), "overlay")

            with patch.object(
                window,
                "_prompt_tile_layer_name",
                return_value="decor",
            ):
                window._on_rename_tile_layer_requested(0)

            self.assertEqual([layer.name for layer in doc.tile_layers], ["decor", "ground"])
            self.assertEqual(window._layer_panel.active_layer_name(), "decor")

            with patch.object(
                window,
                "_confirm_tile_layer_delete",
                return_value=True,
            ):
                window._on_delete_tile_layer_requested(0)

            self.assertEqual([layer.name for layer in doc.tile_layers], ["ground"])
            self.assertEqual(window._layer_panel._list.count(), 1)
            self.assertEqual(window._layer_panel.active_layer_name(), "ground")
            window._tab_widget.set_dirty("areas/demo", False)

    def test_tile_select_copy_delete_paste_and_clear_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_tile_selection_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None
            doc = window._area_docs["areas/demo"]

            window._tile_select_action.setChecked(True)
            self.assertTrue(canvas.tile_select_mode)

            canvas.set_tile_selection(0, 0, 1, 1)
            window._on_copy_tiles()
            self.assertIsNotNone(window._tile_clipboard)
            assert window._tile_clipboard is not None
            self.assertEqual(window._tile_clipboard.grid, ((1, 2), (3, 4)))

            window._on_delete_active_selection()
            self.assertEqual(doc.tile_layers[0].grid, [[0, 0, 0], [0, 0, 0], [0, 0, 0]])

            canvas.set_tile_selection(1, 1, 1, 1)
            window._on_paste_tiles()
            self.assertEqual(doc.tile_layers[0].grid, [[0, 0, 0], [0, 1, 2], [0, 3, 4]])
            self.assertEqual(canvas.tile_selection_bounds(), (1, 1, 2, 2))

            window._on_clear_active_selection()
            self.assertFalse(canvas.has_tile_selection)
            window._tab_widget.set_dirty("areas/demo", False)

    def test_tileset_stamp_selection_paints_multi_tile_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_tile_selection_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None
            doc = window._area_docs["areas/demo"]

            doc.tile_layers[0].grid = [[0, 0, 0], [0, 0, 0], [0, 0, 0]]
            canvas.refresh_scene_contents()

            window._tileset_panel._on_tile_selected(1, ((1, 2), (3, 4)))
            self.assertEqual(window._tileset_panel.selected_brush_block, ((1, 2), (3, 4)))
            self.assertEqual(canvas.selected_gid_block, ((1, 2), (3, 4)))
            self.assertTrue(window._paint_tiles_action.isChecked())

            canvas._paint_tile_block(1, 1, canvas.selected_gid_block or ())
            canvas.refresh_scene_contents()

            self.assertEqual(doc.tile_layers[0].grid, [[0, 0, 0], [0, 1, 2], [0, 3, 4]])
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

    def test_entity_render_properties_save_preserves_other_entity_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            area_path = project_file.parent / "areas" / "demo.json"
            area_data = load_json_data(area_path)
            for entity in area_data["entities"]:
                if entity["id"] == "npc_2":
                    entity["kind"] = "npc"
                    entity["variables"] = {"mood": "calm"}
                    entity["entity_commands"] = {
                        "on_interact": [{"type": "show_message", "text": "Hello"}]
                    }
                    entity["custom_entity_flag"] = True
                    break
            area_path.write_text(json.dumps(area_data, indent=2), encoding="utf-8")

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

            window._render_panel._render_order_spin.setValue(14)
            window._render_panel._y_sort_check.setChecked(False)
            window._render_panel._sort_y_offset_spin.setValue(3.5)
            window._render_panel._stack_order_spin.setValue(7)
            QApplication.processEvents()
            window._on_save_active()

            saved = load_json_data(area_path)
            entity = next(entry for entry in saved["entities"] if entry["id"] == "npc_2")

            self.assertEqual(entity["grid_x"], 0)
            self.assertEqual(entity["grid_y"], 0)
            self.assertEqual(entity["render_order"], 14)
            self.assertFalse(entity["y_sort"])
            self.assertEqual(entity["sort_y_offset"], 3.5)
            self.assertEqual(entity["stack_order"], 7)
            self.assertEqual(entity["kind"], "npc")
            self.assertEqual(entity["variables"], {"mood": "calm"})
            self.assertEqual(
                entity["entity_commands"],
                {"on_interact": [{"type": "show_message", "text": "Hello"}]},
            )
            self.assertTrue(entity["custom_entity_flag"])

    def test_entity_instance_panel_uses_its_own_left_dock_with_internal_tabs(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            self.assertTrue(window._entity_instance_panel.isHidden())
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
            self.assertEqual(window._entity_instance_panel.tab_count, 3)
            self.assertEqual(
                window._entity_instance_panel.tab_titles(),
                ["Parameters", "Entity Instance Editor", "Entity Instance JSON"],
            )
            self.assertEqual(
                window._entity_instance_panel.current_tab_title(),
                "Entity Instance Editor",
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

    def test_entity_instance_dialog_opens_from_entity_edit_request(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            window._on_entity_edit_requested("npc_2")
            QApplication.processEvents()

            dialog = window._entity_instance_dialog
            self.assertIsNotNone(dialog)
            assert dialog is not None
            self.assertTrue(dialog.isVisible())
            self.assertEqual(dialog.target_area_id, "areas/demo")
            self.assertEqual(dialog.target_entity_id, "npc_2")
            self.assertEqual(dialog.editor_widget.entity_id, "npc_2")
            self.assertEqual(
                dialog.editor_widget.current_tab_title(),
                "Entity Instance Editor",
            )

    def test_entity_instance_dialog_stays_pinned_when_selection_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            window._on_entity_edit_requested("npc_2")
            dialog = window._entity_instance_dialog
            self.assertIsNotNone(dialog)
            assert dialog is not None

            fields = dialog.editor_widget._fields_editor
            fields._id_edit.setText("npc_dirty")
            QApplication.processEvents()
            self.assertTrue(dialog.editor_widget.fields_dirty)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None
            canvas.set_selected_entity("npc_1")
            QApplication.processEvents()

            self.assertEqual(window._active_instance_entity_id, "npc_1")
            self.assertEqual(dialog.target_entity_id, "npc_2")
            self.assertEqual(dialog.editor_widget.entity_id, "npc_2")
            self.assertEqual(fields._id_edit.text(), "npc_dirty")
            window._force_close_entity_instance_dialog()

    def test_entity_instance_dialog_dirty_retarget_can_cancel(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            window._on_entity_edit_requested("npc_2")
            dialog = window._entity_instance_dialog
            self.assertIsNotNone(dialog)
            assert dialog is not None

            fields = dialog.editor_widget._fields_editor
            fields._id_edit.setText("npc_dirty")
            QApplication.processEvents()

            with patch.object(
                QMessageBox,
                "question",
                return_value=QMessageBox.StandardButton.Cancel,
            ):
                window._on_entity_edit_requested("npc_1")

            self.assertEqual(dialog.target_entity_id, "npc_2")
            self.assertEqual(dialog.editor_widget.entity_id, "npc_2")
            self.assertTrue(dialog.editor_widget.fields_dirty)
            window._force_close_entity_instance_dialog()

    def test_entity_instance_dialog_applies_pinned_entity_after_selection_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            window._on_entity_edit_requested("npc_2")
            dialog = window._entity_instance_dialog
            self.assertIsNotNone(dialog)
            assert dialog is not None

            fields = dialog.editor_widget._fields_editor
            fields._x_spin.setValue(1)
            QApplication.processEvents()

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None
            canvas.set_selected_entity("npc_1")
            QApplication.processEvents()

            window._on_apply_entity_instance_dialog_fields()

            doc = window._area_docs["areas/demo"]
            npc_1 = next(entity for entity in doc.entities if entity.id == "npc_1")
            npc_2 = next(entity for entity in doc.entities if entity.id == "npc_2")
            self.assertEqual(npc_1.x, 0)
            self.assertEqual(npc_2.x, 1)
            self.assertEqual(window._active_instance_entity_id, "npc_1")
            self.assertEqual(dialog.target_entity_id, "npc_2")
            self.assertFalse(dialog.editor_widget.fields_dirty)
            window._tab_widget.set_dirty("areas/demo", False)
            window._force_close_entity_instance_dialog()

    def test_entity_context_menu_builds_single_entity_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            menu = window._build_area_entity_context_menu("areas/demo", ("npc_1",))

            self.assertIsNotNone(menu)
            assert menu is not None
            self.assertEqual(
                [action.text() for action in menu.actions() if not action.isSeparator()],
                [
                    "Parameters...",
                    "Edit Instance...",
                    "Edit JSON...",
                    "Duplicate",
                    "Copy Entity",
                    "Copy ID",
                    "Delete",
                ],
            )
            self.assertFalse(_find_menu_action(menu, "Parameters...").isEnabled())

    def test_entity_context_menu_builds_stacked_entity_submenus(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            menu = window._build_area_entity_context_menu(
                "areas/demo",
                ("npc_2", "npc_1"),
            )

            self.assertIsNotNone(menu)
            assert menu is not None
            submenu_actions = [action for action in menu.actions() if action.menu() is not None]
            self.assertEqual([action.text() for action in submenu_actions], ["npc_2", "npc_1"])
            first_submenu = submenu_actions[0].menu()
            self.assertIsNotNone(first_submenu)
            assert first_submenu is not None
            self.assertEqual(
                [
                    action.text()
                    for action in first_submenu.actions()
                    if not action.isSeparator()
                ],
                [
                    "Parameters...",
                    "Edit Instance...",
                    "Edit JSON...",
                    "Duplicate",
                    "Copy Entity",
                    "Copy ID",
                    "Delete",
                ],
            )
            self.assertFalse(_find_menu_action(first_submenu, "Parameters...").isEnabled())

    def test_entity_context_menu_parameters_action_opens_parameters_tab(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_fields_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            menu = window._build_area_entity_context_menu("areas/demo", ("house_door",))
            assert menu is not None
            parameters_action = _find_menu_action(menu, "Parameters...")
            self.assertTrue(parameters_action.isEnabled())

            parameters_action.trigger()
            QApplication.processEvents()

            dialog = window._entity_instance_dialog
            self.assertIsNotNone(dialog)
            assert dialog is not None
            self.assertEqual(dialog.target_entity_id, "house_door")
            self.assertEqual(dialog.editor_widget.current_tab_title(), "Parameters")
            window._force_close_entity_instance_dialog()

    def test_entity_context_menu_edit_instance_action_opens_advanced_editor_tab(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            menu = window._build_area_entity_context_menu("areas/demo", ("npc_2",))
            assert menu is not None
            _find_menu_action(menu, "Edit Instance...").trigger()
            QApplication.processEvents()

            dialog = window._entity_instance_dialog
            self.assertIsNotNone(dialog)
            assert dialog is not None
            self.assertEqual(dialog.target_entity_id, "npc_2")
            self.assertEqual(
                dialog.editor_widget.current_tab_title(),
                "Entity Instance Editor",
            )
            window._force_close_entity_instance_dialog()

    def test_entity_context_menu_copy_id_action_updates_clipboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            QApplication.clipboard().setText("")
            menu = window._build_area_entity_context_menu("areas/demo", ("npc_1",))
            assert menu is not None

            _find_menu_action(menu, "Copy ID").trigger()
            QApplication.processEvents()

            self.assertEqual(QApplication.clipboard().text(), "npc_1")

    def test_entity_context_menu_copy_and_tile_paste_duplicate_configured_entity(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            doc = window._area_docs["areas/demo"]
            source = next(entity for entity in doc.entities if entity.id == "npc_1")
            source.template = "entity_templates/inventory_pickup"
            source.parameters = {
                "item_id": "items/consumables/glimmer_berry",
                "quantity": 2,
            }
            source._extra["entity_commands"] = {
                "interact": [
                    {
                        "type": "set_entity_var",
                        "entity_id": "npc_1",
                        "name": "picked_up",
                        "value": True,
                    }
                ]
            }

            empty_menu = window._build_area_cell_context_menu("areas/demo", 1, 1)
            self.assertIsNotNone(empty_menu)
            assert empty_menu is not None
            self.assertFalse(_find_menu_action(empty_menu, "Paste Entity Here").isEnabled())

            entity_menu = window._build_area_entity_context_menu("areas/demo", ("npc_1",))
            assert entity_menu is not None
            _find_menu_action(entity_menu, "Copy Entity").trigger()
            QApplication.processEvents()

            paste_menu = window._build_area_cell_context_menu("areas/demo", 1, 1)
            self.assertIsNotNone(paste_menu)
            assert paste_menu is not None
            paste_action = _find_menu_action(paste_menu, "Paste Entity Here")
            self.assertTrue(paste_action.isEnabled())
            paste_action.trigger()
            QApplication.processEvents()

            pasted = next(entity for entity in doc.entities if entity.id == "npc_3")
            self.assertEqual((pasted.x, pasted.y), (1, 1))
            self.assertEqual(pasted.template, "entity_templates/inventory_pickup")
            self.assertEqual(
                pasted.parameters,
                {
                    "item_id": "items/consumables/glimmer_berry",
                    "quantity": 2,
                },
            )
            self.assertEqual(
                pasted._extra["entity_commands"]["interact"][0]["entity_id"],
                "npc_3",
            )
            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None
            self.assertEqual(canvas.selected_entity_id, "npc_3")
            self.assertTrue(window._tab_widget.is_dirty("areas/demo"))
            window._tab_widget.set_dirty("areas/demo", False)

    def test_entity_context_menu_duplicate_copies_entity_on_same_cell(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            doc = window._area_docs["areas/demo"]
            source = next(entity for entity in doc.entities if entity.id == "npc_1")
            source.parameters = {"target_entity_id": "npc_1"}
            source._extra["entity_commands"] = {
                "inspect": [
                    {
                        "type": "set_entity_var",
                        "entity_id": "npc_1",
                        "name": "seen",
                        "value": True,
                    }
                ]
            }

            menu = window._build_area_entity_context_menu("areas/demo", ("npc_1",))
            assert menu is not None
            _find_menu_action(menu, "Duplicate").trigger()
            QApplication.processEvents()

            duplicated = next(entity for entity in doc.entities if entity.id == "npc_3")
            self.assertEqual((duplicated.x, duplicated.y), (source.x, source.y))
            self.assertEqual(duplicated.parameters, {"target_entity_id": "npc_3"})
            self.assertEqual(
                duplicated._extra["entity_commands"]["inspect"][0]["entity_id"],
                "npc_3",
            )
            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None
            self.assertEqual(canvas.selected_entity_id, "npc_3")
            self.assertTrue(window._tab_widget.is_dirty("areas/demo"))
            window._tab_widget.set_dirty("areas/demo", False)

    def test_ctrl_copy_uses_currently_selected_entity(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None
            canvas.set_selected_entity("npc_2", cycle_position=1, cycle_total=2, emit=False)
            window._select_action.setChecked(True)

            window._on_copy_active_selection()

            self.assertIsNotNone(window._entity_clipboard)
            assert window._entity_clipboard is not None
            self.assertEqual(window._entity_clipboard.source_entity_id, "npc_2")

    def test_entity_context_menu_delete_action_removes_entity_and_closes_dialog(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            window._on_entity_edit_requested("npc_1")
            self.assertIsNotNone(window._entity_instance_dialog)

            menu = window._build_area_entity_context_menu("areas/demo", ("npc_1",))
            assert menu is not None
            _find_menu_action(menu, "Delete").trigger()
            QApplication.processEvents()

            self.assertEqual(
                [entity.id for entity in window._area_docs["areas/demo"].entities],
                ["npc_2"],
            )
            self.assertTrue(window._tab_widget.is_dirty("areas/demo"))
            self.assertIsNone(window._entity_instance_dialog)
            window._tab_widget.set_dirty("areas/demo", False)

    def test_entity_context_menu_edit_json_action_opens_dialog_on_json_tab(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            menu = window._build_area_entity_context_menu("areas/demo", ("npc_2",))
            assert menu is not None
            _find_menu_action(menu, "Edit JSON...").trigger()
            QApplication.processEvents()

            dialog = window._entity_instance_dialog
            self.assertIsNotNone(dialog)
            assert dialog is not None
            self.assertEqual(dialog.target_entity_id, "npc_2")
            self.assertEqual(
                dialog.editor_widget.current_tab_title(),
                "Entity Instance JSON",
            )
            window._force_close_entity_instance_dialog()

    def test_entity_stack_picker_selects_requested_entity(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            window._show_entity_stack_picker(
                "areas/demo",
                ("npc_2", "npc_1"),
                "select",
                QPoint(24, 30),
            )

            popup = window._entity_stack_picker
            self.assertIsNotNone(popup)
            assert popup is not None
            self.assertEqual(popup.entity_ids(), ["npc_2", "npc_1"])

            self.assertTrue(popup.choose_entity("npc_1"))
            QApplication.processEvents()

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None
            self.assertEqual(canvas.selected_entity_id, "npc_1")
            self.assertEqual(window._active_instance_entity_id, "npc_1")

    def test_entity_stack_picker_delete_removes_requested_entity(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            window._show_entity_stack_picker(
                "areas/demo",
                ("npc_2", "npc_1"),
                "delete",
                QPoint(24, 30),
            )

            popup = window._entity_stack_picker
            self.assertIsNotNone(popup)
            assert popup is not None

            self.assertTrue(popup.choose_entity("npc_1"))
            QApplication.processEvents()

            self.assertEqual(
                [entity.id for entity in window._area_docs["areas/demo"].entities],
                ["npc_2"],
            )
            self.assertTrue(window._tab_widget.is_dirty("areas/demo"))
            window._tab_widget.set_dirty("areas/demo", False)

    def test_browser_workspace_tabs_remain_clickable_when_switching_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            row1 = window._browser_workspace._row1
            row2 = window._browser_workspace._row2

            commands_rect = row2.tabRect(1)
            QTest.mouseClick(
                row2,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                commands_rect.center(),
            )
            QApplication.processEvents()
            self.assertEqual(window._browser_workspace.active_key(), "commands")

            areas_rect = row1.tabRect(0)
            QTest.mouseClick(
                row1,
                Qt.MouseButton.LeftButton,
                Qt.KeyboardModifier.NoModifier,
                areas_rect.center(),
            )
            QApplication.processEvents()
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

            parameters = window._entity_instance_panel._parameters_editor
            fields = window._entity_instance_panel._fields_editor
            self.assertEqual(fields._id_edit.text(), "house_door")
            self.assertEqual(
                parameters._parameter_edits["target_area"].text(),
                "areas/village_house",
            )

            fields._id_edit.setText("front_door")
            fields._x_spin.setValue(1)
            fields._kind_edit.setText("door")
            fields._tags_edit.setText("front, locked")
            fields._facing_combo.setCurrentText("left")
            fields._interactable_check.setChecked(True)
            fields._interaction_priority_spin.setValue(4)
            fields._color_check.setChecked(True)
            fields._color_red_spin.setValue(160)
            fields._color_green_spin.setValue(120)
            fields._color_blue_spin.setValue(80)
            fields._variables_text.setPlainText('{\n  "opened": false,\n  "key": "copper"\n}')
            fields._inventory_check.setChecked(True)
            fields._inventory_max_stacks_spin.setValue(1)
            fields._inventory_stacks_text.setPlainText(
                '[{"item_id": "items/copper_key", "quantity": 1}]'
            )
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
            parameters._parameter_edits["target_area"].setText("areas/updated_house")
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
            self.assertEqual(entity._extra["color"], [160, 120, 80])
            self.assertEqual(entity._extra["variables"], {"opened": False, "key": "copper"})
            self.assertEqual(
                entity._extra["inventory"],
                {
                    "max_stacks": 1,
                    "stacks": [{"item_id": "items/copper_key", "quantity": 1}],
                },
            )
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

    def test_area_entity_list_selects_screen_space_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_fields_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None

            panel = window._area_entity_list_panel
            self.assertEqual(panel.entity_ids(), ["house_door", "title_backdrop"])

            panel._filter_combo.setCurrentIndex(2)
            QApplication.processEvents()
            self.assertEqual(panel.entity_ids(), ["title_backdrop"])

            panel._list.setCurrentRow(0)
            QApplication.processEvents()

            self.assertEqual(canvas.selected_entity_id, "title_backdrop")
            self.assertEqual(window._entity_instance_panel.entity_id, "title_backdrop")
            self.assertEqual(window._render_target_ref, "title_backdrop")

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
            self.assertEqual(
                widget.fields_editor.section_labels(),
                [
                    "Basics",
                    "Dialogues",
                    "Visuals",
                    "Entity Commands",
                    "Inventory",
                    "Persistence",
                    "Raw JSON",
                ],
            )
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

    def test_template_fields_editor_updates_basics_and_saves(self):
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
            widget.fields_editor._kind_edit.setText("guide")
            widget.fields_editor._space_combo.setCurrentText("screen")
            widget.fields_editor._tags_edit.setText("friendly, tutorial")
            widget.fields_editor._interactable_check.setChecked(True)
            widget.fields_editor._interaction_priority_spin.setValue(5)
            widget.fields_editor._color_check.setChecked(True)
            widget.fields_editor._color_red_spin.setValue(120)
            widget.fields_editor._color_green_spin.setValue(90)
            widget.fields_editor._color_blue_spin.setValue(40)
            widget.fields_editor._render_order_spin.setValue(8)
            widget.fields_editor._y_sort_check.setChecked(True)
            widget.fields_editor._sort_y_offset_spin.setValue(1.5)
            widget.fields_editor._stack_order_spin.setValue(2)
            widget.fields_editor._variables_text.setPlainText('{"met": false}')
            QApplication.processEvents()

            self.assertTrue(window._tab_widget.is_dirty("entity_templates/npc"))
            window._on_save_active()

            saved = template_path.read_text(encoding="utf-8")
            self.assertIn('"kind": "guide"', saved)
            self.assertIn('"space": "screen"', saved)
            self.assertIn('"friendly"', saved)
            self.assertIn('"interactable": true', saved)
            self.assertIn('"interaction_priority": 5', saved)
            self.assertIn('"color"', saved)
            self.assertIn("120", saved)
            self.assertIn("90", saved)
            self.assertIn("40", saved)
            self.assertIn('"render_order": 8', saved)
            self.assertIn('"y_sort": true', saved)
            self.assertIn('"sort_y_offset": 1.5', saved)
            self.assertIn('"stack_order": 2', saved)
            self.assertIn('"met": false', saved)
            self.assertFalse(window._tab_widget.is_dirty("entity_templates/npc"))

    def test_template_fields_editor_preserves_legacy_input_map_and_saves(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_paint_project(Path(tmp))
            template_path = project_file.parent / "entity_templates" / "npc.json"
            template_data = load_json_data(template_path)
            template_data["input_map"] = {"interact": "interact"}
            template_path.write_text(json.dumps(template_data, indent=2), encoding="utf-8")
            window = MainWindow()
            self.addCleanup(window.close)
            window._enable_json_editing_action.setChecked(False)
            window.open_project(project_file)

            window._open_content("entity_templates/npc", template_path, ContentType.ENTITY_TEMPLATE)

            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, EntityTemplateEditorWidget)
            assert isinstance(widget, EntityTemplateEditorWidget)

            window._enable_json_editing_action.setChecked(True)
            widget.fields_editor._kind_edit.setText("npc_guard")
            QApplication.processEvents()

            self.assertTrue(window._tab_widget.is_dirty("entity_templates/npc"))
            window._on_save_active()

            saved = template_path.read_text(encoding="utf-8")
            self.assertIn('"input_map"', saved)
            self.assertIn('"interact": "interact"', saved)
            self.assertIn('"kind": "npc_guard"', saved)
            self.assertFalse(window._tab_widget.is_dirty("entity_templates/npc"))

    def test_template_fields_editor_updates_entity_commands_and_saves(self):
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
            widget.fields_editor._entity_commands_text.setPlainText(
                '{\n'
                '  "interact": [\n'
                '    {"type": "run_project_command", "command_id": "commands/system/open_gate"}\n'
                "  ]\n"
                "}"
            )
            QApplication.processEvents()

            self.assertTrue(window._tab_widget.is_dirty("entity_templates/npc"))
            window._on_save_active()

            saved = template_path.read_text(encoding="utf-8")
            self.assertIn('"entity_commands"', saved)
            self.assertIn('"interact"', saved)
            self.assertIn('"command_id": "commands/system/open_gate"', saved)
            self.assertFalse(window._tab_widget.is_dirty("entity_templates/npc"))

    def test_template_fields_editor_updates_inventory_and_saves(self):
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
            widget.fields_editor._inventory_check.setChecked(True)
            widget.fields_editor._inventory_max_stacks_spin.setValue(2)
            widget.fields_editor._inventory_stacks_text.setPlainText(
                '[\n'
                '  {"item_id": "items/copper_key", "quantity": 1},\n'
                '  {"item_id": "items/light_orb", "quantity": 2}\n'
                ']'
            )
            QApplication.processEvents()

            self.assertTrue(window._tab_widget.is_dirty("entity_templates/npc"))
            window._on_save_active()

            saved = template_path.read_text(encoding="utf-8")
            self.assertIn('"inventory"', saved)
            self.assertIn('"max_stacks": 2', saved)
            self.assertIn('"item_id": "items/copper_key"', saved)
            self.assertIn('"item_id": "items/light_orb"', saved)
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
                width=6,
                height=4,
                tile_size=16,
            )

            self.assertEqual(area_id, "areas/title_screen")
            self.assertEqual(file_path.suffix, ".json5")
            self.assertTrue(file_path.is_file())
            saved = file_path.read_text(encoding="utf-8")
            self.assertTrue(saved.startswith(DEFAULT_JSON5_FILE_HEADER))
            self.assertEqual(load_json_data(file_path)["tile_size"], 16)

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
            asset_entries = self._panel_file_entries(window._asset_panel)
            self.assertIn(("base.png", project_file.parent / "assets" / "base.png"), asset_entries)
            self.assertIn(("base.json", project_file.parent / "assets" / "base.json"), asset_entries)

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

    def test_new_item_file_opens_item_builder_and_refreshes_items_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            project = project_file.parent
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            created = window._apply_new_item_file(
                root_dir=project / "items",
                relative_name="consumables/glimmer_berry",
            )

            self.assertIsNotNone(created)
            assert created is not None
            content_id, file_path = created
            self.assertEqual(content_id, "items/consumables/glimmer_berry")
            self.assertEqual(file_path, project / "items" / "consumables" / "glimmer_berry.json5")
            self.assertTrue(file_path.is_file())
            self.assertIn(DEFAULT_JSON5_FILE_HEADER, file_path.read_text(encoding="utf-8"))
            self.assertEqual(
                load_json_data(file_path),
                {
                    "name": "Glimmer Berry",
                    "description": "",
                    "max_stack": 1,
                    "consume_quantity_on_use": 0,
                    "use_commands": [],
                },
            )

            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, ItemEditorWidget)
            self.assertEqual(window._tab_widget.active_info().content_type, ContentType.ITEM)
            self.assertEqual(window._tab_widget.active_info().content_id, content_id)
            self.assertIn((content_id, file_path), self._panel_file_entries(window._item_panel))

    def test_new_entity_template_opens_template_builder_and_refreshes_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            project = project_file.parent
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            created = window._apply_new_entity_template_file(
                root_dir=project / "entity_templates",
                relative_name="props/stone-door",
            )

            self.assertIsNotNone(created)
            assert created is not None
            content_id, file_path = created
            self.assertEqual(content_id, "entity_templates/props/stone-door")
            self.assertEqual(
                file_path,
                project / "entity_templates" / "props" / "stone-door.json5",
            )
            self.assertTrue(file_path.is_file())
            self.assertIn(DEFAULT_JSON5_FILE_HEADER, file_path.read_text(encoding="utf-8"))
            self.assertEqual(
                load_json_data(file_path),
                {
                    "kind": "stone_door",
                    "space": "world",
                    "scope": "area",
                    "solid": False,
                    "interactable": False,
                    "render_order": 10,
                    "y_sort": True,
                    "variables": {},
                    "visuals": [],
                    "entity_commands": {},
                },
            )

            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, EntityTemplateEditorWidget)
            self.assertEqual(
                window._tab_widget.active_info().content_type,
                ContentType.ENTITY_TEMPLATE,
            )
            self.assertEqual(window._tab_widget.active_info().content_id, content_id)
            self.assertIn(
                (content_id, file_path),
                self._panel_file_entries(window._template_panel),
            )

    def test_template_panel_context_menus_include_new_template_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            project = project_file.parent
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            empty_menu = QMenu()
            self.addCleanup(empty_menu.close)
            window._populate_empty_space_context_menu(
                empty_menu,
                ContentType.ENTITY_TEMPLATE,
                [],
                None,
                None,
                None,
            )
            _find_menu_action(empty_menu, "New Entity Template...")

            folder_menu = QMenu()
            self.addCleanup(folder_menu.close)
            window._populate_folder_context_menu(
                folder_menu,
                ContentType.ENTITY_TEMPLATE,
                "props",
                project / "entity_templates" / "props",
                project / "entity_templates",
            )
            _find_menu_action(folder_menu, "New Entity Template...")

    def test_new_project_command_opens_command_builder_and_refreshes_panel(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_project_content_project(Path(tmp))
            project = project_file.parent
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            created = window._apply_new_project_command_file(
                root_dir=project / "commands",
                relative_name="system/open_gate",
            )

            self.assertIsNotNone(created)
            assert created is not None
            content_id, file_path = created
            self.assertEqual(content_id, "commands/system/open_gate")
            self.assertEqual(file_path, project / "commands" / "system" / "open_gate.json5")
            self.assertTrue(file_path.is_file())
            self.assertIn(DEFAULT_JSON5_FILE_HEADER, file_path.read_text(encoding="utf-8"))
            self.assertEqual(
                load_json_data(file_path),
                {
                    "inputs": {},
                    "commands": [],
                },
            )

            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, ProjectCommandEditorWidget)
            self.assertEqual(
                window._tab_widget.active_info().content_type,
                ContentType.NAMED_COMMAND,
            )
            self.assertEqual(window._tab_widget.active_info().content_id, content_id)
            self.assertIn(
                (content_id, file_path),
                self._panel_file_entries(window._command_panel),
            )

    def test_command_panel_signal_opens_command_builder(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_reference_rich_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window._enable_json_editing_action.setChecked(False)
            window.open_project(project_file)

            entries = self._panel_file_entries(window._command_panel)
            command_content_id, command_path = entries[0]
            window._command_panel.file_open_requested.emit(command_content_id, command_path)

            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, ProjectCommandEditorWidget)
            assert isinstance(widget, ProjectCommandEditorWidget)
            self.assertEqual(
                window._tab_widget.active_info().content_type,
                ContentType.NAMED_COMMAND,
            )
            self.assertEqual(window._tab_widget.active_info().content_id, command_content_id)
            self.assertTrue(widget.raw_json_widget.isReadOnly())

    def test_project_command_inputs_provider_reads_inputs_and_legacy_params(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_reference_rich_project(Path(tmp))
            project = project_file.parent
            command_path = project / "commands" / "system" / "do_thing.json"
            command_path.write_text(
                json.dumps(
                    {
                        "inputs": {
                            "target_entity": {"type": "entity_id"},
                            "visual": {"type": "visual_id", "of": "target_entity"},
                        },
                        "commands": [],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            legacy_path = project / "commands" / "system" / "legacy.json"
            legacy_path.write_text(
                json.dumps({"params": ["direction"], "commands": []}, indent=2),
                encoding="utf-8",
            )
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            self.assertEqual(
                window._project_command_inputs_for_id("commands/system/do_thing"),
                {
                    "target_entity": {"type": "entity_id"},
                    "visual": {"type": "visual_id", "of": "target_entity"},
                },
            )
            self.assertEqual(
                window._project_command_inputs_for_id("commands/system/legacy"),
                {"direction": {"type": "string"}},
            )

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

    def test_template_drag_move_updates_known_template_references_and_reselects(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            assets = project / "assets"
            areas = project / "areas"
            templates = project / "entity_templates"
            assets.mkdir(parents=True)
            areas.mkdir()
            templates.mkdir()
            (templates / "actively_used").mkdir()

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
            source_item = window._template_panel._find_item("entity_templates/old_controller")
            target_item = self._find_tree_item_by_folder_path(window._template_panel, "actively_used")
            self.assertIsNotNone(source_item)
            self.assertIsNotNone(target_item)
            assert source_item is not None
            assert target_item is not None

            with patch.object(
                window,
                "_confirm_content_rename_preview",
                return_value=True,
            ):
                moved = window._template_panel._request_internal_file_move(
                    source_item,
                    target_item,
                )
                QApplication.processEvents()

            self.assertTrue(moved)
            new_path = templates / "actively_used" / "old_controller.json"
            self.assertFalse(old_path.exists())
            self.assertTrue(new_path.is_file())
            saved_project = project_file.read_text(encoding="utf-8")
            self.assertIn(
                '"template": "entity_templates/actively_used/old_controller"',
                saved_project,
            )
            saved_area = (areas / "demo.json").read_text(encoding="utf-8")
            self.assertIn(
                '"template": "entity_templates/actively_used/old_controller"',
                saved_area,
            )
            entries = self._panel_file_entries(window._template_panel)
            self.assertIn(
                ("entity_templates/actively_used/old_controller", new_path),
                entries,
            )
            current_item = window._template_panel._tree.currentItem()
            self.assertIsNotNone(current_item)
            assert current_item is not None
            current_data = current_item.data(0, window._template_panel._FILE_ROLE)
            self.assertEqual(
                current_data[0],
                "entity_templates/actively_used/old_controller",
            )
            folder_item = self._find_tree_item_by_folder_path(
                window._template_panel,
                "actively_used",
            )
            self.assertIsNotNone(folder_item)
            assert folder_item is not None
            self.assertTrue(folder_item.isExpanded())

    def test_template_drag_move_defers_execution_until_events_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            assets = project / "assets"
            areas = project / "areas"
            templates = project / "entity_templates"
            assets.mkdir(parents=True)
            areas.mkdir()
            templates.mkdir()
            (templates / "actively_used").mkdir()

            base = QPixmap(16, 16)
            base.fill(QColor("magenta"))
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
            new_path = templates / "actively_used" / "old_controller.json"
            source_item = window._template_panel._find_item("entity_templates/old_controller")
            target_item = self._find_tree_item_by_folder_path(window._template_panel, "actively_used")
            self.assertIsNotNone(source_item)
            self.assertIsNotNone(target_item)
            assert source_item is not None
            assert target_item is not None

            with patch.object(
                window,
                "_confirm_content_rename_preview",
                return_value=True,
            ):
                moved = window._template_panel._request_internal_file_move(
                    source_item,
                    target_item,
                )
                self.assertTrue(moved)
                self.assertTrue(old_path.is_file())
                self.assertFalse(new_path.exists())
                QApplication.processEvents()

            self.assertFalse(old_path.exists())
            self.assertTrue(new_path.is_file())
            entries = self._panel_file_entries(window._template_panel)
            self.assertIn(
                ("entity_templates/actively_used/old_controller", new_path),
                entries,
            )

    def test_template_drag_move_cancel_refreshes_original_browser_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            assets = project / "assets"
            areas = project / "areas"
            templates = project / "entity_templates"
            assets.mkdir(parents=True)
            areas.mkdir()
            templates.mkdir()
            (templates / "actively_used").mkdir()

            base = QPixmap(16, 16)
            base.fill(QColor("magenta"))
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
            new_path = templates / "actively_used" / "old_controller.json"
            source_item = window._template_panel._find_item("entity_templates/old_controller")
            target_item = self._find_tree_item_by_folder_path(window._template_panel, "actively_used")
            self.assertIsNotNone(source_item)
            self.assertIsNotNone(target_item)
            assert source_item is not None
            assert target_item is not None

            with patch.object(
                window,
                "_confirm_content_rename_preview",
                return_value=False,
            ), patch.object(
                window,
                "_refresh_project_metadata_surfaces",
                wraps=window._refresh_project_metadata_surfaces,
            ) as refresh_spy:
                moved = window._template_panel._request_internal_file_move(
                    source_item,
                    target_item,
                )
                QApplication.processEvents()

            self.assertTrue(moved)
            refresh_spy.assert_called()
            self.assertTrue(old_path.is_file())
            self.assertFalse(new_path.exists())
            entries = self._panel_file_entries(window._template_panel)
            self.assertIn(("entity_templates/old_controller", old_path), entries)
            current_item = window._template_panel._tree.currentItem()
            self.assertIsNotNone(current_item)
            assert current_item is not None
            current_data = current_item.data(0, window._template_panel._FILE_ROLE)
            self.assertEqual(current_data[0], "entity_templates/old_controller")

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

    def test_asset_rename_moves_file_and_updates_known_asset_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            assets = project / "assets"
            areas = project / "areas"
            templates = project / "entity_templates"
            items = project / "items"
            assets.mkdir(parents=True)
            areas.mkdir()
            templates.mkdir()
            items.mkdir()
            (assets / "fonts").mkdir()
            (assets / "ui").mkdir()

            base = QPixmap(16, 16)
            base.fill(QColor("cyan"))
            self.assertTrue(base.save(str(assets / "base.png")))

            (project / "project.json").write_text(
                (
                    '{\n'
                    '  "startup_area": "areas/demo",\n'
                    '  "entity_template_paths": ["entity_templates/"],\n'
                    '  "item_paths": ["items/"],\n'
                    '  "shared_variables_path": "shared_variables.json"\n'
                    '}\n'
                ),
                encoding="utf-8",
            )
            (project / "shared_variables.json").write_text(
                (
                    '{\n'
                    '  "dialogue_ui": {\n'
                    '    "panel_path": "assets/base.png"\n'
                    '  }\n'
                    '}\n'
                ),
                encoding="utf-8",
            )
            (areas / "demo.json").write_text(
                (
                    '{\n'
                    '  "tile_size": 16,\n'
                    '  "tilesets": [\n'
                    '    {\n'
                    '      "firstgid": 1,\n'
                    '      "path": "assets/base.png",\n'
                    '      "tile_width": 16,\n'
                    '      "tile_height": 16\n'
                    '    }\n'
                    '  ],\n'
                    '  "tile_layers": [],\n'
                    '  "entities": [],\n'
                    '  "variables": {}\n'
                    '}\n'
                ),
                encoding="utf-8",
            )
            (templates / "display.json").write_text(
                (
                    '{\n'
                    '  "space": "screen",\n'
                    '  "visuals": [\n'
                    '    {\n'
                    '      "id": "main",\n'
                    '      "path": "assets/base.png"\n'
                    '    }\n'
                    '  ]\n'
                    '}\n'
                ),
                encoding="utf-8",
            )
            (items / "apple.json").write_text(
                (
                    '{\n'
                    '  "name": "Apple",\n'
                    '  "icon": {\n'
                    '    "path": "assets/base.png"\n'
                    '  }\n'
                    '}\n'
                ),
                encoding="utf-8",
            )
            (assets / "fonts" / "pixelbet.json").write_text(
                (
                    '{\n'
                    '  "kind": "bitmap",\n'
                    '  "atlas": "assets/base.png"\n'
                    '}\n'
                ),
                encoding="utf-8",
            )

            project_file = project / "project.json"
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            old_path = assets / "base.png"
            window._open_content("base.png", old_path, ContentType.ASSET)

            with patch.object(
                window,
                "_prompt_content_relative_name",
                return_value="ui/renamed",
            ), patch.object(
                window,
                "_confirm_content_rename_preview",
                return_value=True,
            ):
                window._on_rename_project_content(
                    ContentType.ASSET,
                    "base.png",
                    old_path,
                )

            new_path = assets / "ui" / "renamed.png"
            self.assertFalse(old_path.exists())
            self.assertTrue(new_path.is_file())
            self.assertIn('"path": "assets/ui/renamed.png"', (areas / "demo.json").read_text(encoding="utf-8"))
            self.assertIn('"path": "assets/ui/renamed.png"', (templates / "display.json").read_text(encoding="utf-8"))
            self.assertIn('"path": "assets/ui/renamed.png"', (items / "apple.json").read_text(encoding="utf-8"))
            self.assertIn('"panel_path": "assets/ui/renamed.png"', (project / "shared_variables.json").read_text(encoding="utf-8"))
            self.assertIn('"atlas": "assets/ui/renamed.png"', (assets / "fonts" / "pixelbet.json").read_text(encoding="utf-8"))
            self.assertEqual(
                window._tab_widget.active_info().content_id,
                "ui/renamed.png",
            )
            entries = self._panel_file_entries(window._asset_panel)
            self.assertIn(("ui/renamed.png", new_path), entries)

    def test_asset_delete_removes_file_and_leaves_known_references_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            assets = project / "assets"
            areas = project / "areas"
            templates = project / "entity_templates"
            items = project / "items"
            assets.mkdir(parents=True)
            areas.mkdir()
            templates.mkdir()
            items.mkdir()

            base = QPixmap(16, 16)
            base.fill(QColor("cyan"))
            self.assertTrue(base.save(str(assets / "base.png")))

            (project / "project.json").write_text(
                (
                    '{\n'
                    '  "startup_area": "areas/demo",\n'
                    '  "entity_template_paths": ["entity_templates/"],\n'
                    '  "item_paths": ["items/"],\n'
                    '  "shared_variables_path": "shared_variables.json"\n'
                    '}\n'
                ),
                encoding="utf-8",
            )
            (project / "shared_variables.json").write_text(
                (
                    '{\n'
                    '  "dialogue_ui": {\n'
                    '    "panel_path": "assets/base.png"\n'
                    '  }\n'
                    '}\n'
                ),
                encoding="utf-8",
            )
            (areas / "demo.json").write_text(
                (
                    '{\n'
                    '  "tile_size": 16,\n'
                    '  "tilesets": [\n'
                    '    {\n'
                    '      "firstgid": 1,\n'
                    '      "path": "assets/base.png",\n'
                    '      "tile_width": 16,\n'
                    '      "tile_height": 16\n'
                    '    }\n'
                    '  ],\n'
                    '  "tile_layers": [],\n'
                    '  "entities": [],\n'
                    '  "variables": {}\n'
                    '}\n'
                ),
                encoding="utf-8",
            )
            (templates / "display.json").write_text(
                (
                    '{\n'
                    '  "space": "screen",\n'
                    '  "visuals": [\n'
                    '    {\n'
                    '      "id": "main",\n'
                    '      "path": "assets/base.png"\n'
                    '    }\n'
                    '  ]\n'
                    '}\n'
                ),
                encoding="utf-8",
            )
            (items / "apple.json").write_text(
                (
                    '{\n'
                    '  "name": "Apple",\n'
                    '  "icon": {\n'
                    '    "path": "assets/base.png"\n'
                    '  }\n'
                    '}\n'
                ),
                encoding="utf-8",
            )

            project_file = project / "project.json"
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            old_path = assets / "base.png"
            window._open_content("base.png", old_path, ContentType.ASSET)

            with patch.object(
                window,
                "_confirm_content_delete_preview",
                return_value=True,
            ) as confirm_delete:
                window._on_delete_project_content(
                    ContentType.ASSET,
                    "base.png",
                    old_path,
                )

            self.assertFalse(old_path.exists())
            self.assertIn('"path": "assets/base.png"', (areas / "demo.json").read_text(encoding="utf-8"))
            self.assertNotIn(("base.png", old_path), self._panel_file_entries(window._asset_panel))
            usages = confirm_delete.call_args.kwargs["reference_usages"]
            self.assertTrue(any(usage.file_path.name == "demo.json" for usage in usages))

    def test_asset_folder_move_updates_known_asset_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            assets = project / "assets"
            areas = project / "areas"
            templates = project / "entity_templates"
            assets.mkdir(parents=True)
            (assets / "ui" / "old").mkdir(parents=True)
            areas.mkdir()
            templates.mkdir()

            base = QPixmap(16, 16)
            base.fill(QColor("cyan"))
            self.assertTrue(base.save(str(assets / "ui" / "old" / "panel.png")))

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
                    '  "dialogue_ui": {\n'
                    '    "panel_path": "assets/ui/old/panel.png"\n'
                    '  }\n'
                    '}\n'
                ),
                encoding="utf-8",
            )
            (areas / "demo.json").write_text(
                (
                    '{\n'
                    '  "tile_size": 16,\n'
                    '  "tilesets": [\n'
                    '    {\n'
                    '      "firstgid": 1,\n'
                    '      "path": "assets/ui/old/panel.png",\n'
                    '      "tile_width": 16,\n'
                    '      "tile_height": 16\n'
                    '    }\n'
                    '  ],\n'
                    '  "tile_layers": [],\n'
                    '  "entities": [],\n'
                    '  "variables": {}\n'
                    '}\n'
                ),
                encoding="utf-8",
            )
            (templates / "dialogue_panel.json").write_text(
                (
                    '{\n'
                    '  "space": "screen",\n'
                    '  "visuals": [\n'
                    '    {\n'
                    '      "id": "main",\n'
                    '      "path": "assets/ui/old/panel.png"\n'
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

            old_folder = assets / "ui" / "old"
            with patch.object(
                window,
                "_confirm_folder_move_preview",
                return_value=True,
            ):
                window._apply_content_folder_move(
                    content_type=ContentType.ASSET,
                    root_dir=assets,
                    relative_path="ui/old",
                    folder_path=old_folder,
                    new_relative_path="ui/menu",
                )

            new_folder = assets / "ui" / "menu"
            self.assertFalse(old_folder.exists())
            self.assertTrue(new_folder.is_dir())
            self.assertIn(
                '"path": "assets/ui/menu/panel.png"',
                (areas / "demo.json").read_text(encoding="utf-8"),
            )
            self.assertIn(
                '"path": "assets/ui/menu/panel.png"',
                (templates / "dialogue_panel.json").read_text(encoding="utf-8"),
            )
            self.assertIn(
                '"panel_path": "assets/ui/menu/panel.png"',
                (project / "shared_variables.json").read_text(encoding="utf-8"),
            )

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

    def test_dialogue_drag_move_updates_known_dialogue_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_reference_rich_project(Path(tmp))
            project = project_file.parent
            dialogues_root = project / "dialogues"
            dialogues = dialogues_root / "system"
            new_folder = dialogues_root / "npc"
            new_folder.mkdir(parents=True)
            areas = project / "areas"
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            old_path = dialogues / "prompt.json"
            source_item = window._dialogue_panel._find_item("dialogues/system/prompt")
            target_item = self._find_tree_item_by_folder_path(window._dialogue_panel, "npc")
            self.assertIsNotNone(source_item)
            self.assertIsNotNone(target_item)
            assert source_item is not None
            assert target_item is not None

            with patch.object(
                window,
                "_confirm_content_rename_preview",
                return_value=True,
            ):
                moved = window._dialogue_panel._request_internal_file_move(
                    source_item,
                    target_item,
                )
                QApplication.processEvents()

            self.assertTrue(moved)
            new_path = new_folder / "prompt.json"
            self.assertFalse(old_path.exists())
            self.assertTrue(new_path.is_file())
            saved_area = (areas / "demo.json").read_text(encoding="utf-8")
            self.assertIn('"dialogue_path": "dialogues/npc/prompt"', saved_area)
            self.assertIn(
                '"success_dialogue_path": "dialogues/npc/prompt"',
                saved_area,
            )
            entries = self._panel_file_entries(window._dialogue_panel)
            self.assertIn(("dialogues/npc/prompt", new_path), entries)

    def test_global_entity_id_rename_updates_known_entity_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_reference_project(Path(tmp))
            project = project_file.parent
            area_path = project / "areas" / "demo.json"
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)
            window._open_global_entities_tab("dialogue_controller")

            with patch.object(
                window,
                "_confirm_global_entity_rename_preview",
                return_value=True,
            ):
                window._apply_global_entity_id_rename(
                    "dialogue_controller",
                    "dialogue_controller_v2",
                )

            saved_project = project_file.read_text(encoding="utf-8")
            saved_area = area_path.read_text(encoding="utf-8")
            self.assertIn('"id": "dialogue_controller_v2"', saved_project)
            self.assertIn('"entity_ids": [\n        "switch_a",\n        "dialogue_controller_v2"\n      ]', saved_area)
            self.assertEqual(
                window._global_entities_panel._tree.topLevelItem(0).text(0),
                "dialogue_controller_v2",
            )
            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, GlobalEntitiesEditorWidget)
            assert isinstance(widget, GlobalEntitiesEditorWidget)
            self.assertIn("dialogue_controller_v2", widget._target_label.text())

    def test_global_entity_duplicate_copies_project_entry_with_new_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_reference_project(Path(tmp))
            project_data = load_json_data(project_file)
            project_data["global_entities"][0]["entity_commands"] = {
                "pause": [
                    {
                        "type": "set_entity_var",
                        "entity_id": "dialogue_controller",
                        "name": "paused",
                        "value": True,
                    }
                ]
            }
            project_file.write_text(json.dumps(project_data, indent=2), encoding="utf-8")

            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)
            window._open_global_entities_tab("dialogue_controller")

            menu = QMenu()
            window._populate_global_entity_context_menu(menu, "dialogue_controller")
            self.assertIn(
                "Duplicate...",
                [action.text() for action in menu.actions() if not action.isSeparator()],
            )

            self.assertTrue(
                window._duplicate_global_entity(
                    "dialogue_controller",
                    "dialogue_controller_copy",
                )
            )

            saved = load_json_data(project_file)
            self.assertEqual(
                [entity["id"] for entity in saved["global_entities"]],
                ["dialogue_controller", "dialogue_controller_copy"],
            )
            duplicated = saved["global_entities"][1]
            self.assertEqual(
                duplicated["entity_commands"]["pause"][0]["entity_id"],
                "dialogue_controller_copy",
            )
            self.assertEqual(
                window._global_entities_panel._tree.topLevelItem(1).text(0),
                "dialogue_controller_copy",
            )
            widget = window._tab_widget.active_widget()
            self.assertIsInstance(widget, GlobalEntitiesEditorWidget)
            assert isinstance(widget, GlobalEntitiesEditorWidget)
            self.assertIn("dialogue_controller_copy", widget._target_label.text())

    def test_global_entity_delete_removes_project_entry_and_leaves_known_references_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_reference_project(Path(tmp))
            project = project_file.parent
            area_path = project / "areas" / "demo.json"
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            with patch.object(
                window,
                "_confirm_global_entity_delete_preview",
                return_value=True,
            ) as confirm_delete:
                window._on_delete_global_entity("dialogue_controller")

            saved_project = project_file.read_text(encoding="utf-8")
            self.assertNotIn('"id": "dialogue_controller"', saved_project)
            saved_area = area_path.read_text(encoding="utf-8")
            self.assertIn('"entity_ids": ["switch_a", "dialogue_controller"]', saved_area)
            usages = confirm_delete.call_args.kwargs["reference_usages"]
            self.assertTrue(any(usage.file_path == area_path for usage in usages))

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
            self.assertIn('"entity_id": "switch_b"', saved_project)
            self.assertIn('"command_id": "confirm"', saved_project)
            saved_area = area_path.read_text(encoding="utf-8")
            self.assertIn('"id": "switch_b"', saved_area)
            self.assertIn('"entity_id": "switch_b"', saved_area)
            self.assertIn('"command_id": "interact"', saved_area)
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

    def test_entity_drag_commit_marks_area_dirty_and_refreshes_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_file = self._create_entity_select_project(Path(tmp))
            window = MainWindow()
            self.addCleanup(window.close)
            window.open_project(project_file)

            canvas = window._active_canvas()
            self.assertIsNotNone(canvas)
            assert canvas is not None

            window._select_action.setChecked(True)
            self.assertTrue(canvas.select_entities_at_cell(0, 0))
            self.assertEqual(canvas.selected_entity_id, "npc_2")

            doc = window._area_docs["areas/demo"]
            dragged = next(entity for entity in doc.entities if entity.id == "npc_2")
            dragged.grid_x = 1
            dragged.grid_y = 1
            window._tab_widget.set_dirty("areas/demo", False)

            canvas.entity_drag_committed.emit("npc_2", "world", 1, 1)

            self.assertTrue(window._tab_widget.is_dirty("areas/demo"))
            self.assertEqual(window._active_instance_entity_id, "npc_2")
            self.assertIn("Moved npc_2 to grid (1, 1).", window.statusBar().currentMessage())
            window._tab_widget.set_dirty("areas/demo", False)
