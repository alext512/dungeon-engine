"""Zoomable image preview widget.

Displays an image file (PNG, JPG, etc.) in a QGraphicsView with
mouse-wheel zoom and drag-to-pan.  Uses nearest-neighbour scaling
for crisp pixel art and a checkerboard background to show transparency.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
)

_MIN_ZOOM = 0.25
_MAX_ZOOM = 20.0
_ZOOM_STEP = 1.15

# Checkerboard colours for transparent backgrounds
_CHECK_LIGHT = QColor(204, 204, 204)
_CHECK_DARK = QColor(170, 170, 170)
_CHECK_SIZE = 8


def _checkerboard_brush() -> QBrush:
    """Create a tiling checkerboard brush for transparency indication."""
    size = _CHECK_SIZE * 2
    pm = QPixmap(size, size)
    pm.fill(_CHECK_LIGHT)
    painter = QPainter(pm)
    painter.fillRect(0, 0, _CHECK_SIZE, _CHECK_SIZE, _CHECK_DARK)
    painter.fillRect(_CHECK_SIZE, _CHECK_SIZE, _CHECK_SIZE, _CHECK_SIZE, _CHECK_DARK)
    painter.end()
    return QBrush(pm)


class ImageViewerWidget(QGraphicsView):
    """Tab content for previewing image assets."""

    def __init__(self, file_path: Path, parent=None) -> None:
        super().__init__(parent)

        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(_checkerboard_brush())
        self.setScene(self._scene)

        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)

        self._zoom: float = 1.0
        self._file_path = file_path
        self._load()

    @property
    def file_path(self) -> Path:
        return self._file_path

    def _load(self) -> None:
        pm = QPixmap(str(self._file_path))
        if pm.isNull():
            return
        item = QGraphicsPixmapItem(pm)
        self._scene.addItem(item)
        self._scene.setSceneRect(QRectF(0, 0, pm.width(), pm.height()))

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        factor = _ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / _ZOOM_STEP
        proposed = self._zoom * factor
        if _MIN_ZOOM <= proposed <= _MAX_ZOOM:
            self._zoom = proposed
            self.scale(factor, factor)
