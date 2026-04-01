"""Runtime transform movement with optional grid occupancy synchronization."""

from __future__ import annotations

import math
from typing import Callable

from dungeon_engine import config
from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import DIRECTION_VECTORS, Direction, Entity, GridSyncPolicy
from dungeon_engine.world.world import World


class MovementSystem:
    """Execute transform movement while keeping grid occupancy explicit."""

    def __init__(self, area: Area, world: World, collision_system: object | None) -> None:
        self.area = area
        self.world = world
        self.collision_system = collision_system
        self.occupancy_transition_callback: (
            Callable[[Entity, tuple[int, int] | None, tuple[int, int] | None], None] | None
        ) = None

    def request_step(
        self,
        entity_id: str,
        direction: Direction,
        *,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
    ) -> list[str]:
        """Backward-compatible wrapper for a one-tile grid move."""
        return self.request_grid_step(
            entity_id,
            direction,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
        )

    def request_grid_step(
        self,
        entity_id: str,
        direction: Direction,
        *,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: GridSyncPolicy = "immediate",
    ) -> list[str]:
        """Move an entity one tile using explicit direction data and grid sync."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            raise KeyError(f"Cannot step missing entity '{entity_id}'.")
        if not entity.present:
            return []

        if entity.movement_state.active:
            return []

        delta_x, delta_y = DIRECTION_VECTORS[direction]
        target_x = entity.grid_x + delta_x
        target_y = entity.grid_y + delta_y
        target_pixel_x = target_x * self.area.tile_size
        target_pixel_y = target_y * self.area.tile_size
        total_ticks = self._resolve_total_ticks(
            float(self.area.tile_size),
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
        )
        self._start_move(
            entity,
            target_pixel_x=target_pixel_x,
            target_pixel_y=target_pixel_y,
            total_ticks=total_ticks,
            grid_sync=grid_sync,
            target_grid_x=target_x,
            target_grid_y=target_y,
        )
        return [entity.entity_id]

    def request_move_to_position(
        self,
        entity_id: str,
        target_pixel_x: float,
        target_pixel_y: float,
        *,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: GridSyncPolicy = "none",
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
    ) -> list[str]:
        """Move an entity to an arbitrary world position in pixels."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            raise KeyError(f"Cannot move missing entity '{entity_id}'.")
        if not entity.present:
            return []

        if entity.movement_state.active:
            return []

        if grid_sync != "none" and (target_grid_x is None or target_grid_y is None):
            inferred_grid = self._infer_grid_target(target_pixel_x, target_pixel_y)
            if inferred_grid is None:
                raise ValueError(
                    "Grid-synced movement requires explicit target_grid_x/target_grid_y "
                    "or a tile-aligned target position."
                )
            target_grid_x, target_grid_y = inferred_grid

        distance = math.hypot(target_pixel_x - entity.pixel_x, target_pixel_y - entity.pixel_y)
        total_ticks = self._resolve_total_ticks(
            distance,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
        )

        if distance <= 0.0:
            entity.pixel_x = target_pixel_x
            entity.pixel_y = target_pixel_y
            self._apply_grid_sync(
                entity,
                grid_sync=grid_sync,
                target_grid_x=target_grid_x,
                target_grid_y=target_grid_y,
                when="start",
            )
            self._apply_grid_sync(
                entity,
                grid_sync=grid_sync,
                target_grid_x=target_grid_x,
                target_grid_y=target_grid_y,
                when="complete",
            )
            return []

        self._start_move(
            entity,
            target_pixel_x=target_pixel_x,
            target_pixel_y=target_pixel_y,
            total_ticks=total_ticks,
            grid_sync=grid_sync,
            target_grid_x=target_grid_x,
            target_grid_y=target_grid_y,
        )
        return [entity.entity_id]

    def request_move_by_offset(
        self,
        entity_id: str,
        delta_x: float,
        delta_y: float,
        *,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: GridSyncPolicy = "none",
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
    ) -> list[str]:
        """Move an entity by an arbitrary pixel offset."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            raise KeyError(f"Cannot move missing entity '{entity_id}'.")
        if not entity.present:
            return []

        return self.request_move_to_position(
            entity_id,
            entity.pixel_x + delta_x,
            entity.pixel_y + delta_y,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync=grid_sync,
            target_grid_x=target_grid_x,
            target_grid_y=target_grid_y,
        )

    def request_move_to_grid_position(
        self,
        entity_id: str,
        target_grid_x: int,
        target_grid_y: int,
        *,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: GridSyncPolicy = "on_complete",
    ) -> list[str]:
        """Move an entity toward a target addressed in grid coordinates."""
        return self.request_move_to_position(
            entity_id,
            target_grid_x * self.area.tile_size,
            target_grid_y * self.area.tile_size,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync=grid_sync,
            target_grid_x=target_grid_x,
            target_grid_y=target_grid_y,
        )

    def request_move_by_grid_offset(
        self,
        entity_id: str,
        delta_grid_x: int,
        delta_grid_y: int,
        *,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: GridSyncPolicy = "on_complete",
    ) -> list[str]:
        """Move an entity by a delta expressed in grid coordinates."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            raise KeyError(f"Cannot move missing entity '{entity_id}'.")
        if not entity.present:
            return []

        return self.request_move_to_grid_position(
            entity_id,
            entity.grid_x + int(delta_grid_x),
            entity.grid_y + int(delta_grid_y),
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync=grid_sync,
        )

    def set_grid_position(
        self,
        entity_id: str,
        target_grid_x: int,
        target_grid_y: int,
    ) -> None:
        """Instantly update an entity's logical grid placement without touching pixels."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            raise KeyError(f"Cannot set grid position for missing entity '{entity_id}'.")
        entity.movement_state.active = False
        previous_grid_x = entity.grid_x
        previous_grid_y = entity.grid_y
        entity.grid_x = int(target_grid_x)
        entity.grid_y = int(target_grid_y)
        self._notify_occupancy_transition(
            entity,
            previous_grid_x=previous_grid_x,
            previous_grid_y=previous_grid_y,
            target_grid_x=entity.grid_x,
            target_grid_y=entity.grid_y,
        )

    def set_pixel_position(
        self,
        entity_id: str,
        target_pixel_x: float,
        target_pixel_y: float,
    ) -> None:
        """Instantly update an entity's pixel position without touching grid placement."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            raise KeyError(f"Cannot set world position for missing entity '{entity_id}'.")
        entity.movement_state.active = False
        entity.pixel_x = float(target_pixel_x)
        entity.pixel_y = float(target_pixel_y)

    def teleport_to_position(
        self,
        entity_id: str,
        target_pixel_x: float,
        target_pixel_y: float,
        *,
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
    ) -> None:
        """Instantly move an entity to a pixel position, optionally updating grid state too."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            raise KeyError(f"Cannot teleport missing entity '{entity_id}'.")
        if not entity.present:
            return

        entity.movement_state.active = False
        previous_grid_x = entity.grid_x
        previous_grid_y = entity.grid_y
        entity.pixel_x = float(target_pixel_x)
        entity.pixel_y = float(target_pixel_y)
        if target_grid_x is not None:
            entity.grid_x = int(target_grid_x)
        if target_grid_y is not None:
            entity.grid_y = int(target_grid_y)
        if target_grid_x is not None and target_grid_y is not None:
            self._notify_occupancy_transition(
                entity,
                previous_grid_x=previous_grid_x,
                previous_grid_y=previous_grid_y,
                target_grid_x=entity.grid_x,
                target_grid_y=entity.grid_y,
            )

    def teleport_to_grid_position(
        self,
        entity_id: str,
        target_grid_x: int,
        target_grid_y: int,
    ) -> None:
        """Instantly move an entity to a grid position and snap pixel position to match."""
        self.teleport_to_position(
            entity_id,
            target_grid_x * self.area.tile_size,
            target_grid_y * self.area.tile_size,
            target_grid_x=target_grid_x,
            target_grid_y=target_grid_y,
        )

    def update(self, dt: float) -> None:
        """Backward-compatible wrapper that advances one fixed movement tick."""
        _ = dt
        self.update_tick()

    def update_tick(self) -> None:
        """Advance all active movement interpolations by one simulation tick."""
        for entity in self.world.iter_entities():
            movement = entity.movement_state
            if not movement.active:
                continue

            if movement.total_ticks <= 0:
                progress = 1.0
            else:
                movement.elapsed_ticks = min(movement.elapsed_ticks + 1, movement.total_ticks)
                progress = movement.elapsed_ticks / movement.total_ticks

            entity.pixel_x = movement.start_pixel_x + (
                (movement.target_pixel_x - movement.start_pixel_x) * progress
            )
            entity.pixel_y = movement.start_pixel_y + (
                (movement.target_pixel_y - movement.start_pixel_y) * progress
            )

            if movement.total_ticks <= 0 or movement.elapsed_ticks >= movement.total_ticks:
                movement.active = False
                entity.pixel_x = movement.target_pixel_x
                entity.pixel_y = movement.target_pixel_y
                self._apply_grid_sync(
                    entity,
                    grid_sync=movement.grid_sync,
                    target_grid_x=movement.target_grid_x,
                    target_grid_y=movement.target_grid_y,
                    when="complete",
                )

    def is_entity_moving(self, entity_id: str) -> bool:
        """Return True when the requested entity is still interpolating."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            return False
        return entity.movement_state.active

    def _start_move(
        self,
        entity: Entity,
        *,
        target_pixel_x: float,
        target_pixel_y: float,
        total_ticks: int,
        grid_sync: GridSyncPolicy,
        target_grid_x: int | None,
        target_grid_y: int | None,
    ) -> None:
        """Begin a transform interpolation and apply the requested grid-sync policy."""
        previous_grid_x = entity.grid_x
        previous_grid_y = entity.grid_y

        movement = entity.movement_state
        movement.active = True
        movement.start_grid_x = previous_grid_x
        movement.start_grid_y = previous_grid_y
        movement.target_grid_x = target_grid_x
        movement.target_grid_y = target_grid_y
        movement.start_pixel_x = entity.pixel_x
        movement.start_pixel_y = entity.pixel_y
        movement.target_pixel_x = target_pixel_x
        movement.target_pixel_y = target_pixel_y
        movement.elapsed_ticks = 0
        movement.total_ticks = max(0, int(total_ticks))
        movement.grid_sync = grid_sync

        self._apply_grid_sync(
            entity,
            grid_sync=grid_sync,
            target_grid_x=target_grid_x,
            target_grid_y=target_grid_y,
            when="start",
        )

    def _apply_grid_sync(
        self,
        entity: Entity,
        *,
        grid_sync: GridSyncPolicy,
        target_grid_x: int | None,
        target_grid_y: int | None,
        when: str,
    ) -> None:
        """Apply a grid-occupancy update when the selected policy requires it."""
        if target_grid_x is None or target_grid_y is None:
            return

        if grid_sync == "immediate" and when == "start":
            previous_grid_x = entity.grid_x
            previous_grid_y = entity.grid_y
            entity.grid_x = target_grid_x
            entity.grid_y = target_grid_y
            self._notify_occupancy_transition(
                entity,
                previous_grid_x=previous_grid_x,
                previous_grid_y=previous_grid_y,
                target_grid_x=entity.grid_x,
                target_grid_y=entity.grid_y,
            )
        elif grid_sync == "on_complete" and when == "complete":
            previous_grid_x = entity.grid_x
            previous_grid_y = entity.grid_y
            entity.grid_x = target_grid_x
            entity.grid_y = target_grid_y
            self._notify_occupancy_transition(
                entity,
                previous_grid_x=previous_grid_x,
                previous_grid_y=previous_grid_y,
                target_grid_x=entity.grid_x,
                target_grid_y=entity.grid_y,
            )

    def _notify_occupancy_transition(
        self,
        entity: Entity,
        *,
        previous_grid_x: int,
        previous_grid_y: int,
        target_grid_x: int,
        target_grid_y: int,
    ) -> None:
        """Notify the runtime when a present world-space entity changes occupied tiles."""
        if self.occupancy_transition_callback is None:
            return
        if not entity.present or entity.space != "world":
            return
        previous_cell = (int(previous_grid_x), int(previous_grid_y))
        next_cell = (int(target_grid_x), int(target_grid_y))
        if previous_cell == next_cell:
            return
        self.occupancy_transition_callback(entity, previous_cell, next_cell)

    def _resolve_total_ticks(
        self,
        distance_in_pixels: float,
        *,
        duration: float | None,
        frames_needed: int | None,
        speed_px_per_second: float | None,
    ) -> int:
        """Resolve a movement length in simulation ticks."""
        if duration is not None and duration < 0:
            raise ValueError("Movement duration cannot be negative.")
        if frames_needed is not None and frames_needed < 0:
            raise ValueError("frames_needed cannot be negative.")
        if speed_px_per_second is not None and speed_px_per_second <= 0:
            raise ValueError("Movement speed must be positive.")

        if frames_needed is not None:
            return int(frames_needed)
        if duration is not None:
            return self._seconds_to_ticks(duration)
        if speed_px_per_second is not None:
            if distance_in_pixels <= 0:
                return 0
            return self._seconds_to_ticks(distance_in_pixels / speed_px_per_second)
        return self._seconds_to_ticks(config.MOVE_DURATION_SECONDS)

    def _seconds_to_ticks(self, seconds: float) -> int:
        """Convert seconds into a whole-number simulation tick count."""
        if seconds <= 0 or config.FPS <= 0:
            return 0
        return max(1, round(seconds * config.FPS))

    def _infer_grid_target(
        self,
        target_pixel_x: float,
        target_pixel_y: float,
    ) -> tuple[int, int] | None:
        """Infer a grid target when the pixel target lands exactly on a tile."""
        tile_size = float(self.area.tile_size)
        snapped_grid_x = round(target_pixel_x / tile_size)
        snapped_grid_y = round(target_pixel_y / tile_size)
        if not math.isclose(target_pixel_x, snapped_grid_x * tile_size, abs_tol=0.001):
            return None
        if not math.isclose(target_pixel_y, snapped_grid_y * tile_size, abs_tol=0.001):
            return None
        return (snapped_grid_x, snapped_grid_y)

