"""Tile and entity collision helpers for grid movement."""

from __future__ import annotations

from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity
from dungeon_engine.world.world import World


class CollisionSystem:
    """Provide low-level area walkability queries without entity-blocking rules."""

    def __init__(self, area: Area, world: World) -> None:
        self.area = area
        self.world = world

    def get_blocking_entity(
        self,
        grid_x: int,
        grid_y: int,
        *,
        ignore_entity_id: str | None = None,
    ) -> Entity | None:
        """Return no blocker because blocking is now authored explicitly in JSON flows."""
        _ = grid_x, grid_y, ignore_entity_id
        return None

    def can_move_to(
        self,
        grid_x: int,
        grid_y: int,
        *,
        ignore_entity_id: str | None = None,
    ) -> bool:
        """Return True when the area marks the tile as walkable."""
        _ = ignore_entity_id
        return self.area.is_walkable(grid_x, grid_y)


