"""Zoomable, pannable tile-map canvas built on QGraphicsView.

Renders tile layers as composited pixmap items, entity markers as
coloured rectangles, and an optional grid overlay.  Z-ordering respects
the ``draw_above_entities`` flag on each tile layer so that overlay
layers are drawn on top of entity markers, matching the runtime's
rendering contract.

Zoom:
    Mouse-wheel with anchor-under-mouse.  Range 0.25x .. 10x.
    ``SmoothPixmapTransform`` is disabled so pixel art stays crisp.

Pan:
    Middle-mouse drag (ScrollHandDrag mode).
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsItemGroup,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)

from area_editor.catalogs.template_catalog import TemplateCatalog
from area_editor.catalogs.tileset_catalog import TilesetCatalog
from area_editor.documents.area_document import AreaDocument
from area_editor.operations.cell_flags import cell_is_walkable, set_cell_walkable
from area_editor.operations.tiles import eyedrop_tile, paint_tile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_ZOOM = 0.25
_MAX_ZOOM = 10.0
_ZOOM_STEP = 1.15

# Entity marker appearance (fallback when no sprite available)
_ENTITY_FILL = QColor(0, 200, 220, 100)
_ENTITY_BORDER = QColor(0, 200, 220, 200)
_ENTITY_SCREEN_FILL = QColor(220, 140, 0, 100)
_ENTITY_SCREEN_BORDER = QColor(220, 140, 0, 200)

# Grid overlay
_GRID_COLOR = QColor(255, 255, 255, 40)
_CELL_FLAG_BLOCKED_FILL = QColor(220, 40, 40, 90)
_CELL_FLAG_BLOCKED_BORDER = QColor(220, 40, 40, 180)

# Scene background
_BG_COLOR = QColor(30, 30, 30)


class TileCanvas(QGraphicsView):
    """Central widget: renders tile layers, entity markers, and grid."""

    # Signals for status-bar updates
    cell_hovered = Signal(int, int)       # (col, row) in tile coords
    zoom_changed = Signal(float)          # current zoom factor
    cell_flag_edited = Signal(int, int, bool)
    tile_painted = Signal(int, int, int, int)  # (layer_idx, col, row, gid)
    tile_eyedropped = Signal(int)              # gid picked from canvas

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # Scene
        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(_BG_COLOR)
        self.setScene(self._scene)

        # View behaviour
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setMouseTracking(True)
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate
        )

        # State
        self._zoom: float = 1.0
        self._tile_size: int = 16
        self._area: AreaDocument | None = None
        self._catalog: TilesetCatalog | None = None
        self._layer_groups: list[QGraphicsItemGroup] = []
        self._entity_group: QGraphicsItemGroup | None = None
        self._cell_flag_group: QGraphicsItemGroup | None = None
        self._grid_group: QGraphicsItemGroup | None = None
        self._ghost_item: QGraphicsPixmapItem | None = None
        self._grid_visible: bool = True
        self._cell_flags_edit_mode: bool = False
        self._tile_paint_mode: bool = False
        self._active_layer: int = 0
        self._selected_gid: int = 0
        self._last_painted: tuple[int, int, bool] | None = None
        self._last_tile_painted: tuple[int, int, int] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_area(
        self,
        area: AreaDocument,
        catalog: TilesetCatalog,
        templates: TemplateCatalog | None = None,
    ) -> None:
        """Populate the scene from an area document."""
        self._scene.clear()
        self._area = area
        self._catalog = catalog
        self._layer_groups.clear()
        self._entity_group = None
        self._cell_flag_group = None
        self._grid_group = None
        self._ghost_item = None
        self._tile_size = area.tile_size or 16

        width_px = area.width * self._tile_size
        height_px = area.height * self._tile_size
        self._scene.setSceneRect(QRectF(0, 0, max(width_px, 1), max(height_px, 1)))

        # ----- Tile layers + entity markers with correct z-order -----
        #
        # Z-value allocation:
        #   below-entity layers  : 0, 1, 2, ...
        #   entity markers       : 1000
        #   above-entity layers  : 2000, 2001, ...
        #   grid overlay         : 3000

        z_below = 0
        z_above = 2000
        below_groups: list[QGraphicsItemGroup] = []
        above_groups: list[QGraphicsItemGroup] = []

        for layer in area.tile_layers:
            group = self._build_tile_layer_group(layer.grid, area, catalog)
            if layer.draw_above_entities:
                group.setZValue(z_above)
                z_above += 1
                above_groups.append(group)
            else:
                group.setZValue(z_below)
                z_below += 1
                below_groups.append(group)
            self._scene.addItem(group)

        # Store all groups in draw order (below first, then above) so the
        # layer-list panel indices map 1:1.
        self._layer_groups = []
        for layer in area.tile_layers:
            if not layer.draw_above_entities:
                self._layer_groups.append(below_groups.pop(0))
            else:
                self._layer_groups.append(above_groups.pop(0))

        # Entity markers (with sprites when templates are available)
        self._entity_group = self._build_entity_group(area, catalog, templates)
        self._entity_group.setZValue(1000)
        self._scene.addItem(self._entity_group)

        self._cell_flag_group = self._build_cell_flag_group(area)
        self._cell_flag_group.setZValue(2500)
        self._cell_flag_group.setVisible(self._cell_flags_edit_mode)
        self._scene.addItem(self._cell_flag_group)

        # Grid overlay
        self._grid_group = self._build_grid_group(area)
        self._grid_group.setZValue(3000)
        self._grid_group.setVisible(self._grid_visible)
        self._scene.addItem(self._grid_group)
        self._update_drag_mode()

    def clear_area(self) -> None:
        """Remove all items from the scene."""
        self._scene.clear()
        self._area = None
        self._catalog = None
        self._layer_groups.clear()
        self._entity_group = None
        self._cell_flag_group = None
        self._grid_group = None
        self._ghost_item = None

    # -- Layer visibility ------------------------------------------------

    def set_layer_visible(self, index: int, visible: bool) -> None:
        """Show or hide the tile-layer group at *index*."""
        if 0 <= index < len(self._layer_groups):
            self._layer_groups[index].setVisible(visible)

    def set_entities_visible(self, visible: bool) -> None:
        if self._entity_group is not None:
            self._entity_group.setVisible(visible)

    def set_grid_visible(self, visible: bool) -> None:
        self._grid_visible = visible
        if self._grid_group is not None:
            self._grid_group.setVisible(visible)

    def set_cell_flags_edit_mode(self, enabled: bool) -> None:
        self._cell_flags_edit_mode = enabled
        if self._cell_flag_group is not None:
            self._cell_flag_group.setVisible(enabled)
        self.viewport().setCursor(
            Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor
        )
        self._update_drag_mode()
        self._last_painted = None

    @property
    def cell_flags_edit_mode(self) -> bool:
        return self._cell_flags_edit_mode

    # -- Tile paint mode -------------------------------------------------

    def set_tile_paint_mode(self, enabled: bool) -> None:
        self._tile_paint_mode = enabled
        self.viewport().setCursor(
            Qt.CursorShape.CrossCursor
            if enabled
            else Qt.CursorShape.ArrowCursor
        )
        self._update_drag_mode()
        self._last_tile_painted = None
        # Remove ghost when leaving paint mode
        if not enabled and self._ghost_item is not None:
            self._scene.removeItem(self._ghost_item)
            self._ghost_item = None

    @property
    def tile_paint_mode(self) -> bool:
        return self._tile_paint_mode

    def set_active_layer(self, index: int) -> None:
        self._active_layer = index

    def set_selected_gid(self, gid: int) -> None:
        self._selected_gid = gid
        self._update_ghost_pixmap()

    def apply_cell_flag_brush(self, col: int, row: int, walkable: bool) -> bool:
        """Apply the cell-flag brush directly to one cell."""
        if self._area is None:
            return False
        changed = set_cell_walkable(self._area, col, row, walkable)
        if changed:
            self._rebuild_cell_flag_group()
            self.cell_flag_edited.emit(col, row, walkable)
        return changed

    # -- Zoom ------------------------------------------------------------

    def reset_zoom(self) -> None:
        """Reset the view to 1:1 zoom."""
        self.resetTransform()
        self._zoom = 1.0
        self.zoom_changed.emit(self._zoom)

    @property
    def zoom_level(self) -> float:
        return self._zoom

    # ------------------------------------------------------------------
    # Qt event overrides
    # ------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        factor = _ZOOM_STEP if event.angleDelta().y() > 0 else 1.0 / _ZOOM_STEP
        proposed = self._zoom * factor
        if _MIN_ZOOM <= proposed <= _MAX_ZOOM:
            self._zoom = proposed
            self.scale(factor, factor)
            self.zoom_changed.emit(self._zoom)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._handle_edit_pointer_event(event, event.button()):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        scene_pos = self.mapToScene(event.position().toPoint())
        col = -1
        row = -1
        if self._tile_size > 0:
            col = int(scene_pos.x() / self._tile_size)
            row = int(scene_pos.y() / self._tile_size)
            self.cell_hovered.emit(col, row)

        # Update ghost preview position
        if self._tile_paint_mode and self._area is not None:
            if 0 <= col < self._area.width and 0 <= row < self._area.height:
                self._show_ghost(col, row)
            else:
                self._hide_ghost()

        buttons = event.buttons()
        if buttons & Qt.MouseButton.LeftButton:
            if self._handle_edit_pointer_event(event, Qt.MouseButton.LeftButton):
                event.accept()
                return
        elif buttons & Qt.MouseButton.RightButton:
            if self._handle_edit_pointer_event(event, Qt.MouseButton.RightButton):
                event.accept()
                return
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hide_ghost()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._last_painted = None
        self._last_tile_painted = None
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Scene-building helpers
    # ------------------------------------------------------------------

    def _build_tile_layer_group(
        self,
        grid: list[list[int]],
        area: AreaDocument,
        catalog: TilesetCatalog,
    ) -> QGraphicsItemGroup:
        group = QGraphicsItemGroup()
        ts = self._tile_size
        for row_idx, row in enumerate(grid):
            for col_idx, gid in enumerate(row):
                if gid == 0:
                    continue
                pm = catalog.get_tile_pixmap(gid, area.tilesets, fallback_size=ts)
                if pm is None:
                    continue
                item = QGraphicsPixmapItem(pm)
                item.setPos(col_idx * ts, row_idx * ts)
                item.setParentItem(group)
        return group

    def _build_entity_group(
        self,
        area: AreaDocument,
        catalog: TilesetCatalog,
        templates: TemplateCatalog | None,
    ) -> QGraphicsItemGroup:
        group = QGraphicsItemGroup()
        ts = self._tile_size

        for entity in area.entities:
            if entity.is_screen_space:
                px = entity.pixel_x or 0
                py = entity.pixel_y or 0
                fill = _ENTITY_SCREEN_FILL
                border = _ENTITY_SCREEN_BORDER
            else:
                px = entity.x * ts
                py = entity.y * ts
                fill = _ENTITY_FILL
                border = _ENTITY_BORDER

            tooltip = entity.id
            if entity.template:
                tooltip += f"  ({entity.template})"

            # Try to render the actual sprite from the template visual
            sprite_rendered = False
            if templates and entity.template:
                visual = templates.get_first_visual(entity.template)
                if visual:
                    frame_index = visual.frames[0] if visual.frames else 0
                    sprite = catalog.get_sprite_frame(
                        visual.path,
                        visual.frame_width,
                        visual.frame_height,
                        frame_index,
                    )
                    if sprite is not None:
                        sprite_item = QGraphicsPixmapItem(sprite)
                        sprite_item.setPos(
                            px + visual.offset_x,
                            py + visual.offset_y,
                        )
                        sprite_item.setToolTip(tooltip)
                        sprite_item.setParentItem(group)
                        sprite_rendered = True

            # Fallback: coloured rectangle marker when no sprite available
            if not sprite_rendered:
                rect = QGraphicsRectItem(0, 0, ts, ts)
                rect.setPos(px, py)
                rect.setBrush(fill)
                rect.setPen(QPen(border, 1))
                rect.setToolTip(tooltip)
                rect.setParentItem(group)

        return group

    def _build_cell_flag_group(self, area: AreaDocument) -> QGraphicsItemGroup:
        group = QGraphicsItemGroup()
        ts = self._tile_size
        pen = QPen(_CELL_FLAG_BLOCKED_BORDER, 1)
        for row in range(area.height):
            for col in range(area.width):
                if cell_is_walkable(area, col, row):
                    continue
                rect = QGraphicsRectItem(0, 0, ts, ts)
                rect.setPos(col * ts, row * ts)
                rect.setBrush(_CELL_FLAG_BLOCKED_FILL)
                rect.setPen(pen)
                rect.setParentItem(group)
        return group

    def _build_grid_group(self, area: AreaDocument) -> QGraphicsItemGroup:
        group = QGraphicsItemGroup()
        ts = self._tile_size
        w = area.width
        h = area.height
        pen = QPen(_GRID_COLOR, 0)  # cosmetic pen (1px regardless of zoom)

        # Vertical lines
        for col in range(w + 1):
            line = self._scene.addLine(col * ts, 0, col * ts, h * ts, pen)
            line.setParentItem(group)
        # Horizontal lines
        for row in range(h + 1):
            line = self._scene.addLine(0, row * ts, w * ts, row * ts, pen)
            line.setParentItem(group)
        return group

    def _rebuild_cell_flag_group(self) -> None:
        if self._area is None:
            return
        if self._cell_flag_group is not None:
            self._scene.removeItem(self._cell_flag_group)
        self._cell_flag_group = self._build_cell_flag_group(self._area)
        self._cell_flag_group.setZValue(2500)
        self._cell_flag_group.setVisible(self._cell_flags_edit_mode)
        self._scene.addItem(self._cell_flag_group)

    def _handle_edit_pointer_event(
        self,
        event: QMouseEvent,
        button: Qt.MouseButton,
    ) -> bool:
        if self._area is None:
            return False

        # --- Cell-flag editing ---
        if self._cell_flags_edit_mode:
            if button not in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
                return False
            scene_pos = self.mapToScene(event.position().toPoint())
            col = int(scene_pos.x() / self._tile_size)
            row = int(scene_pos.y() / self._tile_size)
            if not (0 <= col < self._area.width and 0 <= row < self._area.height):
                return False
            walkable = button == Qt.MouseButton.LeftButton
            marker = (col, row, walkable)
            if self._last_painted == marker:
                return True
            self._last_painted = marker
            self.apply_cell_flag_brush(col, row, walkable)
            return True

        # --- Tile painting ---
        if self._tile_paint_mode:
            scene_pos = self.mapToScene(event.position().toPoint())
            col = int(scene_pos.x() / self._tile_size)
            row = int(scene_pos.y() / self._tile_size)
            if not (0 <= col < self._area.width and 0 <= row < self._area.height):
                return False

            # Eyedropper: Alt + left-click
            modifiers = event.modifiers()
            if (
                button == Qt.MouseButton.LeftButton
                and modifiers & Qt.KeyboardModifier.AltModifier
            ):
                gid = eyedrop_tile(self._area, self._active_layer, col, row)
                self.tile_eyedropped.emit(gid)
                return True

            if button == Qt.MouseButton.LeftButton:
                gid = self._selected_gid
            elif button == Qt.MouseButton.RightButton:
                gid = 0  # erase
            else:
                return False

            marker = (col, row, gid)
            if self._last_tile_painted == marker:
                return True
            self._last_tile_painted = marker

            if paint_tile(self._area, self._active_layer, col, row, gid):
                self._rebuild_tile_layer(self._active_layer)
                self.tile_painted.emit(self._active_layer, col, row, gid)
            return True

        return False

    def _update_drag_mode(self) -> None:
        editing = self._cell_flags_edit_mode or self._tile_paint_mode
        self.setDragMode(
            QGraphicsView.DragMode.NoDrag
            if editing
            else QGraphicsView.DragMode.ScrollHandDrag
        )

    # -- Tile layer rebuild after painting --------------------------------

    def _rebuild_tile_layer(self, layer_index: int) -> None:
        """Rebuild the graphics group for one tile layer after editing."""
        if (
            self._area is None
            or self._catalog is None
            or layer_index < 0
            or layer_index >= len(self._layer_groups)
        ):
            return

        old_group = self._layer_groups[layer_index]
        z = old_group.zValue()
        visible = old_group.isVisible()
        self._scene.removeItem(old_group)

        layer = self._area.tile_layers[layer_index]
        new_group = self._build_tile_layer_group(layer.grid, self._area, self._catalog)
        new_group.setZValue(z)
        new_group.setVisible(visible)
        self._scene.addItem(new_group)
        self._layer_groups[layer_index] = new_group

    # -- Ghost preview ----------------------------------------------------

    def _show_ghost(self, col: int, row: int) -> None:
        """Show a semi-transparent preview of the selected tile at (col, row)."""
        if self._catalog is None or self._area is None:
            return

        ts = self._tile_size
        px = col * ts
        py = row * ts

        if self._ghost_item is None:
            self._ghost_item = QGraphicsPixmapItem()
            self._ghost_item.setZValue(2999)
            self._ghost_item.setOpacity(0.5)
            self._scene.addItem(self._ghost_item)
            self._update_ghost_pixmap()

        self._ghost_item.setPos(px, py)
        self._ghost_item.setVisible(True)

    def _hide_ghost(self) -> None:
        if self._ghost_item is not None:
            self._ghost_item.setVisible(False)

    def _update_ghost_pixmap(self) -> None:
        """Update the ghost item's pixmap when the selected GID changes."""
        if self._ghost_item is None:
            return
        if self._catalog is None or self._area is None:
            return

        if self._selected_gid == 0:
            # Eraser: no ghost preview
            self._ghost_item.setVisible(False)
            return

        pm = self._catalog.get_tile_pixmap(
            self._selected_gid, self._area.tilesets, fallback_size=self._tile_size
        )
        if pm is not None:
            self._ghost_item.setPixmap(pm)
        else:
            self._ghost_item.setVisible(False)
