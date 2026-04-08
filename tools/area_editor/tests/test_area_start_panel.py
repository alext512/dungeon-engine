"""Tests for the focused area-start commands panel."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.widgets.area_start_panel import AreaStartPanel


class TestAreaStartPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = AreaStartPanel()
        self.addCleanup(self.panel.close)

    def test_route_inputs_helper_appends_command_and_apply_emits_commands(self):
        self.panel.load_area("areas/demo", [])
        self.panel._helper_combo.setCurrentIndex(0)
        self.panel._route_entity_edit.setText("player_1")

        seen: list[object] = []
        self.panel.commands_applied.connect(lambda commands: seen.append(commands))

        self.panel._on_add_helper_command()
        self.panel._on_apply()

        self.assertEqual(len(seen), 1)
        self.assertEqual(
            seen[0],
            [
                {
                    "type": "route_inputs_to_entity",
                    "entity_id": "player_1",
                }
            ],
        )

    def test_revert_restores_original_enter_commands(self):
        original = [{"type": "play_music", "path": "assets/theme.ogg", "loop": True}]
        self.panel.load_area("areas/demo", original)
        self.panel._commands_text.setPlainText("[]")

        self.panel._on_revert()

        self.assertIn('"type": "play_music"', self.panel._commands_text.toPlainText())

    def test_set_camera_follow_helper_builds_structured_follow_spec(self):
        self.panel.load_area("areas/demo", [])
        self.panel._helper_combo.setCurrentIndex(3)
        self.panel._camera_entity_edit.setText("player_1")

        self.panel._on_add_helper_command()

        text = self.panel._commands_text.toPlainText()
        self.assertIn('"type": "set_camera_follow"', text)
        self.assertIn('"mode": "entity"', text)
        self.assertIn('"entity_id": "player_1"', text)
