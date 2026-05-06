"""Tests for the integrated documentation browser."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication

from area_editor.widgets.documentation_viewer import (
    _Heading,
    _markdown_to_html_with_heading_anchors,
    DocumentationViewerWidget,
)


class TestDocumentationViewerWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_contents_tree_and_markdown_links_navigate_inside_viewer(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs_base = Path(tmp) / "docs"
            docs_root = docs_base / "authoring"
            commands_dir = docs_root / "commands"
            commands_dir.mkdir(parents=True)
            (docs_root / "index.md").write_text(
                "# Getting Started\n\n"
                "[Dialogue Commands](commands/dialogue.md#set_entity_active_dialogue)\n\n"
                "## Overview\n\n"
                "Welcome.\n",
                encoding="utf-8",
            )
            dialogue_path = commands_dir / "dialogue.md"
            dialogue_path.write_text(
                "# Dialogue Commands\n\n"
                "## open_entity_dialogue\n\n"
                "Open one dialogue.\n\n"
                "## set_entity_active_dialogue\n\n"
                "Choose the active dialogue.\n",
                encoding="utf-8",
            )

            widget = DocumentationViewerWidget(docs_root=docs_root, docs_base=docs_base)
            self.addCleanup(widget.close)

            self.assertEqual(widget.current_path, (docs_root / "index.md").resolve())
            self.assertGreaterEqual(widget._contents_tree.topLevelItemCount(), 2)

            with patch.object(widget._browser, "scrollToAnchor") as scroll_to_anchor:
                widget._on_anchor_clicked(
                    QUrl("commands/dialogue.md#set_entity_active_dialogue")
                )

            self.assertEqual(widget.current_path, dialogue_path.resolve())
            self.assertEqual(
                widget._contents_tree.currentItem().text(0),
                "set_entity_active_dialogue",
            )
            scroll_to_anchor.assert_called_once_with("set_entity_active_dialogue")

            widget.back()
            self.assertEqual(widget.current_path, (docs_root / "index.md").resolve())

            widget.forward()
            self.assertEqual(widget.current_path, dialogue_path.resolve())

    def test_external_links_use_desktop_services(self):
        with tempfile.TemporaryDirectory() as tmp:
            docs_base = Path(tmp) / "docs"
            docs_root = docs_base / "authoring"
            docs_root.mkdir(parents=True)
            (docs_root / "index.md").write_text(
                "# Getting Started\n\n[External](https://example.com)\n",
                encoding="utf-8",
            )
            widget = DocumentationViewerWidget(docs_root=docs_root, docs_base=docs_base)
            self.addCleanup(widget.close)

            with patch(
                "area_editor.widgets.documentation_viewer.QDesktopServices.openUrl",
                return_value=True,
            ) as open_url:
                widget._on_anchor_clicked(QUrl("https://example.com"))

            open_url.assert_called_once()
            self.assertEqual(open_url.call_args.args[0].toString(), "https://example.com")

    def test_heading_anchors_are_inserted_before_real_headings(self):
        markdown = (
            "# Dialogue Commands\n\n"
            "## open_dialogue_session\n\n"
            "Open a dialogue.\n\n"
            "Related: [set_entity_active_dialogue](#set_entity_active_dialogue)\n\n"
            "## close_dialogue_session\n\n"
            "Close a dialogue.\n\n"
            "## open_entity_dialogue\n\n"
            "Open an entity dialogue.\n\n"
            "## set_entity_active_dialogue\n\n"
            "Choose the active dialogue.\n"
        )
        html = _markdown_to_html_with_heading_anchors(
            markdown,
            [
                _Heading(1, "Dialogue Commands", "dialogue-commands"),
                _Heading(2, "open_dialogue_session", "open_dialogue_session"),
                _Heading(2, "close_dialogue_session", "close_dialogue_session"),
                _Heading(2, "open_entity_dialogue", "open_entity_dialogue"),
                _Heading(2, "set_entity_active_dialogue", "set_entity_active_dialogue"),
            ],
        )

        link_index = html.index('href="#set_entity_active_dialogue"')
        anchor_index = html.index('<a name="set_entity_active_dialogue"')
        heading_index = html.index("<h2", anchor_index)
        heading_text_index = html.index("set_entity_active_dialogue", heading_index)
        open_entity_anchor_index = html.index('<a name="open_entity_dialogue"')
        open_entity_text_index = html.index("open_entity_dialogue", open_entity_anchor_index)

        self.assertLess(link_index, anchor_index)
        self.assertLess(anchor_index, heading_index)
        self.assertLess(heading_index, heading_text_index)
        self.assertLess(open_entity_anchor_index, open_entity_text_index)
        self.assertLess(open_entity_text_index, anchor_index)


if __name__ == "__main__":
    unittest.main()
