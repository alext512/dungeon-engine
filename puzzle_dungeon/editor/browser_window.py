"""A separate pygame window for visual editor tools and palettes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pygame

from puzzle_dungeon import config
from puzzle_dungeon.editor.level_editor import EditorAction
from puzzle_dungeon.engine.asset_manager import AssetManager
from puzzle_dungeon.engine.text import TextRenderer
from puzzle_dungeon.logging_utils import get_logger
from puzzle_dungeon.world.loader import load_entity_template

if TYPE_CHECKING:
    from puzzle_dungeon.editor.level_editor import LevelEditor


@dataclass(slots=True)
class BrowserButton:
    """A small clickable button or tab inside the browser window."""

    key: str
    rect: pygame.Rect
    label: str
    active: bool = False


class EditorBrowserWindow:
    """Show layers, a visual tile palette, and entity stack tools in a second pygame window."""

    WINDOW_SIZE = (420, 720)
    PADDING = 8
    GAP = 4
    BUTTON_HEIGHT = 22
    ROW_HEIGHT = 18
    TILE_SIZE = 32
    TILE_GAP = 6

    def __init__(self, asset_manager: AssetManager) -> None:
        self.logger = get_logger("editor.browser_window")
        self.asset_manager = asset_manager
        self.text_renderer = TextRenderer(asset_manager)
        self.window = pygame.Window(
            title="Puzzle Engine Browser",
            size=self.WINDOW_SIZE,
            position=(980, 80),
            hidden=True,
            resizable=True,
        )
        self.visible = False
        self.last_mouse_pos = (0, 0)
        self.layer_scroll = 0
        self.palette_scroll_rows = 0
        self.entity_scroll = 0
        self.layer_name_buffer = ""
        self.active_text_field: str | None = None

    @property
    def id(self) -> int:
        """Return the SDL window id for event routing."""
        return self.window.id

    def show(self, editor: "LevelEditor") -> None:
        """Show the browser and sync its editable text state."""
        self.visible = True
        self.window.show()
        if self.active_text_field != "layer_name":
            self.layer_name_buffer = editor.current_layer_name

    def hide(self) -> None:
        """Hide the browser window without destroying it."""
        self.visible = False
        self.window.hide()

    def destroy(self) -> None:
        """Destroy the secondary pygame window."""
        self.window.destroy()

    def process(
        self,
        editor: "LevelEditor",
        events: list[pygame.event.Event],
    ) -> list[EditorAction]:
        """Handle routed events for the browser and redraw the current tool state."""
        if not self.visible:
            return []

        if self.active_text_field != "layer_name":
            self.layer_name_buffer = editor.current_layer_name

        actions: list[EditorAction] = []
        for event in events:
            actions.extend(self._handle_event(editor, event))

        self._render(editor)
        return actions

    def _handle_event(
        self,
        editor: "LevelEditor",
        event: pygame.event.Event,
    ) -> list[EditorAction]:
        """Process one browser-window event and return any game-level actions."""
        actions: list[EditorAction] = []

        if event.type == pygame.WINDOWCLOSE:
            self.hide()
            return actions

        if event.type == pygame.MOUSEMOTION:
            self.last_mouse_pos = event.pos
            return actions

        if event.type == pygame.MOUSEWHEEL:
            self._handle_wheel(editor, event)
            return actions

        if event.type == pygame.TEXTINPUT and self.active_text_field == "layer_name":
            self.layer_name_buffer += event.text
            return actions

        if event.type == pygame.KEYDOWN:
            if self.active_text_field == "layer_name":
                if event.key == pygame.K_BACKSPACE:
                    self.layer_name_buffer = self.layer_name_buffer[:-1]
                    return actions
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    editor.rename_selected_layer(self.layer_name_buffer)
                    self.active_text_field = None
                    return actions
                if event.key == pygame.K_ESCAPE:
                    self.layer_name_buffer = editor.current_layer_name
                    self.active_text_field = None
                    return actions

            if event.key == pygame.K_DELETE:
                editor._remove_selected_entity()
                return actions

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.last_mouse_pos = event.pos
            actions.extend(self._handle_left_click(editor, event.pos))

        return actions

    def _handle_left_click(
        self,
        editor: "LevelEditor",
        mouse_pos: tuple[int, int],
    ) -> list[EditorAction]:
        """Handle all clickable regions inside the browser window."""
        actions: list[EditorAction] = []
        layout = self._layout(self.window.get_surface().get_size())

        for button in self._action_buttons(layout):
            if button.rect.collidepoint(mouse_pos):
                if button.key == "action:play":
                    actions.append(EditorAction("toggle_play"))
                elif button.key == "action:save":
                    editor.save()
                elif button.key == "action:reload":
                    actions.append(EditorAction("reload_document"))
                return actions

        for button in self._mode_buttons(layout, editor):
            if button.rect.collidepoint(mouse_pos):
                editor.set_mode(button.key.split(":", 1)[1])
                return actions

        for button in self._layer_action_buttons(layout):
            if button.rect.collidepoint(mouse_pos):
                if button.key == "layer:add":
                    editor.add_layer(self.layer_name_buffer.strip() or None)
                elif button.key == "layer:delete":
                    editor.remove_selected_layer()
                elif button.key == "layer:rename":
                    editor.rename_selected_layer(self.layer_name_buffer)
                elif button.key == "layer:name":
                    self.active_text_field = "layer_name"
                return actions

        layer_index = self._layer_index_at(editor, layout["layers_list"], mouse_pos)
        if layer_index is not None:
            editor.selected_layer_index = layer_index
            editor._choose_default_tile_for_layer()
            editor.status_message = f"Layer {editor.current_layer_name}"
            self.layer_name_buffer = editor.current_layer_name
            return actions

        palette_index = self._palette_index_at(editor, layout["palette"], mouse_pos)
        if palette_index is not None:
            self._apply_palette_selection(editor, palette_index)
            return actions

        entity_index = self._entity_index_at(editor, layout["entity_list"], mouse_pos)
        if entity_index is not None:
            entities = editor.entities_for_selected_cell()
            if entity_index < len(entities):
                editor.selected_entity_id = entities[entity_index].entity_id
                editor.status_message = f"Selected {editor.selected_entity_id}"
            return actions

        for button in self._entity_action_buttons(layout):
            if button.rect.collidepoint(mouse_pos):
                if button.key == "entity:up":
                    editor._move_selected_entity(-1)
                elif button.key == "entity:down":
                    editor._move_selected_entity(1)
                elif button.key == "entity:delete":
                    editor._remove_selected_entity()
                return actions

        self.active_text_field = None
        return actions

    def _handle_wheel(self, editor: "LevelEditor", event: pygame.event.Event) -> None:
        """Scroll the list or palette under the mouse cursor."""
        layout = self._layout(self.window.get_surface().get_size())
        if layout["layers_list"].collidepoint(self.last_mouse_pos):
            max_scroll = max(0, len(editor.area.tile_layers) - self._visible_list_rows(layout["layers_list"]))
            self.layer_scroll = min(max(self.layer_scroll - event.y, 0), max_scroll)
            return

        if layout["entity_list"].collidepoint(self.last_mouse_pos):
            visible_rows = self._visible_list_rows(layout["entity_list"])
            max_scroll = max(0, len(editor.entities_for_selected_cell()) - visible_rows)
            self.entity_scroll = min(max(self.entity_scroll - event.y, 0), max_scroll)
            return

        if layout["palette"].collidepoint(self.last_mouse_pos):
            total_items = self._palette_item_count(editor)
            columns = self._palette_columns(layout["palette"])
            visible_rows = self._palette_visible_rows(layout["palette"])
            total_rows = max(1, (total_items + columns - 1) // columns)
            max_scroll = max(0, total_rows - visible_rows)
            self.palette_scroll_rows = min(max(self.palette_scroll_rows - event.y, 0), max_scroll)

    def _render(self, editor: "LevelEditor") -> None:
        """Draw the whole browser window using pygame surfaces."""
        surface = self.window.get_surface()
        surface.fill((20, 24, 31))
        layout = self._layout(surface.get_size())

        for rect, title in (
            (layout["actions"], "Actions"),
            (layout["modes"], "Mode"),
            (layout["layers"], "Layers"),
            (layout["palette_panel"], "Palette"),
            (layout["cell_panel"], "Cell"),
            (layout["entity_panel"], "Entity Stack"),
        ):
            self._draw_panel(surface, rect, title)

        for button in self._action_buttons(layout):
            self._draw_button(surface, button)

        for button in self._mode_buttons(layout, editor):
            self._draw_button(surface, button)

        self._draw_layers(surface, editor, layout)
        self._draw_palette(surface, editor, layout)
        self._draw_selected_cell(surface, editor, layout)
        self._draw_entity_stack(surface, editor, layout)
        self._draw_status(surface, editor, layout)
        self.window.flip()

    def _layout(self, size: tuple[int, int]) -> dict[str, pygame.Rect]:
        """Return all major panel rectangles for the current browser size."""
        width, height = size
        pad = self.PADDING
        gap = self.GAP

        actions = pygame.Rect(pad, pad, width - (pad * 2), 40)
        modes = pygame.Rect(pad, actions.bottom + gap, actions.width, 40)
        layers = pygame.Rect(pad, modes.bottom + gap, actions.width, 170)
        palette_panel = pygame.Rect(pad, layers.bottom + gap, actions.width, 220)
        cell_panel = pygame.Rect(pad, palette_panel.bottom + gap, actions.width, 100)
        entity_panel = pygame.Rect(pad, cell_panel.bottom + gap, actions.width, height - cell_panel.bottom - gap - pad - 24)

        return {
            "actions": actions,
            "modes": modes,
            "layers": layers,
            "layers_list": pygame.Rect(layers.x + 6, layers.y + 20, layers.width - 12, 90),
            "layer_name": pygame.Rect(layers.x + 6, layers.bottom - 46, layers.width - 132, 18),
            "layer_rename": pygame.Rect(layers.right - 120, layers.bottom - 46, 114, 18),
            "layer_add": pygame.Rect(layers.x + 6, layers.bottom - 24, (layers.width - 18) // 2, 18),
            "layer_delete": pygame.Rect(layers.x + 12 + ((layers.width - 18) // 2), layers.bottom - 24, (layers.width - 18) // 2, 18),
            "palette_panel": palette_panel,
            "palette": pygame.Rect(palette_panel.x + 6, palette_panel.y + 20, palette_panel.width - 12, palette_panel.height - 26),
            "cell_panel": cell_panel,
            "entity_panel": entity_panel,
            "entity_list": pygame.Rect(entity_panel.x + 6, entity_panel.y + 20, entity_panel.width - 12, max(30, entity_panel.height - 46)),
            "entity_buttons": pygame.Rect(entity_panel.x + 6, entity_panel.bottom - 22, entity_panel.width - 12, 18),
            "status": pygame.Rect(pad, height - 20, width - (pad * 2), 16),
        }

    def _action_buttons(self, layout: dict[str, pygame.Rect]) -> list[BrowserButton]:
        """Return top action buttons."""
        rect = layout["actions"]
        inner = pygame.Rect(rect.x + 6, rect.y + 18, rect.width - 12, 18)
        width = (inner.width - (self.GAP * 2)) // 3
        return [
            BrowserButton("action:play", pygame.Rect(inner.x, inner.y, width, 18), "Play"),
            BrowserButton("action:save", pygame.Rect(inner.x + width + self.GAP, inner.y, width, 18), "Save"),
            BrowserButton("action:reload", pygame.Rect(inner.x + ((width + self.GAP) * 2), inner.y, width, 18), "Reload"),
        ]

    def _mode_buttons(self, layout: dict[str, pygame.Rect], editor: "LevelEditor") -> list[BrowserButton]:
        """Return mode-tab buttons."""
        rect = layout["modes"]
        inner = pygame.Rect(rect.x + 6, rect.y + 18, rect.width - 12, 18)
        width = (inner.width - (self.GAP * 2)) // 3
        return [
            BrowserButton("mode:tile", pygame.Rect(inner.x, inner.y, width, 18), "Tiles", editor.mode == "tile"),
            BrowserButton("mode:walkability", pygame.Rect(inner.x + width + self.GAP, inner.y, width, 18), "Flags", editor.mode == "walkability"),
            BrowserButton("mode:entity", pygame.Rect(inner.x + ((width + self.GAP) * 2), inner.y, width, 18), "Entities", editor.mode == "entity"),
        ]

    def _layer_action_buttons(self, layout: dict[str, pygame.Rect]) -> list[BrowserButton]:
        """Return layer-management controls."""
        return [
            BrowserButton("layer:name", layout["layer_name"], self.layer_name_buffer or ""),
            BrowserButton("layer:rename", layout["layer_rename"], "Rename"),
            BrowserButton("layer:add", layout["layer_add"], "Add"),
            BrowserButton("layer:delete", layout["layer_delete"], "Delete"),
        ]

    def _entity_action_buttons(self, layout: dict[str, pygame.Rect]) -> list[BrowserButton]:
        """Return buttons for entity stack management."""
        rect = layout["entity_buttons"]
        width = (rect.width - (self.GAP * 2)) // 3
        return [
            BrowserButton("entity:up", pygame.Rect(rect.x, rect.y, width, rect.height), "Up"),
            BrowserButton("entity:down", pygame.Rect(rect.x + width + self.GAP, rect.y, width, rect.height), "Down"),
            BrowserButton("entity:delete", pygame.Rect(rect.x + ((width + self.GAP) * 2), rect.y, width, rect.height), "Delete"),
        ]

    def _draw_layers(self, surface: pygame.Surface, editor: "LevelEditor", layout: dict[str, pygame.Rect]) -> None:
        """Draw the generic layer list plus controls."""
        list_rect = layout["layers_list"]
        pygame.draw.rect(surface, (14, 17, 23), list_rect)
        pygame.draw.rect(surface, (74, 90, 112), list_rect, width=1)

        visible_rows = self._visible_list_rows(list_rect)
        start = self.layer_scroll
        layers = editor.area.tile_layers[start:start + visible_rows]
        for row_index, layer in enumerate(layers):
            absolute_index = start + row_index
            row_rect = pygame.Rect(list_rect.x + 2, list_rect.y + 2 + (row_index * self.ROW_HEIGHT), list_rect.width - 4, self.ROW_HEIGHT - 2)
            active = absolute_index == editor.selected_layer_index
            pygame.draw.rect(surface, (38, 55, 79) if active else (20, 24, 31), row_rect)
            pygame.draw.rect(surface, (110, 150, 210) if active else (74, 90, 112), row_rect, width=1)
            self._draw_text(surface, layer.name, (row_rect.x + 4, row_rect.y + 4))

        for button in self._layer_action_buttons(layout):
            active = button.key == "layer:name" and self.active_text_field == "layer_name"
            self._draw_button(surface, BrowserButton(button.key, button.rect, button.label, active))

    def _draw_palette(self, surface: pygame.Surface, editor: "LevelEditor", layout: dict[str, pygame.Rect]) -> None:
        """Draw a visual palette instead of tile names."""
        rect = layout["palette"]
        pygame.draw.rect(surface, (14, 17, 23), rect)
        pygame.draw.rect(surface, (74, 90, 112), rect, width=1)

        if editor.mode == "walkability":
            items = [("walk", (48, 180, 96)), ("block", (200, 64, 64))]
            for index, (key, color) in enumerate(items):
                card = pygame.Rect(rect.x + 8 + (index * 96), rect.y + 12, 88, 88)
                active = (key == "walk" and editor.walk_brush_walkable) or (key == "block" and not editor.walk_brush_walkable)
                pygame.draw.rect(surface, (38, 55, 79) if active else (24, 29, 38), card)
                pygame.draw.rect(surface, (110, 150, 210) if active else (74, 90, 112), card, width=2 if active else 1)
                swatch = pygame.Rect(card.x + 20, card.y + 16, 48, 48)
                pygame.draw.rect(surface, color, swatch)
                self._draw_text(surface, "Walk" if key == "walk" else "Block", (card.x + 18, card.bottom - 16))
            return

        columns = self._palette_columns(rect)
        start_index = self.palette_scroll_rows * columns
        palette_ids = editor.tile_ids if editor.mode == "tile" else editor.template_ids
        selected_id = editor.current_tile_id if editor.mode == "tile" else editor.current_template_id
        visible_rows = self._palette_visible_rows(rect)
        visible_count = visible_rows * columns
        visible_ids = palette_ids[start_index:start_index + visible_count]

        for visible_index, item_id in enumerate(visible_ids):
            grid_index = start_index + visible_index
            column = visible_index % columns
            row = visible_index // columns
            cell_rect = pygame.Rect(
                rect.x + 8 + (column * (self.TILE_SIZE + self.TILE_GAP)),
                rect.y + 8 + (row * (self.TILE_SIZE + self.TILE_GAP)),
                self.TILE_SIZE,
                self.TILE_SIZE,
            )
            active = item_id == selected_id
            pygame.draw.rect(surface, (38, 55, 79) if active else (24, 29, 38), cell_rect)
            pygame.draw.rect(surface, (110, 150, 210) if active else (74, 90, 112), cell_rect, width=2 if active else 1)
            icon = self._palette_icon(editor, item_id)
            icon_rect = icon.get_rect(center=cell_rect.center)
            surface.blit(icon, icon_rect.topleft)
            _ = grid_index

    def _draw_selected_cell(self, surface: pygame.Surface, editor: "LevelEditor", layout: dict[str, pygame.Rect]) -> None:
        """Draw selected-cell summary with layer icons instead of tile names."""
        panel = layout["cell_panel"]
        self._draw_text(surface, f"Cell {editor.selected_cell_label}", (panel.x + 6, panel.y + 18))
        self._draw_text(surface, f"Walk {editor.cell_walk_label}", (panel.x + 120, panel.y + 18))

        row_y = panel.y + 40
        visible_rows = max(1, (panel.height - 44) // 22)
        visible_layers = editor.area.tile_layers[:visible_rows]
        for layer in visible_layers:
            tile_id = "-"
            if editor.selected_cell is not None:
                grid_x, grid_y = editor.selected_cell
                tile_id = layer.grid[grid_y][grid_x] or "-"
            self._draw_text(surface, layer.name, (panel.x + 6, row_y + 4))
            preview_rect = pygame.Rect(panel.x + 92, row_y, 20, 20)
            pygame.draw.rect(surface, (24, 29, 38), preview_rect)
            pygame.draw.rect(surface, (74, 90, 112), preview_rect, width=1)
            if tile_id != "-":
                icon = self._tile_icon_surface(editor, tile_id, icon_size=16)
                surface.blit(icon, (preview_rect.x + 2, preview_rect.y + 2))
            row_y += 22

        if len(editor.area.tile_layers) > len(visible_layers):
            self._draw_text(surface, f"+{len(editor.area.tile_layers) - len(visible_layers)} more", (panel.x + 140, panel.y + 18))

    def _draw_entity_stack(self, surface: pygame.Surface, editor: "LevelEditor", layout: dict[str, pygame.Rect]) -> None:
        """Draw the current stacked entities with icons and reorder controls."""
        list_rect = layout["entity_list"]
        pygame.draw.rect(surface, (14, 17, 23), list_rect)
        pygame.draw.rect(surface, (74, 90, 112), list_rect, width=1)

        entities = editor.entities_for_selected_cell()
        visible_rows = self._visible_list_rows(list_rect)
        start = self.entity_scroll
        for row_index, entity in enumerate(entities[start:start + visible_rows]):
            row_rect = pygame.Rect(list_rect.x + 2, list_rect.y + 2 + (row_index * self.ROW_HEIGHT), list_rect.width - 4, self.ROW_HEIGHT - 2)
            active = entity.entity_id == editor.selected_entity_id
            pygame.draw.rect(surface, (38, 55, 79) if active else (20, 24, 31), row_rect)
            pygame.draw.rect(surface, (110, 150, 210) if active else (74, 90, 112), row_rect, width=1)
            icon = self._entity_icon_surface(entity, 14)
            surface.blit(icon, (row_rect.x + 2, row_rect.y + 2))
            self._draw_text(surface, entity.entity_id, (row_rect.x + 20, row_rect.y + 4))

        for button in self._entity_action_buttons(layout):
            self._draw_button(surface, button)

    def _draw_status(self, surface: pygame.Surface, editor: "LevelEditor", layout: dict[str, pygame.Rect]) -> None:
        """Draw one compact status line at the bottom."""
        self._draw_text(surface, editor.status_message[:60], (layout["status"].x, layout["status"].y))

    def _draw_panel(self, surface: pygame.Surface, rect: pygame.Rect, title: str) -> None:
        """Draw a simple panel shell."""
        pygame.draw.rect(surface, (10, 14, 20), rect)
        pygame.draw.rect(surface, (82, 98, 124), rect, width=1)
        self._draw_text(surface, title, (rect.x + 4, rect.y + 4))

    def _draw_button(self, surface: pygame.Surface, button: BrowserButton) -> None:
        """Draw one clickable button."""
        fill = (38, 55, 79) if button.active else (22, 28, 38)
        border = (110, 150, 210) if button.active else (74, 90, 112)
        pygame.draw.rect(surface, fill, button.rect)
        pygame.draw.rect(surface, border, button.rect, width=1)
        if button.label:
            text_width, text_height = self.text_renderer.measure_text(button.label)
            text_x = button.rect.x + max(2, (button.rect.width - text_width) // 2)
            text_y = button.rect.y + max(2, (button.rect.height - text_height) // 2)
            self._draw_text(surface, button.label, (text_x, text_y))

    def _draw_text(self, surface: pygame.Surface, text: str, position: tuple[int, int]) -> None:
        """Render bitmap text in the browser window."""
        self.text_renderer.render_text(surface, text, position, config.COLOR_TEXT)

    def _visible_list_rows(self, rect: pygame.Rect) -> int:
        """Return how many list rows fit in a scrollable list box."""
        return max(1, (rect.height - 4) // self.ROW_HEIGHT)

    def _palette_columns(self, rect: pygame.Rect) -> int:
        """Return how many palette icons fit across the current palette area."""
        return max(1, (rect.width - 16 + self.TILE_GAP) // (self.TILE_SIZE + self.TILE_GAP))

    def _palette_visible_rows(self, rect: pygame.Rect) -> int:
        """Return how many palette rows fit in the current palette area."""
        return max(1, (rect.height - 16 + self.TILE_GAP) // (self.TILE_SIZE + self.TILE_GAP))

    def _palette_item_count(self, editor: "LevelEditor") -> int:
        """Return the active palette item count."""
        if editor.mode == "tile":
            return len(editor.tile_ids)
        if editor.mode == "entity":
            return len(editor.template_ids)
        return 2

    def _layer_index_at(
        self,
        editor: "LevelEditor",
        rect: pygame.Rect,
        mouse_pos: tuple[int, int],
    ) -> int | None:
        """Return the clicked layer index inside the layer list."""
        if not rect.collidepoint(mouse_pos):
            return None
        local_y = mouse_pos[1] - rect.y - 2
        row = local_y // self.ROW_HEIGHT
        if row < 0:
            return None
        index = self.layer_scroll + row
        if index >= len(editor.area.tile_layers):
            return None
        return index

    def _entity_index_at(
        self,
        editor: "LevelEditor",
        rect: pygame.Rect,
        mouse_pos: tuple[int, int],
    ) -> int | None:
        """Return the clicked entity index inside the selected-cell stack list."""
        if not rect.collidepoint(mouse_pos):
            return None
        local_y = mouse_pos[1] - rect.y - 2
        row = local_y // self.ROW_HEIGHT
        if row < 0:
            return None
        index = self.entity_scroll + row
        if index >= len(editor.entities_for_selected_cell()):
            return None
        return index

    def _palette_index_at(
        self,
        editor: "LevelEditor",
        rect: pygame.Rect,
        mouse_pos: tuple[int, int],
    ) -> int | None:
        """Return the clicked palette index based on the visible visual grid."""
        if not rect.collidepoint(mouse_pos):
            return None

        if editor.mode == "walkability":
            first = pygame.Rect(rect.x + 8, rect.y + 12, 88, 88)
            second = pygame.Rect(rect.x + 104, rect.y + 12, 88, 88)
            if first.collidepoint(mouse_pos):
                return 0
            if second.collidepoint(mouse_pos):
                return 1
            return None

        columns = self._palette_columns(rect)
        local_x = mouse_pos[0] - rect.x - 8
        local_y = mouse_pos[1] - rect.y - 8
        if local_x < 0 or local_y < 0:
            return None

        column = local_x // (self.TILE_SIZE + self.TILE_GAP)
        row = local_y // (self.TILE_SIZE + self.TILE_GAP)
        if column >= columns or row < 0:
            return None

        cell_left = column * (self.TILE_SIZE + self.TILE_GAP)
        cell_top = row * (self.TILE_SIZE + self.TILE_GAP)
        if local_x - cell_left >= self.TILE_SIZE or local_y - cell_top >= self.TILE_SIZE:
            return None

        index = (self.palette_scroll_rows + row) * columns + column
        if index >= self._palette_item_count(editor):
            return None
        return index

    def _apply_palette_selection(self, editor: "LevelEditor", palette_index: int) -> None:
        """Apply the clicked visual palette choice to the editor state."""
        if editor.mode == "tile":
            if palette_index < len(editor.tile_ids):
                editor.selected_tile_index = palette_index
                editor.status_message = "Tile selected"
            return

        if editor.mode == "walkability":
            editor.walk_brush_walkable = palette_index == 0
            editor.status_message = f"Walk brush {editor.current_walk_brush_label}"
            return

        if editor.mode == "entity" and palette_index < len(editor.template_ids):
            editor.selected_template_index = palette_index
            editor.status_message = f"Template {editor.current_template_id}"

    def _palette_icon(self, editor: "LevelEditor", item_id: str) -> pygame.Surface:
        """Return a scaled icon for either a tile or an entity template."""
        if editor.mode == "tile":
            return self._tile_icon_surface(editor, item_id, icon_size=24)
        return self._template_icon_surface(editor.area.tile_size, item_id, icon_size=24)

    def _tile_icon_surface(
        self,
        editor: "LevelEditor",
        tile_id: str,
        *,
        icon_size: int,
    ) -> pygame.Surface:
        """Return a scaled visual tile icon from the active tile definitions."""
        tile_definition = editor.area.tile_definition(tile_id)
        sprite_data = tile_definition.get("sprite", {})
        if sprite_data:
            source = self.asset_manager.get_frame(
                str(sprite_data["path"]),
                int(sprite_data.get("frame_width", editor.area.tile_size)),
                int(sprite_data.get("frame_height", editor.area.tile_size)),
                int(sprite_data.get("frame", 0)),
            )
        else:
            source = pygame.Surface((editor.area.tile_size, editor.area.tile_size), pygame.SRCALPHA)
            source.fill(config.COLOR_GRID_ACCENT)
        return pygame.transform.scale(source, (icon_size, icon_size))

    def _template_icon_surface(
        self,
        tile_size: int,
        template_id: str,
        *,
        icon_size: int,
    ) -> pygame.Surface:
        """Return a scaled entity-template icon for the visual palette."""
        template = load_entity_template(template_id)
        sprite_data = dict(template.get("sprite", {}))
        if sprite_data.get("path"):
            source = self.asset_manager.get_frame(
                str(sprite_data["path"]),
                int(sprite_data.get("frame_width", tile_size)),
                int(sprite_data.get("frame_height", tile_size)),
                int(sprite_data.get("frames", [0])[0]),
            )
        else:
            color = tuple(template.get("color", [255, 255, 255]))
            source = pygame.Surface((tile_size, tile_size), pygame.SRCALPHA)
            source.fill((*color, 255))
        return pygame.transform.scale(source, (icon_size, icon_size))

    def _entity_icon_surface(self, entity: object, icon_size: int) -> pygame.Surface:
        """Return a scaled icon for one runtime entity."""
        if getattr(entity, "sprite_path", ""):
            source = self.asset_manager.get_frame(
                entity.sprite_path,
                entity.sprite_frame_width,
                entity.sprite_frame_height,
                entity.current_frame,
            )
        else:
            source = pygame.Surface((16, 16), pygame.SRCALPHA)
            source.fill((*entity.color, 255))
        return pygame.transform.scale(source, (icon_size, icon_size))
