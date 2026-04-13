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

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap, QTransform, QWheelEvent
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
from area_editor.operations.cell_flags import (
    CellFlagBrush,
    apply_cell_flag_brush,
    cell_is_blocked,
    clear_cell_flag_for_brush,
)
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
_ENTITY_HIDDEN_FILL = QColor(180, 180, 180, 70)
_ENTITY_HIDDEN_BORDER = QColor(220, 220, 220, 180)
_ENTITY_GHOST_FILL = QColor(0, 200, 220, 100)
_ENTITY_GHOST_BORDER = QColor(0, 200, 220, 180)
_ENTITY_SELECT_BORDER = QColor(255, 220, 40, 230)
_ENTITY_COUNT_BADGE_FILL = QColor(20, 20, 20, 190)
_ENTITY_COUNT_BADGE_BORDER = QColor(250, 250, 250, 190)
_ENTITY_COUNT_BADGE_TEXT = QColor(255, 255, 255)
_SCREEN_PANE_FILL = QColor(80, 60, 90, 40)
_SCREEN_PANE_BORDER = QColor(230, 120, 220, 210)
_SCREEN_PANE_LABEL = QColor(240, 220, 240)

# Grid overlay
_GRID_COLOR = QColor(255, 255, 255, 40)
_CELL_FLAG_BLOCKED_FILL = QColor(220, 40, 40, 90)
_CELL_FLAG_BLOCKED_BORDER = QColor(220, 40, 40, 180)
_TILE_SELECTION_FILL = QColor(80, 160, 255, 45)
_TILE_SELECTION_BORDER = QColor(80, 160, 255, 220)
_ENTITY_DRAG_THRESHOLD_PIXELS = 4.0
_ENTITY_STACK_PICKER_HOVER_DELAY_MS = 500
_ENTITY_STACK_PICKER_HOVER_ENABLED = False

# Scene background
_BG_COLOR = QColor(30, 30, 30)
_SCENE_EDGE_PADDING = 32


@dataclass(slots=True)
class _CanvasRenderEntry:
    sort_key: tuple
    item: QGraphicsItem
    entity_id: str | None = None


