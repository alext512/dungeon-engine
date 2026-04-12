"""Tests for the focused project-manifest editor widget."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.widgets.project_manifest_editor_widget import ProjectManifestEditorWidget


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TestProjectManifestEditorWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_focused_edits_preserve_runtime_control_fields_owned_by_raw_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            project_file = project_root / "project.json"
            _write_json(project_root / "areas" / "demo.json", {"tile_size": 16})
            _write_json(
                project_file,
                {
                    "startup_area": "areas/demo",
                    "save_dir": "saves",
                    "input_targets": {
                        "interact": "player_1",
                        "pause": "pause_controller",
                    },
                    "debug_inspection_enabled": False,
                    "global_entities": [
                        {
                            "id": "dialogue_controller",
                            "template": "entity_templates/controllers/dialogue_controller",
                        }
                    ],
                    "command_runtime": {
                        "max_settle_passes": 64,
                        "max_immediate_commands_per_settle": 4096,
                    },
                },
            )

            widget = ProjectManifestEditorWidget(
                project_file,
                area_ids=["areas/demo"],
            )
            self.addCleanup(widget.close)
            widget.set_editing_enabled(True)

            widget.fields_editor._save_dir_edit.setText("slot_data")
            widget.fields_editor._debug_check.setChecked(True)
            widget.save_to_file()

            saved = json.loads(project_file.read_text(encoding="utf-8"))

            self.assertEqual(saved["save_dir"], "slot_data")
            self.assertTrue(saved["debug_inspection_enabled"])
            self.assertEqual(
                saved["input_targets"],
                {
                    "interact": "player_1",
                    "pause": "pause_controller",
                },
            )
            self.assertEqual(
                saved["global_entities"],
                [
                    {
                        "id": "dialogue_controller",
                        "template": "entity_templates/controllers/dialogue_controller",
                    }
                ],
            )
            self.assertEqual(
                saved["command_runtime"],
                {
                    "max_settle_passes": 64,
                    "max_immediate_commands_per_settle": 4096,
                },
            )
