"""Zoomable, pannable tile-map canvas built on QGraphicsView.

Renders tile layers as composited pixmap items, entity markers as
coloured rectangles, and an optional grid overlay. Tile layers and
entity markers now share one unified render-order model so y-sorted tile
cells can interleave with entities the same way the runtime does.

Zoom:
    Mouse-wheel with anchor-under-mouse.  Range 0.25x .. 10x.
    ``SmoothPixmapTransform`` is disabled so pixel art stays crisp.

Pan:
    Middle-mouse drag (ScrollHandDrag mode).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
)

from area_editor.catalogs.template_catalog import TemplateCatalog
from area_editor.catalogs.tileset_catalog import TilesetCatalog
from area_editor.documents.area_document import AreaDocument, EntityDocument
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
_ENTITY_GHOST_FILL = QColor(0, 200, 220, 100)
_ENTITY_GHOST_BORDER = QColor(0, 200, 220, 180)
_ENTITY_SELECT_BORDER = QColor(255, 220, 40, 230)
_SCREEN_PANE_FILL = QColor(80, 60, 90, 40)
_SCREEN_PANE_BORDER = QColor(230, 120, 220, 210)
_SCREEN_PANE_LABEL = QColor(240, 220, 240)

# Grid overlay
_GRID_COLOR = QColor(255, 255, 255, 40)
_CELL_FLAG_BLOCKED_FILL = QColor(220, 40, 40, 90)
_CELL_FLAG_BLOCKED_BORDER = QColor(220, 40, 40, 180)

# Scene background
_BG_COLOR = QColor(30, 30, 30)
_SCENE_EDGE_PADDING = 32


@dataclass(slots=True)
class _CanvasRenderEntry:
    sort_key: tuple
    item: QGraphicsItem
    entity_id: str | None = None


class BrushType(str, Enum):
    TILE = "tile"
    ENTITY = "entity"
    ERASER = "eraser"


class TileCanvas(QGraphicsView):
    """Central widget: renders tile layers, entity markers, and grid."""

    # Signals for status-bar updates
    cell_hovered = Signal(int, int)       # (col, row) in tile coords
    screen_pixel_hovered = Signal(int, int)  # (px, py) in screen-space coords
    zoom_changed = Signal(float)          # current zoom factor
    cell_flag_edited = Signal(int, int, bool)
    tile_painted = Signal(int, int, int, int)  # (layer_idx, col, row, gid)
    tile_eyedropped = Signal(int)              # gid picked from canvas
    entity_paint_requested = Signal(str, int, int)
    entity_screen_paint_requested = Signal(str, int, int)
    entity_delete_requested = Signal(int, int)
    entity_selection_changed = Signal(str, int, int)  # entity_id, position, total

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
        self._display_width: int = 320
        self._display_height: int = 240
        self._area: AreaDocument | None = None
        self._catalog: TilesetCatalog | None = None
        self._templates: TemplateCatalog | None = None
        self._layer_items: list[list[QGraphicsItem]] = []
        self._entity_items: list[QGraphicsItem] = []
        self._layer_visibility: list[bool] = []
        self._entities_visible: bool = True
        self._cell_flag_group: QGraphicsItemGroup | None = None
        self._grid_group: QGraphicsItemGroup | None = None
        self._screen_pane_group: QGraphicsItemGroup | None = None
        self._ghost_item: QGraphicsPixmapItem | None = None
        self._grid_visible: bool = True
        self._cell_flags_edit_mode: bool = False
        self._tile_paint_mode: bool = False
        self._select_mode: bool = False
        self._active_brush_type: BrushType = BrushType.ERASER
        self._active_layer: int = 0
        self._selected_gid: int = 0
        self._tileset_index_hint: int = 0
        self._brush_erase_mode: bool = True
        self._entity_brush_template: str | None = None
        self._entity_brush_supported: bool = False
        self._entity_brush_space: str = "world"
        self._entity_ghost_pixmap: QPixmap | None = None
        self._selected_entity_id: str | None = None
        self._selected_entity_cycle_position: int = 0
        self._selected_entity_cycle_total: int = 0
        self._selection_cycle_cell: tuple[int, int] | None = None
        self._selection_cycle_ids: tuple[str, ...] = ()
        self._screen_selection_cycle_ids: tuple[str, ...] = ()
        self._last_painted: tuple[int, int, bool] | None = None
        self._last_tile_painted: tuple[int, int, int] | None = None
        self._last_entity_painted: tuple[str, int, int] | None = None
        self._last_entity_deleted: tuple[int, int] | None = None
        self._entity_item_by_id: dict[str, QGraphicsItem] = {}
        self._selection_item: QGraphicsRectItem | None = None
        self._middle_pan_pos = None
        self._screen_pane_origin: tuple[int, int] = (16, 0)
        self._screen_pane_size: tuple[int, int] = (self._display_width, self._display_height)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_area(
        self,
        area: AreaDocument,
        catalog: TilesetCatalog,
        templates: TemplateCatalog | None = None,
        *,
        display_size: tuple[int, int] | None = None,
    ) -> None:
        """Populate the scene from an area document."""
        previous_layer_visibility = list(self._layer_visibility)
        previous_entities_visible = self._entities_visible
        self._clear_scene_contents()
        self._area = area
        self._catalog = catalog
        self._templates = templates
        self._layer_items = [[] for _ in area.tile_layers]
        self._entity_items = []
        self._entity_item_by_id = {}
        if len(previous_layer_visibility) == len(area.tile_layers):
            self._layer_visibility = previous_layer_visibility
        else:
            self._layer_visibility = [True for _ in area.tile_layers]
        self._entities_visible = previous_entities_visible
        self._cell_flag_group = None
        self._grid_group = None
        self._ghost_item = None
        self._selection_item = None
        self._tileset_index_hint = 0
        self._brush_erase_mode = True
        self._last_entity_painted = None
        self._last_entity_deleted = None
        self._tile_size = area.tile_size or 16
        if display_size is not None:
            self._display_width = max(1, int(display_size[0]))
            self._display_height = max(1, int(display_size[1]))
        self._recompute_scene_layout()
        self._rebuild_scene_contents()
        self._update_drag_mode()

    def clear_area(self) -> None:
        """Remove all items from the scene."""
        self._scene.clear()
        self._area = None
        self._catalog = None
        self._templates = None
        self._layer_items.clear()
        self._entity_items.clear()
        self._entity_item_by_id.clear()
        self._layer_visibility.clear()
        self._entities_visible = True
        self._cell_flag_group = None
        self._grid_group = None
        self._screen_pane_group = None
        self._ghost_item = None
        self._selection_item = None
        self._screen_selection_cycle_ids = ()

    def refresh_scene_contents(self) -> None:
        """Redraw the current area without reinitialising editor state."""
        if self._area is None or self._catalog is None:
            return
        self._recompute_scene_layout()
        self._rebuild_scene_contents()

    def _recompute_scene_layout(self) -> None:
        """Recalculate scene extents and screen-pane placement from current area size."""
        if self._area is None:
            return
        width_px = self._area.width * self._tile_size
        height_px = self._area.height * self._tile_size
        gap = self._tile_size
        screen_x = max(width_px, 0) + gap
        self._screen_pane_origin = (screen_x, 0)
        self._screen_pane_size = (self._display_width, self._display_height)
        scene_w = max(screen_x + self._display_width, 1)
        scene_h = max(height_px, self._display_height, 1)
        pad = float(_SCENE_EDGE_PADDING)
        self._scene.setSceneRect(QRectF(-pad, -pad, scene_w + (pad * 2.0), scene_h + (pad * 2.0)))

    # -- Layer visibility ------------------------------------------------

    def set_layer_visible(self, index: int, visible: bool) -> None:
        """Show or hide the tile-layer group at *index*."""
        if 0 <= index < len(self._layer_items):
            self._layer_visibility[index] = visible
            for item in self._layer_items[index]:
                item.setVisible(visible)

    def set_entities_visible(self, visible: bool) -> None:
        self._entities_visible = visible
        for item in self._entity_items:
            item.setVisible(visible)

    def set_grid_visible(self, visible: bool) -> None:
        self._grid_visible = visible
        if self._grid_group is not None:
            self._grid_group.setVisible(visible)

    def set_cell_flags_edit_mode(self, enabled: bool) -> None:
        self._cell_flags_edit_mode = enabled
        if self._cell_flag_group is not None:
            self._cell_flag_group.setVisible(enabled)
        self._apply_cursor()
        self._update_drag_mode()
        self._last_painted = None

    @property
    def cell_flags_edit_mode(self) -> bool:
        return self._cell_flags_edit_mode

    # -- Tile paint mode -------------------------------------------------

    def set_tile_paint_mode(self, enabled: bool) -> None:
        self._tile_paint_mode = enabled
        self._apply_cursor()
        self._update_drag_mode()
        self._last_tile_painted = None
        self._last_entity_painted = None
        self._last_entity_deleted = None
        # Remove ghost when leaving paint mode
        if not enabled and self._ghost_item is not None:
            self._scene.removeItem(self._ghost_item)
            self._ghost_item = None
        elif enabled:
            self._update_ghost_pixmap()

    @property
    def tile_paint_mode(self) -> bool:
        return self._tile_paint_mode

    def set_select_mode(self, enabled: bool) -> None:
        self._select_mode = enabled
        self._apply_cursor()
        self._update_drag_mode()
        if enabled:
            self._hide_ghost()

    @property
    def select_mode(self) -> bool:
        return self._select_mode

    @property
    def active_layer(self) -> int:
        return self._active_layer

    def set_active_layer(self, index: int) -> None:
        self._active_layer = index

    @property
    def selected_gid(self) -> int:
        return self._selected_gid

    def set_selected_gid(self, gid: int) -> None:
        self._selected_gid = gid
        if gid != 0:
            self._brush_erase_mode = False
        self._update_ghost_pixmap()

    @property
    def tileset_index_hint(self) -> int:
        return self._tileset_index_hint

    def set_tileset_index_hint(self, index: int) -> None:
        self._tileset_index_hint = max(index, 0)

    @property
    def brush_erase_mode(self) -> bool:
        return self._brush_erase_mode

    def set_brush_erase_mode(self, enabled: bool) -> None:
        self._brush_erase_mode = enabled
        if enabled:
            self._active_brush_type = BrushType.ERASER
        self._update_ghost_pixmap()

    @property
    def active_brush_type(self) -> BrushType:
        return self._active_brush_type

    @property
    def entity_brush_template(self) -> str | None:
        return self._entity_brush_template

    @property
    def entity_brush_supported(self) -> bool:
        return self._entity_brush_supported

    @property
    def selected_entity_id(self) -> str | None:
        return self._selected_entity_id

    @property
    def selected_entity_cycle_position(self) -> int:
        return self._selected_entity_cycle_position

    @property
    def selected_entity_cycle_total(self) -> int:
        return self._selected_entity_cycle_total

    def set_active_brush_type(self, brush_type: BrushType) -> None:
        self._active_brush_type = brush_type
        self._last_tile_painted = None
        self._last_entity_painted = None
        self._last_entity_deleted = None
        self._update_ghost_pixmap()

    def set_entity_brush(
        self,
        template_id: str,
        ghost_pixmap: QPixmap | None,
        *,
        supported: bool,
        target_space: str = "world",
    ) -> None:
        self._entity_brush_template = template_id
        self._entity_ghost_pixmap = ghost_pixmap
        self._entity_brush_supported = supported
        self._entity_brush_space = target_space
        self._update_ghost_pixmap()

    def clear_entity_brush(self) -> None:
        self._entity_brush_template = None
        self._entity_ghost_pixmap = None
        self._entity_brush_supported = False
        self._entity_brush_space = "world"
        if self._active_brush_type == BrushType.ENTITY:
            self._active_brush_type = BrushType.ERASER if self._brush_erase_mode else BrushType.TILE
        self._update_ghost_pixmap()

    def set_selected_entity(
        self,
        entity_id: str | None,
        *,
        cycle_position: int = 0,
        cycle_total: int = 0,
        emit: bool = True,
    ) -> None:
        self._selected_entity_id = entity_id
        self._selected_entity_cycle_position = cycle_position if entity_id else 0
        self._selected_entity_cycle_total = cycle_total if entity_id else 0
        self._update_selection_highlight()
        if emit:
            self.entity_selection_changed.emit(
                entity_id or "",
                self._selected_entity_cycle_position,
                self._selected_entity_cycle_total,
            )

    def clear_selected_entity(self, *, emit: bool = True) -> None:
        self._selection_cycle_cell = None
        self._selection_cycle_ids = ()
        self._screen_selection_cycle_ids = ()
        self.set_selected_entity(None, emit=emit)

    def select_entities_at_cell(self, col: int, row: int) -> bool:
        if self._area is None:
            return False
        matches = self._world_entities_at_cell(col, row)
        ids = tuple(entity.id for entity in matches)
        if not ids:
            self.clear_selected_entity()
            return True

        if (
            self._selection_cycle_cell == (col, row)
            and self._selection_cycle_ids == ids
            and self._selected_entity_id in ids
        ):
            current_index = ids.index(self._selected_entity_id)
            next_index = (current_index + 1) % len(ids)
        else:
            next_index = 0

        self._selection_cycle_cell = (col, row)
        self._selection_cycle_ids = ids
        self._screen_selection_cycle_ids = ()
        self.set_selected_entity(
            ids[next_index],
            cycle_position=next_index + 1,
            cycle_total=len(ids),
        )
        return True

    def set_display_size(self, width: int, height: int) -> None:
        """Update the screen-pane reference size used for screen-space entities."""
        self._display_width = max(1, int(width))
        self._display_height = max(1, int(height))
        self._screen_pane_size = (self._display_width, self._display_height)
        if self._area is not None:
            self.set_area(
                self._area,
                self._catalog,
                self._templates,
                display_size=(self._display_width, self._display_height),
            )

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
        if event.button() == Qt.MouseButton.MiddleButton:
            self._middle_pan_pos = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if self._handle_edit_pointer_event(event, event.button()):
            event.accept()
            return
        if self._cell_flags_edit_mode or self._tile_paint_mode or self._select_mode:
            if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        scene_pos = self.mapToScene(event.position().toPoint())
        local_screen = self._screen_pixel_from_scene_pos(scene_pos.x(), scene_pos.y())
        if local_screen is not None:
            self.screen_pixel_hovered.emit(*local_screen)
        else:
            self.screen_pixel_hovered.emit(-1, -1)
            col = -1
            row = -1
            if self._tile_size > 0:
                col = int(scene_pos.x() / self._tile_size)
                row = int(scene_pos.y() / self._tile_size)
            self.cell_hovered.emit(col, row)

        if self._middle_pan_pos is not None:
            delta = event.position() - self._middle_pan_pos
            self._middle_pan_pos = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - int(delta.x())
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - int(delta.y())
            )
            event.accept()
            return

        # Update ghost preview position
        if self._tile_paint_mode and self._area is not None:
            if self._active_brush_type == BrushType.ENTITY and self._entity_brush_space == "screen":
                if local_screen is not None:
                    self._show_ghost_at_scene(
                        self._screen_pane_origin[0] + local_screen[0],
                        self._screen_pane_origin[1] + local_screen[1],
                    )
                else:
                    self._hide_ghost()
            else:
                col = int(scene_pos.x() / self._tile_size) if self._tile_size > 0 else -1
                row = int(scene_pos.y() / self._tile_size) if self._tile_size > 0 else -1
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
        if self._cell_flags_edit_mode or self._tile_paint_mode or self._select_mode:
            if buttons & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton):
                event.accept()
                return
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hide_ghost()
        self.cell_hovered.emit(-1, -1)
        self.screen_pixel_hovered.emit(-1, -1)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton and self._middle_pan_pos is not None:
            self._middle_pan_pos = None
            self._apply_cursor()
            event.accept()
            return
        self._last_painted = None
        self._last_tile_painted = None
        self._last_entity_painted = None
        self._last_entity_deleted = None
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

    def _build_tile_cell_item(
        self,
        gid: int,
        *,
        col_idx: int,
        row_idx: int,
        area: AreaDocument,
        catalog: TilesetCatalog,
    ) -> QGraphicsPixmapItem | None:
        pm = catalog.get_tile_pixmap(gid, area.tilesets, fallback_size=self._tile_size)
        if pm is None:
            return None
        item = QGraphicsPixmapItem(pm)
        item.setPos(col_idx * self._tile_size, row_idx * self._tile_size)
        return item

    def _build_entity_items(
        self,
        area: AreaDocument,
        catalog: TilesetCatalog,
        templates: TemplateCatalog | None,
    ) -> list[_CanvasRenderEntry]:
        items: list[_CanvasRenderEntry] = []
        ts = self._tile_size

        for entity in area.entities:
            if self._effective_space(entity) == "screen":
                px = self._screen_pane_origin[0] + (entity.pixel_x or 0)
                py = self._screen_pane_origin[1] + (entity.pixel_y or 0)
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
                visual = templates.get_first_visual(
                    entity.template,
                    entity.parameters or {},
                )
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
                        items.append(
                            _CanvasRenderEntry(
                                self._entity_sort_key(entity, px=px, py=py, tile_size=ts),
                                sprite_item,
                                entity.id,
                            )
                        )
                        sprite_rendered = True

            # Fallback: coloured rectangle marker when no sprite available
            if not sprite_rendered:
                rect = QGraphicsRectItem(0, 0, ts, ts)
                rect.setPos(px, py)
                rect.setBrush(fill)
                rect.setPen(QPen(border, 1))
                rect.setToolTip(tooltip)
                items.append(
                    _CanvasRenderEntry(
                        self._entity_sort_key(entity, px=px, py=py, tile_size=ts),
                        rect,
                        entity.id,
                    )
                )

        return items

    def _build_screen_pane_group(self) -> QGraphicsItemGroup:
        group = QGraphicsItemGroup()
        screen_x, screen_y = self._screen_pane_origin
        screen_w, screen_h = self._screen_pane_size
        rect = QGraphicsRectItem(0, 0, screen_w, screen_h)
        border = QPen(_SCREEN_PANE_BORDER, 1, Qt.PenStyle.DashLine)
        rect.setPos(screen_x, screen_y)
        rect.setBrush(_SCREEN_PANE_FILL)
        rect.setPen(border)
        rect.setParentItem(group)

        label = QGraphicsSimpleTextItem(f"Screen ({screen_w}x{screen_h})")
        label.setBrush(_SCREEN_PANE_LABEL)
        label.setPos(screen_x + 6, screen_y + 4)
        label.setParentItem(group)
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

    def _tile_layer_sort_key(self, layer, *, layer_index: int) -> tuple:
        return (layer.render_order, 0, 0.0, layer.stack_order, 0, layer_index, layer.name)

    def _tile_cell_sort_key(self, layer, *, layer_index: int, grid_x: int, grid_y: int) -> tuple:
        sort_y = ((grid_y + 1) * self._tile_size) + float(layer.sort_y_offset)
        return (layer.render_order, 1, sort_y, layer.stack_order, 0, grid_x, f"{layer_index}:{grid_y}:{grid_x}")

    def _entity_sort_key(self, entity, *, px: float, py: float, tile_size: int) -> tuple:
        if entity.y_sort:
            sort_bucket = 1
            sort_y = float(py + tile_size + entity.sort_y_offset)
        else:
            sort_bucket = 0
            sort_y = 0.0
        return (
            entity.render_order,
            sort_bucket,
            sort_y,
            entity.stack_order,
            1,
            px,
            entity.id,
        )

    def _rebuild_scene_contents(self) -> None:
        if self._area is None or self._catalog is None:
            return

        self._clear_scene_contents()
        self._layer_items = [[] for _ in self._area.tile_layers]
        self._entity_items = []
        self._entity_item_by_id = {}
        self._cell_flag_group = None
        self._grid_group = None
        self._screen_pane_group = None
        self._ghost_item = None
        self._selection_item = None

        render_entries: list[_CanvasRenderEntry] = []
        for layer_index, layer in enumerate(self._area.tile_layers):
            if layer.y_sort:
                for row_idx, row in enumerate(layer.grid):
                    for col_idx, gid in enumerate(row):
                        if gid == 0:
                            continue
                        item = self._build_tile_cell_item(
                            gid,
                            col_idx=col_idx,
                            row_idx=row_idx,
                            area=self._area,
                            catalog=self._catalog,
                        )
                        if item is None:
                            continue
                        self._layer_items[layer_index].append(item)
                        render_entries.append(
                            _CanvasRenderEntry(
                                self._tile_cell_sort_key(
                                    layer,
                                    layer_index=layer_index,
                                    grid_x=col_idx,
                                    grid_y=row_idx,
                                ),
                                item,
                            )
                        )
                continue

            group = self._build_tile_layer_group(layer.grid, self._area, self._catalog)
            self._layer_items[layer_index].append(group)
            render_entries.append(
                _CanvasRenderEntry(
                    self._tile_layer_sort_key(layer, layer_index=layer_index),
                    group,
                )
            )

        for entry in self._build_entity_items(self._area, self._catalog, self._templates):
            self._entity_items.append(entry.item)
            render_entries.append(entry)

        for z_index, entry in enumerate(sorted(render_entries, key=lambda item: item.sort_key)):
            entry.item.setZValue(float(z_index))
            self._scene.addItem(entry.item)
            if entry.entity_id is not None:
                self._entity_item_by_id[entry.entity_id] = entry.item

        for layer_index, items in enumerate(self._layer_items):
            visible = self._layer_visibility[layer_index] if layer_index < len(self._layer_visibility) else True
            for item in items:
                item.setVisible(visible)
        for item in self._entity_items:
            item.setVisible(self._entities_visible)

        self._screen_pane_group = self._build_screen_pane_group()
        self._screen_pane_group.setZValue(-100.0)
        self._scene.addItem(self._screen_pane_group)

        overlay_base = float(len(render_entries) + 100)
        self._cell_flag_group = self._build_cell_flag_group(self._area)
        self._cell_flag_group.setZValue(overlay_base)
        self._cell_flag_group.setVisible(self._cell_flags_edit_mode)
        self._scene.addItem(self._cell_flag_group)

        self._grid_group = self._build_grid_group(self._area)
        self._grid_group.setZValue(overlay_base + 100.0)
        self._grid_group.setVisible(self._grid_visible)
        self._scene.addItem(self._grid_group)
        self._update_selection_highlight()

    def _clear_scene_contents(self) -> None:
        """Remove tracked render items without resetting the whole scene object."""
        for items in self._layer_items:
            for item in items:
                if item.scene() is self._scene:
                    self._scene.removeItem(item)
        for item in self._entity_items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        for overlay in (
            self._cell_flag_group,
            self._grid_group,
            self._screen_pane_group,
            self._ghost_item,
            self._selection_item,
        ):
            if overlay is not None and overlay.scene() is self._scene:
                self._scene.removeItem(overlay)

    def _rebuild_cell_flag_group(self) -> None:
        if self._area is None:
            return
        if self._cell_flag_group is not None:
            self._scene.removeItem(self._cell_flag_group)
        self._cell_flag_group = self._build_cell_flag_group(self._area)
        self._cell_flag_group.setZValue(float(len(self._scene.items()) + 50))
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

        # --- Entity selection ---
        if self._select_mode:
            if button != Qt.MouseButton.LeftButton:
                return False
            scene_pos = self.mapToScene(event.position().toPoint())
            screen_matches = self._screen_entities_at_scene_pos(scene_pos.x(), scene_pos.y())
            if screen_matches:
                return self._select_screen_entity_cycle(screen_matches)
            col = int(scene_pos.x() / self._tile_size)
            row = int(scene_pos.y() / self._tile_size)
            if not (0 <= col < self._area.width and 0 <= row < self._area.height):
                self.clear_selected_entity()
                return True
            return self.select_entities_at_cell(col, row)

        # --- Unified paint tool ---
        if self._tile_paint_mode:
            scene_pos = self.mapToScene(event.position().toPoint())
            local_screen = self._screen_pixel_from_scene_pos(scene_pos.x(), scene_pos.y())
            col = int(scene_pos.x() / self._tile_size)
            row = int(scene_pos.y() / self._tile_size)

            if self._active_brush_type == BrushType.ENTITY:
                if self._entity_brush_template is None or not self._entity_brush_supported:
                    return True
                if self._entity_brush_space == "screen":
                    if local_screen is None:
                        return True
                    if button == Qt.MouseButton.LeftButton:
                        self.entity_screen_paint_requested.emit(
                            self._entity_brush_template,
                            local_screen[0],
                            local_screen[1],
                        )
                        return True
                    return True
            if not (0 <= col < self._area.width and 0 <= row < self._area.height):
                if local_screen is not None:
                    return True
                return False

            if self._active_brush_type == BrushType.ENTITY:
                if button == Qt.MouseButton.LeftButton:
                    marker = (self._entity_brush_template, col, row)
                    if self._last_entity_painted == marker:
                        return True
                    self._last_entity_painted = marker
                    self.entity_paint_requested.emit(self._entity_brush_template, col, row)
                    return True
                if button == Qt.MouseButton.RightButton:
                    marker = (col, row)
                    if self._last_entity_deleted == marker:
                        return True
                    self._last_entity_deleted = marker
                    self.entity_delete_requested.emit(col, row)
                    return True
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
                self._rebuild_scene_contents()
                self.tile_painted.emit(self._active_layer, col, row, gid)
            return True

        return False

    def _update_drag_mode(self) -> None:
        editing = self._cell_flags_edit_mode or self._tile_paint_mode or self._select_mode
        self.setDragMode(
            QGraphicsView.DragMode.NoDrag
            if editing
            else QGraphicsView.DragMode.ScrollHandDrag
        )

    def _apply_cursor(self) -> None:
        cursor = (
            Qt.CursorShape.CrossCursor
            if self._cell_flags_edit_mode or self._tile_paint_mode
            else Qt.CursorShape.ArrowCursor
        )
        self.setCursor(cursor)
        self.viewport().setCursor(cursor)

    def _update_selection_highlight(self) -> None:
        if self._selection_item is not None and self._selection_item.scene() is self._scene:
            self._scene.removeItem(self._selection_item)
        self._selection_item = None

        if self._selected_entity_id is None:
            return

        item = self._entity_item_by_id.get(self._selected_entity_id)
        if item is None or item.scene() is not self._scene:
            self._selected_entity_id = None
            self._selected_entity_cycle_position = 0
            self._selected_entity_cycle_total = 0
            return

        rect = item.sceneBoundingRect().adjusted(-1.0, -1.0, 1.0, 1.0)
        highlight = QGraphicsRectItem(rect)
        highlight.setPen(QPen(_ENTITY_SELECT_BORDER, 2))
        highlight.setBrush(Qt.BrushStyle.NoBrush)
        highlight.setZValue(float(len(self._scene.items()) + 300))
        self._selection_item = highlight
        self._scene.addItem(highlight)

    def _effective_space(self, entity: EntityDocument) -> str:
        """Resolve one entity's effective space with template fallback."""
        if entity.space != "world":
            return entity.space
        if entity.template and self._templates is not None:
            template_space = self._templates.get_template_space(entity.template)
            if template_space is not None:
                return template_space
        return entity.space

    def _world_entities_at_cell(self, col: int, row: int) -> list[EntityDocument]:
        """Return world-space entities at one cell, ordered topmost-first."""
        if self._area is None:
            return []
        matches = [
            entity
            for entity in self._area.entities
            if self._effective_space(entity) != "screen" and entity.x == col and entity.y == row
        ]
        return sorted(
            matches,
            key=lambda entity: float(
                self._entity_item_by_id[entity.id].zValue()
            ) if entity.id in self._entity_item_by_id else -1.0,
            reverse=True,
        )

    def _screen_pixel_from_scene_pos(self, sx: float, sy: float) -> tuple[int, int] | None:
        """Return screen-pane-local pixel coordinates for one scene position."""
        pane_x, pane_y = self._screen_pane_origin
        pane_w, pane_h = self._screen_pane_size
        if pane_x <= sx < pane_x + pane_w and pane_y <= sy < pane_y + pane_h:
            return int(sx - pane_x), int(sy - pane_y)
        return None

    def _screen_entities_at_scene_pos(self, sx: float, sy: float) -> list[str]:
        """Return screen-space entity ids whose rendered items contain one scene point."""
        if self._area is None:
            return []
        point = QPointF(sx, sy)
        hits: list[tuple[float, str]] = []
        for entity in self._area.entities:
            if self._effective_space(entity) != "screen":
                continue
            item = self._entity_item_by_id.get(entity.id)
            if item is None:
                continue
            if item.sceneBoundingRect().contains(point):
                hits.append((float(item.zValue()), entity.id))
        hits.sort(reverse=True)
        return [entity_id for _z_value, entity_id in hits]

    def _select_screen_entity_cycle(self, matches: list[str]) -> bool:
        """Cycle through screen-space entities under the current click point."""
        ids = tuple(matches)
        self._selection_cycle_cell = None
        self._selection_cycle_ids = ()
        if (
            self._screen_selection_cycle_ids == ids
            and self._selected_entity_id in ids
        ):
            current_index = ids.index(self._selected_entity_id)
            next_index = (current_index + 1) % len(ids)
        else:
            next_index = 0
        self._screen_selection_cycle_ids = ids
        self.set_selected_entity(
            ids[next_index],
            cycle_position=next_index + 1,
            cycle_total=len(ids),
        )
        return True

    # -- Tile layer rebuild after painting --------------------------------

    def _rebuild_tile_layer(self, layer_index: int) -> None:
        """Rebuild the canvas render items after tile edits."""
        if self._area is None or self._catalog is None or layer_index < 0:
            return
        self._rebuild_scene_contents()

    # -- Ghost preview ----------------------------------------------------

    def _show_ghost(self, col: int, row: int) -> None:
        """Show a semi-transparent preview of the active brush at (col, row)."""
        if self._area is None:
            return

        ts = self._tile_size
        px = col * ts
        py = row * ts

        if self._ghost_item is None:
            self._ghost_item = QGraphicsPixmapItem()
            self._ghost_item.setZValue(float(len(self._scene.items()) + 100))
            self._ghost_item.setOpacity(0.5)
            self._scene.addItem(self._ghost_item)
            self._update_ghost_pixmap()

        self._ghost_item.setPos(px, py)
        self._ghost_item.setVisible(not self._ghost_item.pixmap().isNull())

    def _show_ghost_at_scene(self, px: int, py: int) -> None:
        if self._ghost_item is None:
            self._ghost_item = QGraphicsPixmapItem()
            self._ghost_item.setZValue(float(len(self._scene.items()) + 100))
            self._ghost_item.setOpacity(0.5)
            self._scene.addItem(self._ghost_item)
            self._update_ghost_pixmap()
        self._ghost_item.setPos(px, py)
        self._ghost_item.setVisible(not self._ghost_item.pixmap().isNull())

    def _hide_ghost(self) -> None:
        if self._ghost_item is not None:
            self._ghost_item.setVisible(False)

    def _update_ghost_pixmap(self) -> None:
        """Update the ghost item's pixmap when the active brush changes."""
        if self._ghost_item is None:
            return
        if self._area is None:
            return

        if self._active_brush_type == BrushType.ERASER:
            self._ghost_item.setVisible(False)
            return

        if self._active_brush_type == BrushType.ENTITY:
            if not self._entity_brush_supported:
                self._ghost_item.setVisible(False)
                return
            if self._entity_ghost_pixmap is not None and not self._entity_ghost_pixmap.isNull():
                self._ghost_item.setPixmap(self._entity_ghost_pixmap)
                return
            placeholder = QPixmap(self._tile_size, self._tile_size)
            placeholder.fill(Qt.GlobalColor.transparent)
            painter = QPainter(placeholder)
            painter.setPen(QPen(_ENTITY_GHOST_BORDER, 1))
            painter.setBrush(_ENTITY_GHOST_FILL)
            painter.drawRect(0, 0, self._tile_size - 1, self._tile_size - 1)
            painter.end()
            self._ghost_item.setPixmap(placeholder)
            return

        if self._catalog is None or self._selected_gid == 0:
            self._ghost_item.setVisible(False)
            return

        pm = self._catalog.get_tile_pixmap(
            self._selected_gid, self._area.tilesets, fallback_size=self._tile_size
        )
        if pm is not None:
            self._ghost_item.setPixmap(pm)
        else:
            self._ghost_item.setVisible(False)
