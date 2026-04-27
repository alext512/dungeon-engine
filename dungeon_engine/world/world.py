"""World container for runtime entities."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from dungeon_engine.world.entity import Entity

InputRoute = dict[str, str]

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
    default_input_routes: dict[str, InputRoute] = field(default_factory=dict)
    input_routes: dict[str, InputRoute] = field(default_factory=dict)
    input_route_stack: list[dict[str, InputRoute]] = field(default_factory=list, repr=False)
    variables: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize authored and runtime input-route maps."""
        normalized_defaults = self._normalize_input_routes(self.default_input_routes)
        self.default_input_routes = normalized_defaults

        normalized_current = self._normalize_input_routes(self.input_routes)
        if not normalized_current:
            self.input_routes = copy.deepcopy(self.default_input_routes)
            return

        merged_routes = copy.deepcopy(self.default_input_routes)
        merged_routes.update(normalized_current)
        self.input_routes = merged_routes

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
        for action, route in list(self.input_routes.items()):
            if route.get("entity_id") != entity_id:
                continue
            default_route = self.default_input_routes.get(action, {})
            if default_route.get("entity_id") == entity_id:
                self.input_routes[action] = self._empty_input_route()
            else:
                self.input_routes[action] = copy.deepcopy(default_route)

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
        for action in [*DEFAULT_INPUT_ACTIONS, *self.default_input_routes.keys(), *self.input_routes.keys()]:
            if action in seen:
                continue
            seen.add(action)
            ordered_actions.append(action)
        return ordered_actions

    def get_input_route(self, action: str) -> InputRoute | None:
        """Return the current entity-command route for one logical input action."""
        action_name = str(action).strip()
        if not action_name:
            return None
        current_route = self.input_routes.get(action_name)
        if self._route_is_available(current_route):
            return copy.deepcopy(current_route)
        default_route = self.default_input_routes.get(action_name)
        if self._route_is_available(default_route):
            return copy.deepcopy(default_route)
        return None

    def get_input_target_id(self, action: str) -> str | None:
        """Return the current entity id routed for one logical input action."""
        route = self.get_input_route(action)
        if route is None:
            return None
        return route["entity_id"]

    def get_input_command_id(self, action: str) -> str | None:
        """Return the current entity-command id routed for one logical input action."""
        route = self.get_input_route(action)
        if route is None:
            return None
        return route["command_id"]

    def get_input_target(self, action: str) -> Entity | None:
        """Return the entity currently routed for one logical input action."""
        target_id = self.get_input_target_id(action)
        if target_id is None:
            return None
        return self.get_entity(target_id)

    def set_input_route(
        self,
        action: str,
        entity_id: str | None,
        command_id: str | None,
    ) -> None:
        """Route one logical input action to a specific entity command or clear it."""
        action_name = str(action).strip()
        if not action_name:
            raise ValueError("Input action names must be non-empty.")
        if entity_id in (None, "") or command_id in (None, ""):
            self.input_routes[action_name] = self._empty_input_route()
            return
        entity = self.get_entity(str(entity_id))
        if entity is None:
            raise KeyError(f"Input target entity '{entity_id}' was not found in the world.")
        resolved_command_id = str(command_id).strip()
        if not resolved_command_id:
            self.input_routes[action_name] = self._empty_input_route()
            return
        self.input_routes[action_name] = {
            "entity_id": entity.entity_id,
            "command_id": resolved_command_id,
        }

    def set_input_routes(self, routes: dict[str, Any], *, replace: bool = False) -> None:
        """Update or replace the current logical-input route table."""
        normalized_routes = self._normalize_input_routes(routes)
        if replace:
            next_routes = copy.deepcopy(self.default_input_routes)
            next_routes.update(normalized_routes)
            self.input_routes = next_routes
            return
        self.input_routes.update(normalized_routes)

    def push_input_routes(
        self,
        *,
        actions: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        """Remember the current routed entity commands for one set of logical actions."""
        selected_actions = self.list_input_actions() if actions is None else [str(action) for action in actions]
        snapshot: dict[str, InputRoute] = {}
        for raw_action in selected_actions:
            action = str(raw_action).strip()
            if not action:
                raise ValueError("Input action names must be non-empty.")
            snapshot[action] = self.get_input_route(action) or self._empty_input_route()
        self.input_route_stack.append(snapshot)

    def pop_input_routes(self) -> None:
        """Restore the last remembered routed entity commands for one set of logical actions."""
        if not self.input_route_stack:
            raise ValueError("Cannot pop input routes because the input route stack is empty.")
        snapshot = self.input_route_stack.pop()
        for action, route in snapshot.items():
            route_entity_id = str(route.get("entity_id", "")).strip()
            route_command_id = str(route.get("command_id", "")).strip()
            if (
                route_entity_id
                and route_command_id
                and self.get_entity(route_entity_id) is not None
            ):
                self.input_routes[action] = {
                    "entity_id": route_entity_id,
                    "command_id": route_command_id,
                }
                continue
            self.input_routes[action] = self._empty_input_route()

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

    def _normalize_input_routes(self, routes: dict[str, Any]) -> dict[str, InputRoute]:
        """Convert authored/runtime input-route data into stable string mappings."""
        normalized: dict[str, InputRoute] = {}
        for raw_action, raw_route in dict(routes).items():
            action = str(raw_action).strip()
            if not action:
                continue
            normalized[action] = self._normalize_input_route(raw_route)
        return normalized

    @staticmethod
    def _empty_input_route() -> InputRoute:
        return {"entity_id": "", "command_id": ""}

    def _normalize_input_route(self, raw_route: Any) -> InputRoute:
        if raw_route in (None, ""):
            return self._empty_input_route()
        if not isinstance(raw_route, dict):
            raise TypeError("Input routes must map actions to route objects.")
        entity_id = str(raw_route.get("entity_id", "")).strip()
        command_id = str(raw_route.get("command_id", "")).strip()
        if not entity_id or not command_id:
            return self._empty_input_route()
        return {"entity_id": entity_id, "command_id": command_id}

    def _route_is_available(self, route: InputRoute | None) -> bool:
        if not route:
            return False
        entity_id = str(route.get("entity_id", "")).strip()
        command_id = str(route.get("command_id", "")).strip()
        return bool(entity_id and command_id and self.get_entity(entity_id) is not None)

