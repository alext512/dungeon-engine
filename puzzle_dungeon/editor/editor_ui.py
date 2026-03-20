"""Screen-resolution editor UI overlay with toolbar and contextual popups.

Renders at native display resolution (960x720) on top of the scaled pixel-art
game view. Handles toolbar interaction, popup lifecycle, and event routing.

Depends on: config, level_editor
Used by: game, renderer
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pygame

from puzzle_dungeon import config
from puzzle_dungeon.world.loader import instantiate_entity

if TYPE_CHECKING:
    from puzzle_dungeon.editor.level_editor import LevelEditor
    from puzzle_dungeon.engine.asset_manager import AssetManager
    from puzzle_dungeon.engine.camera import Camera

# -- Screen layout constants --
SCREEN_W = config.INTERNAL_WIDTH * config.SCALE
SCREEN_H = config.INTERNAL_HEIGHT * config.SCALE
TOOLBAR_H = 36
STATUS_H = 24
TILE_DISPLAY_SCALE = 3
DOUBLE_CLICK_MS = 400

# -- UI Colors --
C_BG = (24, 28, 36)
C_PANEL = (34, 38, 48)
C_BORDER = (70, 78, 96)
C_BTN = (48, 54, 68)
C_BTN_HOVER = (62, 70, 88)
C_BTN_ACTIVE = (80, 120, 190)
C_TEXT = (226, 230, 238)
C_TEXT_DIM = (140, 148, 165)
C_HIGHLIGHT = (100, 160, 240)
C_DANGER = (200, 70, 70)
C_WALK = (48, 180, 96)
C_BLOCK = (200, 64, 64)

# ---- Font helpers (lazy-init to avoid calling before pygame.init) ----

_font_cache: dict[str, pygame.font.Font] = {}


def _font(size: int = 14, bold: bool = False) -> pygame.font.Font:
    key = f"{size}_{bold}"
    if key not in _font_cache:
        _font_cache[key] = pygame.font.SysFont("consolas,courier new,monospace", size, bold=bold)
    return _font_cache[key]


def _text(surface: pygame.Surface, text: str, pos: tuple[int, int],
          color: tuple[int, int, int] = C_TEXT, size: int = 14,
          bold: bool = False, center_in: pygame.Rect | None = None) -> tuple[int, int]:
    rendered = _font(size, bold).render(str(text), True, color)
    if center_in is not None:
        surface.blit(rendered, rendered.get_rect(center=center_in.center))
    else:
        surface.blit(rendered, pos)
    return rendered.get_size()


def _btn(surface: pygame.Surface, rect: pygame.Rect, label: str,
         active: bool = False, hover: bool = False, danger: bool = False) -> None:
    bg = C_DANGER if danger else C_BTN_ACTIVE if active else C_BTN_HOVER if hover else C_BTN
    pygame.draw.rect(surface, bg, rect, border_radius=3)
    pygame.draw.rect(surface, C_BORDER, rect, width=1, border_radius=3)
    _text(surface, label, (0, 0), center_in=rect)


def _popup_bg(surface: pygame.Surface, rect: pygame.Rect) -> None:
    overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 100))
    surface.blit(overlay, (0, 0))
    pygame.draw.rect(surface, C_BG, rect, border_radius=6)
    pygame.draw.rect(surface, C_BORDER, rect, width=1, border_radius=6)


# =====================================================================
#  Brush Picker Popup
# =====================================================================

class BrushPickerPopup:
    """Popup for selecting tile brush or walkability brush."""

    WIDTH = 510
    HEIGHT = 420
    TAB_H = 30
    SELECTOR_H = 28

    def __init__(self, asset_manager: AssetManager, editor: LevelEditor) -> None:
        self.asset_manager = asset_manager
        self.tab: str = "tiles" if editor.paint_submode == "tile" else "walk"
        self.scroll_y: int = 0
        self.rect = pygame.Rect(
            (SCREEN_W - self.WIDTH) // 2,
            (SCREEN_H - self.HEIGHT) // 2,
            self.WIDTH, self.HEIGHT,
        )
        self._scaled_cache: dict[str, pygame.Surface] = {}

    def handle_event(self, event: pygame.event.Event, editor: LevelEditor) -> str | None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "close"
            if event.key in (pygame.K_LEFTBRACKET, pygame.K_RIGHTBRACKET) and self.tab == "tiles":
                direction = -1 if event.key == pygame.K_LEFTBRACKET else 1
                n = len(editor.available_tileset_paths)
                if n > 0:
                    editor.selected_tileset_index = (editor.selected_tileset_index + direction) % n
                    self.scroll_y = 0
                return None

        if event.type == pygame.MOUSEBUTTONDOWN:
            if not self.rect.collidepoint(event.pos):
                return "close"

            rx, ry = event.pos[0] - self.rect.x, event.pos[1] - self.rect.y

            # Tab bar
            if ry < self.TAB_H:
                if rx < self.WIDTH // 2:
                    self.tab = "tiles"
                else:
                    self.tab = "walk"
                return None

            # Close button
            if rx > self.WIDTH - 30 and ry < self.TAB_H:
                return "close"

            if self.tab == "walk":
                return self._handle_walk_click(rx, ry, editor)
            else:
                return self._handle_tiles_click(rx, ry, editor)

        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            if self.rect.collidepoint(event.pos) and self.tab == "tiles":
                self.scroll_y += -48 if event.button == 4 else 48
                self.scroll_y = max(0, self.scroll_y)
                return None

        if event.type == pygame.MOUSEWHEEL:
            if self.rect.collidepoint(pygame.mouse.get_pos()) and self.tab == "tiles":
                self.scroll_y -= event.y * 48
                self.scroll_y = max(0, self.scroll_y)
                return None

        return None

    def _handle_walk_click(self, rx: int, ry: int, editor: LevelEditor) -> str | None:
        content_y = self.TAB_H + 20
        walk_rect = pygame.Rect(20, content_y, 200, 60)
        block_rect = pygame.Rect(self.WIDTH - 220, content_y, 200, 60)
        click_pt = (rx, ry)
        if walk_rect.collidepoint(click_pt):
            editor.walk_brush_walkable = True
            editor.paint_submode = "walk"
            editor.status_message = "Brush: walkable"
            return "close"
        if block_rect.collidepoint(click_pt):
            editor.walk_brush_walkable = False
            editor.paint_submode = "walk"
            editor.status_message = "Brush: blocked"
            return "close"
        return None

    def _handle_tiles_click(self, rx: int, ry: int, editor: LevelEditor) -> str | None:
        # Tileset prev/next arrows
        selector_y = self.TAB_H + 4
        if selector_y <= ry < selector_y + self.SELECTOR_H:
            n = len(editor.available_tileset_paths)
            if n > 0:
                if rx < 40:
                    editor.selected_tileset_index = (editor.selected_tileset_index - 1) % n
                    self.scroll_y = 0
                elif rx > self.WIDTH - 40:
                    editor.selected_tileset_index = (editor.selected_tileset_index + 1) % n
                    self.scroll_y = 0
            return None

        # Tile frame click
        grid_top = self.TAB_H + self.SELECTOR_H + 12
        if ry >= grid_top:
            tile_size = editor.area.tile_size
            display_size = tile_size * TILE_DISPLAY_SCALE
            grid_x_offset = 10
            col = (rx - grid_x_offset) // display_size
            row = (ry - grid_top + self.scroll_y) // display_size
            columns = (self.WIDTH - 20) // display_size

            if col < 0 or col >= columns:
                return None

            frame_index = row * columns + col
            tileset_path = editor.current_tileset_path
            if tileset_path:
                frame_count = self.asset_manager.get_frame_count(
                    tileset_path, tile_size, tile_size
                )
                if 0 <= frame_index < frame_count:
                    editor.select_tileset_frame(editor.selected_tileset_index, frame_index)
                    editor.paint_submode = "tile"
                    mods = pygame.key.get_mods()
                    if not (mods & pygame.KMOD_SHIFT):
                        return "close"
        return None

    def render(self, surface: pygame.Surface, editor: LevelEditor) -> None:
        _popup_bg(surface, self.rect)
        x, y = self.rect.x, self.rect.y

        # Tab bar
        tiles_rect = pygame.Rect(x + 4, y + 4, self.WIDTH // 2 - 8, self.TAB_H - 8)
        walk_rect = pygame.Rect(x + self.WIDTH // 2 + 4, y + 4, self.WIDTH // 2 - 38, self.TAB_H - 8)
        _btn(surface, tiles_rect, "Tiles", active=(self.tab == "tiles"))
        _btn(surface, walk_rect, "Walkability", active=(self.tab == "walk"))
        close_rect = pygame.Rect(x + self.WIDTH - 30, y + 4, 26, self.TAB_H - 8)
        _btn(surface, close_rect, "X")

        if self.tab == "walk":
            self._render_walk_tab(surface, x, y, editor)
        else:
            self._render_tiles_tab(surface, x, y, editor)

    def _render_walk_tab(self, surface: pygame.Surface, x: int, y: int, editor: LevelEditor) -> None:
        content_y = y + self.TAB_H + 20
        walk_rect = pygame.Rect(x + 20, content_y, 200, 60)
        block_rect = pygame.Rect(x + self.WIDTH - 220, content_y, 200, 60)

        walk_active = editor.paint_submode == "walk" and editor.walk_brush_walkable
        block_active = editor.paint_submode == "walk" and not editor.walk_brush_walkable

        pygame.draw.rect(surface, C_WALK if walk_active else (30, 80, 50), walk_rect, border_radius=4)
        pygame.draw.rect(surface, C_WALK, walk_rect, width=2, border_radius=4)
        _text(surface, "Walkable", (0, 0), color=C_TEXT, size=16, bold=True, center_in=walk_rect)

        pygame.draw.rect(surface, C_BLOCK if block_active else (80, 30, 30), block_rect, border_radius=4)
        pygame.draw.rect(surface, C_BLOCK, block_rect, width=2, border_radius=4)
        _text(surface, "Blocked", (0, 0), color=C_TEXT, size=16, bold=True, center_in=block_rect)

        _text(surface, "Click to select walkability brush", (x + 20, content_y + 80), color=C_TEXT_DIM, size=12)

    def _render_tiles_tab(self, surface: pygame.Surface, x: int, y: int, editor: LevelEditor) -> None:
        # Tileset selector row
        selector_y = y + self.TAB_H + 4
        tileset_path = editor.current_tileset_path
        stem = Path(tileset_path).stem if tileset_path else "(none)"
        prev_rect = pygame.Rect(x + 10, selector_y, 30, self.SELECTOR_H)
        next_rect = pygame.Rect(x + self.WIDTH - 40, selector_y, 30, self.SELECTOR_H)
        _btn(surface, prev_rect, "<")
        _btn(surface, next_rect, ">")
        _text(surface, stem, (x + 50, selector_y + 6), bold=True)

        if not tileset_path:
            _text(surface, "No tilesets found", (x + 20, selector_y + 40), color=C_TEXT_DIM)
            return

        # Tile frame grid
        tile_size = editor.area.tile_size
        display_size = tile_size * TILE_DISPLAY_SCALE
        grid_top = selector_y + self.SELECTOR_H + 8
        grid_left = x + 10
        columns = (self.WIDTH - 20) // display_size
        grid_area_h = self.rect.bottom - grid_top - 8

        # Clip to grid area
        clip_rect = pygame.Rect(grid_left, grid_top, columns * display_size, grid_area_h)
        old_clip = surface.get_clip()
        surface.set_clip(clip_rect)

        # Get or build scaled tileset surface
        scaled_img = self._get_scaled_tileset(tileset_path, tile_size)
        if scaled_img is None:
            surface.set_clip(old_clip)
            return

        frame_count = self.asset_manager.get_frame_count(tileset_path, tile_size, tile_size)
        img_columns = self.asset_manager.get_columns(tileset_path, tile_size)
        total_rows = (frame_count + columns - 1) // columns

        # Draw frames
        for frame_idx in range(frame_count):
            row = frame_idx // columns
            col = frame_idx % columns
            dest_x = grid_left + col * display_size
            dest_y = grid_top + row * display_size - self.scroll_y

            if dest_y + display_size < grid_top or dest_y > self.rect.bottom:
                continue

            # Source rect from original tileset
            src_col = frame_idx % img_columns
            src_row = frame_idx // img_columns
            src_rect = pygame.Rect(
                src_col * tile_size * TILE_DISPLAY_SCALE,
                src_row * tile_size * TILE_DISPLAY_SCALE,
                display_size, display_size,
            )
            surface.blit(scaled_img, (dest_x, dest_y), src_rect)
            pygame.draw.rect(surface, C_BORDER, (dest_x, dest_y, display_size, display_size), width=1)

        # Highlight selected frame
        if editor.selected_gid > 0:
            resolved = editor.area.resolve_gid(editor.selected_gid)
            if resolved is not None:
                ts_path, _, _, local_frame = resolved
                if ts_path == tileset_path:
                    sel_row = local_frame // columns
                    sel_col = local_frame % columns
                    sel_x = grid_left + sel_col * display_size
                    sel_y = grid_top + sel_row * display_size - self.scroll_y
                    pygame.draw.rect(surface, C_HIGHLIGHT,
                                     (sel_x, sel_y, display_size, display_size), width=2)

        surface.set_clip(old_clip)

        # Scroll hint
        max_scroll = max(0, total_rows * display_size - grid_area_h)
        self.scroll_y = min(self.scroll_y, max_scroll)

    def _get_scaled_tileset(self, tileset_path: str, tile_size: int) -> pygame.Surface | None:
        if tileset_path in self._scaled_cache:
            return self._scaled_cache[tileset_path]
        try:
            img = self.asset_manager.get_image(tileset_path)
        except Exception:
            return None
        scaled = pygame.transform.scale(
            img, (img.get_width() * TILE_DISPLAY_SCALE, img.get_height() * TILE_DISPLAY_SCALE)
        )
        self._scaled_cache[tileset_path] = scaled
        return scaled


# =====================================================================
#  Cell Inspector Popup
# =====================================================================

class CellInspectorPopup:
    """Popup for managing entities at a specific cell."""

    WIDTH = 420
    ROW_H = 26
    BTN_SIZE = 22
    PROP_ROW_H = 24

    def __init__(self, cell: tuple[int, int], editor: LevelEditor, asset_manager: AssetManager) -> None:
        self.cell = cell
        self.asset_manager = asset_manager
        self.selected_entity_id: str | None = editor.selected_entity_id
        self.editing_field: str | None = None
        self.edit_buffer: str = ""
        self.edit_entity_id: str | None = None
        self.add_template_index: int = editor.selected_template_index
        self._layout_height(editor)
        self.rect = pygame.Rect(
            (SCREEN_W - self.WIDTH) // 2,
            (SCREEN_H - self._total_h) // 2,
            self.WIDTH, self._total_h,
        )

    def _layout_height(self, editor: LevelEditor) -> None:
        entities = editor.world.get_entities_at(self.cell[0], self.cell[1], include_hidden=True)
        entity_count = len(list(entities))
        header = 32
        entity_list = 22 + max(1, entity_count) * self.ROW_H + 8
        add_row = 34
        props = 22 + 6 * self.PROP_ROW_H + 8
        self._total_h = min(560, header + entity_list + add_row + props)

    def handle_event(self, event: pygame.event.Event, editor: LevelEditor) -> str | None:
        if event.type == pygame.KEYDOWN:
            if self.editing_field is not None:
                return self._handle_edit_key(event, editor)
            if event.key == pygame.K_ESCAPE:
                return "close"

        if event.type == pygame.TEXTINPUT and self.editing_field is not None:
            self.edit_buffer += event.text
            return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.rect.collidepoint(event.pos):
                return "close"
            return self._handle_click(event.pos, editor)

        return None

    def _handle_edit_key(self, event: pygame.event.Event, editor: LevelEditor) -> str | None:
        if event.key == pygame.K_RETURN:
            if self.edit_entity_id and self.editing_field:
                editor.set_entity_property(self.edit_entity_id, self.editing_field, self.edit_buffer)
            self.editing_field = None
            return None
        if event.key == pygame.K_ESCAPE:
            self.editing_field = None
            return None
        if event.key == pygame.K_BACKSPACE:
            self.edit_buffer = self.edit_buffer[:-1]
            return None
        return None

    def _handle_click(self, pos: tuple[int, int], editor: LevelEditor) -> str | None:
        rx = pos[0] - self.rect.x
        ry = pos[1] - self.rect.y

        # Close button
        if rx > self.WIDTH - 30 and ry < 32:
            return "close"

        entities = list(editor.world.get_entities_at(self.cell[0], self.cell[1], include_hidden=True))
        header_h = 32
        list_label_h = 22

        # Entity list area
        list_top = header_h + list_label_h
        for i, entity in enumerate(entities):
            row_y = list_top + i * self.ROW_H
            if row_y <= ry < row_y + self.ROW_H:
                btn_x_start = self.WIDTH - 10 - 4 * (self.BTN_SIZE + 4)
                is_player = entity.entity_id == editor.world.player_id

                # Check action buttons (right to left: M, X, v, ^)
                btns_x = self.WIDTH - 10
                if not is_player:
                    # [M] move button
                    btns_x -= self.BTN_SIZE + 4
                    if btns_x <= rx < btns_x + self.BTN_SIZE:
                        editor.move_pending_entity_id = entity.entity_id
                        editor.status_message = f"Click destination for {entity.entity_id} (Esc cancel)"
                        return "close"

                    # [X] delete button
                    btns_x -= self.BTN_SIZE + 4
                    if btns_x <= rx < btns_x + self.BTN_SIZE:
                        editor.world.remove_entity(entity.entity_id)
                        editor._mark_dirty(f"Removed {entity.entity_id}")
                        if self.selected_entity_id == entity.entity_id:
                            self.selected_entity_id = None
                        self._layout_height(editor)
                        self.rect.height = self._total_h
                        return None

                # [v] down button
                btns_x -= self.BTN_SIZE + 4
                if btns_x <= rx < btns_x + self.BTN_SIZE:
                    if i < len(entities) - 1:
                        editor.selected_entity_id = entity.entity_id
                        editor._move_selected_entity(1)
                    return None

                # [^] up button
                btns_x -= self.BTN_SIZE + 4
                if btns_x <= rx < btns_x + self.BTN_SIZE:
                    if i > 0:
                        editor.selected_entity_id = entity.entity_id
                        editor._move_selected_entity(-1)
                    return None

                # Clicked on entity row - select it
                self.selected_entity_id = entity.entity_id
                editor.selected_entity_id = entity.entity_id
                self.editing_field = None
                return None

        # Add entity row
        add_y = list_top + len(entities) * self.ROW_H + 8
        if add_y <= ry < add_y + 28:
            # Prev/next template buttons
            n = len(editor.template_ids)
            if n > 0:
                if rx < 100:
                    self.add_template_index = (self.add_template_index - 1) % n
                    return None
                if 100 <= rx < self.WIDTH - 80:
                    self.add_template_index = (self.add_template_index + 1) % n
                    return None
                # Add button
                if rx >= self.WIDTH - 80:
                    template_id = editor.template_ids[self.add_template_index]
                    editor.selected_template_index = self.add_template_index
                    editor._place_entity(self.cell[0], self.cell[1])
                    self._layout_height(editor)
                    self.rect.height = self._total_h
                    return None
            return None

        # Properties area - check for property clicks
        props_top = add_y + 34
        if ry >= props_top and self.selected_entity_id:
            entity = editor.world.get_entity(self.selected_entity_id)
            if entity:
                props = editor.selected_entity_properties()
                prop_idx = (ry - props_top - 20) // self.PROP_ROW_H
                if 0 <= prop_idx < len(props):
                    field_name, label, value = props[prop_idx]
                    if field_name in ("template_id", "kind"):
                        return None  # read-only

                    # Boolean fields: toggle on click
                    if field_name in ("solid", "pushable", "enabled", "visible"):
                        new_val = "false" if value == "true" else "true"
                        editor.set_entity_property(self.selected_entity_id, field_name, new_val)
                        return None

                    # Facing: cycle
                    if field_name == "facing":
                        cycle = ["up", "right", "down", "left"]
                        idx = cycle.index(value) if value in cycle else 0
                        new_val = cycle[(idx + 1) % 4]
                        editor.set_entity_property(self.selected_entity_id, field_name, new_val)
                        return None

                    # Template params: start text editing
                    self.editing_field = field_name
                    self.edit_entity_id = self.selected_entity_id
                    self.edit_buffer = value
                    return None

        return None

    def render(self, surface: pygame.Surface, editor: LevelEditor) -> None:
        _popup_bg(surface, self.rect)
        x, y = self.rect.x, self.rect.y

        # Header
        _text(surface, f"Cell ({self.cell[0]}, {self.cell[1]})", (x + 12, y + 8), bold=True)
        close_rect = pygame.Rect(x + self.WIDTH - 30, y + 4, 26, 24)
        _btn(surface, close_rect, "X")

        entities = list(editor.world.get_entities_at(self.cell[0], self.cell[1], include_hidden=True))
        header_h = 32

        # Entity list label
        _text(surface, "Entities:", (x + 12, y + header_h + 2), color=C_TEXT_DIM, size=12)
        list_top = y + header_h + 22

        if not entities:
            _text(surface, "(empty)", (x + 20, list_top + 4), color=C_TEXT_DIM)
        else:
            for i, entity in enumerate(entities):
                row_y = list_top + i * self.ROW_H
                is_selected = entity.entity_id == self.selected_entity_id
                is_player = entity.entity_id == editor.world.player_id

                # Row background
                if is_selected:
                    pygame.draw.rect(surface, (40, 50, 70),
                                     (x + 4, row_y, self.WIDTH - 8, self.ROW_H))

                # Entity info
                idx_label = f"{i + 1}."
                id_label = entity.entity_id
                kind_label = f"({entity.kind})"
                _text(surface, idx_label, (x + 12, row_y + 4), size=12, color=C_TEXT_DIM)
                _text(surface, id_label, (x + 32, row_y + 4), bold=is_selected)
                _text(surface, kind_label, (x + 180, row_y + 4), color=C_TEXT_DIM, size=12)

                # Action buttons
                btns_x = x + self.WIDTH - 10
                if not is_player:
                    btns_x -= self.BTN_SIZE + 4
                    _btn(surface, pygame.Rect(btns_x, row_y + 2, self.BTN_SIZE, self.BTN_SIZE), "M")
                    btns_x -= self.BTN_SIZE + 4
                    _btn(surface, pygame.Rect(btns_x, row_y + 2, self.BTN_SIZE, self.BTN_SIZE), "X",
                         danger=True)
                btns_x -= self.BTN_SIZE + 4
                _btn(surface, pygame.Rect(btns_x, row_y + 2, self.BTN_SIZE, self.BTN_SIZE), "v")
                btns_x -= self.BTN_SIZE + 4
                _btn(surface, pygame.Rect(btns_x, row_y + 2, self.BTN_SIZE, self.BTN_SIZE), "^")

        # Add entity row
        add_y = list_top + len(entities) * self.ROW_H + 8
        pygame.draw.line(surface, C_BORDER, (x + 8, add_y - 2), (x + self.WIDTH - 8, add_y - 2))
        _text(surface, "+ Add:", (x + 12, add_y + 6), size=12, bold=True)

        if editor.template_ids:
            template_id = editor.template_ids[self.add_template_index % len(editor.template_ids)]
            prev_rect = pygame.Rect(x + 70, add_y + 2, 24, 22)
            next_rect = pygame.Rect(x + self.WIDTH - 140, add_y + 2, 24, 22)
            add_rect = pygame.Rect(x + self.WIDTH - 70, add_y + 2, 56, 22)
            _btn(surface, prev_rect, "<")
            _text(surface, template_id, (x + 100, add_y + 5))
            _btn(surface, next_rect, ">")
            _btn(surface, add_rect, "Add")

        # Properties section
        props_top = add_y + 34
        pygame.draw.line(surface, C_BORDER, (x + 8, props_top - 4), (x + self.WIDTH - 8, props_top - 4))

        if self.selected_entity_id:
            entity = editor.world.get_entity(self.selected_entity_id)
            if entity:
                _text(surface, f"Properties: {entity.entity_id}", (x + 12, props_top + 2),
                      color=C_TEXT_DIM, size=12)
                props = editor.selected_entity_properties()
                for i, (field_name, label, value) in enumerate(props):
                    py = props_top + 20 + i * self.PROP_ROW_H
                    if py + self.PROP_ROW_H > self.rect.bottom - 4:
                        break
                    is_readonly = field_name in ("template_id", "kind")
                    is_editing = (self.editing_field == field_name
                                  and self.edit_entity_id == self.selected_entity_id)

                    _text(surface, f"{label}:", (x + 20, py + 3), color=C_TEXT_DIM, size=12)

                    if is_editing:
                        edit_rect = pygame.Rect(x + 140, py, self.WIDTH - 160, self.PROP_ROW_H - 2)
                        pygame.draw.rect(surface, (50, 55, 70), edit_rect)
                        pygame.draw.rect(surface, C_HIGHLIGHT, edit_rect, width=1)
                        _text(surface, self.edit_buffer + "|", (x + 144, py + 3), size=12)
                    else:
                        color = C_TEXT_DIM if is_readonly else C_TEXT
                        _text(surface, value, (x + 140, py + 3), color=color, size=12)
        else:
            _text(surface, "Click an entity to see properties", (x + 12, props_top + 2),
                  color=C_TEXT_DIM, size=12)


# =====================================================================
#  Layer Manager Popup
# =====================================================================

class LayerManagerPopup:
    """Popup for managing tile layers."""

    WIDTH = 340
    ROW_H = 28

    def __init__(self, editor: LevelEditor) -> None:
        n_layers = len(editor.area.tile_layers)
        self._total_h = 40 + n_layers * self.ROW_H + 50
        self.rect = pygame.Rect(
            (SCREEN_W - self.WIDTH) // 2,
            (SCREEN_H - self._total_h) // 2,
            self.WIDTH, self._total_h,
        )
        self.renaming_index: int | None = None
        self.rename_buffer: str = ""

    def handle_event(self, event: pygame.event.Event, editor: LevelEditor) -> str | None:
        if event.type == pygame.KEYDOWN:
            if self.renaming_index is not None:
                return self._handle_rename_key(event, editor)
            if event.key == pygame.K_ESCAPE:
                return "close"

        if event.type == pygame.TEXTINPUT and self.renaming_index is not None:
            self.rename_buffer += event.text
            return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.rect.collidepoint(event.pos):
                return "close"
            return self._handle_click(event.pos, editor)

        return None

    def _handle_rename_key(self, event: pygame.event.Event, editor: LevelEditor) -> str | None:
        if event.key == pygame.K_RETURN:
            if self.renaming_index is not None:
                old_idx = editor.selected_layer_index
                editor.selected_layer_index = self.renaming_index
                editor.rename_selected_layer(self.rename_buffer)
                editor.selected_layer_index = old_idx
            self.renaming_index = None
            return None
        if event.key == pygame.K_ESCAPE:
            self.renaming_index = None
            return None
        if event.key == pygame.K_BACKSPACE:
            self.rename_buffer = self.rename_buffer[:-1]
            return None
        return None

    def _handle_click(self, pos: tuple[int, int], editor: LevelEditor) -> str | None:
        rx = pos[0] - self.rect.x
        ry = pos[1] - self.rect.y

        # Close button
        if rx > self.WIDTH - 30 and ry < 32:
            return "close"

        layers = editor.area.tile_layers
        list_top = 36

        # Layer rows
        for i, layer in enumerate(layers):
            row_y = list_top + i * self.ROW_H
            if row_y <= ry < row_y + self.ROW_H:
                # Delete button
                if rx > self.WIDTH - 70 and rx < self.WIDTH - 10:
                    old_idx = editor.selected_layer_index
                    editor.selected_layer_index = i
                    editor.remove_selected_layer()
                    n_layers = len(editor.area.tile_layers)
                    self._total_h = 40 + n_layers * self.ROW_H + 50
                    self.rect.height = self._total_h
                    return None

                # Rename button
                if rx > self.WIDTH - 140 and rx < self.WIDTH - 76:
                    self.renaming_index = i
                    self.rename_buffer = layer.name
                    return None

                # Click layer name to select
                editor.selected_layer_index = i
                editor.status_message = f"Layer {layer.name}"
                return "close"

        # Add layer button
        add_y = list_top + len(layers) * self.ROW_H + 10
        if add_y <= ry < add_y + 28:
            editor.add_layer()
            n_layers = len(editor.area.tile_layers)
            self._total_h = 40 + n_layers * self.ROW_H + 50
            self.rect.height = self._total_h
            return None

        return None

    def render(self, surface: pygame.Surface, editor: LevelEditor) -> None:
        _popup_bg(surface, self.rect)
        x, y = self.rect.x, self.rect.y

        _text(surface, "Layers", (x + 12, y + 8), bold=True)
        close_rect = pygame.Rect(x + self.WIDTH - 30, y + 4, 26, 24)
        _btn(surface, close_rect, "X")

        layers = editor.area.tile_layers
        list_top = y + 36

        for i, layer in enumerate(layers):
            row_y = list_top + i * self.ROW_H
            is_active = i == editor.selected_layer_index

            if is_active:
                pygame.draw.rect(surface, (40, 50, 70),
                                 (x + 4, row_y, self.WIDTH - 8, self.ROW_H))

            marker = ">" if is_active else " "

            if self.renaming_index == i:
                _text(surface, f"{marker} ", (x + 12, row_y + 5))
                edit_rect = pygame.Rect(x + 30, row_y + 2, 140, self.ROW_H - 4)
                pygame.draw.rect(surface, (50, 55, 70), edit_rect)
                pygame.draw.rect(surface, C_HIGHLIGHT, edit_rect, width=1)
                _text(surface, self.rename_buffer + "|", (x + 34, row_y + 5), size=12)
            else:
                above = " [above]" if layer.draw_above_entities else ""
                _text(surface, f"{marker} {layer.name}{above}", (x + 12, row_y + 5),
                      bold=is_active)

            rename_rect = pygame.Rect(x + self.WIDTH - 140, row_y + 3, 58, self.ROW_H - 6)
            delete_rect = pygame.Rect(x + self.WIDTH - 70, row_y + 3, 56, self.ROW_H - 6)
            _btn(surface, rename_rect, "Rename")
            _btn(surface, delete_rect, "Del", danger=True)

        add_y = list_top + len(layers) * self.ROW_H + 10
        add_rect = pygame.Rect(x + 12, add_y, self.WIDTH - 24, 28)
        _btn(surface, add_rect, "+ Add Layer")


# =====================================================================
#  Main EditorUI class
# =====================================================================

class EditorUI:
    """Manages the screen-resolution toolbar, status bar, and popup overlays."""

    def __init__(self, asset_manager: AssetManager) -> None:
        self.asset_manager = asset_manager
        self.active_popup: BrushPickerPopup | CellInspectorPopup | LayerManagerPopup | None = None
        self._last_click_cell: tuple[int, int] | None = None
        self._last_click_time: int = 0
        self._mouse_pos: tuple[int, int] = (0, 0)

    def handle_event(
        self,
        event: pygame.event.Event,
        editor: LevelEditor,
        camera: Camera,
    ) -> bool:
        """Process an event. Returns True if consumed (should not go to editor)."""
        if event.type == pygame.MOUSEMOTION:
            self._mouse_pos = event.pos

        # ---- Modal popup captures all events ----
        if self.active_popup is not None:
            result = self.active_popup.handle_event(event, editor)
            if result == "close":
                self.active_popup = None
            return True

        # ---- Move-pending mode: intercept map events ----
        if editor.move_pending_entity_id is not None:
            return self._handle_move_pending(event, editor, camera)

        # ---- Keyboard shortcuts (before toolbar/map) ----
        if event.type == pygame.KEYDOWN:
            consumed = self._handle_shortcut(event, editor)
            if consumed:
                return True

        # ---- Toolbar click ----
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if event.pos[1] < TOOLBAR_H:
                self._handle_toolbar_click(event.pos, editor)
                return True

        # ---- Double-click detection on map ----
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if event.pos[1] >= TOOLBAR_H:
                if self._check_double_click(event.pos, editor, camera):
                    return True

        return False

    def _handle_move_pending(
        self, event: pygame.event.Event, editor: LevelEditor, camera: Camera
    ) -> bool:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            editor.move_pending_entity_id = None
            editor.status_message = "Move cancelled"
            return True

        if event.type == pygame.MOUSEMOTION:
            internal_pos = editor._window_to_internal(event.pos)
            editor.hovered_cell = editor._mouse_to_cell(internal_pos, camera)
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            internal_pos = editor._window_to_internal(event.pos)
            cell = editor._mouse_to_cell(internal_pos, camera)
            if cell is not None:
                editor.move_entity_to(editor.move_pending_entity_id, cell[0], cell[1])
            else:
                editor.status_message = "Move cancelled"
            editor.move_pending_entity_id = None
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            editor.move_pending_entity_id = None
            editor.status_message = "Move cancelled"
            return True

        return True  # consume all events during move-pending

    def _handle_shortcut(self, event: pygame.event.Event, editor: LevelEditor) -> bool:
        if event.key == pygame.K_b:
            self.active_popup = BrushPickerPopup(self.asset_manager, editor)
            return True
        if event.key == pygame.K_l:
            self.active_popup = LayerManagerPopup(editor)
            return True
        if event.key == pygame.K_w and not (event.mod & pygame.KMOD_CTRL):
            editor.toggle_paint_submode()
            return True
        return False

    def _handle_toolbar_click(self, pos: tuple[int, int], editor: LevelEditor) -> None:
        x = pos[0]
        # Action buttons: Save, Reload, Play
        if x < 60:
            editor.save()
        elif x < 130:
            # Reload - editor handles this via action
            editor.reload_from_disk()
        elif x < 200:
            # Play button - handled via actions in game loop
            pass  # toggle_play is handled by F1 / game loop
        # Brush indicator (clickable to open brush picker)
        elif 240 < x < 540:
            self.active_popup = BrushPickerPopup(self.asset_manager, editor)
        # Layer prev/next
        elif 580 < x < 610:
            editor._step_layer(-1)
        elif 700 < x < 730:
            editor._step_layer(1)
        # Walk overlay toggle
        elif x > 800:
            editor.show_walk_overlay = not editor.show_walk_overlay

    def _check_double_click(
        self,
        pos: tuple[int, int],
        editor: LevelEditor,
        camera: Camera,
    ) -> bool:
        now = pygame.time.get_ticks()
        internal_pos = editor._window_to_internal(pos)
        cell = editor._mouse_to_cell(internal_pos, camera)

        if (
            cell is not None
            and cell == self._last_click_cell
            and (now - self._last_click_time) < DOUBLE_CLICK_MS
        ):
            editor.selected_cell = cell
            editor._sync_selected_entity_to_cell()
            self.active_popup = CellInspectorPopup(cell, editor, self.asset_manager)
            self._last_click_cell = None
            self._last_click_time = 0
            return True

        self._last_click_cell = cell
        self._last_click_time = now
        return False

    def render(self, surface: pygame.Surface, editor: LevelEditor) -> None:
        """Draw toolbar, status bar, and any open popup on the display surface."""
        self._draw_toolbar(surface, editor)
        self._draw_status_bar(surface, editor)
        if self.active_popup is not None:
            self.active_popup.render(surface, editor)

    def _draw_toolbar(self, surface: pygame.Surface, editor: LevelEditor) -> None:
        toolbar_surf = pygame.Surface((SCREEN_W, TOOLBAR_H), pygame.SRCALPHA)
        toolbar_surf.fill((20, 24, 32, 220))
        surface.blit(toolbar_surf, (0, 0))
        pygame.draw.line(surface, C_BORDER, (0, TOOLBAR_H - 1), (SCREEN_W, TOOLBAR_H - 1))

        y_center = TOOLBAR_H // 2

        # Action buttons
        save_rect = pygame.Rect(6, 6, 50, TOOLBAR_H - 12)
        reload_rect = pygame.Rect(62, 6, 60, TOOLBAR_H - 12)
        play_rect = pygame.Rect(128, 6, 50, TOOLBAR_H - 12)
        _btn(surface, save_rect, "Save")
        _btn(surface, reload_rect, "Reload")
        _btn(surface, play_rect, "Play")

        # Separator
        pygame.draw.line(surface, C_BORDER, (190, 4), (190, TOOLBAR_H - 4))

        # Brush indicator
        submode = editor.paint_submode
        if submode == "tile":
            brush_label = f"Brush: {editor.current_gid_label}"
            brush_color = C_TEXT
        else:
            walk_label = "walkable" if editor.walk_brush_walkable else "blocked"
            brush_label = f"Brush: {walk_label}"
            brush_color = C_WALK if editor.walk_brush_walkable else C_BLOCK

        brush_rect = pygame.Rect(200, 4, 320, TOOLBAR_H - 8)
        pygame.draw.rect(surface, (36, 40, 52), brush_rect, border_radius=3)
        pygame.draw.rect(surface, C_BORDER, brush_rect, width=1, border_radius=3)

        # Paint submode indicator
        mode_label = "[T]" if submode == "tile" else "[W]"
        _text(surface, mode_label, (208, y_center - 7), color=C_HIGHLIGHT, size=12, bold=True)
        _text(surface, brush_label, (240, y_center - 7), color=brush_color)

        # Separator
        pygame.draw.line(surface, C_BORDER, (530, 4), (530, TOOLBAR_H - 4))

        # Layer selector
        _text(surface, "Layer:", (544, y_center - 7), color=C_TEXT_DIM, size=12)
        prev_rect = pygame.Rect(590, 6, 20, TOOLBAR_H - 12)
        next_rect = pygame.Rect(730, 6, 20, TOOLBAR_H - 12)
        _btn(surface, prev_rect, "<")
        _btn(surface, next_rect, ">")
        _text(surface, editor.current_layer_name, (618, y_center - 7), bold=True)

        # Separator
        pygame.draw.line(surface, C_BORDER, (760, 4), (760, TOOLBAR_H - 4))

        # Walk overlay toggle
        show_walk = getattr(editor, 'show_walk_overlay', False)
        walk_label = "Walk: ON" if show_walk else "Walk: off"
        walk_color = C_WALK if show_walk else C_TEXT_DIM
        walk_rect = pygame.Rect(770, 6, 80, TOOLBAR_H - 12)
        _btn(surface, walk_rect, walk_label, active=show_walk)

        # Dirty indicator
        if editor.dirty:
            _text(surface, "*", (SCREEN_W - 20, y_center - 7), color=C_DANGER, bold=True)

    def _draw_status_bar(self, surface: pygame.Surface, editor: LevelEditor) -> None:
        status_y = SCREEN_H - STATUS_H
        status_surf = pygame.Surface((SCREEN_W, STATUS_H), pygame.SRCALPHA)
        status_surf.fill((20, 24, 32, 200))
        surface.blit(status_surf, (0, status_y))
        pygame.draw.line(surface, C_BORDER, (0, status_y), (SCREEN_W, status_y))

        # Left: status message
        _text(surface, editor.status_message, (8, status_y + 4), size=12)

        # Center: hint
        if editor.move_pending_entity_id:
            hint = f"Click to move {editor.move_pending_entity_id} | Esc cancel"
        else:
            hint = "L paint  R erase  B brush  DblClick entities  L layers  W walk"
        hw, _ = _font(12).size(hint)
        _text(surface, hint, ((SCREEN_W - hw) // 2, status_y + 4), color=C_TEXT_DIM, size=12)

        # Right: cell coords
        hover = editor.hovered_cell
        hover_label = f"({hover[0]},{hover[1]})" if hover else ""
        if hover_label:
            tw, _ = _font(12).size(hover_label)
            _text(surface, hover_label, (SCREEN_W - tw - 8, status_y + 4), size=12)
