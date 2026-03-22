"""Tile and entity collision helpers for grid movement."""

from __future__ import annotations

from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity
from dungeon_engine.world.world import World


class CollisionSystem:
    """Provide collision queries without embedding them into commands directly."""

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
        """Return the first solid entity on the requested tile."""
        for entity in self.world.get_entities_at(
            grid_x,
            grid_y,
            exclude_entity_id=ignore_entity_id,
        ):
            if entity.solid:
                return entity
        return None

    def can_move_to(
        self,
        grid_x: int,
        grid_y: int,
        *,
        ignore_entity_id: str | None = None,
    ) -> bool:
        """Return True when a tile is walkable and not blocked by another entity."""
        if not self.area.is_walkable(grid_x, grid_y):
            return False
        return self.get_blocking_entity(
            grid_x,
            grid_y,
            ignore_entity_id=ignore_entity_id,
        ) is None


