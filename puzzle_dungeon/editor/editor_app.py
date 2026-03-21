"""Standalone Tiled-like level editor application.

Renders at native resolution in a resizable window with persistent panels
for tileset browsing, entity management, and property editing.
"""

from __future__ import annotations

from pathlib import Path

import pygame

from puzzle_dungeon import config
from puzzle_dungeon.editor.level_editor import LevelEditor, list_tileset_paths
from puzzle_dungeon.engine.asset_manager import AssetManager
from puzzle_dungeon.engine.camera import Camera
from puzzle_dungeon.world.area import Area
from puzzle_dungeon.world.loader import load_area
from puzzle_dungeon.world.world import World


# ---------------------------------------------------------------------------
# Simple UI button helper
# ---------------------------------------------------------------------------

class _Button:
    """A clickable text button drawn at native resolution."""

    __slots__ = ("label", "rect", "active")

    def __init__(self, label: str, rect: pygame.Rect, active: bool = False) -> None:
        self.label = label
        self.rect = rect
        self.active = active


# ---------------------------------------------------------------------------
# EditorApp
# ---------------------------------------------------------------------------

class EditorApp:
    """Standalone Tiled-like level editor with a resizable window."""

    TOOLBAR_H = 36
    STATUS_H = 24
    LEFT_PANEL_W = 260
    RIGHT_PANEL_W = 280

    MIN_WIDTH = 800
    MIN_HEIGHT = 500

    COL_TOOLBAR = (40, 44, 52)
    COL_PANEL = (30, 33, 40)
    COL_STATUS = (40, 44, 52)
    COL_BORDER = (60, 65, 75)
    COL_MAP_BG = (22, 24, 30)
    COL_GRID = (255, 255, 255, 25)
    COL_HIGHLIGHT = (248, 218, 94)
    COL_HOVER = (255, 255, 255, 80)
    COL_BTN = (55, 60, 70)
    COL_BTN_ACTIVE = (80, 130, 200)
    COL_BTN_HOVER = (70, 75, 85)
    COL_WALK_OK = (48, 180, 96, 70)
    COL_WALK_BLOCK = (200, 64, 64, 90)
    COL_SELECTION_BG = (50, 55, 65)

    TILESET_ZOOM = 2  # Zoom for tileset frames in the left panel
    FACING_CYCLE = ("up", "right", "down", "left")

    def __init__(self, area_path: Path, project: "ProjectContext | None" = None) -> None:
        from puzzle_dungeon.project import ProjectContext  # noqa: F811

        pygame.init()

        # Pick a sensible initial size: 80% of the desktop, clamped to minimum
        info = pygame.display.Info()
        init_w = max(self.MIN_WIDTH, int(info.current_w * 0.80))
        init_h = max(self.MIN_HEIGHT, int(info.current_h * 0.80))

        self.display = pygame.display.set_mode((init_w, init_h), pygame.RESIZABLE)
        pygame.display.set_caption(f"Editor - {area_path.stem}")
        self.clock = pygame.time.Clock()

        # Track live window size (updated on resize)
        self.win_w = init_w
        self.win_h = init_h

        self.project = project
        self.asset_manager = AssetManager(project=project)
        area, world = load_area(area_path, asset_manager=self.asset_manager)
        self.editor = LevelEditor(area_path, area, world, asset_manager=self.asset_manager)

        # Layout rects (recomputed on resize)
        self._compute_layout()

        # Camera works in world-pixel coords
        self.map_zoom = 2
        self._rebuild_camera()

        # Fonts
        self.font = pygame.font.SysFont("Segoe UI", 14)
        self.font_bold = pygame.font.SysFont("Segoe UI", 14, bold=True)
        self.font_small = pygame.font.SysFont("Segoe UI", 12)

        # Interaction state
        self.middle_pan_active = False
        self.tileset_pan_active = False
        self.left_drag_active = False
        self.right_drag_active = False
        self.running = False

        # Left panel scroll
        self.tileset_scroll_x = 0
        self.tileset_scroll_y = 0

        # Text editing (property inspector and layer rename)
        self.editing_field: str | None = None
        self.editing_entity_id: str | None = None
        self.editing_text: str = ""

        # Layer rename state
        self.renaming_layer_index: int | None = None
        self.rename_text: str = ""

        # Toolbar buttons (rebuilt each frame)
        self._toolbar_buttons: list[_Button] = []

        # ESC-to-quit confirmation when dirty
        self._esc_quit_pending = False

    def run(self) -> None:
        """Main editor loop."""
        self.running = True
        while self.running:
            dt = self.clock.tick(config.FPS) / 1000.0
            events = pygame.event.get()
            self._handle_events(events, dt)
            self._render()
            pygame.display.flip()
        pygame.quit()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _compute_layout(self) -> None:
        w, h = self.win_w, self.win_h
        self.toolbar_rect = pygame.Rect(0, 0, w, self.TOOLBAR_H)
        self.left_rect = pygame.Rect(
            0, self.TOOLBAR_H,
            self.LEFT_PANEL_W,
            h - self.TOOLBAR_H - self.STATUS_H,
        )
        self.right_rect = pygame.Rect(
            w - self.RIGHT_PANEL_W, self.TOOLBAR_H,
            self.RIGHT_PANEL_W,
            h - self.TOOLBAR_H - self.STATUS_H,
        )
        self.map_rect = pygame.Rect(
            self.LEFT_PANEL_W, self.TOOLBAR_H,
            w - self.LEFT_PANEL_W - self.RIGHT_PANEL_W,
            h - self.TOOLBAR_H - self.STATUS_H,
        )
        self.status_rect = pygame.Rect(0, h - self.STATUS_H, w, self.STATUS_H)

    def _rebuild_camera(self) -> None:
        old_x = getattr(self, "camera", None) and self.camera.x or 0.0
        old_y = getattr(self, "camera", None) and self.camera.y or 0.0
        cam_vp_w = int(self.map_rect.width / self.map_zoom)
        cam_vp_h = int(self.map_rect.height / self.map_zoom)
        self.camera = Camera(cam_vp_w, cam_vp_h, self.editor.area, clamp_to_area=False)
        self.camera.set_position(old_x, old_y)

    def _on_resize(self, new_w: int, new_h: int) -> None:
        """Handle window resize: clamp, update surface, recompute layout."""
        self.win_w = max(self.MIN_WIDTH, new_w)
        self.win_h = max(self.MIN_HEIGHT, new_h)
        self.display = pygame.display.set_mode(
            (self.win_w, self.win_h), pygame.RESIZABLE,
        )
        self._compute_layout()
        self._rebuild_camera()
        self._clamp_tileset_scroll()

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _handle_events(self, events: list[pygame.event.Event], dt: float) -> None:
        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
                continue

            if event.type == pygame.VIDEORESIZE:
                self._on_resize(event.w, event.h)
                continue

            if event.type == pygame.KEYDOWN:
                if self._handle_text_editing_key(event):
                    self._esc_quit_pending = False
                    continue
                if event.key == pygame.K_ESCAPE:
                    if self._esc_quit_pending:
                        self.running = False
                        continue
                    if self.editor.move_pending_entity_id:
                        self.editor.move_pending_entity_id = None
                        self.editor.status_message = "Move cancelled"
                    elif self.editing_field:
                        self._cancel_text_edit()
                    elif self.editor.selected_entity_id:
                        self.editor.selected_entity_id = None
                        self.editor.status_message = "Deselected entity"
                    elif self.editor.selected_cell:
                        self.editor.selected_cell = None
                        self.editor.status_message = "Deselected cell"
                    elif self.editor.dirty:
                        self.editor.status_message = "Unsaved changes! Ctrl+S to save, ESC again to quit"
                        self._esc_quit_pending = True
                    else:
                        self.running = False
                    continue
                # Any non-ESC key resets the quit confirmation
                if event.key != pygame.K_ESCAPE:
                    self._esc_quit_pending = False
                if event.key == pygame.K_s and (event.mod & pygame.KMOD_CTRL):
                    self._commit_text_edit()
                    self.editor.save()
                    continue
                if event.key == pygame.K_TAB:
                    new_mode = "select" if self.editor.mode == "paint" else "paint"
                    self.editor.set_mode(new_mode)
                    continue
                if event.key == pygame.K_LEFTBRACKET:
                    self._cycle_tileset(-1)
                    continue
                if event.key == pygame.K_RIGHTBRACKET:
                    self._cycle_tileset(1)
                    continue
                if event.key == pygame.K_DELETE:
                    if self.editor.mode == "select" and self.editor.selected_entity_id:
                        self.editor._remove_selected_entity()
                    continue

            if event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_mouse_down(event)
                continue

            if event.type == pygame.MOUSEBUTTONUP:
                self._handle_mouse_up(event)
                continue

            if event.type == pygame.MOUSEMOTION:
                self._handle_mouse_motion(event)
                continue

            if event.type == pygame.MOUSEWHEEL:
                self._handle_mouse_wheel(event)
                continue

        # Arrow key panning
        key_state = pygame.key.get_pressed()
        pan_speed = config.EDITOR_CAMERA_PAN_SPEED
        dx = dy = 0.0
        if key_state[pygame.K_LEFT]:
            dx -= pan_speed * dt
        if key_state[pygame.K_RIGHT]:
            dx += pan_speed * dt
        if key_state[pygame.K_UP]:
            dy -= pan_speed * dt
        if key_state[pygame.K_DOWN]:
            dy += pan_speed * dt
        if dx or dy:
            self.camera.pan(dx, dy)

    def _handle_mouse_down(self, event: pygame.event.Event) -> None:
        pos = event.pos

        # Commit any in-progress text edit before handling clicks elsewhere
        if self.editing_field and not self.right_rect.collidepoint(pos):
            self._commit_text_edit()

        if event.button == 2 and self._tileset_grid_rect().collidepoint(pos):
            self.tileset_pan_active = True
            return

        if event.button == 2 and self.map_rect.collidepoint(pos):
            self.middle_pan_active = True
            return

        if self.toolbar_rect.collidepoint(pos):
            self._handle_toolbar_click(pos)
            return

        if self.left_rect.collidepoint(pos):
            self._handle_left_panel_click(pos, event.button)
            return

        if self.right_rect.collidepoint(pos):
            self._handle_right_panel_click(pos, event.button)
            return

        if self.map_rect.collidepoint(pos):
            cell = self._screen_to_cell(pos)
            if cell is None:
                return

            if self.editor.move_pending_entity_id and event.button == 1:
                self.editor.move_entity_to(self.editor.move_pending_entity_id, cell[0], cell[1])
                self.editor.move_pending_entity_id = None
                self.editor.selected_cell = cell
                return

            if self.editor.mode == "paint":
                self.editor._select_cell(cell[0], cell[1])
                if event.button == 1:
                    self.editor._apply_primary()
                    self.left_drag_active = True
                elif event.button == 3:
                    self.editor._apply_secondary()
                    self.right_drag_active = True
            elif self.editor.mode == "select":
                if event.button == 1:
                    self.editor._select_cell(cell[0], cell[1])

    def _handle_mouse_up(self, event: pygame.event.Event) -> None:
        if event.button == 2:
            self.middle_pan_active = False
            self.tileset_pan_active = False
        if event.button == 1:
            self.left_drag_active = False
            self.editor.last_drag_cell = None
        if event.button == 3:
            self.right_drag_active = False
            self.editor.last_drag_cell = None

    def _handle_mouse_motion(self, event: pygame.event.Event) -> None:
        if self.tileset_pan_active and event.buttons[1]:
            self._pan_tileset_grid(-event.rel[0], -event.rel[1])

        if self.middle_pan_active and event.buttons[1]:
            self.camera.pan(-event.rel[0] / self.map_zoom, -event.rel[1] / self.map_zoom)

        if self.map_rect.collidepoint(event.pos):
            cell = self._screen_to_cell(event.pos)
            self.editor.hovered_cell = cell

            if self.editor.mode == "paint" and cell is not None and cell != self.editor.last_drag_cell:
                if self.left_drag_active:
                    self.editor._select_cell(cell[0], cell[1])
                    self.editor._apply_primary()
                    self.editor.last_drag_cell = cell
                elif self.right_drag_active:
                    self.editor._select_cell(cell[0], cell[1])
                    self.editor._apply_secondary()
                    self.editor.last_drag_cell = cell
        else:
            self.editor.hovered_cell = None

    def _handle_mouse_wheel(self, event: pygame.event.Event) -> None:
        mx, my = pygame.mouse.get_pos()
        if self._tileset_grid_rect().collidepoint(mx, my):
            self._pan_tileset_grid(-event.x * 32, -event.y * 32)
        elif self.map_rect.collidepoint(mx, my):
            self.camera.pan(0, -event.y * self.editor.area.tile_size)

    def _handle_toolbar_click(self, pos: tuple[int, int]) -> None:
        for btn in self._toolbar_buttons:
            if btn.rect.collidepoint(pos):
                if btn.label == "Save":
                    self.editor.save()
                elif btn.label == "Reload":
                    self.editor.reload_from_disk()
                    self._rebuild_camera()
                elif btn.label == "Paint":
                    self.editor.set_mode("paint")
                elif btn.label == "Select":
                    self.editor.set_mode("select")
                break

    def _handle_left_panel_click(self, pos: tuple[int, int], button: int) -> None:
        """Handle clicks in the left panel (tileset grid + area tiles)."""
        local_y = pos[1] - self.left_rect.y

        # Tileset selector arrows area (top 28px)
        if local_y < 28:
            prev_rect, next_rect = self._tileset_selector_button_rects()
            if prev_rect.collidepoint(pos):
                self._cycle_tileset(-1)
            elif next_rect.collidepoint(pos):
                self._cycle_tileset(1)
            return

        # Check area tiles section (bottom of left panel)
        area_tiles_y = self._area_tiles_top_y()
        if pos[1] >= area_tiles_y:
            rel_y = pos[1] - area_tiles_y
            row = rel_y // 26
            if row == 0:
                self.editor.paint_submode = "walk"
                self.editor.walk_brush_walkable = True
                self.editor.show_walk_overlay = True
                self.editor.status_message = "Brush: walkable"
            elif row == 1:
                self.editor.paint_submode = "walk"
                self.editor.walk_brush_walkable = False
                self.editor.show_walk_overlay = True
                self.editor.status_message = "Brush: blocked"
            return

        # Tileset grid click
        tileset_path = self.editor.current_tileset_path
        if not tileset_path:
            return

        tile_w = self.editor.area.tile_size
        tile_h = self.editor.area.tile_size
        frame_px = tile_w * self.TILESET_ZOOM
        columns = self.asset_manager.get_columns(tileset_path, tile_w)
        frame_count = self.asset_manager.get_frame_count(tileset_path, tile_w, tile_h)

        grid_rect = self._tileset_grid_rect()
        if not grid_rect.collidepoint(pos):
            return

        local_x = pos[0] - grid_rect.x + self.tileset_scroll_x
        local_y_in_grid = pos[1] - grid_rect.y + self.tileset_scroll_y
        col = local_x // frame_px
        row = local_y_in_grid // frame_px

        if col < 0 or col >= columns:
            return
        frame_index = row * columns + col
        if frame_index < 0 or frame_index >= frame_count:
            return

        self.editor.paint_submode = "tile"
        self.editor.select_tileset_frame(self.editor.selected_tileset_index, frame_index)

    def _handle_right_panel_click(self, pos: tuple[int, int], button: int) -> None:
        """Handle clicks in the right panel."""
        if self.editor.mode == "paint":
            self._handle_right_panel_paint_click(pos, button)
        elif self.editor.mode == "select":
            self._handle_right_panel_select_click(pos, button)

    def _handle_right_panel_paint_click(self, pos: tuple[int, int], button: int) -> None:
        """Handle right panel clicks in paint mode (layer management).

        Single-click selects a layer. Double-click starts renaming.
        """
        layers = self.editor.area.tile_layers

        for i, layer in enumerate(layers):
            row_rect = self._paint_layer_row_rect(i)
            if not row_rect.collidepoint(pos):
                continue

            if self._paint_layer_delete_rect(i).collidepoint(pos):
                self.editor.selected_layer_index = i
                self.editor.remove_selected_layer()
                return

            if self._paint_layer_toggle_rect(i).collidepoint(pos):
                layer.draw_above_entities = not layer.draw_above_entities
                self.editor._mark_dirty(f"{'Above' if layer.draw_above_entities else 'Below'} entities: {layer.name}")
                return

            # Double-click to rename
            if button == 1 and i == self.editor.selected_layer_index:
                self.renaming_layer_index = i
                self.rename_text = layer.name
                self.editor.status_message = f"Renaming layer (Enter to confirm)"
                return

            self.editor.selected_layer_index = i
            self.editor.status_message = f"Layer {layer.name}"
            return

        if self._paint_add_layer_rect(len(layers)).collidepoint(pos):
            self.editor.add_layer()

    def _handle_right_panel_select_click(self, pos: tuple[int, int], button: int) -> None:
        """Handle right panel clicks in select mode (entity management + properties)."""
        local_y = pos[1] - self.right_rect.y
        local_x = pos[0] - self.right_rect.x

        entities = self.editor.entities_for_selected_cell()
        entity_list_start_y = 30

        for i, entity in enumerate(entities):
            row_y = entity_list_start_y + i * 24
            if local_y < row_y or local_y >= row_y + 24:
                continue

            btn_x = self.RIGHT_PANEL_W - 8
            btn_x -= 40
            if local_x >= btn_x:
                self.editor.move_pending_entity_id = entity.entity_id
                self.editor.status_message = f"Click map to move {entity.entity_id}"
                return

            btn_x -= 24
            if local_x >= btn_x and entity.entity_id != self.editor.world.player_id:
                self.editor.world.remove_entity(entity.entity_id)
                self.editor._sync_selected_entity_to_cell()
                self.editor._mark_dirty(f"Removed {entity.entity_id}")
                return

            btn_x -= 20
            if local_x >= btn_x:
                self.editor.selected_entity_id = entity.entity_id
                self.editor._move_selected_entity(1)
                return

            btn_x -= 20
            if local_x >= btn_x:
                self.editor.selected_entity_id = entity.entity_id
                self.editor._move_selected_entity(-1)
                return

            self.editor.selected_entity_id = entity.entity_id
            return

        # "Add Entity" label row, then button row below it
        add_label_y = entity_list_start_y + len(entities) * 24 + 8
        add_btn_y = add_label_y + 20
        btn_w = 22
        add_w = 36
        if add_btn_y <= local_y < add_btn_y + 22:
            # [<] prev template
            if local_x < btn_w:
                self.editor.selected_template_index = (self.editor.selected_template_index - 1) % max(1, len(self.editor.template_ids))
                return
            # [Add] button (rightmost)
            add_left = self.RIGHT_PANEL_W - 8 - add_w
            if local_x >= add_left:
                if self.editor.selected_cell:
                    self.editor._place_entity(*self.editor.selected_cell)
                return
            # [>] next template (just left of Add)
            next_left = add_left - 4 - btn_w
            if local_x >= next_left and local_x < next_left + btn_w:
                self.editor.selected_template_index = (self.editor.selected_template_index + 1) % max(1, len(self.editor.template_ids))
                return
            return

        props = self.editor.selected_entity_properties()
        if not props:
            return
        props_start_y = add_btn_y + 30
        for i, (field_name, display_label, current_value) in enumerate(props):
            row_y = props_start_y + i * 22
            if local_y < row_y or local_y >= row_y + 22:
                continue

            if field_name in ("template_id", "kind"):
                return

            entity_id = self.editor.selected_entity_id
            if entity_id is None:
                return

            if field_name == "facing":
                try:
                    idx = self.FACING_CYCLE.index(current_value)
                except ValueError:
                    idx = 0
                new_val = self.FACING_CYCLE[(idx + 1) % 4]
                self.editor.set_entity_property(entity_id, field_name, new_val)
                return

            if field_name in ("solid", "pushable", "present", "visible", "events_enabled"):
                new_val = "false" if current_value == "true" else "true"
                self.editor.set_entity_property(entity_id, field_name, new_val)
                return

            if field_name.startswith("param:"):
                self.editing_field = field_name
                self.editing_entity_id = entity_id
                self.editing_text = current_value
                return

    # ------------------------------------------------------------------
    # Text editing for property fields
    # ------------------------------------------------------------------

    def _handle_text_editing_key(self, event: pygame.event.Event) -> bool:
        # Layer rename mode
        if self.renaming_layer_index is not None:
            if event.key == pygame.K_RETURN:
                self.editor.selected_layer_index = self.renaming_layer_index
                self.editor.rename_selected_layer(self.rename_text)
                self.renaming_layer_index = None
                self.rename_text = ""
                return True
            if event.key == pygame.K_ESCAPE:
                self.renaming_layer_index = None
                self.rename_text = ""
                return True
            if event.key == pygame.K_BACKSPACE:
                self.rename_text = self.rename_text[:-1]
                return True
            if event.unicode and event.unicode.isprintable():
                self.rename_text += event.unicode
                return True
            return False

        # Property field edit mode
        if self.editing_field is None:
            return False

        if event.key == pygame.K_RETURN:
            self._commit_text_edit()
            return True
        if event.key == pygame.K_ESCAPE:
            self._cancel_text_edit()
            return True
        if event.key == pygame.K_BACKSPACE:
            self.editing_text = self.editing_text[:-1]
            return True

        if event.unicode and event.unicode.isprintable():
            self.editing_text += event.unicode
            return True

        return False

    def _commit_text_edit(self) -> None:
        if self.editing_field and self.editing_entity_id:
            self.editor.set_entity_property(self.editing_entity_id, self.editing_field, self.editing_text)
        self.editing_field = None
        self.editing_entity_id = None
        self.editing_text = ""

    def _cancel_text_edit(self) -> None:
        self.editing_field = None
        self.editing_entity_id = None
        self.editing_text = ""

    # ------------------------------------------------------------------
    # Tileset cycling
    # ------------------------------------------------------------------

    def _cycle_tileset(self, direction: int) -> None:
        current_path = self.editor.current_tileset_path
        self.editor.refresh_catalogs()
        paths = self.editor.available_tileset_paths
        if not paths:
            self.editor.status_message = "No tilesets found in the active project"
            return

        if current_path and current_path in paths:
            self.editor.selected_tileset_index = paths.index(current_path)

        if len(paths) == 1:
            self.editor.selected_tileset_index = 0
            self.tileset_scroll_x = 0
            self.tileset_scroll_y = 0
            self.editor.status_message = (
                f"Tileset: {self._tileset_display_name(paths[0])} (only available tileset)"
            )
            return

        self.editor.selected_tileset_index = (self.editor.selected_tileset_index + direction) % len(paths)
        self.tileset_scroll_x = 0
        self.tileset_scroll_y = 0
        tileset_name = self._tileset_display_name(paths[self.editor.selected_tileset_index])
        self.editor.status_message = (
            f"Tileset {self.editor.selected_tileset_index + 1}/{len(paths)}: {tileset_name}"
        )

    def _tileset_display_name(self, tileset_path: str) -> str:
        """Return a compact, readable label for nested asset paths."""
        path = Path(tileset_path)
        parts = path.parts
        if len(parts) >= 3:
            return f"{parts[-2]}/{path.stem}"
        return path.stem

    def _tileset_selector_button_rects(self) -> tuple[pygame.Rect, pygame.Rect]:
        """Return the clickable button rects for the left-panel tileset selector."""
        y = self.left_rect.y + 4
        button_w = 22
        button_h = 20
        prev_rect = pygame.Rect(self.left_rect.x + 8, y, button_w, button_h)
        next_rect = pygame.Rect(self.left_rect.right - 8 - button_w, y, button_w, button_h)
        return prev_rect, next_rect

    def _tileset_grid_rect(self) -> pygame.Rect:
        """Return the scrollable tileset-grid viewport inside the left panel."""
        top = self.left_rect.y + 28
        height = max(0, self._area_tiles_top_y() - top - 8)
        return pygame.Rect(self.left_rect.x, top, self.LEFT_PANEL_W, height)

    def _tileset_content_size(self) -> tuple[int, int]:
        """Return the full pixel size of the currently selected tileset sheet."""
        tileset_path = self.editor.current_tileset_path
        if not tileset_path:
            return (0, 0)

        tile_w = self.editor.area.tile_size
        tile_h = self.editor.area.tile_size
        frame_px = tile_w * self.TILESET_ZOOM
        columns = max(1, self.asset_manager.get_columns(tileset_path, tile_w))
        frame_count = self.asset_manager.get_frame_count(tileset_path, tile_w, tile_h)
        rows = (frame_count + columns - 1) // columns if frame_count > 0 else 0
        return (columns * frame_px, rows * frame_px)

    def _clamp_tileset_scroll(self) -> None:
        """Keep left-panel tileset panning within the visible content bounds."""
        grid_rect = self._tileset_grid_rect()
        content_w, content_h = self._tileset_content_size()
        max_x = max(0, content_w - grid_rect.width)
        max_y = max(0, content_h - grid_rect.height)
        self.tileset_scroll_x = max(0, min(self.tileset_scroll_x, max_x))
        self.tileset_scroll_y = max(0, min(self.tileset_scroll_y, max_y))

    def _pan_tileset_grid(self, delta_x: int, delta_y: int) -> None:
        """Pan the left-panel tileset view like a grab-scroll surface."""
        self.tileset_scroll_x += delta_x
        self.tileset_scroll_y += delta_y
        self._clamp_tileset_scroll()

    def _paint_layer_row_rect(self, index: int) -> pygame.Rect:
        """Return the clickable/drawn rect for a paint-mode layer row."""
        return pygame.Rect(
            self.right_rect.x + 8,
            self.right_rect.y + 90 + index * 28,
            self.RIGHT_PANEL_W - 16,
            24,
        )

    def _paint_layer_toggle_rect(self, index: int) -> pygame.Rect:
        """Return the toggle-area rect for above/below-entities state."""
        row_rect = self._paint_layer_row_rect(index)
        return pygame.Rect(self.right_rect.right - 64, row_rect.y, 20, row_rect.height)

    def _paint_layer_delete_rect(self, index: int) -> pygame.Rect:
        """Return the delete-area rect for a paint-mode layer row."""
        row_rect = self._paint_layer_row_rect(index)
        return pygame.Rect(self.right_rect.right - 36, row_rect.y, 20, row_rect.height)

    def _paint_add_layer_rect(self, layer_count: int) -> pygame.Rect:
        """Return the add-layer button rect in paint mode."""
        return pygame.Rect(
            self.right_rect.x + 8,
            self.right_rect.y + 94 + layer_count * 28,
            80,
            22,
        )

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _screen_to_cell(self, screen_pos: tuple[int, int]) -> tuple[int, int] | None:
        local_x = screen_pos[0] - self.map_rect.x
        local_y = screen_pos[1] - self.map_rect.y
        world_x = local_x / self.map_zoom + self.camera.render_x
        world_y = local_y / self.map_zoom + self.camera.render_y
        grid_x = int(world_x // self.editor.area.tile_size)
        grid_y = int(world_y // self.editor.area.tile_size)
        if not self.editor.area.in_bounds(grid_x, grid_y):
            return None
        return (grid_x, grid_y)

    def _world_x_to_screen(self, world_x: float) -> int:
        return int((world_x - self.camera.render_x) * self.map_zoom) + self.map_rect.x

    def _world_y_to_screen(self, world_y: float) -> int:
        return int((world_y - self.camera.render_y) * self.map_zoom) + self.map_rect.y

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(self) -> None:
        self.display.fill(config.COLOR_BACKGROUND)
        self._draw_map()
        self._draw_toolbar()
        self._draw_left_panel()
        self._draw_right_panel()
        self._draw_status_bar()

    # --- Map ---

    def _draw_map(self) -> None:
        area = self.editor.area
        world = self.editor.world
        zoom = self.map_zoom
        tile_size = area.tile_size
        tile_px = tile_size * zoom

        self.display.set_clip(self.map_rect)
        pygame.draw.rect(self.display, self.COL_MAP_BG, self.map_rect)

        cam_x = self.camera.render_x
        cam_y = self.camera.render_y
        start_col = max(0, int(cam_x // tile_size))
        start_row = max(0, int(cam_y // tile_size))
        end_col = min(area.width, int((cam_x + self.map_rect.width / zoom) // tile_size) + 2)
        end_row = min(area.height, int((cam_y + self.map_rect.height / zoom) // tile_size) + 2)

        self._draw_tile_layers(area, start_col, start_row, end_col, end_row, draw_above_entities=False)
        self._draw_entities(area, world)
        self._draw_tile_layers(area, start_col, start_row, end_col, end_row, draw_above_entities=True)

        # Walk overlay
        if self.editor.paint_submode == "walk" or self.editor.show_walk_overlay:
            overlay = pygame.Surface((self.map_rect.width, self.map_rect.height), pygame.SRCALPHA)
            for gy in range(start_row, end_row):
                for gx in range(start_col, end_col):
                    flags = area.cell_flags[gy][gx]
                    walkable = flags.get("walkable", True)
                    color = self.COL_WALK_OK if walkable else self.COL_WALK_BLOCK
                    sx = self._world_x_to_screen(gx * tile_size) - self.map_rect.x
                    sy = self._world_y_to_screen(gy * tile_size) - self.map_rect.y
                    pygame.draw.rect(overlay, color, (sx, sy, tile_px, tile_px))
            self.display.blit(overlay, self.map_rect.topleft)

        # Grid
        grid_surface = pygame.Surface((self.map_rect.width, self.map_rect.height), pygame.SRCALPHA)
        for col in range(start_col, end_col + 1):
            sx = self._world_x_to_screen(col * tile_size) - self.map_rect.x
            pygame.draw.line(grid_surface, self.COL_GRID, (sx, 0), (sx, self.map_rect.height))
        for row in range(start_row, end_row + 1):
            sy = self._world_y_to_screen(row * tile_size) - self.map_rect.y
            pygame.draw.line(grid_surface, self.COL_GRID, (0, sy), (self.map_rect.width, sy))
        self.display.blit(grid_surface, self.map_rect.topleft)

        # Tile preview (paint mode, hovering)
        if self.editor.mode == "paint" and self.editor.hovered_cell is not None:
            gx, gy = self.editor.hovered_cell
            if self.editor.paint_submode == "tile" and self.editor.selected_gid > 0:
                resolved = area.resolve_gid(self.editor.selected_gid)
                if resolved:
                    ts_path, tw, th, local_frame = resolved
                    preview = self.asset_manager.get_frame(ts_path, tw, th, local_frame).copy()
                    if zoom != 1:
                        preview = pygame.transform.scale(preview, (tw * zoom, th * zoom))
                    preview.set_alpha(120)
                    self.display.blit(preview, (self._world_x_to_screen(gx * tile_size), self._world_y_to_screen(gy * tile_size)))

        # Move-pending ghost
        if self.editor.move_pending_entity_id and self.editor.hovered_cell is not None:
            preview_entity = self.editor.build_preview_entity()
            if preview_entity is not None:
                sx = self._world_x_to_screen(preview_entity.pixel_x)
                sy = self._world_y_to_screen(preview_entity.pixel_y)
                ghost = pygame.Surface((tile_px, tile_px), pygame.SRCALPHA)
                ghost.fill((*preview_entity.color, 100))
                self.display.blit(ghost, (sx, sy))

        # Selected cell
        if self.editor.selected_cell is not None:
            gx, gy = self.editor.selected_cell
            rect = pygame.Rect(self._world_x_to_screen(gx * tile_size), self._world_y_to_screen(gy * tile_size), tile_px, tile_px)
            pygame.draw.rect(self.display, self.COL_HIGHLIGHT, rect, width=2)

        # Hovered cell
        if self.editor.hovered_cell is not None:
            gx, gy = self.editor.hovered_cell
            hover_surf = pygame.Surface((tile_px, tile_px), pygame.SRCALPHA)
            hover_surf.fill(self.COL_HOVER)
            self.display.blit(hover_surf, (self._world_x_to_screen(gx * tile_size), self._world_y_to_screen(gy * tile_size)))

        self.display.set_clip(None)

    def _draw_tile_layers(self, area: Area, start_col: int, start_row: int, end_col: int, end_row: int, *, draw_above_entities: bool) -> None:
        zoom = self.map_zoom
        tile_size = area.tile_size
        for layer in area.iter_tile_layers(draw_above_entities=draw_above_entities):
            for gy in range(start_row, end_row):
                row = layer.grid[gy]
                for gx in range(start_col, end_col):
                    gid = row[gx]
                    if gid <= 0:
                        continue
                    resolved = area.resolve_gid(gid)
                    if resolved is None:
                        continue
                    ts_path, tw, th, local_frame = resolved
                    frame_surf = self.asset_manager.get_frame(ts_path, tw, th, local_frame)
                    if zoom != 1:
                        frame_surf = pygame.transform.scale(frame_surf, (tw * zoom, th * zoom))
                    self.display.blit(frame_surf, (self._world_x_to_screen(gx * tile_size), self._world_y_to_screen(gy * tile_size)))

    def _draw_entities(self, area: Area, world: World) -> None:
        zoom = self.map_zoom
        tile_size = area.tile_size
        for entity in sorted(
            world.iter_entities(),
            key=lambda e: (e.layer, e.pixel_y, e.stack_order, e.pixel_x, e.entity_id),
        ):
            if not entity.visible:
                continue
            sx = self._world_x_to_screen(entity.pixel_x)
            sy = self._world_y_to_screen(entity.pixel_y)

            if entity.sprite_path:
                sprite = self.asset_manager.get_frame(entity.sprite_path, entity.sprite_frame_width, entity.sprite_frame_height, entity.current_frame)
                if entity.color != (255, 255, 255):
                    sprite = sprite.copy()
                    sprite.fill((*entity.color, 255), special_flags=pygame.BLEND_RGBA_MULT)
                if zoom != 1:
                    sprite = pygame.transform.scale(sprite, (entity.sprite_frame_width * zoom, entity.sprite_frame_height * zoom))
                self.display.blit(sprite, (sx, sy))
            else:
                inset = (2 if entity.kind == "player" else 3) * zoom
                rect = pygame.Rect(sx + inset, sy + inset, tile_size * zoom - inset * 2, tile_size * zoom - inset * 2)
                pygame.draw.rect(self.display, entity.color, rect, border_radius=max(1, 2 * zoom))

    # --- Toolbar ---

    def _draw_toolbar(self) -> None:
        pygame.draw.rect(self.display, self.COL_TOOLBAR, self.toolbar_rect)
        pygame.draw.line(self.display, self.COL_BORDER, (0, self.TOOLBAR_H - 1), (self.win_w, self.TOOLBAR_H - 1))

        self._toolbar_buttons.clear()
        x = 8
        y = 6

        x = self._draw_toolbar_button("Save", x, y, False)
        x = self._draw_toolbar_button("Reload", x + 4, y, False)
        x += 16

        x = self._draw_toolbar_button("Paint", x, y, self.editor.mode == "paint")
        x = self._draw_toolbar_button("Select", x + 4, y, self.editor.mode == "select")
        x += 16

        layer_label = f"Layer: {self.editor.current_layer_name}"
        self._draw_text(layer_label, x, y + 4)

    def _draw_toolbar_button(self, label: str, x: int, y: int, active: bool) -> int:
        text_surf = self.font.render(label, True, config.COLOR_TEXT)
        w = text_surf.get_width() + 16
        h = 24
        rect = pygame.Rect(x, y, w, h)
        color = self.COL_BTN_ACTIVE if active else self.COL_BTN
        pygame.draw.rect(self.display, color, rect, border_radius=3)
        pygame.draw.rect(self.display, self.COL_BORDER, rect, 1, border_radius=3)
        self.display.blit(text_surf, (x + 8, y + 4))
        self._toolbar_buttons.append(_Button(label, rect, active))
        return x + w

    # --- Left Panel ---

    def _draw_left_panel(self) -> None:
        pygame.draw.rect(self.display, self.COL_PANEL, self.left_rect)
        pygame.draw.line(self.display, self.COL_BORDER,
                        (self.LEFT_PANEL_W - 1, self.TOOLBAR_H),
                        (self.LEFT_PANEL_W - 1, self.win_h - self.STATUS_H))

        y = self.left_rect.y + 4

        # Tileset selector
        prev_rect, next_rect = self._tileset_selector_button_rects()
        for rect, label in ((prev_rect, "<"), (next_rect, ">")):
            pygame.draw.rect(self.display, self.COL_BTN, rect, border_radius=2)
            pygame.draw.rect(self.display, self.COL_BORDER, rect, 1, border_radius=2)
            self._draw_text_small(label, rect.x + 7, rect.y + 4)

        tileset_count = len(self.editor.available_tileset_paths)
        if self.editor.current_tileset_path:
            tileset_name = self._tileset_display_name(self.editor.current_tileset_path)
            tileset_label = (
                f"{tileset_name} ({self.editor.selected_tileset_index + 1}/{tileset_count})"
                if tileset_count > 1
                else tileset_name
            )
        else:
            tileset_label = "(none)"

        label_rect = pygame.Rect(
            prev_rect.right + 8,
            y,
            max(0, next_rect.left - prev_rect.right - 16),
            20,
        )
        label_surface = self.font.render(tileset_label, True, config.COLOR_TEXT)
        label_x = label_rect.x + max(0, (label_rect.width - label_surface.get_width()) // 2)
        self.display.set_clip(label_rect)
        self.display.blit(label_surface, (label_x, y + 2))
        self.display.set_clip(None)
        y += 24

        # Tileset grid
        tileset_path = self.editor.current_tileset_path
        if tileset_path:
            self._clamp_tileset_scroll()
            tile_w = self.editor.area.tile_size
            tile_h = self.editor.area.tile_size
            frame_px = tile_w * self.TILESET_ZOOM
            columns = self.asset_manager.get_columns(tileset_path, tile_w)
            frame_count = self.asset_manager.get_frame_count(tileset_path, tile_w, tile_h)

            grid_clip = self._tileset_grid_rect()
            self.display.set_clip(grid_clip)

            selected_local_frame = -1
            if self.editor.paint_submode == "tile" and self.editor.selected_gid > 0:
                for ts in self.editor.area.tilesets:
                    if ts.path == tileset_path:
                        local = self.editor.selected_gid - ts.firstgid
                        if 0 <= local < frame_count:
                            selected_local_frame = local
                        break

            for frame_idx in range(frame_count):
                col = frame_idx % columns
                row = frame_idx // columns
                fx = self.left_rect.x + col * frame_px - self.tileset_scroll_x
                fy = y + row * frame_px - self.tileset_scroll_y

                frame_surf = self.asset_manager.get_frame(tileset_path, tile_w, tile_h, frame_idx)
                if self.TILESET_ZOOM != 1:
                    frame_surf = pygame.transform.scale(frame_surf, (frame_px, frame_px))
                self.display.blit(frame_surf, (fx, fy))

                if frame_idx == selected_local_frame:
                    pygame.draw.rect(self.display, self.COL_BTN_ACTIVE, (fx, fy, frame_px, frame_px), 2)

            self.display.set_clip(None)

        # Separator + Area tiles
        area_y = self._area_tiles_top_y()
        pygame.draw.line(self.display, self.COL_BORDER,
                        (self.left_rect.x + 8, area_y - 4),
                        (self.left_rect.x + self.LEFT_PANEL_W - 8, area_y - 4))
        self._draw_text("Area Tiles", self.left_rect.x + 8, area_y - 20, bold=True)

        walk_active = self.editor.paint_submode == "walk" and self.editor.walk_brush_walkable
        block_active = self.editor.paint_submode == "walk" and not self.editor.walk_brush_walkable

        walk_rect = pygame.Rect(self.left_rect.x + 8, area_y, self.LEFT_PANEL_W - 16, 22)
        col = self.COL_BTN_ACTIVE if walk_active else self.COL_BTN
        pygame.draw.rect(self.display, col, walk_rect, border_radius=2)
        pygame.draw.rect(self.display, (48, 180, 96), (walk_rect.x + 4, walk_rect.y + 4, 14, 14))
        self._draw_text("Walkable", walk_rect.x + 24, walk_rect.y + 3)

        block_rect = pygame.Rect(self.left_rect.x + 8, area_y + 26, self.LEFT_PANEL_W - 16, 22)
        col = self.COL_BTN_ACTIVE if block_active else self.COL_BTN
        pygame.draw.rect(self.display, col, block_rect, border_radius=2)
        pygame.draw.rect(self.display, (200, 64, 64), (block_rect.x + 4, block_rect.y + 4, 14, 14))
        self._draw_text("Blocked", block_rect.x + 24, block_rect.y + 3)

    def _area_tiles_top_y(self) -> int:
        """Return the Y position where the area tiles section starts."""
        return self.left_rect.y + self.left_rect.height - 80

    # --- Right Panel ---

    def _draw_right_panel(self) -> None:
        pygame.draw.rect(self.display, self.COL_PANEL, self.right_rect)
        pygame.draw.line(self.display, self.COL_BORDER,
                        (self.right_rect.x, self.TOOLBAR_H),
                        (self.right_rect.x, self.win_h - self.STATUS_H))

        if self.editor.mode == "paint":
            self._draw_right_panel_paint()
        elif self.editor.mode == "select":
            self._draw_right_panel_select()

    def _draw_right_panel_paint(self) -> None:
        """Draw paint mode right panel: brush preview + layer management."""
        rx = self.right_rect.x + 8
        ry = self.right_rect.y + 8

        self._draw_text("Brush", rx, ry, bold=True)
        ry += 20
        if self.editor.paint_submode == "tile" and self.editor.selected_gid > 0:
            resolved = self.editor.area.resolve_gid(self.editor.selected_gid)
            if resolved:
                ts_path, tw, th, local_frame = resolved
                preview = self.asset_manager.get_frame(ts_path, tw, th, local_frame)
                preview = pygame.transform.scale(preview, (tw * 2, th * 2))
                self.display.blit(preview, (rx, ry))
                self._draw_text(self.editor.current_gid_label, rx + tw * 2 + 8, ry + 4)
        elif self.editor.paint_submode == "walk":
            label = "Walkable" if self.editor.walk_brush_walkable else "Blocked"
            color = (48, 180, 96) if self.editor.walk_brush_walkable else (200, 64, 64)
            pygame.draw.rect(self.display, color, (rx, ry, 32, 32))
            self._draw_text(label, rx + 40, ry + 8)
        ry += 40

        self._draw_text("Layers", rx, ry, bold=True)
        ry += 22

        layers = self.editor.area.tile_layers
        for i, layer in enumerate(layers):
            active = i == self.editor.selected_layer_index
            row_rect = self._paint_layer_row_rect(i)

            if active:
                pygame.draw.rect(self.display, self.COL_SELECTION_BG, row_rect, border_radius=2)

            if self.renaming_layer_index == i:
                # Editable text field for rename
                name_rect = pygame.Rect(row_rect.x + 2, row_rect.y + 2, self.RIGHT_PANEL_W - 80, 20)
                pygame.draw.rect(self.display, (50, 55, 70), name_rect)
                pygame.draw.rect(self.display, self.COL_BTN_ACTIVE, name_rect, 1)
                self._draw_text(self.rename_text + "|", row_rect.x + 6, row_rect.y + 4)
            else:
                self._draw_text(layer.name, row_rect.x + 4, row_rect.y + 4)

            above_label = "A" if layer.draw_above_entities else "B"
            toggle_rect = self._paint_layer_toggle_rect(i)
            self._draw_text(above_label, toggle_rect.x + 5, row_rect.y + 4)

            delete_rect = self._paint_layer_delete_rect(i)
            self._draw_text("X", delete_rect.x + 5, row_rect.y + 4)

        add_rect = self._paint_add_layer_rect(len(layers))
        pygame.draw.rect(self.display, self.COL_BTN, add_rect, border_radius=2)
        self._draw_text("+ Layer", add_rect.x + 8, add_rect.y + 3)

    def _draw_right_panel_select(self) -> None:
        """Draw select mode right panel: entity stack + properties."""
        rx = self.right_rect.x + 8
        ry = self.right_rect.y + 8

        if self.editor.selected_cell is None:
            self._draw_text("No cell selected", rx, ry)
            return

        gx, gy = self.editor.selected_cell
        self._draw_text(f"Cell ({gx}, {gy})", rx, ry, bold=True)
        ry += 22

        entities = self.editor.entities_for_selected_cell()
        for i, entity in enumerate(entities):
            active = entity.entity_id == self.editor.selected_entity_id
            row_rect = pygame.Rect(rx, ry, self.RIGHT_PANEL_W - 16, 22)
            if active:
                pygame.draw.rect(self.display, self.COL_SELECTION_BG, row_rect, border_radius=2)

            kind_label = entity.template_id or entity.kind
            label = f"{i + 1}. {entity.entity_id} ({kind_label})"
            max_label_w = self.RIGHT_PANEL_W - 120
            text_surf = self.font_small.render(label, True, config.COLOR_TEXT)
            if text_surf.get_width() > max_label_w:
                label = label[:20] + "..."
            self._draw_text_small(label, rx + 4, ry + 3)

            btn_x = self.right_rect.x + self.RIGHT_PANEL_W - 8

            btn_x -= 40
            self._draw_text_small("Move", btn_x, ry + 3)

            if entity.entity_id != self.editor.world.player_id:
                btn_x -= 20
                self._draw_text_small("X", btn_x, ry + 3)
            else:
                btn_x -= 20

            btn_x -= 16
            self._draw_text_small("v", btn_x, ry + 3)
            btn_x -= 14
            self._draw_text_small("^", btn_x, ry + 3)

            ry += 24

        ry += 8
        self._draw_text("Add Entity", rx, ry, bold=True)
        ry += 20

        # Template selector: [<] button — template name — [>] button — [Add] button
        btn_w = 22
        btn_h = 22
        prev_rect = pygame.Rect(rx, ry, btn_w, btn_h)
        pygame.draw.rect(self.display, self.COL_BTN, prev_rect, border_radius=2)
        pygame.draw.rect(self.display, self.COL_BORDER, prev_rect, 1, border_radius=2)
        self._draw_text_small("<", prev_rect.x + 7, prev_rect.y + 4)

        template_id = self.editor.current_template_id or "(none)"
        self._draw_text_small(template_id, rx + btn_w + 8, ry + 4)

        add_w = 36
        next_x = self.right_rect.x + self.RIGHT_PANEL_W - 8 - add_w - 4 - btn_w
        next_rect = pygame.Rect(next_x, ry, btn_w, btn_h)
        pygame.draw.rect(self.display, self.COL_BTN, next_rect, border_radius=2)
        pygame.draw.rect(self.display, self.COL_BORDER, next_rect, 1, border_radius=2)
        self._draw_text_small(">", next_rect.x + 7, next_rect.y + 4)

        add_rect = pygame.Rect(self.right_rect.x + self.RIGHT_PANEL_W - 8 - add_w, ry, add_w, btn_h)
        pygame.draw.rect(self.display, self.COL_BTN, add_rect, border_radius=2)
        pygame.draw.rect(self.display, self.COL_BORDER, add_rect, 1, border_radius=2)
        self._draw_text_small("Add", add_rect.x + 8, add_rect.y + 4)
        ry += 30

        props = self.editor.selected_entity_properties()
        if not props:
            return

        pygame.draw.line(self.display, self.COL_BORDER, (rx, ry), (rx + self.RIGHT_PANEL_W - 16, ry))
        ry += 4

        for field_name, display_label, current_value in props:
            is_editing = (
                self.editing_field == field_name
                and self.editing_entity_id == self.editor.selected_entity_id
            )

            self._draw_text_small(f"{display_label}:", rx + 4, ry + 3)

            value_x = rx + 90
            if is_editing:
                edit_rect = pygame.Rect(value_x, ry, self.RIGHT_PANEL_W - 106, 18)
                pygame.draw.rect(self.display, (50, 55, 70), edit_rect)
                pygame.draw.rect(self.display, self.COL_BTN_ACTIVE, edit_rect, 1)
                self._draw_text_small(self.editing_text + "|", value_x + 2, ry + 3)
            elif field_name in ("template_id", "kind"):
                self._draw_text_small(current_value, value_x, ry + 3)
            elif field_name in ("solid", "pushable", "present", "visible", "events_enabled"):
                color = (100, 200, 120) if current_value == "true" else (180, 100, 100)
                self._draw_text_small(current_value, value_x, ry + 3, color=color)
            elif field_name == "facing":
                self._draw_text_small(current_value, value_x, ry + 3, color=(140, 170, 220))
            else:
                self._draw_text_small(current_value, value_x, ry + 3, color=(180, 180, 140))

            ry += 22

    # --- Status Bar ---

    def _draw_status_bar(self) -> None:
        pygame.draw.rect(self.display, self.COL_STATUS, self.status_rect)
        pygame.draw.line(self.display, self.COL_BORDER, (0, self.status_rect.y), (self.win_w, self.status_rect.y))

        parts = []
        if self.editor.paint_submode == "tile":
            parts.append(f"Brush: {self.editor.current_gid_label}")
        else:
            parts.append(f"Brush: {self.editor.current_walk_brush_label}")
        if self.editor.hovered_cell:
            parts.append(f"Hover ({self.editor.hovered_cell[0]},{self.editor.hovered_cell[1]})")
        if self.editor.selected_cell:
            parts.append(f"Sel ({self.editor.selected_cell[0]},{self.editor.selected_cell[1]})")
        parts.append(f"Dirty: {self.editor.dirty_label}")
        if self.editor.move_pending_entity_id:
            parts.append(f"Moving: {self.editor.move_pending_entity_id}")
        parts.append(self.editor.status_message)

        self._draw_text("  |  ".join(parts), self.status_rect.x + 8, self.status_rect.y + 4)

    # --- Text helpers ---

    def _draw_text(self, text: str, x: int, y: int, bold: bool = False) -> None:
        font = self.font_bold if bold else self.font
        surface = font.render(text, True, config.COLOR_TEXT)
        self.display.blit(surface, (x, y))

    def _draw_text_small(self, text: str, x: int, y: int, color: tuple[int, int, int] = config.COLOR_TEXT) -> None:
        surface = self.font_small.render(text, True, color)
        self.display.blit(surface, (x, y))
