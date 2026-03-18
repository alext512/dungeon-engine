"""A separate pygame window for visual editor tools and palettes.

Shows the full tileset image for tile painting, entity templates for placement,
and a property inspector for selected entities. Uses the GID-based tilemap system.

Depends on: config, asset_manager, text, level_editor, loader
Used by: game
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
    """Show tileset view, entity palette, property inspector in a second pygame window."""

    WINDOW_SIZE = (420, 780)
    PADDING = 8
    GAP = 4
    BUTTON_HEIGHT = 22
    ROW_HEIGHT = 18
    TILE_DISPLAY_SCALE = 2

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

        # Scroll state
        self.layer_scroll = 0
        self.tileset_scroll_y = 0
        self.entity_template_scroll = 0
        self.entity_stack_scroll = 0
        self.inspector_scroll = 0

        # Text editing state
        self.layer_name_buffer = ""
        self.active_text_field: str | None = None
        self.property_value_buffer = ""

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

    # --- Event handling ---

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

        if event.type == pygame.TEXTINPUT and self.active_text_field is not None:
            if self.active_text_field == "layer_name":
                self.layer_name_buffer += event.text
            elif self.active_text_field.startswith("prop:"):
                self.property_value_buffer += event.text
            return actions

        if event.type == pygame.KEYDOWN:
            if self.active_text_field is not None:
                if event.key == pygame.K_BACKSPACE:
                    if self.active_text_field == "layer_name":
                        self.layer_name_buffer = self.layer_name_buffer[:-1]
                    elif self.active_text_field.startswith("prop:"):
                        self.property_value_buffer = self.property_value_buffer[:-1]
                    return actions
                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    self._commit_text_field(editor)
                    return actions
                if event.key == pygame.K_ESCAPE:
                    self._cancel_text_field(editor)
                    return actions

            # Tileset cycling with [ and ]
            if event.key == pygame.K_LEFTBRACKET:
                self._cycle_tileset(editor, -1)
                return actions
            if event.key == pygame.K_RIGHTBRACKET:
                self._cycle_tileset(editor, 1)
                return actions

            if event.key == pygame.K_DELETE:
                editor._remove_selected_entity()
                return actions

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.last_mouse_pos = event.pos
            actions.extend(self._handle_left_click(editor, event.pos))

        return actions

    def _commit_text_field(self, editor: "LevelEditor") -> None:
        """Commit the active text field."""
        if self.active_text_field == "layer_name":
            editor.rename_selected_layer(self.layer_name_buffer)
        elif self.active_text_field is not None and self.active_text_field.startswith("prop:"):
            field_name = self.active_text_field[5:]
            if editor.selected_entity_id:
                editor.set_entity_property(editor.selected_entity_id, field_name, self.property_value_buffer)
        self.active_text_field = None

    def _cancel_text_field(self, editor: "LevelEditor") -> None:
        """Cancel the active text field."""
        if self.active_text_field == "layer_name":
            self.layer_name_buffer = editor.current_layer_name
        self.active_text_field = None
        self.property_value_buffer = ""

    def _cycle_tileset(self, editor: "LevelEditor", direction: int) -> None:
        """Cycle through available tilesets."""
        if not editor.available_tileset_paths:
            return
        editor.selected_tileset_index = (
            editor.selected_tileset_index + direction
        ) % len(editor.available_tileset_paths)
        self.tileset_scroll_y = 0
        editor.status_message = f"Tileset {Path(editor.current_tileset_path).stem}"

    def _handle_left_click(
        self,
        editor: "LevelEditor",
        mouse_pos: tuple[int, int],
    ) -> list[EditorAction]:
        """Handle all clickable regions inside the browser window."""
        actions: list[EditorAction] = []
        layout = self._layout(self.window.get_surface().get_size(), editor.mode)

        # Action buttons
        for button in self._action_buttons(layout):
            if button.rect.collidepoint(mouse_pos):
                if button.key == "action:play":
                    actions.append(EditorAction("toggle_play"))
                elif button.key == "action:save":
                    editor.save()
                elif button.key == "action:reload":
                    actions.append(EditorAction("reload_document"))
                return actions

        # Mode tabs
        for button in self._mode_buttons(layout, editor):
            if button.rect.collidepoint(mouse_pos):
                editor.set_mode(button.key.split(":", 1)[1])
                return actions

        # Layer controls
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

        # Layer list
        layer_index = self._layer_index_at(editor, layout["layers_list"], mouse_pos)
        if layer_index is not None:
            editor.selected_layer_index = layer_index
            editor.status_message = f"Layer {editor.current_layer_name}"
            self.layer_name_buffer = editor.current_layer_name
            return actions

        # Mode-specific content area clicks
        if editor.mode == "tile":
            return self._handle_tile_mode_click(editor, layout, mouse_pos, actions)
        elif editor.mode == "entity":
            return self._handle_entity_mode_click(editor, layout, mouse_pos, actions)
        elif editor.mode == "walkability":
            return self._handle_walk_mode_click(editor, layout, mouse_pos, actions)

        self.active_text_field = None
        return actions

    def _handle_tile_mode_click(
        self,
        editor: "LevelEditor",
        layout: dict[str, pygame.Rect],
        mouse_pos: tuple[int, int],
        actions: list[EditorAction],
    ) -> list[EditorAction]:
        """Handle clicks in tile mode: tileset selector and tileset image."""
        # Tileset selector prev/next
        for button in self._tileset_selector_buttons(layout, editor):
            if button.rect.collidepoint(mouse_pos):
                if button.key == "ts:prev":
                    self._cycle_tileset(editor, -1)
                elif button.key == "ts:next":
                    self._cycle_tileset(editor, 1)
                return actions

        # Tileset image click
        tileset_rect = layout.get("tileset_image")
        if tileset_rect is not None and tileset_rect.collidepoint(mouse_pos):
            frame = self._tileset_frame_at(editor, tileset_rect, mouse_pos)
            if frame is not None:
                editor.select_tileset_frame(editor.selected_tileset_index, frame)
            return actions

        return actions

    def _handle_entity_mode_click(
        self,
        editor: "LevelEditor",
        layout: dict[str, pygame.Rect],
        mouse_pos: tuple[int, int],
        actions: list[EditorAction],
    ) -> list[EditorAction]:
        """Handle clicks in entity mode: template palette, entity stack, inspector."""
        # Template palette
        template_index = self._template_index_at(editor, layout.get("entity_templates", pygame.Rect(0, 0, 0, 0)), mouse_pos)
        if template_index is not None and template_index < len(editor.template_ids):
            editor.selected_template_index = template_index
            editor.status_message = f"Template {editor.current_template_id}"
            return actions

        # Entity stack
        entity_index = self._entity_index_at(editor, layout.get("entity_list", pygame.Rect(0, 0, 0, 0)), mouse_pos)
        if entity_index is not None:
            entities = editor.entities_for_selected_cell()
            if entity_index < len(entities):
                editor.selected_entity_id = entities[entity_index].entity_id
                editor.status_message = f"Selected {editor.selected_entity_id}"
            return actions

        # Entity stack buttons
        for button in self._entity_action_buttons(layout):
            if button.rect.collidepoint(mouse_pos):
                if button.key == "entity:up":
                    editor._move_selected_entity(-1)
                elif button.key == "entity:down":
                    editor._move_selected_entity(1)
                elif button.key == "entity:delete":
                    editor._remove_selected_entity()
                return actions

        # Property inspector click
        inspector_rect = layout.get("inspector")
        if inspector_rect is not None and inspector_rect.collidepoint(mouse_pos):
            prop_field = self._property_field_at(editor, inspector_rect, mouse_pos)
            if prop_field is not None:
                self.active_text_field = f"prop:{prop_field[0]}"
                self.property_value_buffer = prop_field[1]
            return actions

        return actions

    def _handle_walk_mode_click(
        self,
        editor: "LevelEditor",
        layout: dict[str, pygame.Rect],
        mouse_pos: tuple[int, int],
        actions: list[EditorAction],
    ) -> list[EditorAction]:
        """Handle clicks in walkability mode."""
        walk_rect = layout.get("walk_palette")
        if walk_rect is not None and walk_rect.collidepoint(mouse_pos):
            first = pygame.Rect(walk_rect.x + 8, walk_rect.y + 12, 88, 88)
            second = pygame.Rect(walk_rect.x + 104, walk_rect.y + 12, 88, 88)
            if first.collidepoint(mouse_pos):
                editor.walk_brush_walkable = True
                editor.status_message = "Walk brush walk"
            elif second.collidepoint(mouse_pos):
                editor.walk_brush_walkable = False
                editor.status_message = "Walk brush block"
        return actions

    def _handle_wheel(self, editor: "LevelEditor", event: pygame.event.Event) -> None:
        """Scroll the list or palette under the mouse cursor."""
        layout = self._layout(self.window.get_surface().get_size(), editor.mode)

        if layout["layers_list"].collidepoint(self.last_mouse_pos):
            max_scroll = max(0, len(editor.area.tile_layers) - self._visible_list_rows(layout["layers_list"]))
            self.layer_scroll = min(max(self.layer_scroll - event.y, 0), max_scroll)
            return

        if editor.mode == "tile":
            tileset_rect = layout.get("tileset_image")
            if tileset_rect is not None and tileset_rect.collidepoint(self.last_mouse_pos):
                # Scroll the tileset view
                max_scroll = self._tileset_max_scroll(editor, tileset_rect)
                self.tileset_scroll_y = min(max(self.tileset_scroll_y - event.y * 32, 0), max_scroll)
                return

        if editor.mode == "entity":
            entity_list = layout.get("entity_list")
            if entity_list is not None and entity_list.collidepoint(self.last_mouse_pos):
                visible_rows = self._visible_list_rows(entity_list)
                max_scroll = max(0, len(editor.entities_for_selected_cell()) - visible_rows)
                self.entity_stack_scroll = min(max(self.entity_stack_scroll - event.y, 0), max_scroll)
                return

            templates_rect = layout.get("entity_templates")
            if templates_rect is not None and templates_rect.collidepoint(self.last_mouse_pos):
                visible_rows = self._visible_list_rows(templates_rect)
                max_scroll = max(0, len(editor.template_ids) - visible_rows)
                self.entity_template_scroll = min(max(self.entity_template_scroll - event.y, 0), max_scroll)
                return

    # --- Rendering ---

    def _render(self, editor: "LevelEditor") -> None:
        """Draw the whole browser window."""
        surface = self.window.get_surface()
        surface.fill((20, 24, 31))
        layout = self._layout(surface.get_size(), editor.mode)

        # Common panels
        self._draw_panel(surface, layout["actions"], "Actions")
        self._draw_panel(surface, layout["modes"], "Mode")
        self._draw_panel(surface, layout["layers"], "Layers")

        for button in self._action_buttons(layout):
            self._draw_button(surface, button)
        for button in self._mode_buttons(layout, editor):
            self._draw_button(surface, button)

        self._draw_layers(surface, editor, layout)

        # Mode-specific content
        if editor.mode == "tile":
            self._draw_tile_mode(surface, editor, layout)
        elif editor.mode == "entity":
            self._draw_entity_mode(surface, editor, layout)
        elif editor.mode == "walkability":
            self._draw_walk_mode(surface, editor, layout)

        self._draw_status(surface, editor, layout)
        self.window.flip()

    def _draw_tile_mode(self, surface: pygame.Surface, editor: "LevelEditor", layout: dict[str, pygame.Rect]) -> None:
        """Draw tileset selector and full tileset image view."""
        ts_panel = layout.get("tileset_panel")
        if ts_panel:
            self._draw_panel(surface, ts_panel, "Tileset")

        # Tileset selector buttons
        for button in self._tileset_selector_buttons(layout, editor):
            self._draw_button(surface, button)

        # Draw tileset name
        ts_selector = layout.get("tileset_selector")
        if ts_selector and editor.current_tileset_path:
            name = Path(editor.current_tileset_path).stem
            self._draw_text(surface, name, (ts_selector.x + 30, ts_selector.y + 4))

        # Draw the full tileset image
        tileset_rect = layout.get("tileset_image")
        if tileset_rect is None or not editor.current_tileset_path:
            return

        try:
            full_image = self.asset_manager.get_image(editor.current_tileset_path)
        except Exception:
            self._draw_text(surface, "Tileset not found", (tileset_rect.x + 4, tileset_rect.y + 4))
            return

        scale = self.TILE_DISPLAY_SCALE
        tile_w = editor.area.tile_size
        tile_h = editor.area.tile_size

        scaled_w = full_image.get_width() * scale
        scaled_h = full_image.get_height() * scale
        scaled_image = pygame.transform.scale(full_image, (scaled_w, scaled_h))

        # Clip and blit with scroll
        old_clip = surface.get_clip()
        surface.set_clip(tileset_rect)
        surface.blit(scaled_image, (tileset_rect.x, tileset_rect.y - self.tileset_scroll_y))

        # Grid overlay
        columns = max(1, full_image.get_width() // tile_w)
        rows = max(1, full_image.get_height() // tile_h)
        cell_w = tile_w * scale
        cell_h = tile_h * scale
        grid_color = (255, 255, 255, 40)
        grid_surface = pygame.Surface((scaled_w, scaled_h), pygame.SRCALPHA)
        for col in range(columns + 1):
            x = col * cell_w
            pygame.draw.line(grid_surface, grid_color, (x, 0), (x, scaled_h))
        for row in range(rows + 1):
            y = row * cell_h
            pygame.draw.line(grid_surface, grid_color, (0, y), (scaled_w, y))
        surface.blit(grid_surface, (tileset_rect.x, tileset_rect.y - self.tileset_scroll_y))

        # Selection highlight
        selected_frame = self._get_selected_local_frame(editor)
        if selected_frame is not None and selected_frame >= 0:
            sel_col = selected_frame % columns
            sel_row = selected_frame // columns
            sel_x = tileset_rect.x + sel_col * cell_w
            sel_y = tileset_rect.y + sel_row * cell_h - self.tileset_scroll_y
            sel_rect = pygame.Rect(sel_x, sel_y, cell_w, cell_h)
            if tileset_rect.colliderect(sel_rect):
                pygame.draw.rect(surface, (110, 150, 210), sel_rect, width=2)

        surface.set_clip(old_clip)

    def _draw_entity_mode(self, surface: pygame.Surface, editor: "LevelEditor", layout: dict[str, pygame.Rect]) -> None:
        """Draw entity template palette, entity stack, and property inspector."""
        # Template palette
        templates_panel = layout.get("templates_panel")
        if templates_panel:
            self._draw_panel(surface, templates_panel, "Templates")
        templates_rect = layout.get("entity_templates")
        if templates_rect:
            self._draw_template_list(surface, editor, templates_rect)

        # Entity stack
        stack_panel = layout.get("stack_panel")
        if stack_panel:
            self._draw_panel(surface, stack_panel, "Entity Stack")
        entity_list = layout.get("entity_list")
        if entity_list:
            self._draw_entity_stack(surface, editor, entity_list)
        for button in self._entity_action_buttons(layout):
            self._draw_button(surface, button)

        # Property inspector
        inspector_panel = layout.get("inspector_panel")
        if inspector_panel:
            self._draw_panel(surface, inspector_panel, "Properties")
        inspector_rect = layout.get("inspector")
        if inspector_rect:
            self._draw_inspector(surface, editor, inspector_rect)

    def _draw_walk_mode(self, surface: pygame.Surface, editor: "LevelEditor", layout: dict[str, pygame.Rect]) -> None:
        """Draw walk/block selector cards."""
        walk_panel = layout.get("walk_panel")
        if walk_panel:
            self._draw_panel(surface, walk_panel, "Walkability")

        walk_rect = layout.get("walk_palette")
        if walk_rect is None:
            return

        items = [("walk", (48, 180, 96)), ("block", (200, 64, 64))]
        for index, (key, color) in enumerate(items):
            card = pygame.Rect(walk_rect.x + 8 + (index * 96), walk_rect.y + 12, 88, 88)
            active = (key == "walk" and editor.walk_brush_walkable) or (key == "block" and not editor.walk_brush_walkable)
            pygame.draw.rect(surface, (38, 55, 79) if active else (24, 29, 38), card)
            pygame.draw.rect(surface, (110, 150, 210) if active else (74, 90, 112), card, width=2 if active else 1)
            swatch = pygame.Rect(card.x + 20, card.y + 16, 48, 48)
            pygame.draw.rect(surface, color, swatch)
            self._draw_text(surface, "Walk" if key == "walk" else "Block", (card.x + 18, card.bottom - 16))

    def _draw_template_list(self, surface: pygame.Surface, editor: "LevelEditor", rect: pygame.Rect) -> None:
        """Draw the entity template list with icons."""
        pygame.draw.rect(surface, (14, 17, 23), rect)
        pygame.draw.rect(surface, (74, 90, 112), rect, width=1)

        visible_rows = self._visible_list_rows(rect)
        start = self.entity_template_scroll
        templates = editor.template_ids[start:start + visible_rows]
        for row_index, template_id in enumerate(templates):
            row_rect = pygame.Rect(rect.x + 2, rect.y + 2 + (row_index * self.ROW_HEIGHT), rect.width - 4, self.ROW_HEIGHT - 2)
            active = template_id == editor.current_template_id
            pygame.draw.rect(surface, (38, 55, 79) if active else (20, 24, 31), row_rect)
            pygame.draw.rect(surface, (110, 150, 210) if active else (74, 90, 112), row_rect, width=1)
            icon = self._template_icon_surface(editor.area.tile_size, template_id, icon_size=14)
            surface.blit(icon, (row_rect.x + 2, row_rect.y + 2))
            self._draw_text(surface, template_id, (row_rect.x + 20, row_rect.y + 4))

    def _draw_entity_stack(self, surface: pygame.Surface, editor: "LevelEditor", list_rect: pygame.Rect) -> None:
        """Draw the current stacked entities with icons."""
        pygame.draw.rect(surface, (14, 17, 23), list_rect)
        pygame.draw.rect(surface, (74, 90, 112), list_rect, width=1)

        entities = editor.entities_for_selected_cell()
        visible_rows = self._visible_list_rows(list_rect)
        start = self.entity_stack_scroll
        for row_index, entity in enumerate(entities[start:start + visible_rows]):
            row_rect = pygame.Rect(list_rect.x + 2, list_rect.y + 2 + (row_index * self.ROW_HEIGHT), list_rect.width - 4, self.ROW_HEIGHT - 2)
            active = entity.entity_id == editor.selected_entity_id
            pygame.draw.rect(surface, (38, 55, 79) if active else (20, 24, 31), row_rect)
            pygame.draw.rect(surface, (110, 150, 210) if active else (74, 90, 112), row_rect, width=1)
            icon = self._entity_icon_surface(entity, 14)
            surface.blit(icon, (row_rect.x + 2, row_rect.y + 2))
            self._draw_text(surface, entity.entity_id, (row_rect.x + 20, row_rect.y + 4))

    def _draw_inspector(self, surface: pygame.Surface, editor: "LevelEditor", rect: pygame.Rect) -> None:
        """Draw the property inspector for the selected entity."""
        pygame.draw.rect(surface, (14, 17, 23), rect)
        pygame.draw.rect(surface, (74, 90, 112), rect, width=1)

        props = editor.selected_entity_properties()
        if not props:
            self._draw_text(surface, "No entity selected", (rect.x + 4, rect.y + 4))
            return

        row_y = rect.y + 4
        for field_name, label, value in props:
            if row_y + self.ROW_HEIGHT > rect.bottom:
                break

            # Label
            self._draw_text(surface, label, (rect.x + 4, row_y + 2))

            # Value (clickable for editable fields)
            value_x = rect.x + rect.width // 2
            value_rect = pygame.Rect(value_x, row_y, rect.width // 2 - 4, self.ROW_HEIGHT - 2)

            # Read-only fields
            is_readonly = field_name in ("template_id", "kind")
            if is_readonly:
                self._draw_text(surface, value[:20], (value_x + 2, row_y + 2))
            else:
                # Editable field
                is_editing = self.active_text_field == f"prop:{field_name}"
                fill = (38, 55, 79) if is_editing else (22, 28, 38)
                pygame.draw.rect(surface, fill, value_rect)
                pygame.draw.rect(surface, (110, 150, 210) if is_editing else (74, 90, 112), value_rect, width=1)
                display_val = self.property_value_buffer if is_editing else value
                self._draw_text(surface, display_val[:20], (value_x + 2, row_y + 2))

            row_y += self.ROW_HEIGHT

    def _draw_layers(self, surface: pygame.Surface, editor: "LevelEditor", layout: dict[str, pygame.Rect]) -> None:
        """Draw the layer list plus controls."""
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

    # --- Layout ---

    def _layout(self, size: tuple[int, int], mode: str) -> dict[str, pygame.Rect]:
        """Return all major panel rectangles, mode-aware."""
        width, height = size
        pad = self.PADDING
        gap = self.GAP

        actions = pygame.Rect(pad, pad, width - (pad * 2), 40)
        modes = pygame.Rect(pad, actions.bottom + gap, actions.width, 40)
        layers = pygame.Rect(pad, modes.bottom + gap, actions.width, 150)

        content_top = layers.bottom + gap
        status = pygame.Rect(pad, height - 20, width - (pad * 2), 16)
        content_bottom = status.y - gap

        result: dict[str, pygame.Rect] = {
            "actions": actions,
            "modes": modes,
            "layers": layers,
            "layers_list": pygame.Rect(layers.x + 6, layers.y + 20, layers.width - 12, 72),
            "layer_name": pygame.Rect(layers.x + 6, layers.bottom - 46, layers.width - 132, 18),
            "layer_rename": pygame.Rect(layers.right - 120, layers.bottom - 46, 114, 18),
            "layer_add": pygame.Rect(layers.x + 6, layers.bottom - 24, (layers.width - 18) // 2, 18),
            "layer_delete": pygame.Rect(layers.x + 12 + ((layers.width - 18) // 2), layers.bottom - 24, (layers.width - 18) // 2, 18),
            "status": status,
        }

        if mode == "tile":
            ts_panel = pygame.Rect(pad, content_top, actions.width, content_bottom - content_top)
            result["tileset_panel"] = ts_panel
            result["tileset_selector"] = pygame.Rect(ts_panel.x + 6, ts_panel.y + 20, ts_panel.width - 12, 22)
            result["tileset_image"] = pygame.Rect(ts_panel.x + 6, ts_panel.y + 46, ts_panel.width - 12, ts_panel.height - 52)

        elif mode == "walkability":
            walk_panel = pygame.Rect(pad, content_top, actions.width, 120)
            result["walk_panel"] = walk_panel
            result["walk_palette"] = pygame.Rect(walk_panel.x + 6, walk_panel.y + 16, walk_panel.width - 12, walk_panel.height - 22)

        elif mode == "entity":
            remaining = content_bottom - content_top
            templates_h = min(180, remaining // 3)
            stack_h = min(140, remaining // 3)
            inspector_h = remaining - templates_h - stack_h - gap * 2

            templates_panel = pygame.Rect(pad, content_top, actions.width, templates_h)
            result["templates_panel"] = templates_panel
            result["entity_templates"] = pygame.Rect(templates_panel.x + 6, templates_panel.y + 20, templates_panel.width - 12, templates_panel.height - 26)

            stack_panel = pygame.Rect(pad, templates_panel.bottom + gap, actions.width, stack_h)
            result["stack_panel"] = stack_panel
            result["entity_list"] = pygame.Rect(stack_panel.x + 6, stack_panel.y + 20, stack_panel.width - 12, max(30, stack_panel.height - 46))
            result["entity_buttons"] = pygame.Rect(stack_panel.x + 6, stack_panel.bottom - 22, stack_panel.width - 12, 18)

            inspector_panel = pygame.Rect(pad, stack_panel.bottom + gap, actions.width, inspector_h)
            result["inspector_panel"] = inspector_panel
            result["inspector"] = pygame.Rect(inspector_panel.x + 6, inspector_panel.y + 20, inspector_panel.width - 12, inspector_panel.height - 26)

        return result

    # --- Button definitions ---

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

    def _tileset_selector_buttons(self, layout: dict[str, pygame.Rect], editor: "LevelEditor") -> list[BrowserButton]:
        """Return prev/next buttons for the tileset selector."""
        ts_selector = layout.get("tileset_selector")
        if ts_selector is None:
            return []
        return [
            BrowserButton("ts:prev", pygame.Rect(ts_selector.x, ts_selector.y, 24, 18), "<"),
            BrowserButton("ts:next", pygame.Rect(ts_selector.right - 24, ts_selector.y, 24, 18), ">"),
        ]

    def _entity_action_buttons(self, layout: dict[str, pygame.Rect]) -> list[BrowserButton]:
        """Return buttons for entity stack management."""
        rect = layout.get("entity_buttons")
        if rect is None:
            return []
        width = (rect.width - (self.GAP * 2)) // 3
        return [
            BrowserButton("entity:up", pygame.Rect(rect.x, rect.y, width, rect.height), "Up"),
            BrowserButton("entity:down", pygame.Rect(rect.x + width + self.GAP, rect.y, width, rect.height), "Down"),
            BrowserButton("entity:delete", pygame.Rect(rect.x + ((width + self.GAP) * 2), rect.y, width, rect.height), "Delete"),
        ]

    # --- Hit testing ---

    def _visible_list_rows(self, rect: pygame.Rect) -> int:
        """Return how many list rows fit in a scrollable list box."""
        return max(1, (rect.height - 4) // self.ROW_HEIGHT)

    def _layer_index_at(self, editor: "LevelEditor", rect: pygame.Rect, mouse_pos: tuple[int, int]) -> int | None:
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

    def _tileset_frame_at(self, editor: "LevelEditor", rect: pygame.Rect, mouse_pos: tuple[int, int]) -> int | None:
        """Return the local frame index clicked in the tileset image view."""
        if not rect.collidepoint(mouse_pos):
            return None

        tileset_path = editor.current_tileset_path
        if not tileset_path:
            return None

        scale = self.TILE_DISPLAY_SCALE
        tile_w = editor.area.tile_size
        tile_h = editor.area.tile_size

        local_x = mouse_pos[0] - rect.x
        local_y = mouse_pos[1] - rect.y + self.tileset_scroll_y

        column = int(local_x // (tile_w * scale))
        row = int(local_y // (tile_h * scale))

        try:
            img_w, img_h = self.asset_manager.get_image_size(tileset_path)
        except Exception:
            return None

        columns = max(1, img_w // tile_w)
        total_rows = max(1, img_h // tile_h)

        if column < 0 or column >= columns or row < 0 or row >= total_rows:
            return None

        frame = row * columns + column
        total_frames = columns * total_rows
        if frame >= total_frames:
            return None
        return frame

    def _tileset_max_scroll(self, editor: "LevelEditor", rect: pygame.Rect) -> int:
        """Return the maximum vertical scroll for the tileset view."""
        tileset_path = editor.current_tileset_path
        if not tileset_path:
            return 0
        try:
            _, img_h = self.asset_manager.get_image_size(tileset_path)
        except Exception:
            return 0
        scaled_h = img_h * self.TILE_DISPLAY_SCALE
        return max(0, scaled_h - rect.height)

    def _get_selected_local_frame(self, editor: "LevelEditor") -> int | None:
        """Get the local frame index of the selected GID in the currently viewed tileset."""
        if editor.selected_gid <= 0:
            return None
        tileset_path = editor.current_tileset_path
        for ts in editor.area.tilesets:
            if ts.path == tileset_path and ts.contains_gid(editor.selected_gid):
                return ts.local_frame(editor.selected_gid)
        return None

    def _template_index_at(self, editor: "LevelEditor", rect: pygame.Rect, mouse_pos: tuple[int, int]) -> int | None:
        """Return the clicked template index."""
        if not rect.collidepoint(mouse_pos):
            return None
        local_y = mouse_pos[1] - rect.y - 2
        row = local_y // self.ROW_HEIGHT
        if row < 0:
            return None
        return self.entity_template_scroll + row

    def _entity_index_at(self, editor: "LevelEditor", rect: pygame.Rect, mouse_pos: tuple[int, int]) -> int | None:
        """Return the clicked entity index inside the selected-cell stack list."""
        if not rect.collidepoint(mouse_pos):
            return None
        local_y = mouse_pos[1] - rect.y - 2
        row = local_y // self.ROW_HEIGHT
        if row < 0:
            return None
        return self.entity_stack_scroll + row

    def _property_field_at(self, editor: "LevelEditor", rect: pygame.Rect, mouse_pos: tuple[int, int]) -> tuple[str, str] | None:
        """Return (field_name, current_value) for the clicked property row."""
        props = editor.selected_entity_properties()
        if not props:
            return None

        local_y = mouse_pos[1] - rect.y - 4
        row = local_y // self.ROW_HEIGHT
        if row < 0 or row >= len(props):
            return None

        field_name, _, value = props[row]
        # Don't allow editing read-only fields
        if field_name in ("template_id", "kind"):
            return None

        # Only respond to clicks in the value half
        value_x = rect.x + rect.width // 2
        if mouse_pos[0] < value_x:
            return None

        return (field_name, value)

    # --- Icon helpers ---

    def _template_icon_surface(self, tile_size: int, template_id: str, *, icon_size: int) -> pygame.Surface:
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
