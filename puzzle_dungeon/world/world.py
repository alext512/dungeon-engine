"""World container for runtime entities in the current loaded area."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from puzzle_dungeon.world.entity import Entity


@dataclass(slots=True)
class World:
    """Store and query runtime entities for the current room."""

    entities: dict[str, Entity] = field(default_factory=dict)
    player_id: str = "player"
    variables: dict[str, Any] = field(default_factory=dict)

    def add_entity(self, entity: Entity) -> None:
        """Insert or replace an entity by its stable identifier."""
        self.entities[entity.entity_id] = entity

    def remove_entity(self, entity_id: str) -> None:
        """Remove an entity when it exists in the current room."""
        self.entities.pop(entity_id, None)

    def get_entity(self, entity_id: str) -> Entity | None:
        """Return an entity when it exists in the current room."""
        return self.entities.get(entity_id)

    def get_player(self) -> Entity:
        """Return the configured player entity."""
        player = self.get_entity(self.player_id)
        if player is None:
            raise KeyError(f"Player entity '{self.player_id}' was not found in the world.")
        return player

    def iter_entities(self) -> list[Entity]:
        """Return all entities as a list for simple iteration."""
        return list(self.entities.values())

    def entity_sort_key(self, entity: Entity) -> tuple[int, int, str]:
        """Return a stable per-cell stacking key for editor and runtime queries."""
        return (entity.layer, entity.stack_order, entity.entity_id)

    def get_entities_at(
        self,
        grid_x: int,
        grid_y: int,
        *,
        exclude_entity_id: str | None = None,
        include_hidden: bool = False,
    ) -> list[Entity]:
        """Return entities that currently occupy the requested grid tile."""
        return sorted(
            [
                entity
                for entity in self.entities.values()
                if (include_hidden or entity.visible)
                and entity.entity_id != exclude_entity_id
                and entity.grid_x == grid_x
                and entity.grid_y == grid_y
            ],
            key=self.entity_sort_key,
        )

    def get_first_enabled_entity_at(
        self,
        grid_x: int,
        grid_y: int,
        *,
        exclude_entity_id: str | None = None,
    ) -> Entity | None:
        """Return the first enabled visible entity at the given tile, if any."""
        for entity in reversed(
            self.get_entities_at(
                grid_x,
                grid_y,
                exclude_entity_id=exclude_entity_id,
            )
        ):
            if entity.enabled:
                return entity
        return None

    def generate_entity_id(self, base_name: str) -> str:
        """Return a stable unique entity id for editor-created instances."""
        candidate = base_name
        counter = 1
        while candidate in self.entities:
            counter += 1
            candidate = f"{base_name}_{counter}"
        return candidate
