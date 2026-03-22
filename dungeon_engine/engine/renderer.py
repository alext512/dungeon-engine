"""Simple pixel-art style rendering for play mode.

Renders GID-based tile layers and entities. Uses the Area's resolve_gid()
method to map integer tile IDs to tileset frames.

Depends on: config, asset_manager, camera, area, world
Used by: game
"""

from __future__ import annotations

import pygame

from dungeon_engine import config
from dungeon_engine.engine.asset_manager import AssetManager
from dungeon_engine.engine.camera import Camera
from dungeon_engine.engine.screen import ScreenElementManager
from dungeon_engine.engine.text import TextRenderer
from dungeon_engine.world.area import Area
from dungeon_engine.world.world import World


class Renderer:
    """Draw tile data and entities."""

    def __init__(
        self,
        display_surface: pygame.Surface,
        asset_manager: AssetManager,
        *,
        internal_width: int = config.INTERNAL_WIDTH,
        internal_height: int = config.INTERNAL_HEIGHT,
        output_scale: int = config.SCALE,
    ) -> None:
        self.display_surface = display_surface
        self.asset_manager = asset_manager
        self.internal_width = max(1, int(internal_width))
        self.internal_height = max(1, int(internal_height))
        self.output_scale = max(1, int(output_scale))
        self.text_renderer = TextRenderer(asset_manager)
        self.internal_surface = pygame.Surface(
            (self.internal_width, self.internal_height)
        )

    def set_display_surface(self, display_surface: pygame.Surface) -> None:
        """Swap the window surface after the game recreates the display."""
        self.display_surface = display_surface

    def set_output_scale(self, output_scale: int) -> None:
        """Change the integer window magnification used for rendering."""
        self.output_scale = max(1, int(output_scale))

    def render(
        self,
        area: Area,
        world: World,
        camera: Camera,
        screen_elements: ScreenElementManager | None = None,
    ) -> None:
        """Render the current area and all visible entities."""
        self.internal_surface.fill(config.COLOR_BACKGROUND)
        self._draw_tile_layers(area, camera, draw_above_entities=False)
        self._draw_entities(area, world, camera)
        self._draw_tile_layers(area, camera, draw_above_entities=True)
        if screen_elements is not None:
            self._draw_screen_elements(screen_elements)

        scaled_surface = pygame.transform.scale(
            self.internal_surface,
            (
                self.internal_width * self.output_scale,
                self.internal_height * self.output_scale,
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
                if entity.sprite_flip_x:
                    sprite_surface = pygame.transform.flip(sprite_surface, True, False)
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

    def _draw_screen_elements(self, screen_elements: ScreenElementManager) -> None:
        """Draw generic screen-space elements above the world."""
        for element in screen_elements.iter_elements():
            if not element.visible:
                continue
            if element.kind == "image":
                self._draw_screen_image(element)
            elif element.kind == "text":
                self._draw_screen_text(element)

    def _draw_screen_image(self, element) -> None:
        """Draw one screen-space image element."""
        if not element.asset_path:
            return
        if element.frame_width is not None and element.frame_height is not None:
            surface = self.asset_manager.get_frame(
                element.asset_path,
                element.frame_width,
                element.frame_height,
                element.frame_index,
            )
        else:
            surface = self.asset_manager.get_image(element.asset_path)

        if element.flip_x:
            surface = pygame.transform.flip(surface, True, False)
        surface = self._apply_tint(surface, element.tint)

        draw_x, draw_y = self._resolve_screen_anchor(
            element.x,
            element.y,
            surface.get_width(),
            surface.get_height(),
            element.anchor,
        )
        self.internal_surface.blit(surface, (draw_x, draw_y))

    def _draw_screen_text(self, element) -> None:
        """Draw one screen-space text element."""
        text = element.text
        if element.max_width is not None:
            text = self.text_renderer.wrap_text(
                text,
                int(element.max_width),
                font_id=element.font_id,
            )
        width, height = self.text_renderer.measure_text(text, font_id=element.font_id)
        draw_x, draw_y = self._resolve_screen_anchor(
            element.x,
            element.y,
            width,
            height,
            element.anchor,
        )
        self.text_renderer.render_text(
            self.internal_surface,
            text,
            (draw_x, draw_y),
            element.color,
            font_id=element.font_id,
        )

    def _resolve_screen_anchor(
        self,
        x: float,
        y: float,
        width: int,
        height: int,
        anchor: str,
    ) -> tuple[int, int]:
        """Convert an anchored screen-space point into a draw origin."""
        draw_x = float(x)
        draw_y = float(y)

        if anchor in {"top", "center", "bottom"}:
            draw_x -= width / 2
        elif anchor in {"topright", "right", "bottomright"}:
            draw_x -= width

        if anchor in {"left", "center", "right"}:
            draw_y -= height / 2
        elif anchor in {"bottomleft", "bottom", "bottomright"}:
            draw_y -= height

        if config.PIXEL_ART_MODE:
            return round(draw_x), round(draw_y)
        return int(draw_x), int(draw_y)

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

