"""Dock panel for browsing and selecting tiles from the area's tilesets.

Shows a grid of tile frames rendered from the tileset PNG.  The user
clicks a tile to select it as the active painting brush.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QColor,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from area_editor.catalogs.tileset_catalog import TilesetCatalog
from area_editor.documents.area_document import TilesetRef

# Display size for each tile cell in the browser (pixels).
_CELL_DISPLAY_SIZE = 34
_CELL_PADDING = 2
_CELL_TOTAL = _CELL_DISPLAY_SIZE + _CELL_PADDING

# Highlight
_HIGHLIGHT_PEN = QPen(QColor(0, 200, 220), 2)
_HOVER_PEN = QPen(QColor(255, 255, 255, 100), 1)

# Eraser crosshatch
_ERASER_BG = QColor(40, 40, 40)
_ERASER_LINE = QColor(200, 60, 60, 180)


class _TileGridWidget(QWidget):
    """Internal widget that renders a scrollable grid of tile frames."""

    tile_clicked = Signal(int)  # GID

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)

        self._frames: list[tuple[int, QPixmap | None]] = []  # (gid, pixmap)
        self._selected_gid: int = 0
        self._hovered_index: int = -1

    def set_frames(self, frames: list[tuple[int, QPixmap | None]]) -> None:
        """Set the list of (GID, pixmap) pairs to display.

        The first entry should be (0, None) for the eraser.
        """
        self._frames = frames
        self._selected_gid = 0
        self._hovered_index = -1
        self._update_size()
        self.update()

    def select_gid(self, gid: int) -> None:
        self._selected_gid = gid
        self.update()

    @property
    def selected_gid(self) -> int:
        return self._selected_gid

    # -- geometry --

    def _cols(self) -> int:
        w = max(self.width(), _CELL_TOTAL)
        return max(w // _CELL_TOTAL, 1)

    def _rows(self) -> int:
        n = len(self._frames)
        cols = self._cols()
        return max((n + cols - 1) // cols, 1)

    def _update_size(self) -> None:
        rows = self._rows()
        self.setMinimumHeight(rows * _CELL_TOTAL + _CELL_PADDING)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_size()

    # -- hit testing --

    def _index_at(self, x: int, y: int) -> int:
        col = x // _CELL_TOTAL
        row = y // _CELL_TOTAL
        cols = self._cols()
        if col < 0 or col >= cols:
            return -1
        idx = row * cols + col
        if idx < 0 or idx >= len(self._frames):
            return -1
        return idx

    # -- events --

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self._index_at(
                int(event.position().x()), int(event.position().y())
            )
            if 0 <= idx < len(self._frames):
                gid = self._frames[idx][0]
                self._selected_gid = gid
                self.tile_clicked.emit(gid)
                self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        idx = self._index_at(
            int(event.position().x()), int(event.position().y())
        )
        if idx != self._hovered_index:
            self._hovered_index = idx
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered_index = -1
        self.update()

    # -- painting --

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._frames:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        cols = self._cols()

        for i, (gid, pixmap) in enumerate(self._frames):
            col = i % cols
            row = i // cols
            x = col * _CELL_TOTAL + _CELL_PADDING
            y = row * _CELL_TOTAL + _CELL_PADDING
            cell_rect = QRect(x, y, _CELL_DISPLAY_SIZE, _CELL_DISPLAY_SIZE)

            if pixmap is not None:
                painter.drawPixmap(cell_rect, pixmap)
            else:
                # Eraser cell: crosshatch
                painter.fillRect(cell_rect, _ERASER_BG)
                pen = QPen(_ERASER_LINE, 1)
                painter.setPen(pen)
                # Draw diagonal lines
                for offset in range(-_CELL_DISPLAY_SIZE, _CELL_DISPLAY_SIZE + 1, 6):
                    painter.drawLine(
                        x + offset, y,
                        x + offset + _CELL_DISPLAY_SIZE, y + _CELL_DISPLAY_SIZE,
                    )

            # Hover highlight
            if i == self._hovered_index and gid != self._selected_gid:
                painter.setPen(_HOVER_PEN)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(cell_rect.adjusted(0, 0, -1, -1))

            # Selection highlight
            if gid == self._selected_gid:
                painter.setPen(_HIGHLIGHT_PEN)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(cell_rect.adjusted(0, 0, -1, -1))

        painter.end()


class TilesetBrowserPanel(QDockWidget):
    """Right dock: tileset tile picker for painting."""

    tile_selected = Signal(int)  # GID

    def __init__(self, parent=None) -> None:
        super().__init__("Tileset", parent)
        self.setObjectName("TilesetBrowserPanel")
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)

        # Tileset dropdown
        self._combo = QComboBox()
        self._combo.currentIndexChanged.connect(self._on_tileset_changed)
        layout.addWidget(self._combo)

        # Tile grid
        self._grid = _TileGridWidget()
        self._grid.tile_clicked.connect(self._on_tile_clicked)
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(self._grid)
        layout.addWidget(self._scroll, 1)

        # Status label
        self._status = QLabel("No tileset")
        layout.addWidget(self._status)

        self.setWidget(container)
        self.setMinimumWidth(140)

        # State
        self._tilesets: list[TilesetRef] = []
        self._catalog: TilesetCatalog | None = None
        self._current_tileset_index: int = -1

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_tilesets(
        self,
        tilesets: list[TilesetRef],
        catalog: TilesetCatalog,
    ) -> None:
        """Populate from an area's tileset list."""
        self._tilesets = list(tilesets)
        self._catalog = catalog
        self._current_tileset_index = -1

        self._combo.blockSignals(True)
        self._combo.clear()
        for ts in tilesets:
            # Display the filename without extension
            name = Path(ts.path).stem
            self._combo.addItem(name)
        self._combo.blockSignals(False)

        if tilesets:
            self._combo.setCurrentIndex(0)
            self._load_tileset(0)
        else:
            self._grid.set_frames([])
            self._status.setText("No tileset")

    def clear_tilesets(self) -> None:
        self._tilesets.clear()
        self._catalog = None
        self._current_tileset_index = -1
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.blockSignals(False)
        self._grid.set_frames([])
        self._status.setText("No tileset")

    @property
    def selected_gid(self) -> int:
        return self._grid.selected_gid

    @property
    def current_tileset_index(self) -> int:
        return self._current_tileset_index

    def select_gid(self, gid: int) -> None:
        """Programmatically select a GID (e.g. from eyedropper)."""
        if self._tilesets:
            owner = self._owner_index_for_gid(gid)
            if owner != -1 and owner != self._combo.currentIndex():
                self._combo.setCurrentIndex(owner)
        self._grid.select_gid(gid)
        self._update_status(gid)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_tileset_changed(self, index: int) -> None:
        if 0 <= index < len(self._tilesets):
            self._load_tileset(index)

    def _on_tile_clicked(self, gid: int) -> None:
        self._update_status(gid)
        self.tile_selected.emit(gid)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_tileset(self, index: int) -> None:
        if self._catalog is None or index >= len(self._tilesets):
            return

        ts = self._tilesets[index]
        self._current_tileset_index = index
        firstgid = ts.firstgid

        # Load the sheet to compute frame count
        sheet = self._catalog.get_sheet(ts.path)
        if sheet is None or sheet.isNull():
            self._grid.set_frames([])
            self._status.setText("Tileset image not found")
            return

        tw = ts.tile_width
        th = ts.tile_height
        if tw <= 0 or th <= 0:
            self._grid.set_frames([])
            return

        cols = sheet.width() // tw
        rows = sheet.height() // th
        total = cols * rows

        # Build frame list: eraser first, then all tileset frames
        frames: list[tuple[int, QPixmap | None]] = [(0, None)]  # eraser
        for local_idx in range(total):
            gid = firstgid + local_idx
            pm = self._catalog.get_tile_pixmap(gid, self._tilesets)
            frames.append((gid, pm))

        self._grid.set_frames(frames)
        self._grid.select_gid(0)
        self._update_status(self._grid.selected_gid)

    def _update_status(self, gid: int) -> None:
        if gid == 0:
            self._status.setText("Eraser")
        else:
            self._status.setText(f"GID: {gid}")

    def _owner_index_for_gid(self, gid: int) -> int:
        if not self._tilesets or gid == 0:
            return 0 if self._tilesets else -1
        best_index = -1
        best_firstgid = -1
        for index, ts in enumerate(self._tilesets):
            if ts.firstgid <= gid and ts.firstgid > best_firstgid:
                best_index = index
                best_firstgid = ts.firstgid
        return best_index
