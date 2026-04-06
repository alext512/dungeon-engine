"""Traveler lifecycle helpers for the live persistence runtime."""

from __future__ import annotations

import copy
from typing import Any

from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity
from dungeon_engine.world.persistence_data import TravelerState
from dungeon_engine.world.persistence_snapshots import _serialize_saved_entity
from dungeon_engine.world.world import World


class PersistenceTravelerMixin:
    """Provide traveler-specific persistence helpers for ``PersistenceRuntime``."""

    def prepare_traveler_for_area(
        self,
        entity: Entity,
        *,
        destination_area_id: str,
        tile_size: int,
    ) -> None:
        """Move one runtime entity into traveler-managed session state for a new area."""
        first_departure = entity.origin_area_id is None
        if entity.origin_area_id is None and self.current_area_id:
            entity.origin_area_id = self.current_area_id

        self.save_data.travelers[entity.entity_id] = TravelerState(
            current_area=str(destination_area_id),
            entity_data=(
                _serialize_saved_entity(
                    entity,
                    tile_size,
                    project=self.project,
                )
                if first_departure
                else self._capture_traveler_entity_data(
                    entity,
                    tile_size=tile_size,
                    include_transient=False,
                )
            ),
            origin_area=entity.origin_area_id,
        )
        self._remove_entity_from_area_state(self.current_area_id, entity.entity_id)
        self.dirty = True

    def refresh_live_travelers(
        self,
        area: Area,
        world: World,
        *,
        include_transient: bool = False,
        force_entity_ids: set[str] | None = None,
    ) -> None:
        """Refresh saved traveler payloads from the currently loaded room."""
        forced_ids = set(force_entity_ids or set())
        live_traveler_ids: set[str] = set()
        for entity in world.iter_area_entities(include_absent=True):
            if entity.origin_area_id is None:
                continue
            live_traveler_ids.add(entity.entity_id)
            self.save_data.travelers[entity.entity_id] = TravelerState(
                current_area=area.area_id,
                entity_data=(
                    _serialize_saved_entity(
                        entity,
                        area.tile_size,
                        project=self.project,
                    )
                    if entity.entity_id in forced_ids
                    else self._capture_traveler_entity_data(
                        entity,
                        tile_size=area.tile_size,
                        include_transient=include_transient,
                    )
                ),
                origin_area=entity.origin_area_id,
            )
            self.dirty = True
        stale_ids = [
            entity_id
            for entity_id, traveler_state in self.save_data.travelers.items()
            if traveler_state.current_area == area.area_id and entity_id not in live_traveler_ids
        ]
        for entity_id in stale_ids:
            self.save_data.travelers.pop(entity_id, None)
            self.dirty = True

    def _ensure_traveler_state(
        self,
        entity_id: str,
        *,
        entity: Entity | None,
        tile_size: int | None,
    ) -> TravelerState:
        """Return one traveler's baseline, creating it from runtime state when missing."""
        traveler_state = self.save_data.travelers.get(entity_id)
        if traveler_state is None:
            if entity is None:
                raise ValueError("Traveler persistence updates require the runtime entity.")
            if tile_size is None:
                raise ValueError("Traveler persistence updates require the active area tile size.")
            traveler_state = TravelerState(
                current_area=self.current_area_id,
                entity_data=_serialize_saved_entity(
                    entity,
                    tile_size,
                    project=self.project,
                ),
                origin_area=entity.origin_area_id,
            )
            self.save_data.travelers[entity_id] = traveler_state
        return traveler_state

    def _capture_traveler_entity_data(
        self,
        entity: Entity,
        *,
        tile_size: int,
        include_transient: bool,
    ) -> dict[str, Any]:
        """Return one traveler's persisted payload, optionally including transient live state."""
        if include_transient or entity.persistence.entity_state:
            return _serialize_saved_entity(
                entity,
                tile_size,
                project=self.project,
            )

        traveler_state = self.save_data.travelers.get(entity.entity_id)
        if traveler_state is None:
            entity_data = _serialize_saved_entity(
                entity,
                tile_size,
                project=self.project,
            )
        else:
            entity_data = copy.deepcopy(traveler_state.entity_data)

        if entity.persistence.variables:
            variables = entity_data.setdefault("variables", {})
            for name, value in entity.variables.items():
                if entity.persistence.resolve_variable(str(name)):
                    variables[str(name)] = copy.deepcopy(value)
        return entity_data

    def _persist_traveler_field(
        self,
        entity_id: str,
        field_name: str,
        value: Any,
        *,
        entity: Entity | None,
        tile_size: int | None,
    ) -> None:
        """Persist one traveler field directly onto the traveler baseline payload."""
        traveler_state = self._ensure_traveler_state(
            entity_id,
            entity=entity,
            tile_size=tile_size,
        )
        traveler_state.current_area = self.current_area_id or traveler_state.current_area
        traveler_state.origin_area = entity.origin_area_id if entity is not None else traveler_state.origin_area
        traveler_state.entity_data[str(field_name)] = copy.deepcopy(value)
        self.dirty = True

    def _persist_traveler_variable(
        self,
        entity_id: str,
        name: str,
        value: Any,
        *,
        entity: Entity | None,
        tile_size: int | None,
    ) -> None:
        """Persist one traveler variable directly onto the traveler baseline payload."""
        traveler_state = self._ensure_traveler_state(
            entity_id,
            entity=entity,
            tile_size=tile_size,
        )
        traveler_state.current_area = self.current_area_id or traveler_state.current_area
        traveler_state.origin_area = entity.origin_area_id if entity is not None else traveler_state.origin_area
        variables = traveler_state.entity_data.setdefault("variables", {})
        variables[str(name)] = copy.deepcopy(value)
        self.dirty = True

    def _persist_traveler_command_enabled(
        self,
        entity_id: str,
        command_id: str,
        enabled: bool,
        *,
        entity: Entity | None,
        tile_size: int | None,
    ) -> None:
        """Persist one traveler entity-command enabled flag on the baseline payload."""
        traveler_state = self._ensure_traveler_state(
            entity_id,
            entity=entity,
            tile_size=tile_size,
        )
        traveler_state.current_area = self.current_area_id or traveler_state.current_area
        traveler_state.origin_area = entity.origin_area_id if entity is not None else traveler_state.origin_area
        entity_commands = traveler_state.entity_data.setdefault("entity_commands", {})
        command_entry = entity_commands.setdefault(
            str(command_id),
            {
                "enabled": bool(enabled),
                "commands": [],
            },
        )
        command_entry["enabled"] = bool(enabled)
        self.dirty = True
