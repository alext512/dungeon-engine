"""Simple pixel-art style rendering for the starter room prototype.

Renders GID-based tile layers, entities, and editor overlays. Uses the Area's
resolve_gid() method to map integer tile IDs to tileset frames.

Depends on: config, asset_manager, camera, text, area, world, editor
Used by: game
"""

from __future__ import annotations

from typing import Any

import pygame

from puzzle_dungeon import config
from puzzle_dungeon.engine.asset_manager import AssetManager
from puzzle_dungeon.engine.camera import Camera
from puzzle_dungeon.engine.text import TextRenderer
from puzzle_dungeon.world.area import Area
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
        """Draw all tile layers for the requested render phase using GID resolution."""
        tile_size = area.tile_size
        for layer in area.iter_tile_layers(draw_above_entities=draw_above_entities):
            for grid_y, row in enumerate(layer.grid):
                for grid_x, gid in enumerate(row):
                    if gid <= 0:
                        continue

                    resolved = area.resolve_gid(gid)
                    if resolved is None:
                        continue

                    tileset_path, tile_w, tile_h, local_frame = resolved
                    screen_x, screen_y = self._world_to_screen(
                        grid_x * tile_size,
                        grid_y * tile_size,
                        camera,
                    )
                    frame_surface = self.asset_manager.get_frame(
                        tileset_path, tile_w, tile_h, local_frame
                    )
                    self.internal_surface.blit(frame_surface, (screen_x, screen_y))

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

        if editor.mode == "tile" and editor.selected_gid > 0:
            resolved = area.resolve_gid(editor.selected_gid)
            if resolved is not None:
                tileset_path, tile_w, tile_h, local_frame = resolved
                preview_surface = self.asset_manager.get_frame(
                    tileset_path, tile_w, tile_h, local_frame
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
