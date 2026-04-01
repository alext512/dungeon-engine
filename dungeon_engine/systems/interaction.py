"""Interaction helpers for facing-based object activation."""

from __future__ import annotations

from dungeon_engine.world.entity import DIRECTION_VECTORS, Entity
from dungeon_engine.world.world import World


class InteractionSystem:
    """Resolve which entity, if any, the actor is trying to interact with."""

    def __init__(self, world: World) -> None:
        self.world = world

    def get_facing_target(self, actor_entity_id: str) -> Entity | None:
        """Return the best interactable target in the actor's facing cell."""
        actor = self.world.get_entity(actor_entity_id)
        if actor is None:
            raise KeyError(f"Cannot resolve interaction target for '{actor_entity_id}'.")

        direction = actor.get_effective_facing()
        delta_x, delta_y = DIRECTION_VECTORS[direction]  # type: ignore[index]
        target_x = actor.grid_x + delta_x
        target_y = actor.grid_y + delta_y
        candidates = self.world.get_interactable_entities_at(
            target_x,
            target_y,
            exclude_entity_id=actor.entity_id,
        )
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda entity: (
                int(entity.interaction_priority),
                int(entity.render_order),
                int(entity.stack_order),
                entity.entity_id,
            ),
        )

