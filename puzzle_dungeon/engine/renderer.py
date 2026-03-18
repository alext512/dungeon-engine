"""Simple pixel-art style rendering for the starter room prototype."""

from __future__ import annotations

from typing import Any

import pygame

from puzzle_dungeon import config
from puzzle_dungeon.engine.asset_manager import AssetManager
from puzzle_dungeon.engine.camera import Camera
from puzzle_dungeon.engine.text import TextRenderer
from puzzle_dungeon.world.area import Area
from puzzle_dungeon.world.loader import load_entity_template
from puzzle_dungeon.world.world import World


class Renderer:
    """Draw tile data, entities, and a small debug HUD."""

    def __init__(
        self,
        display_surface: pygame.Surface,
        asset_manager: AssetManager,
    ) -> None:
        self.display_surface = display_surface
        self.asset_manager = asset_manager
        self.internal_surface = pygame.Surface(
            (config.INTERNAL_WIDTH, config.INTERNAL_HEIGHT)
        )
        self.text_renderer = TextRenderer(asset_manager)

    def render(self, area: Area, world: World, camera: Camera) -> None:
        """Render the current area and all visible entities."""
        self.internal_surface.fill(config.COLOR_BACKGROUND)
        self._draw_tile_layers(area, camera, draw_above_entities=False)
        self._draw_entities(area, world, camera)
        self._draw_tile_layers(area, camera, draw_above_entities=True)
        self._draw_play_overlay(world)

        scaled_surface = pygame.transform.scale(
            self.internal_surface,
            (
                config.INTERNAL_WIDTH * config.SCALE,
                config.INTERNAL_HEIGHT * config.SCALE,
            ),
        )
        self.display_surface.blit(scaled_surface, (0, 0))
        pygame.display.flip()

    def render_with_editor(
        self,
        area: Area,
        world: World,
        camera: Camera,
        editor: Any,
    ) -> None:
        """Render the current room plus the visual editor interface."""
        self.internal_surface.fill(config.COLOR_BACKGROUND)
        self.internal_surface.set_clip(editor.map_viewport_rect)
        self._draw_tile_layers(area, camera, draw_above_entities=False)
        self._draw_entities(area, world, camera)
        self._draw_tile_layers(area, camera, draw_above_entities=True)
        self._draw_editor_overlay(area, world, camera, editor)
        self.internal_surface.set_clip(None)

        scaled_surface = pygame.transform.scale(
            self.internal_surface,
            (
                config.INTERNAL_WIDTH * config.SCALE,
                config.INTERNAL_HEIGHT * config.SCALE,
            ),
        )
        self.display_surface.blit(scaled_surface, (0, 0))
        pygame.display.flip()

    def _draw_tile_layers(
        self,
        area: Area,
        camera: Camera,
        *,
        draw_above_entities: bool,
    ) -> None:
        """Draw all tile layers for the requested render phase."""
        tile_size = area.tile_size
        for layer in area.iter_tile_layers(draw_above_entities=draw_above_entities):
            for grid_y, row in enumerate(layer.grid):
                for grid_x, tile_id in enumerate(row):
                    if tile_id is None:
                        continue

                    screen_x, screen_y = self._world_to_screen(
                        grid_x * tile_size,
                        grid_y * tile_size,
                        camera,
                    )
                    rect = pygame.Rect(screen_x, screen_y, tile_size, tile_size)
                    tile_definition = area.tile_definition(tile_id)
                    sprite_data = tile_definition.get("sprite")
                    if sprite_data:
                        frame_surface = self.asset_manager.get_frame(
                            str(sprite_data["path"]),
                            int(sprite_data.get("frame_width", tile_size)),
                            int(sprite_data.get("frame_height", tile_size)),
                            int(sprite_data.get("frame", 0)),
                        )
                        self.internal_surface.blit(frame_surface, rect.topleft)
                    else:
                        fallback_color = config.COLOR_WALL if not area.is_walkable(grid_x, grid_y) else config.COLOR_FLOOR
                        pygame.draw.rect(self.internal_surface, fallback_color, rect)
                        pygame.draw.rect(
                            self.internal_surface,
                            config.COLOR_GRID_ACCENT,
                            rect,
                            width=1,
                        )

    def _draw_entities(self, area: Area, world: World, camera: Camera) -> None:
        tile_size = area.tile_size
        for entity in sorted(
            world.iter_entities(),
            key=lambda item: (item.layer, item.pixel_y, item.stack_order, item.pixel_x, item.entity_id),
        ):
            if not entity.visible:
                continue

            if entity.sprite_path:
                sprite_surface = self.asset_manager.get_frame(
                    entity.sprite_path,
                    entity.sprite_frame_width,
                    entity.sprite_frame_height,
                    entity.current_frame,
                )
                sprite_surface = self._apply_tint(sprite_surface, entity.color)
                screen_x, screen_y = self._world_to_screen(
                    entity.pixel_x,
                    entity.pixel_y,
                    camera,
                )
                self.internal_surface.blit(
                    sprite_surface,
                    (screen_x, screen_y),
                )
                continue

            inset = 2 if entity.kind == "player" else 3
            screen_x, screen_y = self._world_to_screen(
                entity.pixel_x,
                entity.pixel_y,
                camera,
            )
            rect = pygame.Rect(
                screen_x + inset,
                screen_y + inset,
                tile_size - (inset * 2),
                tile_size - (inset * 2),
            )
            pygame.draw.rect(self.internal_surface, entity.color, rect, border_radius=2)

    def _world_to_screen(
        self,
        world_x: float,
        world_y: float,
        camera: Camera,
    ) -> tuple[int, int]:
        """Convert world coordinates to screen coordinates with optional snapping."""
        screen_x = world_x - camera.render_x
        screen_y = world_y - camera.render_y

        if config.PIXEL_ART_MODE:
            return round(screen_x), round(screen_y)
        return int(screen_x), int(screen_y)

    def _apply_tint(
        self,
        surface: pygame.Surface,
        tint: tuple[int, int, int],
    ) -> pygame.Surface:
        """Apply a lightweight tint so commands can still recolor debug sprites."""
        if tint == (255, 255, 255):
            return surface

        tinted = surface.copy()
        tinted.fill((*tint, 255), special_flags=pygame.BLEND_RGBA_MULT)
        return tinted

    def _draw_play_overlay(self, world: World) -> None:
        """Draw a compact play-mode HUD that fits the internal surface."""
        player = world.get_player()
        lines = [
            "PLAY  F1 editor  ESC quit",
            "Move WASD/arrows",
            "SPC act",
            f"P ({player.grid_x},{player.grid_y})  Face {player.facing}",
        ]
        self._draw_text_panel(lines, x=6, y=6)

    def _draw_editor_overlay(
        self,
        area: Area,
        world: World,
        camera: Camera,
        editor: Any,
    ) -> None:
        """Draw editor viewport overlays plus the surrounding UI panels."""
        if editor.mode == "walkability":
            overlay_surface = pygame.Surface(
                (config.INTERNAL_WIDTH, config.INTERNAL_HEIGHT),
                pygame.SRCALPHA,
            )
            for grid_y, row in enumerate(area.cell_flags):
                for grid_x, flags in enumerate(row):
                    screen_x, screen_y = self._world_to_screen(
                        grid_x * area.tile_size,
                        grid_y * area.tile_size,
                        camera,
                    )
                    color = (48, 180, 96, 70) if flags.get("walkable", True) else (200, 64, 64, 90)
                    pygame.draw.rect(
                        overlay_surface,
                        color,
                        pygame.Rect(screen_x, screen_y, area.tile_size, area.tile_size),
                    )
            self.internal_surface.blit(overlay_surface, (0, 0))

        self._draw_stack_badges(area, world, camera, editor)
        self._draw_editor_preview(area, camera, editor)

        if editor.selected_cell is not None:
            grid_x, grid_y = editor.selected_cell
            screen_x, screen_y = self._world_to_screen(
                grid_x * area.tile_size,
                grid_y * area.tile_size,
                camera,
            )
            pygame.draw.rect(
                self.internal_surface,
                (248, 218, 94),
                pygame.Rect(screen_x, screen_y, area.tile_size, area.tile_size),
                width=2,
            )

        if editor.hovered_cell is not None:
            grid_x, grid_y = editor.hovered_cell
            screen_x, screen_y = self._world_to_screen(
                grid_x * area.tile_size,
                grid_y * area.tile_size,
                camera,
            )
            pygame.draw.rect(
                self.internal_surface,
                (255, 255, 255),
                pygame.Rect(screen_x, screen_y, area.tile_size, area.tile_size),
                width=1,
            )

        self.internal_surface.set_clip(None)
        palette_line = "Palette tiles"
        if editor.mode == "walkability":
            palette_line = f"Flags {editor.current_walk_brush_label}"
        elif editor.mode == "entity":
            palette_line = "Palette entities"
        self._draw_text_panel(
            [
                "EDITOR  F1 play",
                f"Mode {editor.mode_label}",
                f"Layer {editor.current_layer_name}",
                palette_line,
                f"Sel {editor.selected_cell_label}",
                editor.workflow_hint(),
            ],
            x=6,
            y=6,
        )

    def _draw_editor_preview(self, area: Area, camera: Camera, editor: Any) -> None:
        """Preview the currently selected tile or entity under the cursor."""
        if editor.hovered_cell is None:
            return

        grid_x, grid_y = editor.hovered_cell
        screen_x, screen_y = self._world_to_screen(
            grid_x * area.tile_size,
            grid_y * area.tile_size,
            camera,
        )
        draw_position = (screen_x, screen_y)

        if editor.mode == "tile" and editor.current_tile_id:
            tile_definition = area.tile_definition(editor.current_tile_id)
            sprite_data = tile_definition.get("sprite")
            if sprite_data:
                preview_surface = self.asset_manager.get_frame(
                    str(sprite_data["path"]),
                    int(sprite_data.get("frame_width", area.tile_size)),
                    int(sprite_data.get("frame_height", area.tile_size)),
                    int(sprite_data.get("frame", 0)),
                ).copy()
                preview_surface.set_alpha(150)
                self.internal_surface.blit(preview_surface, draw_position)
            else:
                preview_surface = pygame.Surface((area.tile_size, area.tile_size), pygame.SRCALPHA)
                preview_surface.fill((*config.COLOR_TEXT, 120))
                self.internal_surface.blit(preview_surface, draw_position)
            return

        preview_entity = editor.build_preview_entity()
        if preview_entity is None:
            return

        if preview_entity.sprite_path:
            preview_surface = self.asset_manager.get_frame(
                preview_entity.sprite_path,
                preview_entity.sprite_frame_width,
                preview_entity.sprite_frame_height,
                preview_entity.current_frame,
            )
            preview_surface = self._apply_tint(preview_surface, preview_entity.color).copy()
            preview_surface.set_alpha(160)
            self.internal_surface.blit(preview_surface, draw_position)
            return

        preview_surface = pygame.Surface((area.tile_size, area.tile_size), pygame.SRCALPHA)
        preview_surface.fill((*preview_entity.color, 140))
        self.internal_surface.blit(preview_surface, draw_position)

    def _draw_stack_badges(self, area: Area, world: World, camera: Camera, editor: Any) -> None:
        """Draw a small count badge on cells with stacked non-player entities."""
        counts: dict[tuple[int, int], int] = {}
        for entity in world.iter_entities():
            if not entity.visible or entity.entity_id == world.player_id:
                continue
            key = (entity.grid_x, entity.grid_y)
            counts[key] = counts.get(key, 0) + 1

        for (grid_x, grid_y), count in counts.items():
            if count < 2:
                continue
            screen_x, screen_y = self._world_to_screen(
                grid_x * area.tile_size,
                grid_y * area.tile_size,
                camera,
            )
            badge_rect = pygame.Rect(screen_x + area.tile_size - 9, screen_y, 9, 8)
            pygame.draw.rect(self.internal_surface, (12, 14, 20), badge_rect)
            pygame.draw.rect(self.internal_surface, (219, 226, 240), badge_rect, width=1)
            self.text_renderer.render_text(
                self.internal_surface,
                str(count),
                (badge_rect.x + 2, badge_rect.y + 1),
                config.COLOR_TEXT,
            )

    def _draw_editor_panels(self, area: Area, world: World, editor: Any) -> None:
        """Draw the browser and selected-cell windows around the map canvas."""
        self._draw_panel(editor.right_panel_rect, "Browser")
        self._draw_panel(editor.bottom_panel_rect, "Cell")

        for item in editor.toolbar_items():
            self._draw_ui_button(item)

        self._draw_panel_text("Layer", (editor.right_panel_rect.x + 4, 50))
        for item in editor.layer_items():
            self._draw_ui_button(item)

        self._draw_panel_text(editor.palette_title, (editor.right_panel_rect.x + 4, 74))
        for item in editor.palette_items():
            self._draw_palette_item(area, item)

        browser_bottom = editor.right_panel_rect.bottom
        self._draw_panel_text(editor.status_message[:17], (editor.right_panel_rect.x + 4, browser_bottom - 28))
        self._draw_panel_text(editor.workflow_hint(), (editor.right_panel_rect.x + 4, browser_bottom - 18))
        self._draw_inspector(area, world, editor)

    def _draw_inspector(self, area: Area, world: World, editor: Any) -> None:
        """Draw selected-cell data with separate layer and entity sections."""
        panel = editor.bottom_panel_rect
        self._draw_panel_text(f"Cell {editor.selected_cell_label}", (panel.x + 4, panel.y + 14))
        self._draw_panel_text(f"Walk {editor.cell_walk_label}", (panel.x + 4, panel.y + 24))
        self._draw_panel_text("Layers", (panel.x + 4, panel.y + 36))
        for index, line in enumerate(editor.selected_layer_lines()):
            self._draw_panel_text(line, (panel.x + 4, panel.y + 46 + (index * 10)))

        self._draw_panel_text("Entities", (panel.x + 92, panel.y + 14))
        for item in editor.inspector_entity_items():
            self._draw_entity_row(world, item)

        if not editor.inspector_entity_items():
            self._draw_panel_text("none", (panel.x + 92, panel.y + 24))

        for item in editor.stack_action_items():
            self._draw_ui_button(item)

    def _draw_ui_button(self, item: Any) -> None:
        """Draw a simple rectangular button or chip."""
        self._draw_ui_frame(item)
        text_width, text_height = self.text_renderer.measure_text(item.label)
        text_x = item.rect.x + max(2, (item.rect.width - text_width) // 2)
        text_y = item.rect.y + max(2, (item.rect.height - text_height) // 2)
        self.text_renderer.render_text(
            self.internal_surface,
            item.label,
            (text_x, text_y),
            config.COLOR_TEXT,
        )

    def _draw_ui_frame(self, item: Any) -> None:
        """Draw just the background and border for a UI item."""
        fill_color = (38, 55, 79) if item.active else (22, 28, 38)
        border_color = (110, 150, 210) if item.active else (74, 90, 112)
        pygame.draw.rect(self.internal_surface, fill_color, item.rect)
        pygame.draw.rect(self.internal_surface, border_color, item.rect, width=1)

    def _draw_palette_item(self, area: Area, item: Any) -> None:
        """Draw a palette row with icon plus label."""
        self._draw_ui_frame(item)
        text_x = item.rect.x + 20
        if item.key.startswith("palette:tile:"):
            tile_id = item.key.split(":", 2)[2]
            self._draw_tile_icon(area, tile_id, (item.rect.x + 2, item.rect.y + 1))
        elif item.key.startswith("palette:template:"):
            template_id = item.key.split(":", 2)[2]
            self._draw_template_icon(area.tile_size, template_id, (item.rect.x + 2, item.rect.y + 1))
        else:
            text_x = item.rect.x + 4
        self.text_renderer.render_text(
            self.internal_surface,
            item.label,
            (text_x, item.rect.y + 5),
            config.COLOR_TEXT,
        )

    def _draw_entity_row(self, world: World, item: Any) -> None:
        """Draw one stacked-entity row in the inspector."""
        self._draw_ui_frame(item)
        entity = world.get_entity(item.key.split(":", 1)[1])
        if entity is not None:
            self._draw_entity_icon(entity, (item.rect.x + 2, item.rect.y))
        self.text_renderer.render_text(
            self.internal_surface,
            item.label,
            (item.rect.x + 18, item.rect.y + 2),
            config.COLOR_TEXT,
        )

    def _draw_tile_icon(self, area: Area, tile_id: str, position: tuple[int, int]) -> None:
        """Draw a 16x16 tile preview icon."""
        tile_definition = area.tile_definition(tile_id)
        sprite_data = tile_definition.get("sprite")
        if sprite_data:
            frame_surface = self.asset_manager.get_frame(
                str(sprite_data["path"]),
                int(sprite_data.get("frame_width", area.tile_size)),
                int(sprite_data.get("frame_height", area.tile_size)),
                int(sprite_data.get("frame", 0)),
            )
            self.internal_surface.blit(frame_surface, position)
            return

        fallback = pygame.Surface((area.tile_size, area.tile_size), pygame.SRCALPHA)
        fallback.fill(config.COLOR_GRID_ACCENT)
        self.internal_surface.blit(fallback, position)

    def _draw_template_icon(self, tile_size: int, template_id: str, position: tuple[int, int]) -> None:
        """Draw a template preview icon for the palette."""
        template = load_entity_template(template_id)
        sprite_data = dict(template.get("sprite", {}))
        if sprite_data.get("path"):
            frame_surface = self.asset_manager.get_frame(
                str(sprite_data["path"]),
                int(sprite_data.get("frame_width", tile_size)),
                int(sprite_data.get("frame_height", tile_size)),
                int(sprite_data.get("frames", [0])[0]),
            )
            self.internal_surface.blit(frame_surface, position)
            return

        color = tuple(template.get("color", [255, 255, 255]))
        preview_surface = pygame.Surface((tile_size, tile_size), pygame.SRCALPHA)
        preview_surface.fill((*color, 255))
        self.internal_surface.blit(preview_surface, position)

    def _draw_entity_icon(self, entity: Any, position: tuple[int, int]) -> None:
        """Draw an entity preview icon for the selected-cell stack."""
        if entity.sprite_path:
            sprite_surface = self.asset_manager.get_frame(
                entity.sprite_path,
                entity.sprite_frame_width,
                entity.sprite_frame_height,
                entity.current_frame,
            )
            sprite_surface = self._apply_tint(sprite_surface, entity.color)
            self.internal_surface.blit(sprite_surface, position)
            return

        preview_surface = pygame.Surface((16, 16), pygame.SRCALPHA)
        preview_surface.fill((*entity.color, 255))
        self.internal_surface.blit(preview_surface, position)

    def _draw_panel(self, rect: pygame.Rect, title: str, *, fill: bool = True) -> None:
        """Draw a framed editor window with a tiny title strip."""
        if fill:
            pygame.draw.rect(self.internal_surface, (10, 14, 20), rect)
        pygame.draw.rect(self.internal_surface, (82, 98, 124), rect, width=1)
        if not title:
            return

        title_rect = pygame.Rect(rect.x + 1, rect.y + 1, rect.width - 2, 10)
        pygame.draw.rect(self.internal_surface, (20, 27, 38), title_rect)
        self._draw_panel_text(title, (rect.x + 4, rect.y + 2))

    def _draw_panel_text(self, text: str, position: tuple[int, int]) -> None:
        """Draw a short panel label using the shared bitmap font."""
        self.text_renderer.render_text(
            self.internal_surface,
            text,
            position,
            config.COLOR_TEXT,
        )

    def _draw_wrapped_status(self, text: str, panel_rect: pygame.Rect) -> None:
        """Draw a short wrapped status message near the bottom of the toolbox."""
        lines = self._wrap_text(text, panel_rect.width - 8)
        base_y = panel_rect.bottom - (len(lines) * self.text_renderer.line_height()) - 6
        for index, line in enumerate(lines[:3]):
            self._draw_panel_text(line, (panel_rect.x + 4, base_y + (index * self.text_renderer.line_height())))

    def _wrap_text(self, text: str, max_width: int) -> list[str]:
        """Wrap a short status string to fit a narrow panel."""
        words = text.split()
        if not words:
            return [""]

        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if self.text_renderer.measure_text(candidate)[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _draw_text_panel(
        self,
        lines: list[str],
        *,
        x: int,
        y: int,
        font_id: str = config.DEFAULT_UI_FONT_ID,
    ) -> None:
        """Draw a translucent text panel with consistent line spacing."""
        if not lines:
            return

        line_height = self.text_renderer.line_height(font_id=font_id)
        width = max(self.text_renderer.measure_text(line, font_id=font_id)[0] for line in lines) + 8
        height = len(lines) * line_height + 8
        panel_surface = pygame.Surface((width, height), pygame.SRCALPHA)
        panel_surface.fill((8, 10, 16, 220))
        self.internal_surface.blit(panel_surface, (x, y))
        for index, text in enumerate(lines):
            self.text_renderer.render_text(
                self.internal_surface,
                text,
                (x + 4, y + 4 + (index * line_height)),
                config.COLOR_TEXT,
                font_id=font_id,
            )
