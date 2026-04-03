"""Widget tests for the editable tile canvas."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from area_editor.catalogs.template_catalog import TemplateCatalog
from area_editor.catalogs.tileset_catalog import TilesetCatalog
from area_editor.documents.area_document import AreaDocument, EntityDocument, TileLayerDocument
from area_editor.project_io.asset_resolver import AssetResolver
from area_editor.widgets.tile_canvas import BrushType, TileCanvas


def _make_area() -> AreaDocument:
    return AreaDocument(
        name="test",
        tile_size=16,
        tilesets=[],
        tile_layers=[
            TileLayerDocument(
                name="ground",
                render_order=0,
                y_sort=False,
                sort_y_offset=0.0,
                stack_order=0,
                grid=[[0, 0], [0, 0]],
            )
        ],
        cell_flags=[[True, False], [True, True]],
        entry_points={},
        entities=[],
        camera={},
        input_targets={},
        variables={},
        enter_commands=[],
    )


class TestTileCanvasCellFlagEditing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_apply_cell_flag_brush_updates_document_and_emits_signal(self):
        area = _make_area()
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_cell_flags_edit_mode(True)

        edits: list[tuple[int, int, bool]] = []
        canvas.cell_flag_edited.connect(
            lambda col, row, walkable: edits.append((col, row, walkable))
        )

        changed = canvas.apply_cell_flag_brush(1, 0, True)

        self.assertTrue(changed)
        self.assertTrue(area.cell_flags[0][1])
        self.assertEqual(edits, [(1, 0, True)])
        self.assertEqual(len(canvas._cell_flag_group.childItems()), 0)

    def test_unified_render_order_interleaves_y_sorted_layer_and_entities(self):
        area = AreaDocument(
            name="render-order",
            tile_size=16,
            tilesets=[],
            tile_layers=[
                TileLayerDocument(
                    name="ground",
                    render_order=0,
                    y_sort=False,
                    sort_y_offset=0.0,
                    stack_order=0,
                    grid=[[0]],
                ),
                TileLayerDocument(
                    name="front",
                    render_order=10,
                    y_sort=True,
                    sort_y_offset=0.0,
                    stack_order=0,
                    grid=[[1]],
                ),
            ],
            cell_flags=[[True]],
            entry_points={},
            entities=[
                EntityDocument(
                    id="player",
                    grid_x=0,
                    grid_y=0,
                    render_order=10,
                    y_sort=True,
                    sort_y_offset=0.0,
                    stack_order=1,
                )
            ],
            camera={},
            input_targets={},
            variables={},
            enter_commands=[],
        )

        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)

        self.assertEqual(len(canvas._layer_items[0]), 1)
        self.assertEqual(len(canvas._layer_items[0][0].childItems()), 0)
        self.assertEqual(len(canvas._layer_items[1]), 1)
        self.assertEqual(len(canvas._entity_items), 1)
        self.assertLess(canvas._layer_items[1][0].zValue(), canvas._entity_items[0].zValue())

    def test_entity_brush_emits_place_and_delete_requests(self):
        area = _make_area()
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_tile_paint_mode(True)
        canvas.set_entity_brush("entity_templates/npc", None, supported=True)
        canvas.set_active_brush_type(BrushType.ENTITY)

        placed: list[tuple[str, int, int]] = []
        deleted: list[tuple[int, int]] = []
        canvas.entity_paint_requested.connect(
            lambda template_id, col, row: placed.append((template_id, col, row))
        )
        canvas.entity_delete_requested.connect(
            lambda col, row: deleted.append((col, row))
        )

        left_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(8, 8),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        right_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(8, 8),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )

        with patch.object(canvas, "mapToScene", return_value=QPointF(8, 8)):
            self.assertTrue(canvas._handle_edit_pointer_event(left_event, Qt.MouseButton.LeftButton))
            self.assertTrue(canvas._handle_edit_pointer_event(right_event, Qt.MouseButton.RightButton))
        self.assertEqual(placed, [("entity_templates/npc", 0, 0)])
        self.assertEqual(deleted, [(0, 0)])

    def test_select_mode_cycles_stacked_entities_and_clears_on_empty_cell(self):
        area = _make_area()
        area.entities = [
            EntityDocument(id="npc_1", grid_x=0, grid_y=0, render_order=10, y_sort=True, stack_order=0),
            EntityDocument(id="npc_2", grid_x=0, grid_y=0, render_order=10, y_sort=True, stack_order=2),
        ]
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_select_mode(True)

        selections: list[tuple[str, int, int]] = []
        canvas.entity_selection_changed.connect(
            lambda entity_id, position, total: selections.append((entity_id, position, total))
        )

        self.assertTrue(canvas.select_entities_at_cell(0, 0))
        self.assertEqual(canvas.selected_entity_id, "npc_2")
        self.assertEqual(canvas.selected_entity_cycle_position, 1)
        self.assertEqual(canvas.selected_entity_cycle_total, 2)
        self.assertIsNotNone(canvas._selection_item)

        self.assertTrue(canvas.select_entities_at_cell(0, 0))
        self.assertEqual(canvas.selected_entity_id, "npc_1")
        self.assertEqual(canvas.selected_entity_cycle_position, 2)
        self.assertEqual(canvas.selected_entity_cycle_total, 2)

        self.assertTrue(canvas.select_entities_at_cell(1, 1))
        self.assertIsNone(canvas.selected_entity_id)
        self.assertIsNone(canvas._selection_item)
        self.assertEqual(
            selections,
            [("npc_2", 1, 2), ("npc_1", 2, 2), ("", 0, 0)],
        )

    def test_paint_mode_forces_no_drag_and_cross_cursor(self):
        area = _make_area()
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)

        canvas.set_tile_paint_mode(True)

        self.assertTrue(canvas.tile_paint_mode)
        self.assertEqual(canvas.dragMode(), canvas.DragMode.NoDrag)
        self.assertEqual(canvas.viewport().cursor().shape(), Qt.CursorShape.CrossCursor)

    def test_screen_pane_offsets_template_driven_screen_entities(self):
        area = _make_area()
        area.entities = [
            EntityDocument(
                id="title_backdrop",
                template="entity_templates/display_sprite",
                pixel_x=12,
                pixel_y=18,
            )
        ]
        templates = TemplateCatalog()
        templates._templates["entity_templates/display_sprite"] = {
            "space": "screen",
        }

        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, templates, display_size=(256, 192))

        item = canvas._entity_item_by_id["title_backdrop"]
        screen_x, screen_y = canvas._screen_pane_origin
        self.assertEqual(item.pos().x(), screen_x + 12)
        self.assertEqual(item.pos().y(), screen_y + 18)
        self.assertEqual(canvas._screen_pane_size, (256, 192))

    def test_select_mode_can_pick_screen_entities_with_template_fallback(self):
        area = _make_area()
        area.entities = [
            EntityDocument(id="npc", grid_x=0, grid_y=0, render_order=10, y_sort=True),
            EntityDocument(
                id="overlay",
                template="entity_templates/display_sprite",
                pixel_x=10,
                pixel_y=12,
                render_order=0,
                y_sort=False,
            ),
        ]
        templates = TemplateCatalog()
        templates._templates["entity_templates/display_sprite"] = {
            "space": "screen",
        }

        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, templates, display_size=(256, 192))
        canvas.set_select_mode(True)
        canvas.select_entities_at_cell(0, 0)
        self.assertEqual(canvas.selected_entity_id, "npc")

        screen_x, screen_y = canvas._screen_pane_origin
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(screen_x + 11, screen_y + 13),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )

        with patch.object(
            canvas,
            "mapToScene",
            return_value=QPointF(screen_x + 11, screen_y + 13),
        ):
            handled = canvas._handle_edit_pointer_event(event, Qt.MouseButton.LeftButton)

        self.assertTrue(handled)
        self.assertEqual(canvas.selected_entity_id, "overlay")
        self.assertEqual(canvas._selection_cycle_ids, ())
        self.assertEqual(canvas._screen_selection_cycle_ids, ("overlay",))

    def test_mouse_move_emits_screen_pixel_hovered_inside_screen_pane(self):
        area = _make_area()
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None, display_size=(256, 192))

        hovered: list[tuple[int, int]] = []
        canvas.screen_pixel_hovered.connect(lambda px, py: hovered.append((px, py)))

        screen_x, screen_y = canvas._screen_pane_origin
        event = QMouseEvent(
            QMouseEvent.Type.MouseMove,
            QPointF(screen_x + 20, screen_y + 30),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        with patch.object(
            canvas,
            "mapToScene",
            return_value=QPointF(screen_x + 20, screen_y + 30),
        ):
            canvas.mouseMoveEvent(event)

        self.assertEqual(hovered[-1], (20, 30))

    def test_paint_mode_click_in_screen_pane_is_consumed_without_editing_world(self):
        area = _make_area()
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None, display_size=(256, 192))
        canvas.set_tile_paint_mode(True)
        canvas.set_selected_gid(9)
        canvas.set_active_brush_type(BrushType.TILE)

        screen_x, screen_y = canvas._screen_pane_origin
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(screen_x + 8, screen_y + 8),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        with patch.object(
            canvas,
            "mapToScene",
            return_value=QPointF(screen_x + 8, screen_y + 8),
        ):
            handled = canvas._handle_edit_pointer_event(event, Qt.MouseButton.LeftButton)

        self.assertTrue(handled)
        self.assertEqual(area.tile_layers[0].grid, [[0, 0], [0, 0]])
