"""Tests for the focused shared-variables editor widget."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.widgets.shared_variables_editor_widget import SharedVariablesEditorWidget


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TestSharedVariablesEditorWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_focused_edits_preserve_other_engine_used_shared_variable_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            shared_variables_path = Path(tmp) / "shared_variables.json"
            _write_json(
                shared_variables_path,
                {
                    "display": {
                        "internal_width": 320,
                        "internal_height": 240,
                    },
                    "movement": {
                        "ticks_per_tile": 16,
                    },
                    "dialogue_ui": {
                        "panel_path": "assets/project/ui/dialogue_panel.png",
                        "choices": {"visible_rows": 3},
                    },
                    "inventory_ui": {
                        "default_preset": "compact",
                        "presets": {
                            "compact": {"panel_path": "assets/project/ui/inventory_panel.png"}
                        },
                    },
                    "custom_settings": {"palette": "sunset"},
                },
            )

            widget = SharedVariablesEditorWidget(shared_variables_path)
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            widget.fields_editor._width_spin.setValue(400)
            widget.fields_editor._height_spin.setValue(224)
            widget.fields_editor._ticks_spin.setValue(20)
            widget.save_to_file()

            saved = json.loads(shared_variables_path.read_text(encoding="utf-8"))

            self.assertEqual(
                saved["display"],
                {"internal_width": 400, "internal_height": 224},
            )
            self.assertEqual(saved["movement"], {"ticks_per_tile": 20})
            self.assertEqual(
                saved["dialogue_ui"],
                {
                    "panel_path": "assets/project/ui/dialogue_panel.png",
                    "choices": {"visible_rows": 3},
                },
            )
            self.assertEqual(
                saved["inventory_ui"],
                {
                    "default_preset": "compact",
                    "presets": {
                        "compact": {"panel_path": "assets/project/ui/inventory_panel.png"}
                    },
                },
            )
            self.assertEqual(saved["custom_settings"], {"palette": "sunset"})
