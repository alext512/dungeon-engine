"""Interaction helpers for facing-based object activation."""

from __future__ import annotations

from dungeon_engine.world.entity import DIRECTION_VECTORS, Entity
from dungeon_engine.world.world import World


class InteractionSystem:
    """Resolve which entity, if any, the actor is trying to interact with."""

    def __init__(self, world: World) -> None:
        self.world = world

    def get_facing_target(self, actor_entity_id: str) -> Entity | None:
        """Return the first present entity with an enabled interact event ahead."""
        actor = self.world.get_entity(actor_entity_id)
        if actor is None:
            raise KeyError(f"Cannot resolve interaction target for '{actor_entity_id}'.")

        direction = str(actor.variables.get("direction", "")).strip()
        if direction not in DIRECTION_VECTORS:
            return None
        delta_x, delta_y = DIRECTION_VECTORS[direction]  # type: ignore[index]
        target_x = actor.grid_x + delta_x
        target_y = actor.grid_y + delta_y
        for entity in reversed(
            self.world.get_entities_at(
                target_x,
                target_y,
                exclude_entity_id=actor.entity_id,
            )
        ):
            if entity.has_enabled_event("interact"):
                return entity
        return None

