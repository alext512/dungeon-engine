"""Tests for the focused global-entities editor widget."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.widgets.global_entities_editor_widget import GlobalEntitiesEditorWidget


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TestGlobalEntitiesEditorWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_saving_global_entities_preserves_other_manifest_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_file = Path(tmp) / "project.json"
            _write_json(
                project_file,
                {
                    "startup_area": "areas/demo",
                    "save_dir": "slot_data",
                    "shared_variables_path": "shared_variables.json",
                    "input_targets": {"interact": "player_1"},
                    "debug_inspection_enabled": True,
                    "command_runtime": {
                        "max_settle_passes": 64,
                    },
                    "global_entities": [
                        {
                            "id": "dialogue_controller",
                            "template": "entity_templates/dialogue_controller",
                        }
                    ],
                },
            )

            widget = GlobalEntitiesEditorWidget(project_file)
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)
            widget.setPlainText(
                json.dumps(
                    [
                        {
                            "id": "dialogue_controller",
                            "template": "entity_templates/dialogue_controller",
                        },
                        {
                            "id": "pause_controller",
                            "template": "entity_templates/pause_controller",
                        },
                    ],
                    indent=2,
                )
            )
            widget.save_to_file()

            saved = json.loads(project_file.read_text(encoding="utf-8"))

            self.assertEqual(saved["startup_area"], "areas/demo")
            self.assertEqual(saved["save_dir"], "slot_data")
            self.assertEqual(saved["shared_variables_path"], "shared_variables.json")
            self.assertEqual(saved["input_targets"], {"interact": "player_1"})
            self.assertTrue(saved["debug_inspection_enabled"])
            self.assertEqual(saved["command_runtime"], {"max_settle_passes": 64})
            self.assertEqual(
                saved["global_entities"],
                [
                    {
                        "id": "dialogue_controller",
                        "template": "entity_templates/dialogue_controller",
                    },
                    {
                        "id": "pause_controller",
                        "template": "entity_templates/pause_controller",
                    },
                ],
            )
