"""Camera utilities for following the player around an area."""

from __future__ import annotations

from puzzle_dungeon import config
from puzzle_dungeon.world.area import Area
from puzzle_dungeon.world.entity import Entity


class Camera:
    """A lightweight camera that follows an entity and clamps to map bounds."""

    def __init__(
        self,
        viewport_width: int,
        viewport_height: int,
        area: Area,
        *,
        clamp_to_area: bool = True,
    ) -> None:
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.area = area
        self.clamp_to_area = clamp_to_area
        self.x = 0.0
        self.y = 0.0
        self.render_x = 0.0
        self.render_y = 0.0

    def set_area(self, area: Area) -> None:
        """Rebind the camera to a different area and keep its position valid."""
        self.area = area
        self.set_position(self.x, self.y)

    def set_position(self, x: float, y: float) -> None:
        """Set the camera position directly while respecting area bounds."""
        if self.clamp_to_area:
            max_x = max(0, self.area.pixel_width - self.viewport_width)
            max_y = max(0, self.area.pixel_height - self.viewport_height)
            self.x = min(max(x, 0), max_x)
            self.y = min(max(y, 0), max_y)
        else:
            self.x = x
            self.y = y
        self._update_render_position()

    def pan(self, delta_x: float, delta_y: float) -> None:
        """Move the camera by a delta and clamp the result to map bounds."""
        self.set_position(self.x + delta_x, self.y + delta_y)

    def update(self, target: Entity | None) -> None:
        """Center the camera on the target while staying inside the area."""
        if target is None:
            return

        target_center_x = target.pixel_x + (self.area.tile_size / 2)
        target_center_y = target.pixel_y + (self.area.tile_size / 2)

        desired_x = target_center_x - (self.viewport_width / 2)
        desired_y = target_center_y - (self.viewport_height / 2)

        if self.clamp_to_area:
            max_x = max(0, self.area.pixel_width - self.viewport_width)
            max_y = max(0, self.area.pixel_height - self.viewport_height)
            self.x = min(max(desired_x, 0), max_x)
            self.y = min(max(desired_y, 0), max_y)
        else:
            self.x = desired_x
            self.y = desired_y
        self._update_render_position()

    def _update_render_position(self) -> None:
        """Compute the final render-space camera position from the logical camera."""
        if config.PIXEL_ART_MODE:
            self.render_x = round(self.x)
            self.render_y = round(self.y)
        else:
            self.render_x = self.x
            self.render_y = self.y
