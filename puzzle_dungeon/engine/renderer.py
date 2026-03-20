"""Simple pixel-art style rendering for play mode.

Renders GID-based tile layers and entities. Uses the Area's resolve_gid()
method to map integer tile IDs to tileset frames.

Depends on: config, asset_manager, camera, text, area, world
Used by: game
"""

from __future__ import annotations

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

    def render(
        self,
        area: Area,
        world: World,
        camera: Camera,
        *,
        status_message: str = "",
        has_save_file: bool = False,
        persistent_state_dirty: bool = False,
    ) -> None:
        """Render the current area and all visible entities."""
        self.internal_surface.fill(config.COLOR_BACKGROUND)
        self._draw_tile_layers(area, camera, draw_above_entities=False)
        self._draw_entities(area, world, camera)
        self._draw_tile_layers(area, camera, draw_above_entities=True)
        self._draw_play_overlay(
            world,
            status_message=status_message,
            has_save_file=has_save_file,
            persistent_state_dirty=persistent_state_dirty,
        )

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

    def _draw_play_overlay(
        self,
        world: World,
        *,
        status_message: str,
        has_save_file: bool,
        persistent_state_dirty: bool,
    ) -> None:
        """Draw a compact play-mode HUD that fits the internal surface."""
        player = world.get_player()
        live_state = "dirty" if persistent_state_dirty else "clean"
        save_state = "yes" if has_save_file else "no"
        lines = [
            "PLAY  ESC quit",
            "Move WASD/arrows",
            "SPC act  F5 save  F9 load",
            f"Live {live_state}  Disk save {save_state}",
            f"P ({player.grid_x},{player.grid_y})  Face {player.facing}",
        ]
        if status_message:
            lines.append(status_message)
        self._draw_text_panel(lines, x=6, y=6)

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
