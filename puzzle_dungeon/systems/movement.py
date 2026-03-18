"""Grid movement execution with smooth interpolation and pushable blocks."""

from __future__ import annotations

from puzzle_dungeon import config
from puzzle_dungeon.systems.collision import CollisionSystem
from puzzle_dungeon.world.area import Area
from puzzle_dungeon.world.entity import DIRECTION_VECTORS, Direction, Entity
from puzzle_dungeon.world.world import World


class MovementSystem:
    """Execute tile-based movement while keeping entity state data-oriented."""

    def __init__(self, area: Area, world: World, collision_system: CollisionSystem) -> None:
        self.area = area
        self.world = world
        self.collision_system = collision_system

    def request_step(self, entity_id: str, direction: Direction) -> list[str]:
        """Try to move an entity one tile and return the entities that started moving."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            raise KeyError(f"Cannot step missing entity '{entity_id}'.")

        if entity.movement.active:
            return []

        entity.facing = direction
        delta_x, delta_y = DIRECTION_VECTORS[direction]
        target_x = entity.grid_x + delta_x
        target_y = entity.grid_y + delta_y

        blocking_entity = self.collision_system.get_blocking_entity(
            target_x,
            target_y,
            ignore_entity_id=entity.entity_id,
        )
        if blocking_entity is None:
            if self.collision_system.can_move_to(
                target_x,
                target_y,
                ignore_entity_id=entity.entity_id,
            ):
                self._start_move(entity, target_x, target_y)
                return [entity.entity_id]
            return []

        if blocking_entity.pushable and not blocking_entity.movement.active:
            push_target_x = blocking_entity.grid_x + delta_x
            push_target_y = blocking_entity.grid_y + delta_y
            if self.collision_system.can_move_to(
                push_target_x,
                push_target_y,
                ignore_entity_id=blocking_entity.entity_id,
            ):
                self._start_move(blocking_entity, push_target_x, push_target_y)
                self._start_move(entity, target_x, target_y)
                return [blocking_entity.entity_id, entity.entity_id]

        return []

    def update(self, dt: float) -> None:
        """Advance all active movement interpolations."""
        tile_size = self.area.tile_size
        for entity in self.world.iter_entities():
            movement = entity.movement
            if not movement.active:
                continue

            movement.elapsed = min(movement.elapsed + dt, movement.duration)
            progress = 1.0
            if movement.duration > 0:
                progress = movement.elapsed / movement.duration

            start_pixel_x = movement.start_grid_x * tile_size
            start_pixel_y = movement.start_grid_y * tile_size
            end_pixel_x = movement.target_grid_x * tile_size
            end_pixel_y = movement.target_grid_y * tile_size

            entity.pixel_x = start_pixel_x + ((end_pixel_x - start_pixel_x) * progress)
            entity.pixel_y = start_pixel_y + ((end_pixel_y - start_pixel_y) * progress)

            if progress >= 1.0:
                movement.active = False
                entity.sync_pixel_position(tile_size)

    def is_entity_moving(self, entity_id: str) -> bool:
        """Return True when the requested entity is still interpolating."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            return False
        return entity.movement.active

    def _start_move(self, entity: Entity, target_x: int, target_y: int) -> None:
        """Begin a tile-to-tile interpolation and reserve the target tile immediately."""
        previous_x = entity.grid_x
        previous_y = entity.grid_y

        movement = entity.movement
        movement.active = True
        movement.start_grid_x = previous_x
        movement.start_grid_y = previous_y
        movement.target_grid_x = target_x
        movement.target_grid_y = target_y
        movement.elapsed = 0.0
        movement.duration = config.MOVE_DURATION_SECONDS

        entity.grid_x = target_x
        entity.grid_y = target_y