@dataclass(slots=True)
class _EntityDragState:
    entity_id: str
    space: str
    press_view_pos: QPointF
    press_scene_pos: QPointF
    start_grid: tuple[int, int]
    start_pixel: tuple[int, int]
    current_grid: tuple[int, int]
    current_pixel: tuple[int, int]
    deferred_selection: bool = False
    active: bool = False


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
    cell_flag_edited = Signal(int, int, object)
    tile_painted = Signal(int, int, int, int)  # (layer_idx, col, row, gid)
    tile_eyedropped = Signal(int)              # gid picked from canvas
    entity_paint_requested = Signal(str, int, int)
    entity_screen_paint_requested = Signal(str, int, int)
    entity_delete_requested = Signal(int, int)
    entity_delete_by_id_requested = Signal(str)
    entity_selection_changed = Signal(str, int, int)  # entity_id, position, total
    entity_edit_requested = Signal(str)
    entity_context_menu_requested = Signal(object, object)  # entity_ids, global_pos
    entity_stack_picker_requested = Signal(object, object, str)  # entity_ids, global_pos, purpose
    entity_drag_committed = Signal(str, str, int, int)  # entity_id, space, x, y
    tile_selection_changed = Signal(bool)

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
        self._cell_flag_brush: CellFlagBrush = CellFlagBrush("blocked", True)
        self._cell_flag_erase_mode: bool = False
        self._tile_paint_mode: bool = False
        self._select_mode: bool = False
        self._tile_select_mode: bool = False
        self._active_brush_type: BrushType = BrushType.ERASER
        self._active_layer: int = 0
        self._selected_gid: int = 0
        self._selected_gid_block: tuple[tuple[int, ...], ...] | None = None
        self._tileset_index_hint: int = 0
        self._brush_erase_mode: bool = True
        self._entity_brush_template: str | None = None
        self._entity_brush_supported: bool = False
        self._entity_brush_space: str = "world"
        self._entity_brush_erase_mode: bool = False
        self._entity_ghost_pixmap: QPixmap | None = None
        self._selected_entity_id: str | None = None
        self._selected_entity_cycle_position: int = 0
        self._selected_entity_cycle_total: int = 0
        self._selection_cycle_cell: tuple[int, int] | None = None
        self._selection_cycle_ids: tuple[str, ...] = ()
        self._screen_selection_cycle_ids: tuple[str, ...] = ()
        self._last_painted: tuple[int, int, str, str] | None = None
        self._last_tile_painted: tuple[int, int, int] | None = None
        self._last_entity_painted: tuple[str, int, int] | None = None
        self._last_entity_deleted: object | None = None
        self._entity_item_by_id: dict[str, QGraphicsItem] = {}
        self._tile_sort_keys: list[tuple] = []
        self._selection_item: QGraphicsRectItem | None = None
        self._tile_selection_item: QGraphicsRectItem | None = None
        self._middle_pan_pos = None
        self._screen_pane_origin: tuple[int, int] = (16, 0)
        self._screen_pane_size: tuple[int, int] = (self._display_width, self._display_height)
        self._tile_selection_anchor: tuple[int, int] | None = None
        self._tile_selection_bounds: tuple[int, int, int, int] | None = None
        self._hover_tile_cell: tuple[int, int] | None = None
        self._entity_drag_state: _EntityDragState | None = None
        self._entity_stack_hover_timer = QTimer(self)
        self._entity_stack_hover_timer.setSingleShot(True)
        self._entity_stack_hover_timer.timeout.connect(
            self._emit_entity_stack_hover_request
        )
        self._entity_stack_hover_ids: tuple[str, ...] = ()
        self._entity_stack_hover_global_pos: QPoint | None = None
        self._entity_stack_hover_emitted_ids: tuple[str, ...] = ()

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
        self._tile_sort_keys = []
        if len(previous_layer_visibility) == len(area.tile_layers):
            self._layer_visibility = previous_layer_visibility
        else:
            self._layer_visibility = [True for _ in area.tile_layers]
        self._entities_visible = previous_entities_visible
        self._cell_flag_group = None
        self._grid_group = None
        self._ghost_item = None
        self._selection_item = None
        self._tile_selection_item = None
        self._tileset_index_hint = 0
        self._brush_erase_mode = True
        self._selected_gid_block = None
        self._last_entity_painted = None
        self._last_entity_deleted = None
        self._entity_drag_state = None
        self._cancel_entity_stack_hover(reset_emitted=True)
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
        self._tile_sort_keys.clear()
        self._layer_visibility.clear()
        self._entities_visible = True
        self._cell_flag_group = None
        self._grid_group = None
        self._screen_pane_group = None
        self._ghost_item = None
        self._selection_item = None
        self._tile_selection_item = None
        self._screen_selection_cycle_ids = ()
        self._tile_selection_anchor = None
        self._tile_selection_bounds = None
        self._hover_tile_cell = None
        self._selected_gid_block = None
        self._entity_drag_state = None
        self._cancel_entity_stack_hover(reset_emitted=True)

    def refresh_scene_contents(self) -> None:
        """Redraw the current area without reinitialising editor state."""
        if self._area is None or self._catalog is None:
            return
        self._sync_layer_visibility_state()
        self._recompute_scene_layout()
        self._rebuild_scene_contents()

    def refresh_entity_items(self) -> None:
        """Rebuild only entity items and z-ordering."""
        if self._area is None or self._catalog is None:
            return
        self._rebuild_entity_items_only()

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

    def _sync_layer_visibility_state(self) -> None:
        """Keep cached layer visibility aligned with the current area layer count."""
        if self._area is None:
            self._layer_visibility = []
            return
        expected = len(self._area.tile_layers)
        current = list(self._layer_visibility[:expected])
        if len(current) < expected:
            current.extend(True for _ in range(expected - len(current)))
        self._layer_visibility = current

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

    def set_cell_flag_brush(self, brush: CellFlagBrush) -> None:
        self._cell_flag_brush = brush
        self._last_painted = None

    @property
    def cell_flag_erase_mode(self) -> bool:
        return self._cell_flag_erase_mode

    def set_cell_flag_erase_mode(self, enabled: bool) -> None:
        self._cell_flag_erase_mode = enabled
        self._last_painted = None

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
        if not enabled:
            self._entity_drag_state = None
        self._select_mode = enabled
        self._apply_cursor()
        self._update_drag_mode()
        if enabled:
            self._hide_ghost()

    @property
    def select_mode(self) -> bool:
        return self._select_mode

    def set_tile_select_mode(self, enabled: bool) -> None:
        self._tile_select_mode = enabled
        self._apply_cursor()
        self._update_drag_mode()
        if enabled:
            self._hide_ghost()
        else:
            self._tile_selection_anchor = None

    @property
    def tile_select_mode(self) -> bool:
        return self._tile_select_mode

    @property
    def has_tile_selection(self) -> bool:
        return self._tile_selection_bounds is not None

    def tile_selection_bounds(self) -> tuple[int, int, int, int] | None:
        return self._tile_selection_bounds

    def set_tile_selection(
        self,
        start_col: int,
        start_row: int,
        end_col: int,
        end_row: int,
    ) -> bool:
        if self._area is None:
            return False
        normalized = self._normalize_tile_selection(start_col, start_row, end_col, end_row)
        if normalized is None:
            return False
        changed = normalized != self._tile_selection_bounds
        self._tile_selection_bounds = normalized
        self._update_tile_selection_overlay()
        if changed:
            self.tile_selection_changed.emit(True)
        return True

    def clear_tile_selection(self) -> bool:
        had_selection = self._tile_selection_bounds is not None
        self._tile_selection_anchor = None
        self._tile_selection_bounds = None
        self._update_tile_selection_overlay()
        if had_selection:
            self.tile_selection_changed.emit(False)
        return had_selection

    def selected_tile_block(self) -> list[list[int]] | None:
        if self._area is None or self._tile_selection_bounds is None:
            return None
        if not (0 <= self._active_layer < len(self._area.tile_layers)):
            return None
        left, top, right, bottom = self._tile_selection_bounds
        layer = self._area.tile_layers[self._active_layer]
        return [
            [int(layer.grid[row][col]) for col in range(left, right + 1)]
            for row in range(top, bottom + 1)
        ]

    def clear_selected_tiles(self) -> bool:
        if self._area is None or self._tile_selection_bounds is None:
            return False
        if not (0 <= self._active_layer < len(self._area.tile_layers)):
            return False
        left, top, right, bottom = self._tile_selection_bounds
        layer = self._area.tile_layers[self._active_layer]
        changed = False
        for row in range(top, bottom + 1):
            for col in range(left, right + 1):
                if layer.grid[row][col] != 0:
                    layer.grid[row][col] = 0
                    changed = True
        if changed:
            self.refresh_scene_contents()
        return changed

    def paste_tile_block(
        self,
        anchor_col: int,
        anchor_row: int,
        block: list[list[int]],
    ) -> tuple[int, int, int, int] | None:
        if self._area is None or not block or not block[0]:
            return None
        if not (0 <= self._active_layer < len(self._area.tile_layers)):
            return None
        layer = self._area.tile_layers[self._active_layer]
        changed = False
        pasted_left: int | None = None
        pasted_top: int | None = None
        pasted_right: int | None = None
        pasted_bottom: int | None = None
        for row_offset, row_values in enumerate(block):
            target_row = anchor_row + row_offset
            if not (0 <= target_row < self._area.height):
                continue
            for col_offset, gid in enumerate(row_values):
                target_col = anchor_col + col_offset
                if not (0 <= target_col < self._area.width):
                    continue
                if layer.grid[target_row][target_col] != gid:
                    layer.grid[target_row][target_col] = int(gid)
                    changed = True
                if pasted_left is None or target_col < pasted_left:
                    pasted_left = target_col
                if pasted_top is None or target_row < pasted_top:
                    pasted_top = target_row
                if pasted_right is None or target_col > pasted_right:
                    pasted_right = target_col
                if pasted_bottom is None or target_row > pasted_bottom:
                    pasted_bottom = target_row
        if pasted_left is None or pasted_top is None or pasted_right is None or pasted_bottom is None:
            return None
        if changed:
            self.refresh_scene_contents()
        self.set_tile_selection(pasted_left, pasted_top, pasted_right, pasted_bottom)
        return (pasted_left, pasted_top, pasted_right, pasted_bottom)

    def preferred_paste_anchor(self) -> tuple[int, int] | None:
        if self._hover_tile_cell is not None:
            return self._hover_tile_cell
        if self._tile_selection_bounds is not None:
            left, top, _right, _bottom = self._tile_selection_bounds
            return (left, top)
        return None

    @property
    def active_layer(self) -> int:
        return self._active_layer

    def set_active_layer(self, index: int) -> None:
        self._active_layer = index

    @property
    def selected_gid(self) -> int:
        return self._selected_gid

    @property
    def selected_gid_block(self) -> tuple[tuple[int, ...], ...] | None:
        return self._selected_gid_block

    def set_selected_gid(self, gid: int) -> None:
        self._selected_gid = gid
        self._selected_gid_block = ((gid,),) if gid != 0 else None
        if gid != 0:
            self._brush_erase_mode = False
        self._update_ghost_pixmap()

    def set_selected_gid_block(self, block: tuple[tuple[int, ...], ...] | None) -> None:
        normalized = self._normalize_gid_block(block)
        self._selected_gid_block = normalized
        if normalized is None:
            self._selected_gid = 0
        else:
            self._selected_gid = int(normalized[0][0])
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
    def entity_brush_erase_mode(self) -> bool:
        return self._entity_brush_erase_mode

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

    def set_entity_brush_erase_mode(self, enabled: bool) -> None:
        self._entity_brush_erase_mode = enabled
        self._last_entity_deleted = None
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

    def apply_cell_flag_brush(
        self,
        col: int,
        row: int,
        brush: CellFlagBrush | None = None,
        *,
        clear: bool = False,
    ) -> bool:
        """Apply the selected cell-flag brush directly to one cell."""
        if self._area is None:
            return False
        selected_brush = brush or self._cell_flag_brush
        if clear:
            changed = clear_cell_flag_for_brush(self._area, col, row, selected_brush)
        else:
            changed = apply_cell_flag_brush(self._area, col, row, selected_brush)
        if changed:
            self._rebuild_cell_flag_group()
            self.cell_flag_edited.emit(col, row, selected_brush)
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
        self._cancel_entity_stack_hover(reset_emitted=False)
        if event.button() == Qt.MouseButton.MiddleButton:
            self._middle_pan_pos = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if self._handle_edit_pointer_event(event, event.button()):
            event.accept()
            return
        if self._cell_flags_edit_mode or self._tile_paint_mode or self._select_mode or self._tile_select_mode:
            if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._cancel_entity_stack_hover(reset_emitted=False)
        if self._select_mode and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            ids = self._entity_ids_at_scene_pos(scene_pos)
            if ids:
                entity_id = self._selected_entity_id if self._selected_entity_id in ids else ids[0]
                index = ids.index(entity_id)
                self.set_selected_entity(
                    entity_id,
                    cycle_position=index + 1,
                    cycle_total=len(ids),
                )
                self.entity_edit_requested.emit(entity_id)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        scene_pos = self.mapToScene(event.position().toPoint())
        buttons = event.buttons()
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
            if self._area is not None and 0 <= col < self._area.width and 0 <= row < self._area.height:
                self._hover_tile_cell = (col, row)
            else:
                self._hover_tile_cell = None

        self._update_entity_stack_hover(
            scene_pos,
            event.globalPosition().toPoint(),
            buttons=buttons,
        )

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

        if buttons & Qt.MouseButton.LeftButton:
            if self._handle_edit_pointer_event(event, Qt.MouseButton.LeftButton):
                event.accept()
                return
        elif buttons & Qt.MouseButton.RightButton:
            if self._handle_edit_pointer_event(event, Qt.MouseButton.RightButton):
                event.accept()
                return
        if self._cell_flags_edit_mode or self._tile_paint_mode or self._select_mode or self._tile_select_mode:
            if buttons & (Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton):
                event.accept()
                return
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hide_ghost()
        self.cell_hovered.emit(-1, -1)
        self.screen_pixel_hovered.emit(-1, -1)
        self._hover_tile_cell = None
        self._cancel_entity_stack_hover(reset_emitted=True)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton and self._middle_pan_pos is not None:
            self._middle_pan_pos = None
            self._apply_cursor()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._finish_entity_drag(event):
            self._last_painted = None
            self._last_tile_painted = None
            self._last_entity_painted = None
            self._last_entity_deleted = None
            self._tile_selection_anchor = None
            event.accept()
            return
        self._last_painted = None
        self._last_tile_painted = None
        self._last_entity_painted = None
        self._last_entity_deleted = None
        if event.button() == Qt.MouseButton.LeftButton:
            self._tile_selection_anchor = None
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
        overlap_counts = self._entity_marker_overlap_counts(area)

        for entity in area.entities:
            overlap_key = self._entity_marker_overlap_key(entity)
            if overlap_key[0] == "screen":
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
            entity_visible = bool(entity._extra.get("visible", True))
            if not entity_visible:
                tooltip += "  [hidden]"

            group = QGraphicsItemGroup()

            marker = QGraphicsRectItem(0, 0, ts, ts)
            marker.setPos(px, py)
            marker.setBrush(fill if entity_visible else _ENTITY_HIDDEN_FILL)
            marker_pen = QPen(border if entity_visible else _ENTITY_HIDDEN_BORDER, 1)
            if not entity_visible:
                marker_pen.setStyle(Qt.PenStyle.DashLine)
            marker.setPen(marker_pen)
            marker.setToolTip(tooltip)
            group.addToGroup(marker)

            overlap_count = overlap_counts.get(overlap_key, 0)
            if overlap_count > 1:
                self._add_entity_overlap_badge(group, px, py, overlap_count)

            # Try to render the actual sprite from the template visual
            sprite_rendered = False
            if entity_visible and templates and entity.template:
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
                        if visual.flip_x:
                            sprite = sprite.transformed(QTransform().scale(-1, 1))
                        sprite_item = QGraphicsPixmapItem(sprite)
                        sprite_item.setPos(
                            px + visual.offset_x,
                            py + visual.offset_y,
                        )
                        sprite_item.setToolTip(tooltip)
                        group.addToGroup(sprite_item)
                        sprite_rendered = True

            # Keep an editor marker even when a sprite exists so placement remains obvious.
            _ = sprite_rendered
            items.append(
                _CanvasRenderEntry(
                    self._entity_sort_key(entity, px=px, py=py, tile_size=ts),
                    group,
                    entity.id,
                )
            )

        return items

    def _entity_marker_overlap_key(self, entity: EntityDocument) -> tuple[str, int, int]:
        if self._effective_space(entity) == "screen":
            return ("screen", int(entity.pixel_x or 0), int(entity.pixel_y or 0))
        return ("world", int(entity.x), int(entity.y))

    def _entity_marker_overlap_counts(
        self,
        area: AreaDocument,
    ) -> dict[tuple[str, int, int], int]:
        counts: dict[tuple[str, int, int], int] = {}
        for entity in area.entities:
            key = self._entity_marker_overlap_key(entity)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def _add_entity_overlap_badge(
        self,
        group: QGraphicsItemGroup,
        px: float,
        py: float,
        count: int,
    ) -> None:
        label = QGraphicsSimpleTextItem(str(count))
        font = label.font()
        font.setBold(True)
        font.setPointSizeF(7.0)
        label.setFont(font)
        label.setBrush(_ENTITY_COUNT_BADGE_TEXT)
        text_rect = label.boundingRect()

        badge_width = max(9.0, text_rect.width() + 4.0)
        badge_height = max(9.0, text_rect.height())
        badge = QGraphicsRectItem(0, 0, badge_width, badge_height)
        badge.setPos(px, py)
        badge.setBrush(_ENTITY_COUNT_BADGE_FILL)
        badge.setPen(QPen(_ENTITY_COUNT_BADGE_BORDER, 1))
        badge.setZValue(50.0)
        group.addToGroup(badge)

        label.setPos(px + 2.0, py)
        label.setToolTip(f"{count} entities")
        label.setZValue(51.0)
        group.addToGroup(label)

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
                if not cell_is_blocked(area, col, row):
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

        tile_entries: list[_CanvasRenderEntry] = []
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
                        tile_entries.append(
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
            tile_entries.append(
                _CanvasRenderEntry(
                    self._tile_layer_sort_key(layer, layer_index=layer_index),
                    group,
                )
            )

        sorted_tiles = sorted(tile_entries, key=lambda item: item.sort_key)
        self._tile_sort_keys = [entry.sort_key for entry in sorted_tiles]
        for z_index, entry in enumerate(sorted_tiles):
            entry.item.setZValue(float(z_index))
            self._scene.addItem(entry.item)

        self._apply_entity_entries(
            self._build_entity_items(self._area, self._catalog, self._templates)
        )

        for layer_index, items in enumerate(self._layer_items):
            visible = self._layer_visibility[layer_index] if layer_index < len(self._layer_visibility) else True
            for item in items:
                item.setVisible(visible)
        for item in self._entity_items:
            item.setVisible(self._entities_visible)

        self._screen_pane_group = self._build_screen_pane_group()
        self._screen_pane_group.setZValue(-100.0)
        self._scene.addItem(self._screen_pane_group)

        overlay_base = float(len(self._tile_sort_keys) + 100)
        self._cell_flag_group = self._build_cell_flag_group(self._area)
        self._cell_flag_group.setZValue(overlay_base)
        self._cell_flag_group.setVisible(self._cell_flags_edit_mode)
        self._scene.addItem(self._cell_flag_group)

        self._grid_group = self._build_grid_group(self._area)
        self._grid_group.setZValue(overlay_base + 100.0)
        self._grid_group.setVisible(self._grid_visible)
        self._scene.addItem(self._grid_group)
        self._update_selection_highlight()
        self._update_tile_selection_overlay()

    def _rebuild_entity_items_only(self) -> None:
        if self._area is None or self._catalog is None:
            return

        for item in self._entity_items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        self._entity_items = []
        self._entity_item_by_id = {}

        self._apply_entity_entries(
            self._build_entity_items(self._area, self._catalog, self._templates)
        )

        overlay_base = float(len(self._tile_sort_keys) + 100)
        if self._cell_flag_group is not None:
            self._cell_flag_group.setZValue(overlay_base)
        if self._grid_group is not None:
            self._grid_group.setZValue(overlay_base + 100.0)

        self._update_selection_highlight()
        self._update_tile_selection_overlay()

    def _apply_entity_entries(self, entries: list[_CanvasRenderEntry]) -> None:
        if self._area is None or self._catalog is None:
            return
        self._entity_items = []
        self._entity_item_by_id = {}

        entries_sorted = sorted(entries, key=lambda item: item.sort_key)
        if not self._tile_sort_keys:
            for z_index, entry in enumerate(entries_sorted):
                entry.item.setZValue(float(z_index))
                self._scene.addItem(entry.item)
                self._entity_items.append(entry.item)
                if entry.entity_id is not None:
                    self._entity_item_by_id[entry.entity_id] = entry.item
            for item in self._entity_items:
                item.setVisible(self._entities_visible)
            return

        from bisect import bisect_right

        grouped: dict[int, list[_CanvasRenderEntry]] = {}
        for entry in entries_sorted:
            index = bisect_right(self._tile_sort_keys, entry.sort_key)
            grouped.setdefault(index, []).append(entry)

        for index, group in grouped.items():
            count = len(group)
            base = float(index - 1)
            for offset_index, entry in enumerate(group, start=1):
                offset = offset_index / float(count + 1)
                entry.item.setZValue(base + offset)
                self._scene.addItem(entry.item)
                self._entity_items.append(entry.item)
                if entry.entity_id is not None:
                    self._entity_item_by_id[entry.entity_id] = entry.item

        for item in self._entity_items:
            item.setVisible(self._entities_visible)

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
            self._tile_selection_item,
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
            clear = button == Qt.MouseButton.RightButton or (
                button == Qt.MouseButton.LeftButton and self._cell_flag_erase_mode
            )
            marker = (col, row, self._cell_flag_brush.key, "clear" if clear else "paint")
            if self._last_painted == marker:
                return True
            self._last_painted = marker
            self.apply_cell_flag_brush(col, row, clear=clear)
            return True

        # --- Entity selection ---
        if self._select_mode:
            scene_pos = self.mapToScene(event.position().toPoint())
            if button == Qt.MouseButton.RightButton:
                self._cancel_entity_stack_hover(reset_emitted=False)
                if event.type() != QMouseEvent.Type.MouseButtonPress:
                    return False
                entity_ids = self._entity_ids_at_scene_pos(scene_pos)
                if not entity_ids:
                    return False
                self.entity_context_menu_requested.emit(
                    tuple(entity_ids),
                    event.globalPosition().toPoint(),
                )
                return True
            if button != Qt.MouseButton.LeftButton:
                return False
            if event.type() == QMouseEvent.Type.MouseMove:
                return self._update_entity_drag(event, scene_pos)
            if event.type() != QMouseEvent.Type.MouseButtonPress:
                return False
            self._entity_drag_state = None
            screen_matches = self._screen_entities_at_scene_pos(scene_pos.x(), scene_pos.y())
            if screen_matches:
                selected_id = self._selected_entity_id
                deferred = selected_id in screen_matches
                if deferred:
                    entity_id = selected_id or ""
                else:
                    self._select_screen_entity_cycle(screen_matches)
                    entity_id = self._selected_entity_id or ""
                self._start_entity_drag_candidate(
                    entity_id,
                    event.position(),
                    scene_pos,
                    deferred_selection=deferred,
                )
                return True
            col = int(scene_pos.x() / self._tile_size)
            row = int(scene_pos.y() / self._tile_size)
            if not (0 <= col < self._area.width and 0 <= row < self._area.height):
                self.clear_selected_entity()
                return True
            matches = self._world_entities_at_cell(col, row)
            ids = tuple(entity.id for entity in matches)
            if not ids:
                self.clear_selected_entity()
                return True
            selected_id = self._selected_entity_id
            deferred = selected_id in ids
            if deferred:
                entity_id = selected_id or ""
            else:
                self.select_entities_at_cell(col, row)
                entity_id = self._selected_entity_id or ""
            self._start_entity_drag_candidate(
                entity_id,
                event.position(),
                scene_pos,
                deferred_selection=deferred,
            )
            return True

        # --- Tile rectangle selection ---
        if self._tile_select_mode:
            if button != Qt.MouseButton.LeftButton:
                return False
            scene_pos = self.mapToScene(event.position().toPoint())
            if event.type() == QMouseEvent.Type.MouseButtonPress:
                tile_cell = self._tile_cell_from_scene_pos(scene_pos.x(), scene_pos.y(), clamp=False)
                if tile_cell is None:
                    self.clear_tile_selection()
                    return True
                self._tile_selection_anchor = tile_cell
                self.set_tile_selection(tile_cell[0], tile_cell[1], tile_cell[0], tile_cell[1])
                return True
            if event.type() == QMouseEvent.Type.MouseMove:
                if self._tile_selection_anchor is None:
                    return False
                tile_cell = self._tile_cell_from_scene_pos(scene_pos.x(), scene_pos.y(), clamp=True)
                if tile_cell is None:
                    return False
                self.set_tile_selection(
                    self._tile_selection_anchor[0],
                    self._tile_selection_anchor[1],
                    tile_cell[0],
                    tile_cell[1],
                )
                return True
            return False

        # --- Unified paint tool ---
        if self._tile_paint_mode:
            scene_pos = self.mapToScene(event.position().toPoint())
            local_screen = self._screen_pixel_from_scene_pos(scene_pos.x(), scene_pos.y())
            col = int(scene_pos.x() / self._tile_size)
            row = int(scene_pos.y() / self._tile_size)

            if self._active_brush_type == BrushType.ENTITY:
                if self._entity_brush_template is None or not self._entity_brush_supported:
                    return True
                if button == Qt.MouseButton.RightButton:
                    entity_ids = tuple(self._entity_ids_at_scene_pos(scene_pos))
                    if entity_ids:
                        self.entity_context_menu_requested.emit(
                            entity_ids,
                            event.globalPosition().toPoint(),
                        )
                        return True
                if self._entity_brush_space == "screen":
                    if local_screen is None:
                        return True
                    if button == Qt.MouseButton.LeftButton and not self._entity_brush_erase_mode:
                        self.entity_screen_paint_requested.emit(
                            self._entity_brush_template,
                            local_screen[0],
                            local_screen[1],
                        )
                        return True
                    if button == Qt.MouseButton.LeftButton and self._entity_brush_erase_mode:
                        entity_ids = tuple(self._entity_ids_at_scene_pos(scene_pos))
                        if len(entity_ids) > 1:
                            self.entity_stack_picker_requested.emit(
                                entity_ids,
                                event.globalPosition().toPoint(),
                                "delete",
                            )
                            return True
                        if len(entity_ids) == 1:
                            marker = ("delete-id", entity_ids[0])
                            if self._last_entity_deleted == marker:
                                return True
                            self._last_entity_deleted = marker
                            self.entity_delete_by_id_requested.emit(entity_ids[0])
                            return True
                    return True
            if not (0 <= col < self._area.width and 0 <= row < self._area.height):
                if local_screen is not None:
                    return True
                return False

            if self._active_brush_type == BrushType.ENTITY:
                if button == Qt.MouseButton.LeftButton and not self._entity_brush_erase_mode:
                    marker = (self._entity_brush_template, col, row)
                    if self._last_entity_painted == marker:
                        return True
                    self._last_entity_painted = marker
                    self.entity_paint_requested.emit(self._entity_brush_template, col, row)
                    return True
                if button == Qt.MouseButton.LeftButton and self._entity_brush_erase_mode:
                    entity_ids = tuple(self._entity_ids_at_scene_pos(scene_pos))
                    if len(entity_ids) > 1:
                        self.entity_stack_picker_requested.emit(
                            entity_ids,
                            event.globalPosition().toPoint(),
                            "delete",
                        )
                        return True
                    if len(entity_ids) == 1:
                        entity = self._entity_by_id(entity_ids[0])
                        if entity is not None and self._effective_space(entity) == "screen":
                            marker = ("delete-id", entity_ids[0])
                            if self._last_entity_deleted == marker:
                                return True
                            self._last_entity_deleted = marker
                            self.entity_delete_by_id_requested.emit(entity_ids[0])
                            return True
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

            if self._active_brush_type == BrushType.ERASER:
                block = ((0,),)
            elif button == Qt.MouseButton.LeftButton:
                block = self._selected_gid_block
                if block is None:
                    return True
            elif button == Qt.MouseButton.RightButton:
                block = ((0,),)
            else:
                return False

            marker = (col, row, block)
            if self._last_tile_painted == marker:
                return True
            self._last_tile_painted = marker

            painted = self._paint_tile_block(col, row, block)
            if painted:
                self._rebuild_scene_contents()
                self.tile_painted.emit(self._active_layer, col, row, int(block[0][0]))
            return True

        return False

    def _update_drag_mode(self) -> None:
        editing = (
            self._cell_flags_edit_mode
            or self._tile_paint_mode
            or self._select_mode
            or self._tile_select_mode
        )
        self.setDragMode(
            QGraphicsView.DragMode.NoDrag
            if editing
            else QGraphicsView.DragMode.ScrollHandDrag
        )

    def _apply_cursor(self) -> None:
        cursor = (
            Qt.CursorShape.CrossCursor
            if self._cell_flags_edit_mode or self._tile_paint_mode or self._tile_select_mode
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

    def _entity_by_id(self, entity_id: str) -> EntityDocument | None:
        if self._area is None:
            return None
        for entity in self._area.entities:
            if entity.id == entity_id:
                return entity
        return None

    def _start_entity_drag_candidate(
        self,
        entity_id: str,
        press_view_pos: QPointF,
        press_scene_pos: QPointF,
        *,
        deferred_selection: bool,
    ) -> bool:
        entity = self._entity_by_id(entity_id)
        if entity is None:
            return False
        effective_space = self._effective_space(entity)
        start_grid = (int(entity.x), int(entity.y))
        start_pixel = (int(entity.pixel_x or 0), int(entity.pixel_y or 0))
        self._entity_drag_state = _EntityDragState(
            entity_id=entity.id,
            space=effective_space,
            press_view_pos=QPointF(press_view_pos),
            press_scene_pos=QPointF(press_scene_pos),
            start_grid=start_grid,
            start_pixel=start_pixel,
            current_grid=start_grid,
            current_pixel=start_pixel,
            deferred_selection=deferred_selection,
        )
        return True

    def _update_entity_drag(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        state = self._entity_drag_state
        if state is None:
            return False
        entity = self._entity_by_id(state.entity_id)
        if entity is None:
            self._entity_drag_state = None
            return False

        if not state.active:
            view_delta = event.position() - state.press_view_pos
            distance = abs(view_delta.x()) + abs(view_delta.y())
            if distance < _ENTITY_DRAG_THRESHOLD_PIXELS:
                return True
            state.active = True
            self.viewport().setCursor(Qt.CursorShape.SizeAllCursor)

        changed = (
            self._drag_screen_entity(entity, state, scene_pos)
            if state.space == "screen"
            else self._drag_world_entity(entity, state, scene_pos)
        )
        if changed:
            self._selection_cycle_cell = None
            self._selection_cycle_ids = ()
            self._screen_selection_cycle_ids = ()
            self._rebuild_entity_items_only()
        return True

    def _drag_world_entity(
        self,
        entity: EntityDocument,
        state: _EntityDragState,
        scene_pos: QPointF,
    ) -> bool:
        tile_cell = self._tile_cell_from_scene_pos(scene_pos.x(), scene_pos.y(), clamp=True)
        if tile_cell is None or tile_cell == state.current_grid:
            return False
        entity.x = tile_cell[0]
        entity.y = tile_cell[1]
        state.current_grid = tile_cell
        return True

    def _drag_screen_entity(
        self,
        entity: EntityDocument,
        state: _EntityDragState,
        scene_pos: QPointF,
    ) -> bool:
        delta_x = int(round(scene_pos.x() - state.press_scene_pos.x()))
        delta_y = int(round(scene_pos.y() - state.press_scene_pos.y()))
        pixel = (
            state.start_pixel[0] + delta_x,
            state.start_pixel[1] + delta_y,
        )
        if pixel == state.current_pixel:
            return False
        entity.pixel_x = pixel[0]
        entity.pixel_y = pixel[1]
        state.current_pixel = pixel
        return True

    def _finish_entity_drag(self, event: QMouseEvent | None = None) -> bool:
        state = self._entity_drag_state
        if state is None:
            return False
        if event is not None:
            scene_pos = self.mapToScene(event.position().toPoint())
            self._update_entity_drag(event, scene_pos)
            state = self._entity_drag_state
            if state is None:
                self._apply_cursor()
                return True
        self._entity_drag_state = None
        self._apply_cursor()

        if state.active:
            if state.space == "screen":
                if state.current_pixel != state.start_pixel:
                    self.entity_drag_committed.emit(
                        state.entity_id,
                        state.space,
                        state.current_pixel[0],
                        state.current_pixel[1],
                    )
            elif state.current_grid != state.start_grid:
                self.entity_drag_committed.emit(
                    state.entity_id,
                    state.space,
                    state.current_grid[0],
                    state.current_grid[1],
                )
            return True

        if state.deferred_selection:
            if state.space == "screen":
                matches = self._screen_entities_at_scene_pos(
                    state.press_scene_pos.x(),
                    state.press_scene_pos.y(),
                )
                if matches:
                    return self._select_screen_entity_cycle(matches)
            tile_cell = self._tile_cell_from_scene_pos(
                state.press_scene_pos.x(),
                state.press_scene_pos.y(),
                clamp=False,
            )
            if tile_cell is not None:
                return self.select_entities_at_cell(tile_cell[0], tile_cell[1])
        return True

    def _update_tile_selection_overlay(self) -> None:
        if self._tile_selection_item is not None and self._tile_selection_item.scene() is self._scene:
            self._scene.removeItem(self._tile_selection_item)
        self._tile_selection_item = None

        if self._tile_selection_bounds is None or self._area is None:
            return

        left, top, right, bottom = self._tile_selection_bounds
        rect = QRectF(
            float(left * self._tile_size),
            float(top * self._tile_size),
            float((right - left + 1) * self._tile_size),
            float((bottom - top + 1) * self._tile_size),
        )
        highlight = QGraphicsRectItem(rect)
        highlight.setPen(QPen(_TILE_SELECTION_BORDER, 2))
        highlight.setBrush(_TILE_SELECTION_FILL)
        highlight.setZValue(float(len(self._scene.items()) + 400))
        self._tile_selection_item = highlight
        self._scene.addItem(highlight)

    def _normalize_tile_selection(
        self,
        start_col: int,
        start_row: int,
        end_col: int,
        end_row: int,
    ) -> tuple[int, int, int, int] | None:
        if self._area is None or self._area.width <= 0 or self._area.height <= 0:
            return None
        left = max(0, min(int(start_col), int(end_col)))
        top = max(0, min(int(start_row), int(end_row)))
        right = min(self._area.width - 1, max(int(start_col), int(end_col)))
        bottom = min(self._area.height - 1, max(int(start_row), int(end_row)))
        if left > right or top > bottom:
            return None
        return (left, top, right, bottom)

    def _tile_cell_from_scene_pos(
        self,
        sx: float,
        sy: float,
        *,
        clamp: bool,
    ) -> tuple[int, int] | None:
        if self._area is None or self._tile_size <= 0 or self._area.width <= 0 or self._area.height <= 0:
            return None
        col = int(sx / self._tile_size)
        row = int(sy / self._tile_size)
        if clamp:
            return (
                max(0, min(col, self._area.width - 1)),
                max(0, min(row, self._area.height - 1)),
            )
        if 0 <= col < self._area.width and 0 <= row < self._area.height:
            return (col, row)
        return None

    def _update_entity_stack_hover(
        self,
        scene_pos: QPointF,
        global_pos: QPoint,
        *,
        buttons: Qt.MouseButton,
    ) -> None:
        if not _ENTITY_STACK_PICKER_HOVER_ENABLED:
            self._cancel_entity_stack_hover(reset_emitted=True)
            return
        if not self._select_mode or buttons != Qt.MouseButton.NoButton:
            self._cancel_entity_stack_hover(reset_emitted=False)
            return
        entity_ids = tuple(self._entity_ids_at_scene_pos(scene_pos))
        if len(entity_ids) <= 1:
            self._cancel_entity_stack_hover(reset_emitted=True)
            return
        self._entity_stack_hover_global_pos = QPoint(global_pos)
        if entity_ids != self._entity_stack_hover_ids:
            self._entity_stack_hover_ids = entity_ids
            self._entity_stack_hover_emitted_ids = ()
            self._entity_stack_hover_timer.start(_ENTITY_STACK_PICKER_HOVER_DELAY_MS)
            return
        if self._entity_stack_hover_timer.isActive():
            return
        if entity_ids == self._entity_stack_hover_emitted_ids:
            return
        self._entity_stack_hover_timer.start(_ENTITY_STACK_PICKER_HOVER_DELAY_MS)

    def _emit_entity_stack_hover_request(self) -> None:
        if not _ENTITY_STACK_PICKER_HOVER_ENABLED:
            return
        if not self._select_mode or len(self._entity_stack_hover_ids) <= 1:
            return
        if self._entity_stack_hover_global_pos is None:
            return
        self.entity_stack_picker_requested.emit(
            self._entity_stack_hover_ids,
            QPoint(self._entity_stack_hover_global_pos),
            "select",
        )
        self._entity_stack_hover_emitted_ids = self._entity_stack_hover_ids

    def _cancel_entity_stack_hover(self, *, reset_emitted: bool) -> None:
        self._entity_stack_hover_timer.stop()
        self._entity_stack_hover_ids = ()
        self._entity_stack_hover_global_pos = None
        if reset_emitted:
            self._entity_stack_hover_emitted_ids = ()

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

    def _entity_ids_at_scene_pos(self, scene_pos: QPointF) -> list[str]:
        """Return selectable entity ids under one scene point."""
        screen_matches = self._screen_entities_at_scene_pos(scene_pos.x(), scene_pos.y())
        if screen_matches:
            return screen_matches
        tile_cell = self._tile_cell_from_scene_pos(
            scene_pos.x(),
            scene_pos.y(),
            clamp=False,
        )
        if tile_cell is None:
            return []
        return [entity.id for entity in self._world_entities_at_cell(*tile_cell)]

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
            if self._entity_brush_erase_mode or not self._entity_brush_supported:
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
        block = self._selected_gid_block
        if block is None:
            self._ghost_item.setVisible(False)
            return
        pm = self._build_tile_block_pixmap(block)
        if pm is not None and not pm.isNull():
            self._ghost_item.setPixmap(pm)
        else:
            self._ghost_item.setVisible(False)

    def _normalize_gid_block(
        self,
        block: tuple[tuple[int, ...], ...] | None,
    ) -> tuple[tuple[int, ...], ...] | None:
        if block is None:
            return None
        if not block or not block[0]:
            return None
        width = len(block[0])
        rows: list[tuple[int, ...]] = []
        for row in block:
            if len(row) != width:
                return None
            rows.append(tuple(int(gid) for gid in row))
        return tuple(rows) if rows else None

    def _paint_tile_block(
        self,
        anchor_col: int,
        anchor_row: int,
        block: tuple[tuple[int, ...], ...],
    ) -> bool:
        if self._area is None:
            return False
        if not (0 <= self._active_layer < len(self._area.tile_layers)):
            return False
        changed = False
        for row_offset, row_values in enumerate(block):
            target_row = anchor_row + row_offset
            if not (0 <= target_row < self._area.height):
                continue
            for col_offset, gid in enumerate(row_values):
                target_col = anchor_col + col_offset
                if not (0 <= target_col < self._area.width):
                    continue
                if paint_tile(self._area, self._active_layer, target_col, target_row, int(gid)):
                    changed = True
        return changed

    def _build_tile_block_pixmap(
        self,
        block: tuple[tuple[int, ...], ...],
    ) -> QPixmap | None:
        if self._catalog is None or self._area is None or not block or not block[0]:
            return None
        width = len(block[0]) * self._tile_size
        height = len(block) * self._tile_size
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        for row_offset, row_values in enumerate(block):
            for col_offset, gid in enumerate(row_values):
                if gid == 0:
                    continue
                tile_pm = self._catalog.get_tile_pixmap(
                    int(gid),
                    self._area.tilesets,
                    fallback_size=self._tile_size,
                )
                if tile_pm is None or tile_pm.isNull():
                    continue
                painter.drawPixmap(col_offset * self._tile_size, row_offset * self._tile_size, tile_pm)
        painter.end()
        return pixmap
