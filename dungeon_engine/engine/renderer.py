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


class _WorldRenderItem:
    """One sortable drawable in world space."""

    __slots__ = ("sort_key", "draw_kind", "payload")

    def __init__(self, sort_key: tuple, draw_kind: str, payload: tuple) -> None:
        self.sort_key = sort_key
        self.draw_kind = draw_kind
        self.payload = payload


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
        self._static_tile_layer_cache: dict[tuple, pygame.Surface] = {}

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
        self._draw_world_scene(area, world, camera)
        self._draw_screen_entities(world)
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

    def _draw_world_scene(self, area: Area, world: World, camera: Camera) -> None:
        """Draw world tile layers and world entities in one unified sort space."""
        for item in sorted(self._collect_world_render_items(area, world), key=lambda current: current.sort_key):
            if item.draw_kind == "tile_layer":
                self._draw_tile_layer(area, camera, item.payload[0])
                continue
            if item.draw_kind == "tile_cell":
                self._draw_tile_cell(area, camera, item.payload[0], item.payload[1], item.payload[2])
                continue
            self._draw_world_entity(area, camera, item.payload[0])

    def _collect_world_render_items(self, area: Area, world: World) -> list[_WorldRenderItem]:
        """Return all world-space drawables addressed with one stable sort key."""
        items: list[_WorldRenderItem] = []
        tile_size = area.tile_size
        for layer_index, layer in enumerate(area.tile_layers):
            if layer.y_sort:
                for grid_y, row in enumerate(layer.grid):
                    for grid_x, gid in enumerate(row):
                        if gid <= 0:
                            continue
                        items.append(
                            _WorldRenderItem(
                                self._tile_cell_sort_key(
                                    tile_size,
                                    layer,
                                    layer_index=layer_index,
                                    grid_x=grid_x,
                                    grid_y=grid_y,
                                ),
                                "tile_cell",
                                (layer, grid_x, grid_y),
                            )
                        )
                continue
            items.append(
                _WorldRenderItem(
                    self._tile_layer_sort_key(layer, layer_index=layer_index),
                    "tile_layer",
                    (layer,),
                )
            )
        for entity in world.iter_entities_in_space("world"):
            if not entity.visible:
                continue
            items.append(
                _WorldRenderItem(
                    self._world_entity_sort_key(area, entity),
                    "entity",
                    (entity,),
                )
            )
        return items

    def _tile_layer_sort_key(self, layer, *, layer_index: int) -> tuple:
        """Return the sort key for one non-y-sorted tile layer batch."""
        return (layer.render_order, 0, 0.0, layer.stack_order, 0, layer_index, layer.name)

    def _tile_cell_sort_key(
        self,
        tile_size: int,
        layer,
        *,
        layer_index: int,
        grid_x: int,
        grid_y: int,
    ) -> tuple:
        """Return the sort key for one y-sorted tile cell."""
        sort_y = ((grid_y + 1) * tile_size) + float(layer.sort_y_offset)
        return (layer.render_order, 1, sort_y, layer.stack_order, 0, grid_x, f"{layer_index}:{grid_y}:{grid_x}")

    def _world_entity_sort_key(self, area: Area, entity) -> tuple:
        """Return the unified sort key for one world-space entity."""
        if entity.y_sort:
            sort_bucket = 1
            sort_y = float(entity.pixel_y + area.tile_size + entity.sort_y_offset)
        else:
            sort_bucket = 0
            sort_y = 0.0
        return (
            entity.render_order,
            sort_bucket,
            sort_y,
            entity.stack_order,
            1,
            entity.pixel_x,
            entity.entity_id,
        )

    def _draw_tile_layer(self, area: Area, camera: Camera, layer) -> None:
        """Draw one cached non-y-sorted tile layer batch."""
        cached_surface = self._get_static_tile_layer_surface(area, layer)
        screen_x, screen_y = self._world_to_screen(area, 0.0, 0.0, camera)
        self.internal_surface.blit(cached_surface, (screen_x, screen_y))

    def _draw_tile_cell(self, area: Area, camera: Camera, layer, grid_x: int, grid_y: int) -> None:
        """Draw exactly one tile cell from a y-sorted layer."""
        gid = int(layer.grid[grid_y][grid_x])
        if gid > 0:
            self._draw_tile_gid(area, camera, grid_x, grid_y, gid)

    def _draw_tile_gid(self, area: Area, camera: Camera, grid_x: int, grid_y: int, gid: int) -> None:
        """Draw one resolved tile at the requested world-grid coordinate."""
        resolved = area.resolve_gid(gid)
        if resolved is None:
            return
        tileset_path, tile_w, tile_h, local_frame = resolved
        screen_x, screen_y = self._world_to_screen(
            area,
            grid_x * area.tile_size,
            grid_y * area.tile_size,
            camera,
        )
        frame_surface = self.asset_manager.get_frame(
            tileset_path,
            tile_w,
            tile_h,
            local_frame,
        )
        self.internal_surface.blit(frame_surface, (screen_x, screen_y))

    def _get_static_tile_layer_surface(self, area: Area, layer) -> pygame.Surface:
        """Return one cached area-space surface for a static tile layer."""
        cache_key = self._static_tile_layer_cache_key(area, layer)
        cached_surface = self._static_tile_layer_cache.get(cache_key)
        if cached_surface is not None:
            return cached_surface

        cached_surface = pygame.Surface(
            (max(1, area.pixel_width), max(1, area.pixel_height)),
            pygame.SRCALPHA,
        )
        for grid_y, row in enumerate(layer.grid):
            for grid_x, gid in enumerate(row):
                if gid <= 0:
                    continue
                resolved = area.resolve_gid(int(gid))
                if resolved is None:
                    continue
                tileset_path, tile_w, tile_h, local_frame = resolved
                frame_surface = self.asset_manager.get_frame(
                    tileset_path,
                    tile_w,
                    tile_h,
                    local_frame,
                )
                cached_surface.blit(
                    frame_surface,
                    (grid_x * area.tile_size, grid_y * area.tile_size),
                )

        self._static_tile_layer_cache[cache_key] = cached_surface
        return cached_surface

    def _static_tile_layer_cache_key(self, area: Area, layer) -> tuple:
        """Return one stable cache key for a static tile layer surface."""
        tileset_signature = tuple(
            (
                int(tileset.firstgid),
                str(tileset.path),
                int(tileset.tile_width),
                int(tileset.tile_height),
                int(tileset.tile_count),
            )
            for tileset in area.tilesets
        )
        grid_signature = tuple(
            tuple(int(gid) for gid in row)
            for row in layer.grid
        )
        return (
            area.area_id,
            int(area.tile_size),
            int(area.pixel_width),
            int(area.pixel_height),
            str(layer.name),
            int(layer.render_order),
            bool(layer.y_sort),
            float(layer.sort_y_offset),
            int(layer.stack_order),
            tileset_signature,
            grid_signature,
        )

    def _draw_world_entity(self, area: Area, camera: Camera, entity) -> None:
        """Draw one world-space entity."""
        if self._draw_entity_visuals(entity, camera=camera):
            return
        screen_x, screen_y = self._world_to_screen(area, entity.pixel_x, entity.pixel_y, camera)
        self._draw_entity_fallback(area.tile_size, entity, screen_x, screen_y)

    def _draw_screen_entities(self, world: World) -> None:
        """Draw screen-space entities above the world."""
        for entity in sorted(
            world.iter_entities_in_space("screen"),
            key=lambda item: (
                item.render_order,
                1 if item.y_sort else 0,
                float(item.pixel_y + item.sort_y_offset) if item.y_sort else 0.0,
                item.stack_order,
                item.entity_id,
            ),
        ):
            if not entity.visible:
                continue
            if self._draw_entity_visuals(entity, camera=None):
                continue
            self._draw_entity_fallback(
                config.DEFAULT_TILE_SIZE,
                entity,
                round(entity.pixel_x),
                round(entity.pixel_y),
            )

    def _draw_entity_visuals(
        self,
        entity,
        *,
        camera: Camera | None,
    ) -> bool:
        """Draw one entity's visuals and return True when anything was rendered."""
        visuals = sorted(entity.visuals, key=lambda item: (item.draw_order, item.visual_id))
        drew_anything = False
        for visual in visuals:
            if not visual.visible:
                continue
            sprite_surface = self.asset_manager.get_frame(
                visual.path,
                visual.frame_width,
                visual.frame_height,
                visual.current_frame,
            )
            if visual.flip_x:
                sprite_surface = pygame.transform.flip(sprite_surface, True, False)
            sprite_surface = self._apply_tint(sprite_surface, visual.tint)
            base_x = entity.pixel_x + visual.offset_x
            base_y = entity.pixel_y + visual.offset_y
            if camera is not None:
                draw_x, draw_y = self._world_to_screen(camera.area, base_x, base_y, camera)
            else:
                draw_x, draw_y = (
                    round(base_x) if config.PIXEL_ART_MODE else int(base_x),
                    round(base_y) if config.PIXEL_ART_MODE else int(base_y),
                )
            self.internal_surface.blit(sprite_surface, (draw_x, draw_y))
            drew_anything = True
        return drew_anything

    def _draw_entity_fallback(
        self,
        tile_size: int,
        entity,
        screen_x: int,
        screen_y: int,
    ) -> None:
        """Draw the simple rectangle fallback when an entity has no visuals."""
        inset = 2 if entity.kind == "player" else 3
        rect = pygame.Rect(
            screen_x + inset,
            screen_y + inset,
            tile_size - (inset * 2),
            tile_size - (inset * 2),
        )
        pygame.draw.rect(self.internal_surface, entity.color, rect, border_radius=2)

    def _world_to_screen(
        self,
        area: Area,
        world_x: float,
        world_y: float,
        camera: Camera,
    ) -> tuple[int, int]:
        """Convert world coordinates to screen coordinates with optional snapping."""
        offset_x, offset_y = self._world_scene_offset(area)
        screen_x = world_x - camera.render_x + offset_x
        screen_y = world_y - camera.render_y + offset_y

        if config.PIXEL_ART_MODE:
            return round(screen_x), round(screen_y)
        return int(screen_x), int(screen_y)

    def _world_scene_offset(self, area: Area) -> tuple[float, float]:
        """Center undersized world scenes within the fixed internal viewport."""
        offset_x = max(0.0, (self.internal_width - area.pixel_width) / 2)
        offset_y = max(0.0, (self.internal_height - area.pixel_height) / 2)
        return offset_x, offset_y

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

