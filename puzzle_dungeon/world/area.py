"""Tile-based area data used by the runtime and future editor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TileLayer:
    """A single visual tile layer inside an area."""

    name: str
    grid: list[list[str | None]]
    draw_above_entities: bool = False


@dataclass(slots=True)
class Area:
    """A loaded room with layered tiles and separate per-cell flags."""

    name: str
    tile_size: int
    tile_definitions: dict[str, dict[str, Any]]
    tile_layers: list[TileLayer]
    cell_flags: list[list[dict[str, Any]]]

    @property
    def width(self) -> int:
        """Return the width of the room in tiles."""
        if self.tile_layers:
            return len(self.tile_layers[0].grid[0]) if self.tile_layers[0].grid else 0
        return len(self.cell_flags[0]) if self.cell_flags else 0

    @property
    def height(self) -> int:
        """Return the height of the room in tiles."""
        if self.tile_layers:
            return len(self.tile_layers[0].grid)
        return len(self.cell_flags)

    @property
    def pixel_width(self) -> int:
        """Return the width of the room in pixels."""
        return self.width * self.tile_size

    @property
    def pixel_height(self) -> int:
        """Return the height of the room in pixels."""
        return self.height * self.tile_size

    def in_bounds(self, grid_x: int, grid_y: int) -> bool:
        """Return True when the tile coordinate is inside the room."""
        return 0 <= grid_x < self.width and 0 <= grid_y < self.height

    def iter_tile_layers(
        self,
        *,
        draw_above_entities: bool | None = None,
    ) -> list[TileLayer]:
        """Return all tile layers or only those matching the requested render phase."""
        if draw_above_entities is None:
            return list(self.tile_layers)
        return [
            layer
            for layer in self.tile_layers
            if layer.draw_above_entities == draw_above_entities
        ]

    def cell_flags_at(self, grid_x: int, grid_y: int) -> dict[str, Any]:
        """Return the per-cell flags for the requested tile coordinate."""
        return self.cell_flags[grid_y][grid_x]

    def is_walkable(self, grid_x: int, grid_y: int) -> bool:
        """Use cell flags, not tile art, to determine walkability."""
        if not self.in_bounds(grid_x, grid_y):
            return False
        return bool(self.cell_flags_at(grid_x, grid_y).get("walkable", True))

    def tile_definition(self, tile_id: str) -> dict[str, Any]:
        """Return the content definition for a tile identifier."""
        return self.tile_definitions.get(tile_id, {})
