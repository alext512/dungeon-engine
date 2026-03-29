"""Dock panel for browsing and selecting tiles from an area's tilesets."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from area_editor.catalogs.tileset_catalog import TilesetCatalog
from area_editor.documents.area_document import TilesetRef

_MIN_ZOOM = 0.25
_MAX_ZOOM = 16.0
_ZOOM_STEP = 1.15

_BACKGROUND = QColor(24, 24, 24)
_GRID_COLOR = QColor(255, 255, 255, 70)
_GRID_AXIS_COLOR = QColor(255, 255, 255, 120)
_HOVER_PEN = QPen(QColor(255, 255, 255, 160), 1)
_SELECTED_PEN = QPen(QColor(0, 200, 220), 2)


class _TilesetSheetWidget(QWidget):
    """Scrollable sheet viewer with tile picking, pan, and wheel zoom."""

    tile_clicked = Signal(int)
    zoom_changed = Signal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setBackgroundRole(self.backgroundRole())

        self._sheet: QPixmap | None = None
        self._tile_width = 16
        self._tile_height = 16
        self._firstgid = 1
        self._selected_gid = 0
        self._hovered_gid = 0
        self._zoom = 1.0
        self._panning = False
        self._pan_pos = QPoint()

    @property
    def zoom_factor(self) -> float:
        return self._zoom

    def clear_sheet(self) -> None:
        self._sheet = None
        self._selected_gid = 0
        self._hovered_gid = 0
        self._zoom = 1.0
        self.resize(1, 1)
        self.update()
        self.zoom_changed.emit(self._zoom)

    def set_tileset(
        self,
        sheet: QPixmap,
        *,
        firstgid: int,
        tile_width: int,
        tile_height: int,
    ) -> None:
        self._sheet = sheet
        self._firstgid = firstgid
        self._tile_width = max(tile_width, 1)
        self._tile_height = max(tile_height, 1)
        self._selected_gid = 0
        self._hovered_gid = 0
        self._zoom = 1.0
        self._update_size()
        self.update()
        self.zoom_changed.emit(self._zoom)

    def select_gid(self, gid: int) -> None:
        self._selected_gid = gid if self.owns_gid(gid) else 0
        self.update()

    def owns_gid(self, gid: int) -> bool:
        if gid <= 0 or self._sheet is None:
            return False
        local_index = gid - self._firstgid
        return 0 <= local_index < self.frame_count()

    def frame_count(self) -> int:
        if self._sheet is None or self._tile_width <= 0 or self._tile_height <= 0:
            return 0
        cols = self._sheet.width() // self._tile_width
        rows = self._sheet.height() // self._tile_height
        return cols * rows

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if self._sheet is None:
            super().wheelEvent(event)
            return

        old_zoom = self._zoom
        if event.angleDelta().y() > 0:
            new_zoom = min(old_zoom * _ZOOM_STEP, _MAX_ZOOM)
        else:
            new_zoom = max(old_zoom / _ZOOM_STEP, _MIN_ZOOM)
        if abs(new_zoom - old_zoom) < 1e-9:
            event.accept()
            return

        image_x = event.position().x() / old_zoom
        image_y = event.position().y() / old_zoom
        self._zoom = new_zoom
        self._update_size()
        self.update()
        self.zoom_changed.emit(self._zoom)

        scroll = self._scroll_area()
        if scroll is not None:
            scroll.horizontalScrollBar().setValue(
                round(image_x * new_zoom - event.position().x())
            )
            scroll.verticalScrollBar().setValue(
                round(image_y * new_zoom - event.position().y())
            )
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_pos = event.globalPosition().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            gid = self._gid_at_position(event.position().toPoint())
            if gid > 0:
                self._selected_gid = gid
                self.tile_clicked.emit(gid)
                self.update()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._panning:
            scroll = self._scroll_area()
            if scroll is not None:
                current = event.globalPosition().toPoint()
                delta = current - self._pan_pos
                self._pan_pos = current
                scroll.horizontalScrollBar().setValue(
                    scroll.horizontalScrollBar().value() - delta.x()
                )
                scroll.verticalScrollBar().setValue(
                    scroll.verticalScrollBar().value() - delta.y()
                )
            event.accept()
            return

        gid = self._gid_at_position(event.position().toPoint())
        if gid != self._hovered_gid:
            self._hovered_gid = gid
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered_gid = 0
        if not self._panning:
            self.unsetCursor()
        self.update()
        super().leaveEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802
        if self._sheet is None:
            return QSize(1, 1)
        return QSize(
            max(1, round(self._sheet.width() * self._zoom)),
            max(1, round(self._sheet.height() * self._zoom)),
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), _BACKGROUND)
        if self._sheet is None or self._sheet.isNull():
            painter.end()
            return

        target = QRect(
            0,
            0,
            max(1, round(self._sheet.width() * self._zoom)),
            max(1, round(self._sheet.height() * self._zoom)),
        )
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawPixmap(target, self._sheet)
        self._draw_grid(painter)
        self._draw_gid_outline(painter, self._hovered_gid, _HOVER_PEN)
        self._draw_gid_outline(painter, self._selected_gid, _SELECTED_PEN)
        painter.end()

    def _draw_grid(self, painter: QPainter) -> None:
        if self._sheet is None:
            return
        scaled_tile_w = self._tile_width * self._zoom
        scaled_tile_h = self._tile_height * self._zoom
        width = self._sheet.width() * self._zoom
        height = self._sheet.height() * self._zoom

        painter.setPen(QPen(_GRID_AXIS_COLOR, 1))
        painter.drawRect(0, 0, int(width) - 1, int(height) - 1)

        painter.setPen(QPen(_GRID_COLOR, 1))
        x = scaled_tile_w
        while x < width:
            painter.drawLine(round(x), 0, round(x), round(height))
            x += scaled_tile_w
        y = scaled_tile_h
        while y < height:
            painter.drawLine(0, round(y), round(width), round(y))
            y += scaled_tile_h

    def _draw_gid_outline(self, painter: QPainter, gid: int, pen: QPen) -> None:
        if gid <= 0 or not self.owns_gid(gid):
            return
        local_index = gid - self._firstgid
        cols = max(self._sheet.width() // self._tile_width, 1) if self._sheet else 1
        col = local_index % cols
        row = local_index // cols
        rect = QRect(
            round(col * self._tile_width * self._zoom),
            round(row * self._tile_height * self._zoom),
            max(1, round(self._tile_width * self._zoom)),
            max(1, round(self._tile_height * self._zoom)),
        )
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

    def _gid_at_position(self, pos: QPoint) -> int:
        if self._sheet is None or self._zoom <= 0:
            return 0
        image_x = int(pos.x() / self._zoom)
        image_y = int(pos.y() / self._zoom)
        if (
            image_x < 0
            or image_y < 0
            or image_x >= self._sheet.width()
            or image_y >= self._sheet.height()
        ):
            return 0
        col = image_x // self._tile_width
        row = image_y // self._tile_height
        cols = self._sheet.width() // self._tile_width
        local_index = row * cols + col
        if local_index < 0 or local_index >= self.frame_count():
            return 0
        return self._firstgid + local_index

    def _update_size(self) -> None:
        hint = self.sizeHint()
        self.resize(hint)
        self.setMinimumSize(hint)

    def _scroll_area(self) -> QScrollArea | None:
        parent = self.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                return parent
            parent = parent.parentWidget()
        return None


class TilesetBrowserPanel(QDockWidget):
    """Right dock: full-sheet tileset picker for painting."""

    tile_selected = Signal(int)
    add_tileset_requested = Signal()
    edit_tileset_requested = Signal(int)

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

        header = QHBoxLayout()
        self._combo = QComboBox()
        self._combo.currentIndexChanged.connect(self._on_tileset_changed)
        header.addWidget(self._combo, 1)

        self._add_button = QToolButton()
        self._add_button.setText("+")
        self._add_button.setToolTip("Add tileset to active area")
        self._add_button.clicked.connect(self.add_tileset_requested.emit)
        header.addWidget(self._add_button)

        self._edit_button = QToolButton()
        self._edit_button.setText("Edit")
        self._edit_button.setToolTip("Edit tile size for this tileset")
        self._edit_button.clicked.connect(self._emit_edit_request)
        header.addWidget(self._edit_button)
        layout.addLayout(header)

        tools = QHBoxLayout()
        self._paint_button = QToolButton()
        self._paint_button.setText("Paint")
        self._paint_button.setCheckable(True)
        self._paint_button.toggled.connect(self._on_paint_toggled)
        tools.addWidget(self._paint_button)

        self._erase_button = QToolButton()
        self._erase_button.setText("Erase")
        self._erase_button.setCheckable(True)
        self._erase_button.toggled.connect(self._on_erase_toggled)
        tools.addWidget(self._erase_button)
        tools.addStretch(1)
        layout.addLayout(tools)

        self._sheet_widget = _TilesetSheetWidget()
        self._sheet_widget.tile_clicked.connect(self._on_tile_clicked)
        self._sheet_widget.zoom_changed.connect(self._on_zoom_changed)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(False)
        self._scroll.setWidget(self._sheet_widget)
        layout.addWidget(self._scroll, 1)

        self._status = QLabel("No tileset")
        layout.addWidget(self._status)

        self.setWidget(container)
        self.setMinimumWidth(220)

        self._tilesets: list[TilesetRef] = []
        self._catalog: TilesetCatalog | None = None
        self._current_tileset_index = -1
        self._remembered_gid = 0
        self._erase_mode = True
        self._zoom_factor = 1.0
        self._apply_brush_state(erase_mode=True, emit=False)

    @property
    def selected_gid(self) -> int:
        return 0 if self._erase_mode else self._remembered_gid

    @property
    def current_tileset_index(self) -> int:
        return self._current_tileset_index

    @property
    def brush_is_erase(self) -> bool:
        return self._erase_mode

    @property
    def zoom_factor(self) -> float:
        return self._zoom_factor

    def set_tilesets(
        self,
        tilesets: list[TilesetRef],
        catalog: TilesetCatalog,
        *,
        current_index: int = 0,
        selected_gid: int = 0,
        erase_mode: bool = True,
    ) -> None:
        """Populate from an area's tileset list and restore browser state."""
        self._tilesets = list(tilesets)
        self._catalog = catalog

        self._combo.blockSignals(True)
        self._combo.clear()
        for ts in self._tilesets:
            self._combo.addItem(Path(ts.path).stem)
        self._combo.blockSignals(False)

        if not self._tilesets:
            self.clear_tilesets()
            return

        index = min(max(current_index, 0), len(self._tilesets) - 1)
        self._combo.blockSignals(True)
        self._combo.setCurrentIndex(index)
        self._combo.blockSignals(False)
        self._load_tileset(index, selected_gid=selected_gid, erase_mode=erase_mode)

    def clear_tilesets(self) -> None:
        self._tilesets.clear()
        self._catalog = None
        self._current_tileset_index = -1
        self._remembered_gid = 0
        self._erase_mode = True
        self._zoom_factor = 1.0
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.blockSignals(False)
        self._sheet_widget.clear_sheet()
        self._apply_brush_state(erase_mode=True, emit=False)
        self._update_status()

    def select_gid(self, gid: int) -> None:
        """Programmatically select a brush GID, e.g. from eyedropper or tab restore."""
        if not self._tilesets:
            return

        if gid <= 0:
            index = self._current_tileset_index if self._current_tileset_index >= 0 else 0
            self._combo.blockSignals(True)
            self._combo.setCurrentIndex(index)
            self._combo.blockSignals(False)
            self._load_tileset(index, selected_gid=0, erase_mode=True)
            return

        owner = self._owner_index_for_gid(gid)
        if owner == -1:
            return
        self._combo.blockSignals(True)
        self._combo.setCurrentIndex(owner)
        self._combo.blockSignals(False)
        self._load_tileset(owner, selected_gid=gid, erase_mode=False)

    def _emit_edit_request(self) -> None:
        if self._current_tileset_index >= 0:
            self.edit_tileset_requested.emit(self._current_tileset_index)

    def _on_tileset_changed(self, index: int) -> None:
        if 0 <= index < len(self._tilesets):
            self._load_tileset(index, selected_gid=0, erase_mode=True)
            self.tile_selected.emit(0)

    def _on_tile_clicked(self, gid: int) -> None:
        self._remembered_gid = gid
        self._sheet_widget.select_gid(gid)
        self._apply_brush_state(erase_mode=False, emit=True)

    def _on_paint_toggled(self, checked: bool) -> None:
        if not checked:
            return
        if self._remembered_gid <= 0:
            self._apply_brush_state(erase_mode=True, emit=False)
            return
        self._apply_brush_state(erase_mode=False, emit=True)

    def _on_erase_toggled(self, checked: bool) -> None:
        if checked:
            self._apply_brush_state(erase_mode=True, emit=True)

    def _on_zoom_changed(self, zoom: float) -> None:
        self._zoom_factor = zoom
        self._update_status()

    def _load_tileset(self, index: int, *, selected_gid: int, erase_mode: bool) -> None:
        if self._catalog is None or index < 0 or index >= len(self._tilesets):
            return

        tileset = self._tilesets[index]
        self._current_tileset_index = index
        sheet = self._catalog.get_sheet(tileset.path)
        if sheet is None or sheet.isNull():
            self._sheet_widget.clear_sheet()
            self._remembered_gid = 0
            self._apply_brush_state(erase_mode=True, emit=False)
            self._status.setText("Tileset image not found")
            return

        self._sheet_widget.set_tileset(
            sheet,
            firstgid=tileset.firstgid,
            tile_width=tileset.tile_width,
            tile_height=tileset.tile_height,
        )
        self._zoom_factor = self._sheet_widget.zoom_factor

        if self._sheet_widget.owns_gid(selected_gid):
            self._remembered_gid = selected_gid
            self._sheet_widget.select_gid(selected_gid)
            self._apply_brush_state(erase_mode=erase_mode, emit=False)
        else:
            self._remembered_gid = 0
            self._sheet_widget.select_gid(0)
            self._apply_brush_state(erase_mode=True, emit=False)
        self._update_status()

    def _apply_brush_state(self, *, erase_mode: bool, emit: bool) -> None:
        self._erase_mode = erase_mode or self._remembered_gid <= 0
        self._paint_button.blockSignals(True)
        self._erase_button.blockSignals(True)
        self._paint_button.setChecked(not self._erase_mode and self._remembered_gid > 0)
        self._erase_button.setChecked(self._erase_mode)
        self._paint_button.blockSignals(False)
        self._erase_button.blockSignals(False)
        self._update_status()
        if emit:
            self.tile_selected.emit(self.selected_gid)

    def _update_status(self) -> None:
        if self._current_tileset_index < 0 or self._current_tileset_index >= len(self._tilesets):
            self._status.setText("No tileset")
            return

        tileset = self._tilesets[self._current_tileset_index]
        if self._erase_mode:
            brush = "Erase"
        elif self._remembered_gid > 0:
            brush = f"Paint GID {self._remembered_gid}"
        else:
            brush = "No tile selected"
        self._status.setText(
            f"{Path(tileset.path).stem} | {tileset.tile_width}x{tileset.tile_height} | "
            f"{brush} | {self._zoom_factor:.0%}"
        )

    def _owner_index_for_gid(self, gid: int) -> int:
        best_index = -1
        best_firstgid = -1
        for index, tileset in enumerate(self._tilesets):
            if tileset.firstgid <= gid and tileset.firstgid > best_firstgid:
                best_index = index
                best_firstgid = tileset.firstgid
        return best_index
