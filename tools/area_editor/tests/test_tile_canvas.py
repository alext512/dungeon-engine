"""Widget tests for the editable tile canvas."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QApplication, QGraphicsSimpleTextItem

from area_editor.catalogs.template_catalog import VisualInfo
from area_editor.catalogs.template_catalog import TemplateCatalog
from area_editor.catalogs.tileset_catalog import TilesetCatalog
from area_editor.documents.area_document import AreaDocument, EntityDocument, TileLayerDocument
from area_editor.operations.cell_flags import CellFlagBrush
from area_editor.project_io.asset_resolver import AssetResolver
from area_editor.widgets.tile_canvas import BrushType, TileCanvas, _SCENE_EDGE_PADDING


def _make_mouse_event(
    event_type: QMouseEvent.Type,
    position: QPointF,
    *,
    button: Qt.MouseButton,
    buttons: Qt.MouseButton | None = None,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> QMouseEvent:
    """Build a mouse event with the non-deprecated Qt position signature."""
    pressed_buttons = button if buttons is None else buttons
    return QMouseEvent(
        event_type,
        position,
        position,
        position,
        button,
        pressed_buttons,
        modifiers,
    )


def _make_area() -> AreaDocument:
    return AreaDocument(
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
        cell_flags=[[{}, {}], [{}, {}]],
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

        edits: list[tuple[int, int, CellFlagBrush]] = []
        canvas.cell_flag_edited.connect(
            lambda col, row, brush: edits.append((col, row, brush))
        )

        changed = canvas.apply_cell_flag_brush(1, 0, CellFlagBrush("blocked", True))

        self.assertTrue(changed)
        self.assertEqual(area.cell_flags[0][1]["blocked"], True)
        self.assertEqual(edits, [(1, 0, CellFlagBrush("blocked", True))])
        self.assertEqual(len(canvas._cell_flag_group.childItems()), 1)

    def test_cell_flag_pointer_left_blocks_and_right_clears(self):
        area = _make_area()
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_cell_flags_edit_mode(True)

        event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(0, 0),
            button=Qt.MouseButton.LeftButton,
        )
        with patch.object(canvas, "mapToScene", return_value=QPointF(1, 1)):
            self.assertTrue(canvas._handle_edit_pointer_event(event, Qt.MouseButton.LeftButton))

        self.assertEqual(area.cell_flags[0][0]["blocked"], True)

        event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(0, 0),
            button=Qt.MouseButton.RightButton,
        )
        with patch.object(canvas, "mapToScene", return_value=QPointF(1, 1)):
            self.assertTrue(canvas._handle_edit_pointer_event(event, Qt.MouseButton.RightButton))

        self.assertEqual(area.cell_flags[0][0]["blocked"], False)

    def test_cell_flag_pointer_paints_selected_custom_brush(self):
        area = _make_area()
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_cell_flags_edit_mode(True)
        canvas.set_cell_flag_brush(CellFlagBrush("tags", ["water"]))

        event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(0, 0),
            button=Qt.MouseButton.LeftButton,
        )
        with patch.object(canvas, "mapToScene", return_value=QPointF(1, 1)):
            self.assertTrue(canvas._handle_edit_pointer_event(event, Qt.MouseButton.LeftButton))

        self.assertEqual(area.cell_flags[0][0]["tags"], ["water"])

        event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(0, 0),
            button=Qt.MouseButton.RightButton,
        )
        with patch.object(canvas, "mapToScene", return_value=QPointF(1, 1)):
            self.assertTrue(canvas._handle_edit_pointer_event(event, Qt.MouseButton.RightButton))

        self.assertNotIn("tags", area.cell_flags[0][0])

    def test_unified_render_order_interleaves_y_sorted_layer_and_entities(self):
        area = AreaDocument(
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
            cell_flags=[[{}]],
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

    def test_entity_with_sprite_still_gets_editor_marker_box(self):
        class _StubTemplates:
            def get_template_space(self, template_id):
                _ = template_id
                return None

            def get_first_visual(self, template_id, parameters=None):
                _ = template_id, parameters
                return VisualInfo(
                    path="assets/project/sprites/test.png",
                    frame_width=16,
                    frame_height=16,
                    frames=[0],
                    offset_x=0.0,
                    offset_y=0.0,
                )

        area = _make_area()
        area.entities = [
            EntityDocument(
                id="player",
                grid_x=0,
                grid_y=0,
                render_order=10,
                y_sort=True,
                stack_order=0,
                template="entity_templates/player",
            )
        ]
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        with patch.object(catalog, "get_sprite_frame", return_value=QPixmap(16, 16)):
            canvas.set_area(area, catalog, _StubTemplates())

        self.assertEqual(len(canvas._entity_items[0].childItems()), 2)

    def test_hidden_entity_still_gets_editor_marker_box(self):
        area = _make_area()
        hidden = EntityDocument(
            id="trigger",
            grid_x=0,
            grid_y=0,
            render_order=10,
            y_sort=True,
            stack_order=0,
        )
        hidden._extra["visible"] = False
        area.entities = [hidden]
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)

        self.assertTrue(canvas._entity_items[0].isVisible())
        self.assertEqual(len(canvas._entity_items[0].childItems()), 1)

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

        left_event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(8, 8),
            button=Qt.MouseButton.LeftButton,
        )
        right_event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(8, 8),
            button=Qt.MouseButton.RightButton,
        )

        with patch.object(canvas, "mapToScene", return_value=QPointF(8, 8)):
            self.assertTrue(canvas._handle_edit_pointer_event(left_event, Qt.MouseButton.LeftButton))
        canvas.set_entity_brush_erase_mode(True)
        erase_event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(8, 8),
            button=Qt.MouseButton.LeftButton,
        )
        with patch.object(canvas, "mapToScene", return_value=QPointF(8, 8)):
            self.assertTrue(canvas._handle_edit_pointer_event(erase_event, Qt.MouseButton.LeftButton))
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

    def test_entity_marker_shows_overlap_count_for_stacked_entities(self):
        area = _make_area()
        area.entities = [
            EntityDocument(id="npc_1", grid_x=0, grid_y=0, render_order=10, y_sort=True),
            EntityDocument(id="npc_2", grid_x=0, grid_y=0, render_order=20, y_sort=True),
            EntityDocument(id="npc_3", grid_x=1, grid_y=0, render_order=10, y_sort=True),
        ]
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)

        badge_texts = [
            child.text()
            for item in canvas._entity_items
            for child in item.childItems()
            if isinstance(child, QGraphicsSimpleTextItem)
        ]

        self.assertEqual(badge_texts.count("2"), 2)
        self.assertNotIn("1", badge_texts)

    def test_select_mode_drags_world_entity_by_tile_and_emits_commit(self):
        area = _make_area()
        area.tile_layers[0].grid = [[0, 0, 0], [0, 0, 0]]
        area.cell_flags = [[{}, {}, {}], [{}, {}, {}]]
        area.entities = [
            EntityDocument(id="npc_1", grid_x=0, grid_y=0, render_order=10, y_sort=True),
        ]
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_select_mode(True)

        commits: list[tuple[str, str, int, int]] = []
        canvas.entity_drag_committed.connect(
            lambda entity_id, space, x, y: commits.append((entity_id, space, x, y))
        )

        press_event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(8, 8),
            button=Qt.MouseButton.LeftButton,
        )
        move_event = _make_mouse_event(
            QMouseEvent.Type.MouseMove,
            QPointF(24, 8),
            button=Qt.MouseButton.NoButton,
            buttons=Qt.MouseButton.LeftButton,
        )
        release_event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(24, 8),
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.NoButton,
        )

        with patch.object(canvas, "mapToScene", return_value=QPointF(8, 8)):
            self.assertTrue(canvas._handle_edit_pointer_event(press_event, Qt.MouseButton.LeftButton))
        with patch.object(canvas, "mapToScene", return_value=QPointF(24, 8)):
            self.assertTrue(canvas._handle_edit_pointer_event(move_event, Qt.MouseButton.LeftButton))
        with patch.object(canvas, "mapToScene", return_value=QPointF(24, 8)):
            canvas.mouseReleaseEvent(release_event)

        self.assertEqual((area.entities[0].grid_x, area.entities[0].grid_y), (1, 0))
        self.assertEqual(commits, [("npc_1", "world", 1, 0)])
        self.assertEqual(canvas.selected_entity_id, "npc_1")

    def test_select_mode_release_updates_world_drag_final_cell(self):
        area = _make_area()
        area.tile_layers[0].grid = [[0, 0, 0], [0, 0, 0]]
        area.cell_flags = [[{}, {}, {}], [{}, {}, {}]]
        area.entities = [
            EntityDocument(id="npc_1", grid_x=0, grid_y=0, render_order=10, y_sort=True),
        ]
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_select_mode(True)

        commits: list[tuple[str, str, int, int]] = []
        canvas.entity_drag_committed.connect(
            lambda entity_id, space, x, y: commits.append((entity_id, space, x, y))
        )

        press_event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(8, 8),
            button=Qt.MouseButton.LeftButton,
        )
        release_event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonRelease,
            QPointF(40, 8),
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.NoButton,
        )

        with patch.object(canvas, "mapToScene", return_value=QPointF(8, 8)):
            self.assertTrue(canvas._handle_edit_pointer_event(press_event, Qt.MouseButton.LeftButton))
        with patch.object(canvas, "mapToScene", return_value=QPointF(40, 8)):
            canvas.mouseReleaseEvent(release_event)

        self.assertEqual((area.entities[0].grid_x, area.entities[0].grid_y), (2, 0))
        self.assertEqual(commits, [("npc_1", "world", 2, 0)])

    def test_select_mode_drags_screen_entity_by_pixel_and_emits_commit(self):
        area = _make_area()
        area.entities = [
            EntityDocument(
                id="hud",
                pixel_x=4,
                pixel_y=5,
                space="screen",
                render_order=0,
                y_sort=False,
            ),
        ]
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None, display_size=(80, 60))
        canvas.set_select_mode(True)
        pane_x, pane_y = canvas._screen_pane_origin

        commits: list[tuple[str, str, int, int]] = []
        canvas.entity_drag_committed.connect(
            lambda entity_id, space, x, y: commits.append((entity_id, space, x, y))
        )

        press_scene = QPointF(pane_x + 5, pane_y + 6)
        move_scene = QPointF(pane_x + 15, pane_y + 16)
        press_event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            press_scene,
            button=Qt.MouseButton.LeftButton,
        )
        move_event = _make_mouse_event(
            QMouseEvent.Type.MouseMove,
            move_scene,
            button=Qt.MouseButton.NoButton,
            buttons=Qt.MouseButton.LeftButton,
        )
        release_event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonRelease,
            move_scene,
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.NoButton,
        )

        with patch.object(canvas, "mapToScene", return_value=press_scene):
            self.assertTrue(canvas._handle_edit_pointer_event(press_event, Qt.MouseButton.LeftButton))
        with patch.object(canvas, "mapToScene", return_value=move_scene):
            self.assertTrue(canvas._handle_edit_pointer_event(move_event, Qt.MouseButton.LeftButton))
        with patch.object(canvas, "mapToScene", return_value=move_scene):
            canvas.mouseReleaseEvent(release_event)

        self.assertEqual((area.entities[0].pixel_x, area.entities[0].pixel_y), (14, 15))
        self.assertEqual(commits, [("hud", "screen", 14, 15)])
        self.assertEqual(canvas.selected_entity_id, "hud")

    def test_select_mode_drags_screen_entity_to_negative_pixels(self):
        area = _make_area()
        area.entities = [
            EntityDocument(
                id="hud",
                pixel_x=4,
                pixel_y=5,
                space="screen",
                render_order=0,
                y_sort=False,
            ),
        ]
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None, display_size=(80, 60))
        canvas.set_select_mode(True)
        pane_x, pane_y = canvas._screen_pane_origin

        commits: list[tuple[str, str, int, int]] = []
        canvas.entity_drag_committed.connect(
            lambda entity_id, space, x, y: commits.append((entity_id, space, x, y))
        )

        press_scene = QPointF(pane_x + 5, pane_y + 6)
        move_scene = QPointF(pane_x - 5, pane_y - 6)
        press_event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            press_scene,
            button=Qt.MouseButton.LeftButton,
        )
        move_event = _make_mouse_event(
            QMouseEvent.Type.MouseMove,
            move_scene,
            button=Qt.MouseButton.NoButton,
            buttons=Qt.MouseButton.LeftButton,
        )
        release_event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonRelease,
            move_scene,
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.NoButton,
        )

        with patch.object(canvas, "mapToScene", return_value=press_scene):
            self.assertTrue(canvas._handle_edit_pointer_event(press_event, Qt.MouseButton.LeftButton))
        with patch.object(canvas, "mapToScene", return_value=move_scene):
            self.assertTrue(canvas._handle_edit_pointer_event(move_event, Qt.MouseButton.LeftButton))
        with patch.object(canvas, "mapToScene", return_value=move_scene):
            canvas.mouseReleaseEvent(release_event)

        self.assertEqual((area.entities[0].pixel_x, area.entities[0].pixel_y), (-6, -7))
        self.assertEqual(commits, [("hud", "screen", -6, -7)])

    def test_tile_select_mode_drag_creates_rectangle_selection(self):
        area = _make_area()
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_tile_select_mode(True)

        press_event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(1, 1),
            button=Qt.MouseButton.LeftButton,
        )
        move_event = _make_mouse_event(
            QMouseEvent.Type.MouseMove,
            QPointF(31, 31),
            button=Qt.MouseButton.NoButton,
            buttons=Qt.MouseButton.LeftButton,
        )

        with patch.object(canvas, "mapToScene", return_value=QPointF(1, 1)):
            self.assertTrue(canvas._handle_edit_pointer_event(press_event, Qt.MouseButton.LeftButton))
        with patch.object(canvas, "mapToScene", return_value=QPointF(31, 31)):
            self.assertTrue(canvas._handle_edit_pointer_event(move_event, Qt.MouseButton.LeftButton))

        self.assertEqual(canvas.tile_selection_bounds(), (0, 0, 1, 1))
        self.assertTrue(canvas.has_tile_selection)
        self.assertIsNotNone(canvas._tile_selection_item)

    def test_tile_selection_clear_and_paste_block(self):
        area = _make_area()
        area.tile_layers[0].grid = [[1, 2], [3, 4]]
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_tile_select_mode(True)

        self.assertTrue(canvas.set_tile_selection(0, 0, 1, 0))
        self.assertEqual(canvas.selected_tile_block(), [[1, 2]])
        self.assertTrue(canvas.clear_selected_tiles())
        self.assertEqual(area.tile_layers[0].grid, [[0, 0], [3, 4]])

        pasted = canvas.paste_tile_block(0, 1, [[5, 6]])
        self.assertEqual(pasted, (0, 1, 1, 1))
        self.assertEqual(area.tile_layers[0].grid, [[0, 0], [5, 6]])
        self.assertEqual(canvas.tile_selection_bounds(), (0, 1, 1, 1))

    def test_tile_brush_block_paints_multi_tile_stamp(self):
        area = _make_area()
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_tile_paint_mode(True)
        canvas.set_selected_gid_block(((1, 2), (3, 4)))
        canvas.set_active_brush_type(BrushType.TILE)

        changed = canvas._paint_tile_block(0, 0, canvas.selected_gid_block or ())

        self.assertTrue(changed)
        self.assertEqual(area.tile_layers[0].grid, [[1, 2], [3, 4]])

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
        rect = item.sceneBoundingRect()
        self.assertAlmostEqual(rect.x(), float(screen_x + 12) - 0.5)
        self.assertAlmostEqual(rect.y(), float(screen_y + 18) - 0.5)
        self.assertEqual(canvas._screen_pane_size, (256, 192))

    def test_refresh_scene_contents_recomputes_screen_pane_after_area_width_changes(self):
        area = _make_area()
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None, display_size=(256, 192))

        original_screen_x, _screen_y = canvas._screen_pane_origin
        self.assertEqual(original_screen_x, area.width * area.tile_size + area.tile_size)

        area.tile_layers[0].grid[0].insert(0, 0)
        area.tile_layers[0].grid[1].insert(0, 0)

        canvas.refresh_scene_contents()

        updated_screen_x, _screen_y = canvas._screen_pane_origin
        self.assertEqual(updated_screen_x, area.width * area.tile_size + area.tile_size)
        self.assertGreater(updated_screen_x, original_screen_x)

    def test_scene_rect_includes_visual_edge_padding(self):
        area = _make_area()
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None, display_size=(256, 192))

        rect = canvas.sceneRect()
        self.assertEqual(rect.x(), float(-_SCENE_EDGE_PADDING))
        self.assertEqual(rect.y(), float(-_SCENE_EDGE_PADDING))
        self.assertGreater(rect.width(), float(area.width * area.tile_size + 256))
        self.assertGreater(rect.height(), float(max(area.height * area.tile_size, 192)))

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
        event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(screen_x + 11, screen_y + 13),
            button=Qt.MouseButton.LeftButton,
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

    def test_select_mode_double_click_requests_entity_edit(self):
        area = _make_area()
        area.entities = [
            EntityDocument(id="npc", grid_x=0, grid_y=0, render_order=10, y_sort=True),
        ]
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_select_mode(True)

        requested: list[str] = []
        canvas.entity_edit_requested.connect(requested.append)
        event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonDblClick,
            QPointF(8, 8),
            button=Qt.MouseButton.LeftButton,
        )

        with patch.object(canvas, "mapToScene", return_value=QPointF(8, 8)):
            canvas.mouseDoubleClickEvent(event)

        self.assertEqual(requested, ["npc"])
        self.assertEqual(canvas.selected_entity_id, "npc")

    def test_select_mode_hover_does_not_request_entity_stack_picker(self):
        area = _make_area()
        area.entities = [
            EntityDocument(id="npc_1", grid_x=0, grid_y=0, render_order=10, y_sort=True, stack_order=0),
            EntityDocument(id="npc_2", grid_x=0, grid_y=0, render_order=10, y_sort=True, stack_order=2),
        ]
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_select_mode(True)

        requested: list[tuple[tuple[str, ...], tuple[int, int], str]] = []
        canvas.entity_stack_picker_requested.connect(
            lambda ids, pos, purpose: requested.append((tuple(ids), (pos.x(), pos.y()), purpose))
        )

        canvas._update_entity_stack_hover(
            QPointF(8, 8),
            QPoint(24, 30),
            buttons=Qt.MouseButton.NoButton,
        )
        canvas._emit_entity_stack_hover_request()

        self.assertEqual(requested, [])

    def test_select_mode_right_click_requests_entity_context_menu(self):
        area = _make_area()
        area.entities = [
            EntityDocument(
                id="npc_1",
                grid_x=0,
                grid_y=0,
                render_order=10,
                y_sort=True,
                stack_order=0,
            ),
            EntityDocument(
                id="npc_2",
                grid_x=0,
                grid_y=0,
                render_order=10,
                y_sort=True,
                stack_order=2,
            ),
        ]
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_select_mode(True)

        requested: list[tuple[tuple[str, ...], tuple[int, int]]] = []
        canvas.entity_context_menu_requested.connect(
            lambda ids, pos: requested.append((tuple(ids), (pos.x(), pos.y())))
        )
        event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(8, 8),
            button=Qt.MouseButton.RightButton,
        )

        with patch.object(canvas, "mapToScene", return_value=QPointF(8, 8)):
            handled = canvas._handle_edit_pointer_event(event, Qt.MouseButton.RightButton)

        self.assertTrue(handled)
        self.assertEqual(requested, [(("npc_2", "npc_1"), (8, 8))])

    def test_entity_brush_erase_requests_delete_picker_for_stacked_entities(self):
        area = _make_area()
        area.entities = [
            EntityDocument(id="npc_1", grid_x=0, grid_y=0, render_order=10, y_sort=True, stack_order=0),
            EntityDocument(id="npc_2", grid_x=0, grid_y=0, render_order=10, y_sort=True, stack_order=2),
        ]
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_tile_paint_mode(True)
        canvas.set_entity_brush("entity_templates/npc", None, supported=True)
        canvas.set_active_brush_type(BrushType.ENTITY)
        canvas.set_entity_brush_erase_mode(True)

        requested: list[tuple[tuple[str, ...], tuple[int, int], str]] = []
        canvas.entity_stack_picker_requested.connect(
            lambda ids, pos, purpose: requested.append((tuple(ids), (pos.x(), pos.y()), purpose))
        )
        event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(8, 8),
            button=Qt.MouseButton.LeftButton,
        )

        with patch.object(canvas, "mapToScene", return_value=QPointF(8, 8)):
            handled = canvas._handle_edit_pointer_event(event, Qt.MouseButton.LeftButton)

        self.assertTrue(handled)
        self.assertEqual(
            requested,
            [(("npc_2", "npc_1"), (8, 8), "delete")],
        )

    def test_entity_brush_right_click_requests_context_menu(self):
        area = _make_area()
        area.entities = [
            EntityDocument(id="npc", grid_x=0, grid_y=0, render_order=10, y_sort=True),
        ]
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None)
        canvas.set_tile_paint_mode(True)
        canvas.set_entity_brush("entity_templates/npc", None, supported=True)
        canvas.set_active_brush_type(BrushType.ENTITY)

        requested: list[tuple[tuple[str, ...], tuple[int, int]]] = []
        canvas.entity_context_menu_requested.connect(
            lambda ids, pos: requested.append((tuple(ids), (pos.x(), pos.y())))
        )
        event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(8, 8),
            button=Qt.MouseButton.RightButton,
        )

        with patch.object(canvas, "mapToScene", return_value=QPointF(8, 8)):
            handled = canvas._handle_edit_pointer_event(event, Qt.MouseButton.RightButton)

        self.assertTrue(handled)
        self.assertEqual(requested, [(("npc",), (8, 8))])

    def test_screen_entity_brush_erase_emits_delete_by_id(self):
        area = _make_area()
        area.entities = [
            EntityDocument(
                id="hud",
                pixel_x=4,
                pixel_y=5,
                space="screen",
                render_order=0,
                y_sort=False,
            ),
        ]
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None, display_size=(80, 60))
        canvas.set_tile_paint_mode(True)
        canvas.set_entity_brush(
            "entity_templates/hud",
            None,
            supported=True,
            target_space="screen",
        )
        canvas.set_active_brush_type(BrushType.ENTITY)
        canvas.set_entity_brush_erase_mode(True)
        pane_x, pane_y = canvas._screen_pane_origin

        deleted: list[str] = []
        canvas.entity_delete_by_id_requested.connect(deleted.append)
        event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(pane_x + 5, pane_y + 6),
            button=Qt.MouseButton.LeftButton,
        )

        with patch.object(
            canvas,
            "mapToScene",
            return_value=QPointF(pane_x + 5, pane_y + 6),
        ):
            handled = canvas._handle_edit_pointer_event(event, Qt.MouseButton.LeftButton)

        self.assertTrue(handled)
        self.assertEqual(deleted, ["hud"])

    def test_mouse_move_emits_screen_pixel_hovered_inside_screen_pane(self):
        area = _make_area()
        canvas = TileCanvas()
        catalog = TilesetCatalog(AssetResolver([]))
        canvas.set_area(area, catalog, None, display_size=(256, 192))

        hovered: list[tuple[int, int]] = []
        canvas.screen_pixel_hovered.connect(lambda px, py: hovered.append((px, py)))

        screen_x, screen_y = canvas._screen_pane_origin
        event = _make_mouse_event(
            QMouseEvent.Type.MouseMove,
            QPointF(screen_x + 20, screen_y + 30),
            button=Qt.MouseButton.NoButton,
            buttons=Qt.MouseButton.NoButton,
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
        event = _make_mouse_event(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(screen_x + 8, screen_y + 8),
            button=Qt.MouseButton.LeftButton,
        )
        with patch.object(
            canvas,
            "mapToScene",
            return_value=QPointF(screen_x + 8, screen_y + 8),
        ):
            handled = canvas._handle_edit_pointer_event(event, Qt.MouseButton.LeftButton)

        self.assertTrue(handled)
        self.assertEqual(area.tile_layers[0].grid, [[0, 0], [0, 0]])
