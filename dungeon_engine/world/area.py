"""Tile-based area data used by the runtime and authoring JSON.

Areas contain layered tile grids using the GID (Global ID) system — the industry
standard used by Tiled, Godot, RPG Maker, etc. Each integer in a tile grid maps
to a specific frame in a specific tileset. GID 0 means empty/no tile.

Depends on: nothing (pure data)
Used by: loader, serializer, renderer, collision
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Tileset:
    """A tileset image sliced into a grid of tile frames.

    Each tileset owns a range of GIDs starting at ``firstgid``.
    For a tileset with ``tile_count`` frames, valid GIDs are
    ``firstgid`` through ``firstgid + tile_count - 1``.
    """

    firstgid: int
    path: str
    tile_width: int
    tile_height: int
    columns: int = 0
    tile_count: int = 0

    @property
    def last_gid(self) -> int:
        """Return the highest GID owned by this tileset (inclusive)."""
        return self.firstgid + self.tile_count - 1 if self.tile_count > 0 else self.firstgid

    def contains_gid(self, gid: int) -> bool:
        """Return True if ``gid`` falls within this tileset's range."""
        return self.firstgid <= gid <= self.last_gid

    def local_frame(self, gid: int) -> int:
        """Convert a global tile ID to a local frame index within this tileset."""
        return gid - self.firstgid


@dataclass(slots=True)
class TileLayer:
    """A single visual tile layer inside an area.

    Grid cells are integers (GIDs). 0 means empty.
    """

    name: str
    grid: list[list[int]]
    render_order: int = 0
    y_sort: bool = False
    sort_y_offset: float = 0.0
    stack_order: int = 0


@dataclass(slots=True)
class AreaEntryPoint:
    """One authored destination marker for cross-area entity transfers."""

    entry_id: str
    grid_x: int
    grid_y: int
    facing: str | None = None
    pixel_x: float | None = None
    pixel_y: float | None = None


@dataclass(slots=True)
class Area:
    """A loaded room with layered tiles and separate per-cell flags.

    Tiles use the GID system: each integer in a layer grid maps to a frame
    in one of the area's tilesets. GID 0 = empty. Use ``resolve_gid()``
    to look up the tileset and local frame for any GID.
    """

    area_id: str
    name: str
    tile_size: int
    tilesets: list[Tileset]
    tile_layers: list[TileLayer]
    cell_flags: list[list[dict[str, Any]]]
    entry_points: dict[str, AreaEntryPoint] = field(default_factory=dict)
    camera_defaults: dict[str, Any] = field(default_factory=dict)
    enter_commands: list[dict[str, Any]] = field(default_factory=list)

    # Reverse lookup built by the loader after tilesets are populated.
    # Maps GID -> (tileset_index) for fast resolution.
    _gid_to_tileset: dict[int, int] = field(default_factory=dict, repr=False)

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

    def iter_tile_layers(self) -> list[TileLayer]:
        """Return all authored tile layers in their stored order."""
        return list(self.tile_layers)

    def cell_flags_at(self, grid_x: int, grid_y: int) -> dict[str, Any]:
        """Return the per-cell flags for the requested tile coordinate."""
        return self.cell_flags[grid_y][grid_x]

    def is_blocked(self, grid_x: int, grid_y: int) -> bool:
        """Use cell flags, not tile art, to determine blocking."""
        if not self.in_bounds(grid_x, grid_y):
            return True
        cell_flags = self.cell_flags_at(grid_x, grid_y)
        if "blocked" in cell_flags:
            return bool(cell_flags.get("blocked", False))
        return not bool(cell_flags.get("walkable", True))

    def is_walkable(self, grid_x: int, grid_y: int) -> bool:
        """Use cell flags, not tile art, to determine walkability."""
        return not self.is_blocked(grid_x, grid_y)

    def cell_tags_at(self, grid_x: int, grid_y: int) -> list[str]:
        """Return the cell tags for the requested tile coordinate."""
        if not self.in_bounds(grid_x, grid_y):
            return []
        raw_tags = self.cell_flags_at(grid_x, grid_y).get("tags", [])
        if not isinstance(raw_tags, list):
            return []
        return [str(tag) for tag in raw_tags]

    def resolve_gid(self, gid: int) -> tuple[str, int, int, int] | None:
        """Resolve a GID to (tileset_path, tile_width, tile_height, local_frame).

        Returns None for GID 0 (empty) or any GID not covered by a tileset.
        """
        if gid <= 0:
            return None

        # Fast path: check the cached lookup
        tileset_idx = self._gid_to_tileset.get(gid)
        if tileset_idx is not None:
            ts = self.tilesets[tileset_idx]
            return (ts.path, ts.tile_width, ts.tile_height, ts.local_frame(gid))

        # Slow path: linear scan (shouldn't happen if build_gid_lookup was called)
        for idx, ts in enumerate(self.tilesets):
            if ts.contains_gid(gid):
                self._gid_to_tileset[gid] = idx
                return (ts.path, ts.tile_width, ts.tile_height, ts.local_frame(gid))

        return None

    def gid_for_tileset_frame(self, tileset_index: int, local_frame: int) -> int:
        """Compute the GID for a local frame in the given tileset."""
        return self.tilesets[tileset_index].firstgid + local_frame

    def next_available_firstgid(self) -> int:
        """Return the next safe firstgid for adding a new tileset."""
        if not self.tilesets:
            return 1
        return max(ts.last_gid for ts in self.tilesets) + 1

    def build_gid_lookup(self) -> None:
        """Rebuild the GID-to-tileset reverse lookup from current tilesets.

        Called by the loader after tileset tile_counts are known.
        """
        self._gid_to_tileset.clear()
        for idx, ts in enumerate(self.tilesets):
            for gid in range(ts.firstgid, ts.firstgid + ts.tile_count):
                self._gid_to_tileset[gid] = idx
