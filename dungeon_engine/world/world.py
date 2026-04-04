"""World container for runtime entities."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from dungeon_engine.world.entity import Entity

DEFAULT_INPUT_ACTIONS: tuple[str, ...] = (
    "move_up",
    "move_down",
    "move_left",
    "move_right",
    "interact",
    "inventory",
    "menu",
)


@dataclass(slots=True)
class World:
    """Store and query runtime entities for the current play state."""

    area_entities: dict[str, Entity] = field(default_factory=dict)
    global_entities: dict[str, Entity] = field(default_factory=dict)
    default_input_targets: dict[str, str] = field(default_factory=dict)
    input_targets: dict[str, str] = field(default_factory=dict)
    input_route_stack: list[dict[str, str]] = field(default_factory=list, repr=False)
    variables: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize authored and runtime input-target maps."""
        normalized_defaults = self._normalize_input_targets(self.default_input_targets)
        self.default_input_targets = normalized_defaults

        normalized_current = self._normalize_input_targets(self.input_targets)
        if not normalized_current:
            self.input_targets = copy.deepcopy(self.default_input_targets)
            return

        merged_targets = copy.deepcopy(self.default_input_targets)
        merged_targets.update(normalized_current)
        self.input_targets = merged_targets

    def add_entity(self, entity: Entity) -> None:
        """Insert a new entity by id and fail on any duplicate identifier."""
        existing_entity = self.get_entity(entity.entity_id)
        if existing_entity is not None:
            if existing_entity.scope != entity.scope:
                raise ValueError(
                    f"Entity id '{entity.entity_id}' already exists as a {existing_entity.scope}-scope "
                    f"entity and cannot be added as a {entity.scope}-scope entity."
                )
            raise ValueError(
                f"Entity id '{entity.entity_id}' already exists as a {entity.scope}-scope "
                "entity and cannot be added again."
            )
        if entity.scope == "global":
            self.global_entities[entity.entity_id] = entity
            return
        self.area_entities[entity.entity_id] = entity

    def replace_entity(self, entity: Entity) -> None:
        """Insert or replace an entity explicitly by its stable identifier."""
        existing_entity = self.get_entity(entity.entity_id)
        if existing_entity is not None and existing_entity.scope != entity.scope:
            raise ValueError(
                f"Entity id '{entity.entity_id}' already exists as a {existing_entity.scope}-scope "
                f"entity and cannot be replaced by a {entity.scope}-scope entity."
            )
        if entity.scope == "global":
            self.global_entities[entity.entity_id] = entity
            return
        self.area_entities[entity.entity_id] = entity

    def remove_entity(self, entity_id: str) -> None:
        """Remove an entity when it exists in the current room."""
        self.area_entities.pop(entity_id, None)
        self.global_entities.pop(entity_id, None)
        for action, target_id in list(self.input_targets.items()):
            if target_id != entity_id:
                continue
            default_target_id = self.default_input_targets.get(action, "")
            self.input_targets[action] = "" if default_target_id == entity_id else default_target_id

    def get_entity(self, entity_id: str) -> Entity | None:
        """Return an entity when it exists in the current room."""
        entity = self.area_entities.get(entity_id)
        if entity is not None:
            return entity
        return self.global_entities.get(entity_id)

    def list_input_actions(self) -> list[str]:
        """Return every logical input action known to the current world."""
        seen: set[str] = set()
        ordered_actions: list[str] = []
        for action in [*DEFAULT_INPUT_ACTIONS, *self.default_input_targets.keys(), *self.input_targets.keys()]:
            if action in seen:
                continue
            seen.add(action)
            ordered_actions.append(action)
        return ordered_actions

    def get_input_target_id(self, action: str) -> str | None:
        """Return the current entity id routed for one logical input action."""
        action_name = str(action).strip()
        if not action_name:
            return None
        if action_name in self.input_targets:
            current_target_id = str(self.input_targets.get(action_name, "")).strip()
            if current_target_id and self.get_entity(current_target_id) is not None:
                return current_target_id
        default_target_id = str(self.default_input_targets.get(action_name, "")).strip()
        if not default_target_id:
            return None
        if self.get_entity(default_target_id) is not None:
            return default_target_id
        return None

    def get_input_target(self, action: str) -> Entity | None:
        """Return the entity currently routed for one logical input action."""
        target_id = self.get_input_target_id(action)
        if target_id is None:
            return None
        return self.get_entity(target_id)

    def set_input_target(self, action: str, entity_id: str | None) -> None:
        """Route one logical input action to a specific entity or clear it."""
        action_name = str(action).strip()
        if not action_name:
            raise ValueError("Input action names must be non-empty.")
        if entity_id in (None, ""):
            self.input_targets[action_name] = ""
            return
        entity = self.get_entity(str(entity_id))
        if entity is None:
            raise KeyError(f"Input target entity '{entity_id}' was not found in the world.")
        self.input_targets[action_name] = entity.entity_id

    def set_input_targets(self, targets: dict[str, str], *, replace: bool = False) -> None:
        """Update or replace the current logical-input routing table."""
        normalized_targets = self._normalize_input_targets(targets)
        if replace:
            next_targets = copy.deepcopy(self.default_input_targets)
            next_targets.update(normalized_targets)
            self.input_targets = next_targets
            return
        self.input_targets.update(normalized_targets)

    def route_inputs_to_entity(
        self,
        entity_id: str | None,
        *,
        actions: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        """Route selected logical inputs, or all inputs, to one entity."""
        if entity_id in (None, ""):
            selected_actions = self.list_input_actions() if actions is None else [str(action) for action in actions]
            for action in selected_actions:
                self.set_input_target(action, "")
            return
        resolved_entity = self.get_entity(str(entity_id))
        if resolved_entity is None:
            raise KeyError(f"Input target entity '{entity_id}' was not found in the world.")
        selected_actions = self.list_input_actions() if actions is None else [str(action) for action in actions]
        for action in selected_actions:
            self.input_targets[str(action)] = resolved_entity.entity_id

    def push_input_routes(
        self,
        *,
        actions: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        """Remember the current routed targets for one set of logical actions."""
        selected_actions = self.list_input_actions() if actions is None else [str(action) for action in actions]
        snapshot: dict[str, str] = {}
        for raw_action in selected_actions:
            action = str(raw_action).strip()
            if not action:
                raise ValueError("Input action names must be non-empty.")
            snapshot[action] = self.get_input_target_id(action) or ""
        self.input_route_stack.append(snapshot)

    def pop_input_routes(self) -> None:
        """Restore the last remembered routed targets for one set of logical actions."""
        if not self.input_route_stack:
            raise ValueError("Cannot pop input routes because the input route stack is empty.")
        snapshot = self.input_route_stack.pop()
        for action, target_id in snapshot.items():
            if target_id and self.get_entity(target_id) is not None:
                self.input_targets[action] = target_id
                continue
            self.input_targets[action] = ""

    def iter_entities(self, *, include_absent: bool = False) -> list[Entity]:
        """Return all entities, optionally including non-present ones."""
        entities = [*self.global_entities.values(), *self.area_entities.values()]
        if include_absent:
            return list(entities)
        return [
            entity
            for entity in entities
            if entity.present
        ]

    def iter_area_entities(self, *, include_absent: bool = False) -> list[Entity]:
        """Return only area-scoped entities."""
        if include_absent:
            return list(self.area_entities.values())
        return [
            entity
            for entity in self.area_entities.values()
            if entity.present
        ]

    def iter_global_entities(self, *, include_absent: bool = False) -> list[Entity]:
        """Return only global entities."""
        if include_absent:
            return list(self.global_entities.values())
        return [
            entity
            for entity in self.global_entities.values()
            if entity.present
        ]

    def iter_entities_in_space(
        self,
        space: str,
        *,
        include_absent: bool = False,
    ) -> list[Entity]:
        """Return entities in one spatial domain."""
        return [
            entity
            for entity in self.iter_entities(include_absent=include_absent)
            if entity.space == space
        ]

    def entity_sort_key(self, entity: Entity) -> tuple[int, int, str]:
        """Return a stable per-cell stacking key for spatial queries."""
        return (entity.render_order, entity.stack_order, entity.entity_id)

    def get_entities_at(
        self,
        grid_x: int,
        grid_y: int,
        *,
        exclude_entity_id: str | None = None,
        include_hidden: bool = False,
        include_absent: bool = False,
    ) -> list[Entity]:
        """Return world-space entities that currently occupy the requested tile."""
        return sorted(
            [
                entity
                for entity in self.iter_entities(include_absent=include_absent)
                if entity.space == "world"
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

    def get_solid_entities_at(
        self,
        grid_x: int,
        grid_y: int,
        *,
        exclude_entity_id: str | None = None,
        include_hidden: bool = False,
        include_absent: bool = False,
    ) -> list[Entity]:
        """Return world-space solid entities that occupy the requested tile."""
        return [
            entity
            for entity in self.get_entities_at(
                grid_x,
                grid_y,
                exclude_entity_id=exclude_entity_id,
                include_hidden=include_hidden,
                include_absent=include_absent,
            )
            if entity.is_effectively_solid()
        ]

    def get_interactable_entities_at(
        self,
        grid_x: int,
        grid_y: int,
        *,
        exclude_entity_id: str | None = None,
        include_hidden: bool = False,
        include_absent: bool = False,
    ) -> list[Entity]:
        """Return world-space interactable entities that occupy the requested tile."""
        return [
            entity
            for entity in self.get_entities_at(
                grid_x,
                grid_y,
                exclude_entity_id=exclude_entity_id,
                include_hidden=include_hidden,
                include_absent=include_absent,
            )
            if entity.is_effectively_interactable()
        ]

    def generate_entity_id(self, base_name: str) -> str:
        """Return a unique entity id within the current live world."""
        candidate = base_name
        counter = 1
        while self.get_entity(candidate) is not None:
            counter += 1
            candidate = f"{base_name}_{counter}"
        return candidate

    def _normalize_input_targets(self, targets: dict[str, str]) -> dict[str, str]:
        """Convert authored/runtime input-target data into stable string mappings."""
        normalized: dict[str, str] = {}
        for raw_action, raw_target in dict(targets).items():
            action = str(raw_action).strip()
            if not action:
                continue
            if raw_target in (None, ""):
                normalized[action] = ""
                continue
            normalized[action] = str(raw_target).strip()
        return normalized

