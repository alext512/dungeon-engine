"""Tests for the entity reference picker dialog."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from area_editor.widgets.entity_reference_picker_dialog import (
    EntityReferencePickerDialog,
    EntityReferencePickerEntry,
    GLOBAL_AREA_KEY,
)


class TestEntityReferencePickerDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def _make_dialog(self) -> EntityReferencePickerDialog:
        dialog = EntityReferencePickerDialog()
        self.addCleanup(dialog.close)
        return dialog

    def test_defaults_to_preferred_area_and_filters_by_search(self):
        dialog = self._make_dialog()
        dialog.set_entries(
            [
                EntityReferencePickerEntry(
                    entity_id="switch_a",
                    template_id="entity_templates/switch",
                    area_key="areas/demo",
                    area_label="areas/demo",
                    scope="area",
                    space="world",
                    position_text="world (0, 0)",
                ),
                EntityReferencePickerEntry(
                    entity_id="hud_overlay",
                    template_id="entity_templates/display_sprite",
                    area_key="areas/demo",
                    area_label="areas/demo",
                    scope="area",
                    space="screen",
                    position_text="screen (12, 4)",
                ),
                EntityReferencePickerEntry(
                    entity_id="arrival_marker",
                    template_id="entity_templates/marker",
                    area_key="areas/start",
                    area_label="areas/start",
                    scope="area",
                    space="world",
                    position_text="world (5, 7)",
                ),
                EntityReferencePickerEntry(
                    entity_id="dialogue_controller",
                    template_id=None,
                    area_key=GLOBAL_AREA_KEY,
                    area_label="Global Entities",
                    scope="global",
                    space="world",
                    position_text="world (0, 0)",
                ),
            ],
            preferred_area_key="areas/demo",
        )

        self.assertEqual(dialog.current_area_key(), "areas/demo")
        self.assertEqual(dialog.visible_entity_ids(), ["switch_a", "hud_overlay"])

        dialog.set_filter_text("screen")
        self.assertEqual(dialog.visible_entity_ids(), ["hud_overlay"])

        dialog.set_filter_text("")
        dialog.select_area_key(GLOBAL_AREA_KEY)
        self.assertEqual(dialog.visible_entity_ids(), ["dialogue_controller"])

    def test_missing_current_value_is_highlighted(self):
        dialog = self._make_dialog()
        dialog.set_entries(
            [
                EntityReferencePickerEntry(
                    entity_id="switch_a",
                    template_id="entity_templates/switch",
                    area_key="areas/demo",
                    area_label="areas/demo",
                    scope="area",
                    space="world",
                    position_text="world (0, 0)",
                ),
            ],
            current_value="missing_entity",
            preferred_area_key="areas/demo",
        )

        self.assertIn("missing_entity", dialog.missing_value_text())
        self.assertEqual(dialog.selected_entity_id, "switch_a")

    def test_locked_area_disables_area_switching(self):
        dialog = self._make_dialog()
        dialog.set_entries(
            [
                EntityReferencePickerEntry(
                    entity_id="switch_a",
                    template_id="entity_templates/switch",
                    area_key="areas/demo",
                    area_label="areas/demo",
                    scope="area",
                    space="world",
                    position_text="world (0, 0)",
                ),
                EntityReferencePickerEntry(
                    entity_id="arrival_marker",
                    template_id="entity_templates/marker",
                    area_key="areas/start",
                    area_label="areas/start",
                    scope="area",
                    space="world",
                    position_text="world (5, 7)",
                ),
            ],
            preferred_area_key="areas/demo",
            locked_area_key="areas/start",
        )

        self.assertFalse(dialog.area_selection_enabled())
        self.assertEqual(dialog.current_area_key(), "areas/start")
        self.assertEqual(dialog.visible_entity_ids(), ["arrival_marker"])
