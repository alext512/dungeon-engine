"""Tests for the focused item editor widget."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.widgets.item_editor_widget import ItemEditorWidget


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TestItemEditorWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_focused_edits_preserve_raw_only_item_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            item_path = Path(tmp) / "glimmer_berry.json"
            _write_json(
                item_path,
                {
                    "name": "Glimmer Berry",
                    "description": "Restores a little energy.",
                    "max_stack": 3,
                    "consume_quantity_on_use": 1,
                    "icon": {
                        "path": "assets/project/items/glimmer_berry_icon.png",
                        "frame_width": 16,
                        "frame_height": 16,
                        "frame": 0,
                        "custom_icon_hint": "keep-me",
                    },
                    "portrait": {
                        "path": "assets/project/items/glimmer_berry_portrait.png",
                        "frame_width": 32,
                        "frame_height": 32,
                        "frame": 1,
                    },
                    "use_commands": [
                        {
                            "type": "set_entity_var",
                            "entity_id": "$caller",
                            "key": "last_used_item",
                            "value": "items/consumables/glimmer_berry",
                        }
                    ],
                    "custom_root_field": {"rarity": "common"},
                },
            )

            widget = ItemEditorWidget("items/consumables/glimmer_berry", item_path)
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            widget.fields_editor._name_edit.setText("Bright Berry")
            widget.fields_editor._consume_spin.setValue(2)
            widget.fields_editor._icon_editor._frame_spin.setValue(3)
            widget.save_to_file()

            saved = json.loads(item_path.read_text(encoding="utf-8"))

            self.assertEqual(saved["name"], "Bright Berry")
            self.assertEqual(saved["consume_quantity_on_use"], 2)
            self.assertEqual(
                saved["icon"],
                {
                    "path": "assets/project/items/glimmer_berry_icon.png",
                    "frame_width": 16,
                    "frame_height": 16,
                    "frame": 3,
                    "custom_icon_hint": "keep-me",
                },
            )
            self.assertEqual(
                saved["portrait"],
                {
                    "path": "assets/project/items/glimmer_berry_portrait.png",
                    "frame_width": 32,
                    "frame_height": 32,
                    "frame": 1,
                },
            )
            self.assertEqual(
                saved["use_commands"],
                [
                    {
                        "type": "set_entity_var",
                        "entity_id": "$caller",
                        "key": "last_used_item",
                        "value": "items/consumables/glimmer_berry",
                    }
                ],
            )
            self.assertEqual(saved["custom_root_field"], {"rarity": "common"})
