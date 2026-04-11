"""Tile and entity collision helpers for grid movement."""

from __future__ import annotations

from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity
from dungeon_engine.world.world import World


class CollisionSystem:
    """Provide low-level cell and entity blocking queries for grid movement."""

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
        """Return the first solid world-space entity at the requested grid cell."""
        blockers = self.world.get_solid_entities_at(
            grid_x,
            grid_y,
            exclude_entity_id=ignore_entity_id,
            include_hidden=True,
        )
        if not blockers:
            return None
        return blockers[-1]

    def get_blocking_entities(
        self,
        grid_x: int,
        grid_y: int,
        *,
        ignore_entity_id: str | None = None,
    ) -> list[Entity]:
        """Return every solid world-space entity at the requested grid cell."""
        return self.world.get_solid_entities_at(
            grid_x,
            grid_y,
            exclude_entity_id=ignore_entity_id,
            include_hidden=True,
        )

    def can_move_to(
        self,
        grid_x: int,
        grid_y: int,
        *,
        ignore_entity_id: str | None = None,
    ) -> bool:
        """Return True when the target cell is not blocked by tiles or solid entities."""
        if self.area.is_blocked(grid_x, grid_y):
            return False
        return self.get_blocking_entity(
            grid_x,
            grid_y,
            ignore_entity_id=ignore_entity_id,
        ) is None


