"""Tests for the focused entity-template editor widget."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.widgets.entity_template_editor_widget import EntityTemplateEditorWidget


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TestEntityTemplateEditorWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_structured_fields_can_update_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "space": "screen",
                    "visuals": [],
                    "entity_commands": {
                        "interact": {
                            "enabled": True,
                            "commands": [
                                {
                                    "type": "run_project_command",
                                    "command_id": "commands/system/open_gate",
                                }
                            ],
                        }
                    },
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            widget.fields_editor._scope_combo.setCurrentText("global")
            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))

            self.assertEqual(saved["space"], "screen")
            self.assertEqual(saved["scope"], "global")
            self.assertEqual(
                saved["entity_commands"],
                {
                    "interact": {
                        "enabled": True,
                        "commands": [
                            {
                                "type": "run_project_command",
                                "command_id": "commands/system/open_gate",
                            }
                        ],
                    }
                },
            )

    def test_structured_fields_preserve_unmanaged_engine_owned_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template_path = Path(tmp) / "console.json"
            _write_json(
                template_path,
                {
                    "space": "screen",
                    "scope": "global",
                    "render_order": 7,
                    "y_sort": False,
                    "color": [255, 240, 200],
                    "inventory": {
                        "max_stacks": 3,
                        "stacks": [{"item_id": "items/copper_key", "quantity": 1}],
                    },
                    "input_map": {"confirm": "interact"},
                    "entity_commands": {
                        "interact": {
                            "enabled": True,
                            "commands": [
                                {
                                    "type": "run_project_command",
                                    "command_id": "commands/system/open_gate",
                                }
                            ],
                        }
                    },
                    "visuals": [],
                },
            )

            widget = EntityTemplateEditorWidget(
                "entity_templates/console",
                template_path,
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            widget.fields_editor._visuals_text.setPlainText(
                '[{"id": "main", "path": "assets/project/ui/console.png"}]'
            )
            widget.fields_editor._entity_state_check.setChecked(True)
            widget.fields_editor._persistence_variables_text.setPlainText(
                '{"last_used": true}'
            )
            widget.save_to_file()

            saved = json.loads(template_path.read_text(encoding="utf-8"))

            self.assertEqual(saved["space"], "screen")
            self.assertEqual(saved["scope"], "global")
            self.assertEqual(saved["render_order"], 7)
            self.assertFalse(saved["y_sort"])
            self.assertEqual(saved["color"], [255, 240, 200])
            self.assertEqual(
                saved["inventory"],
                {
                    "max_stacks": 3,
                    "stacks": [{"item_id": "items/copper_key", "quantity": 1}],
                },
            )
            self.assertEqual(saved["input_map"], {"confirm": "interact"})
            self.assertEqual(
                saved["entity_commands"],
                {
                    "interact": {
                        "enabled": True,
                        "commands": [
                            {
                                "type": "run_project_command",
                                "command_id": "commands/system/open_gate",
                            }
                        ],
                    }
                },
            )
            self.assertEqual(
                saved["visuals"],
                [{"id": "main", "path": "assets/project/ui/console.png"}],
            )
            self.assertEqual(
                saved["persistence"],
                {
                    "entity_state": True,
                    "variables": {"last_used": True},
                },
            )
