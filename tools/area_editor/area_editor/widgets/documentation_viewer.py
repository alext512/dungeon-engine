"""Integrated Markdown documentation browser for the editor."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
DOCS_BASE_PATH = _REPO_ROOT / "docs"
AUTHORING_DOCS_PATH = DOCS_BASE_PATH / "authoring" / "index.md"
COMMAND_DOCS_PATH = DOCS_BASE_PATH / "authoring" / "commands" / "index.md"

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_STRIP_MARKDOWN_RE = re.compile(r"[*`#\[\]]")


@dataclass(frozen=True)
class _Heading:
    level: int
    title: str
    slug: str


def _slug_for_heading(title: str) -> str:
    """Return the simple heading slug used by the editor docs browser."""
    text = title.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text.strip("-")


def _clean_heading_text(text: str) -> str:
    return _STRIP_MARKDOWN_RE.sub("", text).strip()


def _read_markdown_title(path: Path) -> str:
    headings = _extract_headings(path)
    if headings:
        return headings[0].title
    return path.stem.replace("-", " ").replace("_", " ").title()


def _extract_headings(path: Path) -> list[_Heading]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    headings: list[_Heading] = []
    for line in lines:
        match = _HEADING_RE.match(line)
        if match is None:
            continue
        level = len(match.group(1))
        title = _clean_heading_text(match.group(2))
        if title:
            headings.append(_Heading(level=level, title=title, slug=_slug_for_heading(title)))
    return headings


def _markdown_to_html_with_heading_anchors(
    markdown: str,
    headings: list[_Heading],
) -> str:
    """Render Markdown to rich text HTML and inject anchors before headings."""
    document = QTextDocument()
    document.setMarkdown(markdown)
    html = document.toHtml()

    heading_tags = list(re.finditer(r"<h([1-3])\b", html, re.IGNORECASE))
    insertions: list[tuple[int, str]] = []
    tag_index = 0
    for heading in headings:
        while tag_index < len(heading_tags):
            tag = heading_tags[tag_index]
            tag_index += 1
            if int(tag.group(1)) == heading.level:
                insertions.append((tag.start(), heading.slug))
                break
    for insert_at, slug in reversed(insertions):
        anchor = f'<a name="{slug}" id="{slug}"></a>'
        html = f"{html[:insert_at]}{anchor}{html[insert_at:]}"
    return html


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


class DocumentationViewerWidget(QWidget):
    """A small in-editor browser for the repo's Markdown documentation."""

    def __init__(
        self,
        *,
        docs_root: Path | None = None,
        docs_base: Path | None = None,
        start_path: Path | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._docs_root = (docs_root or (DOCS_BASE_PATH / "authoring")).resolve()
        self._docs_base = (docs_base or DOCS_BASE_PATH).resolve()
        self._current_path: Path | None = None
        self._history: list[tuple[Path, str]] = []
        self._history_index = -1
        self._syncing_tree = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(6, 6, 6, 3)
        self._back_button = QPushButton("Back")
        self._back_button.clicked.connect(self.back)
        toolbar.addWidget(self._back_button)
        self._forward_button = QPushButton("Forward")
        self._forward_button.clicked.connect(self.forward)
        toolbar.addWidget(self._forward_button)
        self._home_button = QPushButton("Home")
        self._home_button.clicked.connect(lambda: self.open_document(self._docs_root / "index.md"))
        toolbar.addWidget(self._home_button)
        self._location_label = QLabel("")
        self._location_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        toolbar.addWidget(self._location_label, 1)
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Find in page...")
        self._search_edit.returnPressed.connect(self._find_in_page)
        toolbar.addWidget(self._search_edit)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._contents_tree = QTreeWidget()
        self._contents_tree.setHeaderHidden(True)
        self._contents_tree.itemActivated.connect(self._on_contents_item_activated)
        self._contents_tree.itemClicked.connect(self._on_contents_item_activated)
        splitter.addWidget(self._contents_tree)

        self._browser = QTextBrowser()
        self._browser.setOpenLinks(False)
        self._browser.anchorClicked.connect(self._on_anchor_clicked)
        splitter.addWidget(self._browser)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([260, 760])
        layout.addWidget(splitter, 1)

        self._populate_contents_tree()
        self.open_document(start_path or self._docs_root / "index.md")

    @property
    def current_path(self) -> Path | None:
        return self._current_path

    def open_document(self, path: Path, fragment: str = "", *, add_history: bool = True) -> None:
        """Open one Markdown document and optionally scroll to a heading fragment."""
        resolved = path.resolve()
        if not resolved.exists() or resolved.suffix.lower() != ".md":
            return
        if not _is_relative_to(resolved, self._docs_base):
            return

        try:
            markdown = resolved.read_text(encoding="utf-8")
        except OSError as exc:
            self._browser.setPlainText(f"Could not read documentation file:\n{exc}")
            return

        self._current_path = resolved
        headings = _extract_headings(resolved)
        self._browser.setHtml(_markdown_to_html_with_heading_anchors(markdown, headings))
        self._location_label.setText(self._display_path(resolved))
        self._select_tree_item(resolved, fragment)
        if add_history:
            self._push_history(resolved, fragment)
        self._sync_history_buttons()
        if fragment:
            self._scroll_to_fragment(fragment)
        else:
            self._browser.moveCursor(QTextCursor.MoveOperation.Start)

    def back(self) -> None:
        if self._history_index <= 0:
            return
        self._history_index -= 1
        path, fragment = self._history[self._history_index]
        self.open_document(path, fragment, add_history=False)

    def forward(self) -> None:
        if self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        path, fragment = self._history[self._history_index]
        self.open_document(path, fragment, add_history=False)

    def _populate_contents_tree(self) -> None:
        self._contents_tree.clear()
        for path in sorted(self._docs_root.rglob("*.md"), key=self._tree_sort_key):
            page_item = QTreeWidgetItem([_read_markdown_title(path)])
            page_item.setData(0, Qt.ItemDataRole.UserRole, (str(path.resolve()), ""))
            self._contents_tree.addTopLevelItem(page_item)
            for heading in _extract_headings(path):
                if heading.level == 1:
                    continue
                heading_item = QTreeWidgetItem([heading.title])
                heading_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    (str(path.resolve()), heading.slug),
                )
                page_item.addChild(heading_item)
            if path.resolve() == (self._docs_root / "index.md").resolve():
                page_item.setExpanded(True)

    def _tree_sort_key(self, path: Path) -> tuple[int, str]:
        if path.name == "index.md":
            return (0, str(path.relative_to(self._docs_root)))
        return (1, str(path.relative_to(self._docs_root)))

    def _on_contents_item_activated(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        if self._syncing_tree:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple) or len(data) != 2:
            return
        path_text, fragment = data
        self.open_document(Path(path_text), str(fragment))

    def _on_anchor_clicked(self, url: QUrl) -> None:
        if url.scheme() in {"http", "https"}:
            QDesktopServices.openUrl(url)
            return
        target_path, fragment = self._resolve_link(url)
        if target_path is None:
            return
        if target_path.suffix.lower() == ".md" and target_path.exists():
            self.open_document(target_path, fragment)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_path)))

    def _resolve_link(self, url: QUrl) -> tuple[Path | None, str]:
        if self._current_path is None:
            return None, ""
        fragment = url.fragment()
        raw_path = url.path()
        if not raw_path:
            return self._current_path, fragment
        candidate = (self._current_path.parent / raw_path).resolve()
        if _is_relative_to(candidate, self._docs_base):
            return candidate, fragment
        return None, ""

    def _scroll_to_fragment(self, fragment: str) -> None:
        self._browser.scrollToAnchor(fragment)

    def _select_tree_item(self, path: Path, fragment: str) -> None:
        self._syncing_tree = True
        try:
            target = str(path.resolve())
            for top_index in range(self._contents_tree.topLevelItemCount()):
                top = self._contents_tree.topLevelItem(top_index)
                top_data = top.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(top_data, tuple) and top_data[0] == target and not fragment:
                    self._contents_tree.setCurrentItem(top)
                    return
                for child_index in range(top.childCount()):
                    child = top.child(child_index)
                    child_data = child.data(0, Qt.ItemDataRole.UserRole)
                    if (
                        isinstance(child_data, tuple)
                        and child_data[0] == target
                        and child_data[1] == fragment
                    ):
                        top.setExpanded(True)
                        self._contents_tree.setCurrentItem(child)
                        return
        finally:
            self._syncing_tree = False

    def _push_history(self, path: Path, fragment: str) -> None:
        entry = (path.resolve(), fragment)
        if self._history_index >= 0 and self._history[self._history_index] == entry:
            return
        del self._history[self._history_index + 1 :]
        self._history.append(entry)
        self._history_index = len(self._history) - 1

    def _sync_history_buttons(self) -> None:
        self._back_button.setEnabled(self._history_index > 0)
        self._forward_button.setEnabled(self._history_index < len(self._history) - 1)

    def _display_path(self, path: Path) -> str:
        try:
            return str(path.relative_to(self._docs_base)).replace("\\", "/")
        except ValueError:
            return str(path)

    def _find_in_page(self) -> None:
        text = self._search_edit.text()
        if not text:
            return
        if not self._browser.find(text):
            cursor = self._browser.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self._browser.setTextCursor(cursor)
            self._browser.find(text)


class DocumentationDialog(QDialog):
    """Foreground documentation browser used while another editor dialog is modal."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        start_path: Path | None = None,
        fragment: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Documentation")
        self.resize(980, 720)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.viewer = DocumentationViewerWidget(start_path=start_path, parent=self)
        if start_path is not None and fragment:
            self.viewer.open_document(start_path, fragment)
        layout.addWidget(self.viewer, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
