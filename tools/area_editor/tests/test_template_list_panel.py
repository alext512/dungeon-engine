"""Widget tests for the template list panel brush behavior."""

from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QTreeWidgetItem

from area_editor.widgets.template_list_panel import TemplateListPanel


class TestTemplateListPanel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_single_click_emits_template_brush_signal_and_highlight(self):
        panel = TemplateListPanel()
        item = QTreeWidgetItem(panel._tree, ["npc"])
        item.setData(0, 256, ("entity_templates/npc", Path("npc.json")))

        selected: list[str] = []
        panel.template_brush_selected.connect(selected.append)

        panel._tree.setCurrentItem(item)
        QApplication.processEvents()

        self.assertEqual(selected, ["entity_templates/npc"])

        panel.set_brush_active("entity_templates/npc")
        self.assertTrue(item.font(0).bold())
        self.assertGreater(item.background(0).color().alpha(), 0)

        panel.set_brush_active(None)
        self.assertFalse(item.font(0).bold())
