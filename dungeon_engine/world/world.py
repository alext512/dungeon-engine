"""World container for runtime entities in the current loaded area."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dungeon_engine.world.entity import Entity


@dataclass(slots=True)
class World:
    """Store and query runtime entities for the current room."""

    entities: dict[str, Entity] = field(default_factory=dict)
    player_id: str = "player"
    active_entity_id: str = "player"
    active_entity_stack: list[str] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)

    def add_entity(self, entity: Entity) -> None:
        """Insert or replace an entity by its stable identifier."""
        self.entities[entity.entity_id] = entity

    def remove_entity(self, entity_id: str) -> None:
        """Remove an entity when it exists in the current room."""
        self.entities.pop(entity_id, None)
        self.active_entity_stack = [
            stacked_entity_id
            for stacked_entity_id in self.active_entity_stack
            if stacked_entity_id != entity_id
        ]
        if self.active_entity_id == entity_id:
            self.pop_active_entity()

    def get_entity(self, entity_id: str) -> Entity | None:
        """Return an entity when it exists in the current room."""
        return self.entities.get(entity_id)

    def get_player(self) -> Entity:
        """Return the configured player entity."""
        player = self.get_entity(self.player_id)
        if player is None:
            raise KeyError(f"Player entity '{self.player_id}' was not found in the world.")
        return player

    def get_active_entity(self) -> Entity:
        """Return the entity currently receiving direct input."""
        active_entity = self.get_entity(self.active_entity_id)
        if active_entity is not None:
            return active_entity
        return self.get_player()

    def set_active_entity(self, entity_id: str) -> None:
        """Set which entity currently receives direct input."""
        entity = self.get_entity(entity_id)
        if entity is None:
            raise KeyError(f"Active entity '{entity_id}' was not found in the world.")
        self.active_entity_id = entity.entity_id

    def push_active_entity(self, entity_id: str) -> None:
        """Remember the current active entity, then switch to a new one."""
        self.active_entity_stack.append(self.get_active_entity().entity_id)
        self.set_active_entity(entity_id)

    def pop_active_entity(self) -> str:
        """Restore the most recently pushed active entity, or fall back cleanly."""
        while self.active_entity_stack:
            candidate_id = self.active_entity_stack.pop()
            entity = self.get_entity(candidate_id)
            if entity is not None:
                self.active_entity_id = entity.entity_id
                return self.active_entity_id

        self.active_entity_id = self._resolve_fallback_active_entity_id()
        return self.active_entity_id

    def iter_entities(self, *, include_absent: bool = False) -> list[Entity]:
        """Return entities as a list, optionally including non-present ones."""
        if include_absent:
            return list(self.entities.values())
        return [
            entity
            for entity in self.entities.values()
            if entity.present
        ]

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
        include_absent: bool = False,
    ) -> list[Entity]:
        """Return entities that currently occupy the requested grid tile."""
        return sorted(
            [
                entity
                for entity in self.iter_entities(include_absent=include_absent)
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
        """Return the first present visible entity at the given tile, if any."""
        for entity in reversed(
            self.get_entities_at(
                grid_x,
                grid_y,
                exclude_entity_id=exclude_entity_id,
            )
        ):
            if entity.present:
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

    def _resolve_fallback_active_entity_id(self) -> str:
        """Return the safest active-entity id when the requested one no longer exists."""
        player = self.get_entity(self.player_id)
        if player is not None:
            return player.entity_id
        if self.entities:
            return sorted(self.entities.keys())[0]
        return self.player_id

