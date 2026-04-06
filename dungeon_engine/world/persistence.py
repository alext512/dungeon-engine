"""Live persistence runtime plus compatibility re-exports.

Save-data models and JSON codec helpers live in ``persistence_data.py``.
Snapshot/diff application helpers live in ``persistence_snapshots.py``.
This module keeps the runtime mutation layer as the stable public entry point.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from dungeon_engine.project_context import ProjectContext
from dungeon_engine.world.entity import Entity
from dungeon_engine.world.persistence_data import (
    PersistentAreaState,
    PersistentEntityState,
    ResetRequest,
    SaveData,
    get_persistent_area_state,
    load_save_data,
    save_data_from_dict,
    save_data_to_dict,
    save_save_data,
)
from dungeon_engine.world.persistence_snapshots import (
    _serialize_saved_entity,
    apply_area_travelers,
    apply_current_global_state,
    apply_persistent_area_state,
    apply_persistent_global_state,
    capture_current_area_state,
    capture_current_global_state,
    capture_persistent_area_state,
    select_entity_ids_by_tags,
    update_save_data_for_area,
)
from dungeon_engine.world.persistence_travelers import PersistenceTravelerMixin
from dungeon_engine.world.world import World


class PersistenceRuntime(PersistenceTravelerMixin):
    """Manage live persistent save data plus deferred reset requests."""

    def __init__(
        self,
        save_path: Path | None = None,
        *,
        project: ProjectContext,
        load_existing: bool = False,
    ) -> None:
        self.save_path = save_path
        self.project = project
        self.save_data = (
            load_save_data(save_path)
            if load_existing and save_path is not None
            else SaveData()
        )
        self.current_area_id: str = ""
        self._current_authored_entity_ids: set[str] = set()
        self.dirty = False
        self._pending_immediate_resets: list[ResetRequest] = []
        self._pending_reentry_resets: dict[str, list[ResetRequest]] = {}

    def set_save_path(self, save_path: Path | None) -> None:
        """Update which save-slot path future load/flush calls target."""
        self.save_path = save_path.resolve() if save_path is not None else None

    def bind_area(self, area_id: str, *, authored_world: World | None = None) -> None:
        """Set the currently active area id for mutation commands."""
        self.current_area_id = area_id
        if authored_world is not None:
            self._current_authored_entity_ids = {
                entity.entity_id
                for entity in authored_world.iter_entities(include_absent=True)
            }
        else:
            self._current_authored_entity_ids = set()

    def flush(self, *, force: bool = False) -> bool:
        """Write the current in-memory persistent state to disk when requested."""
        if not force and not self.dirty:
            return False
        if self.save_path is None:
            raise ValueError("No save-slot path is configured for persistence flush.")
        save_save_data(self.save_path, self.save_data)
        self.dirty = False
        return True

    def has_save_file(self) -> bool:
        """Return True when a save slot file currently exists on disk."""
        return self.save_path is not None and self.save_path.exists()

    def reload_from_disk(self) -> bool:
        """Replace in-memory persistent state with the current save slot file."""
        if self.save_path is None:
            self.save_data = SaveData()
            self.dirty = False
            return False
        save_exists = self.save_path.exists()
        self.save_data = load_save_data(self.save_path)
        self.dirty = False
        return save_exists

    def current_area_state(self) -> PersistentAreaState | None:
        """Return the currently bound area's persistent state."""
        if not self.current_area_id:
            return None
        return self.save_data.areas.get(self.current_area_id)

    def set_current_area_variable(self, name: str, value: Any) -> None:
        """Persist one current-area variable override for the bound area."""
        area_state = self._ensure_current_area_state()
        area_state.variables[name] = copy.deepcopy(value)
        self.dirty = True

    def set_area_variable(self, area_id: str, name: str, value: Any) -> None:
        """Persist one area-level variable override for an explicitly chosen area."""
        area_state = self._ensure_area_state(area_id)
        area_state.variables[name] = copy.deepcopy(value)
        self.dirty = True

    def set_entity_field(
        self,
        entity_id: str,
        field_name: str,
        value: Any,
        *,
        entity: Entity | None = None,
        tile_size: int | None = None,
    ) -> None:
        """Persist a top-level entity field override."""
        if entity is not None and entity.scope == "global":
            entity_state = self._ensure_entity_state(entity_id, entity=entity)
            entity_state.removed = False
            entity_state.spawned = None
            entity_state.overrides[field_name] = copy.deepcopy(value)
            self.dirty = True
            return
        if entity is not None and entity.origin_area_id is not None:
            self._persist_traveler_field(
                entity_id,
                field_name,
                value,
                entity=entity,
                tile_size=tile_size,
            )
            return
        if not self._is_authored_entity(entity_id):
            self._record_spawned_entity(entity=entity, tile_size=tile_size)
            return
        entity_state = self._ensure_entity_state(entity_id, entity=entity)
        entity_state.removed = False
        entity_state.spawned = None
        entity_state.overrides[field_name] = copy.deepcopy(value)
        self.dirty = True

    def set_area_entity_field(
        self,
        area_id: str,
        entity_id: str,
        field_name: str,
        value: Any,
    ) -> None:
        """Persist one area-owned entity field override for an explicitly chosen area."""
        entity_state = self._ensure_area_entity_state(area_id, entity_id)
        entity_state.removed = False
        entity_state.spawned = None
        entity_state.overrides[field_name] = copy.deepcopy(value)
        self.dirty = True

    def set_entity_variable(
        self,
        entity_id: str,
        name: str,
        value: Any,
        *,
        entity: Entity | None = None,
        tile_size: int | None = None,
    ) -> None:
        """Persist an entity variable override."""
        if entity is not None and entity.scope == "global":
            entity_state = self._ensure_entity_state(entity_id, entity=entity)
            entity_state.removed = False
            entity_state.spawned = None
            variables = entity_state.overrides.setdefault("variables", {})
            variables[name] = copy.deepcopy(value)
            self.dirty = True
            return
        if entity is not None and entity.origin_area_id is not None:
            self._persist_traveler_variable(
                entity_id,
                name,
                value,
                entity=entity,
                tile_size=tile_size,
            )
            return
        if not self._is_authored_entity(entity_id):
            self._record_spawned_entity(entity=entity, tile_size=tile_size)
            return
        entity_state = self._ensure_entity_state(entity_id, entity=entity)
        entity_state.removed = False
        entity_state.spawned = None
        variables = entity_state.overrides.setdefault("variables", {})
        variables[name] = copy.deepcopy(value)
        self.dirty = True

    def set_area_entity_variable(
        self,
        area_id: str,
        entity_id: str,
        name: str,
        value: Any,
    ) -> None:
        """Persist one area-owned entity variable override for an explicitly chosen area."""
        entity_state = self._ensure_area_entity_state(area_id, entity_id)
        entity_state.removed = False
        entity_state.spawned = None
        variables = entity_state.overrides.setdefault("variables", {})
        variables[name] = copy.deepcopy(value)
        self.dirty = True

    def set_entity_command_enabled(
        self,
        entity_id: str,
        command_id: str,
        enabled: bool,
        *,
        entity: Entity | None = None,
        tile_size: int | None = None,
    ) -> None:
        """Persist an entity-command enabled-state override."""
        if entity is not None and entity.scope == "global":
            entity_state = self._ensure_entity_state(entity_id, entity=entity)
            entity_state.removed = False
            entity_state.spawned = None
            command_states = entity_state.overrides.setdefault("entity_command_states", {})
            command_states[str(command_id)] = bool(enabled)
            self.dirty = True
            return
        if entity is not None and entity.origin_area_id is not None:
            self._persist_traveler_command_enabled(
                entity_id,
                command_id,
                enabled,
                entity=entity,
                tile_size=tile_size,
            )
            return
        if not self._is_authored_entity(entity_id):
            self._record_spawned_entity(entity=entity, tile_size=tile_size)
            return
        entity_state = self._ensure_entity_state(entity_id, entity=entity)
        entity_state.removed = False
        entity_state.spawned = None
        command_states = entity_state.overrides.setdefault("entity_command_states", {})
        command_states[str(command_id)] = bool(enabled)
        self.dirty = True

    def remove_entity(self, entity_id: str, *, entity: Entity | None = None) -> None:
        """Mark an entity as removed in persistent state."""
        if entity is not None and entity.scope == "global":
            if not self._is_authored_entity(entity_id):
                self.save_data.global_entities.pop(entity_id, None)
                self.dirty = True
                return
            entity_state = self._ensure_entity_state(entity_id, entity=entity)
            entity_state.removed = True
            entity_state.spawned = None
            entity_state.overrides.clear()
            self.dirty = True
            return
        if entity is not None and entity.origin_area_id is not None:
            self.save_data.travelers.pop(entity_id, None)
            self._remove_entity_from_area_state(self.current_area_id, entity_id)
            self.dirty = True
            return
        if not self._is_authored_entity(entity_id):
            area_state = self.current_area_state()
            if area_state is None:
                return
            area_state.entities.pop(entity_id, None)
            self._prune_current_area_state()
            self.dirty = True
            return
        entity_state = self._ensure_entity_state(entity_id)
        entity_state.removed = True
        entity_state.spawned = None
        entity_state.overrides.clear()
        self.dirty = True

    def record_spawned_entity(self, entity: Entity, *, tile_size: int) -> None:
        """Persist a spawned entity so it survives re-entry and save/load."""
        self._record_spawned_entity(entity=entity, tile_size=tile_size)

    def request_reset(
        self,
        *,
        kind: str,
        apply: str = "immediate",
        entity_ids: list[str] | tuple[str, ...] | None = None,
        include_tags: list[str] | tuple[str, ...] | None = None,
        exclude_tags: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        """Queue a transient or persistent reset request."""
        if kind not in {"transient", "persistent"}:
            raise ValueError(f"Unknown reset kind '{kind}'.")
        if apply not in {"immediate", "on_reentry"}:
            raise ValueError(f"Unknown reset apply mode '{apply}'.")

        request = ResetRequest(
            kind=kind,
            apply=apply,
            entity_ids=tuple(
                entity_id
                for entity_id in (str(raw_id).strip() for raw_id in (entity_ids or []))
                if entity_id
            ),
            include_tags=tuple(str(tag) for tag in (include_tags or [])),
            exclude_tags=tuple(str(tag) for tag in (exclude_tags or [])),
        )
        if apply == "immediate":
            self._pending_immediate_resets.append(request)
            return

        if not self.current_area_id:
            raise ValueError("Cannot schedule an on_reentry reset without a current area.")
        self._pending_reentry_resets.setdefault(self.current_area_id, []).append(request)

    def consume_immediate_reset(self) -> ResetRequest | None:
        """Return the next immediate reset request, if any."""
        if not self._pending_immediate_resets:
            return None
        return self._pending_immediate_resets.pop(0)

    def consume_reentry_resets(self, area_id: str) -> list[ResetRequest]:
        """Return and clear pending on-reentry resets for an area."""
        return self._pending_reentry_resets.pop(area_id, [])

    def clear_persistent_area_state(
        self,
        area_id: str,
        authored_world: World,
        *,
        include_tags: tuple[str, ...] = (),
        exclude_tags: tuple[str, ...] = (),
    ) -> None:
        """Clear persistent overrides for the whole room or matching tagged entities."""
        area_state = self.save_data.areas.get(area_id)
        if area_state is None:
            return

        if not include_tags and not exclude_tags:
            self.save_data.areas.pop(area_id, None)
            self.dirty = True
            return

        matched_ids = select_entity_ids_by_tags(
            authored_world,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
        )
        for entity_id in matched_ids:
            area_state.entities.pop(entity_id, None)

        if not area_state.variables and not area_state.entities:
            self.save_data.areas.pop(area_id, None)
        self.dirty = True

    def _ensure_area_state(self, area_id: str) -> PersistentAreaState:
        """Return one specific area's persistent state, creating it when missing."""
        resolved_area_id = str(area_id).strip()
        if not resolved_area_id:
            raise ValueError("Area-targeted persistence updates require a non-empty area_id.")
        area_state = self.save_data.areas.get(resolved_area_id)
        if area_state is None:
            area_state = PersistentAreaState()
            self.save_data.areas[resolved_area_id] = area_state
        return area_state

    def _ensure_current_area_state(self) -> PersistentAreaState:
        """Return the current area state, creating it when missing."""
        if not self.current_area_id:
            raise ValueError("No current area is bound for persistence updates.")
        return self._ensure_area_state(self.current_area_id)

    def _ensure_entity_state(
        self,
        entity_id: str,
        *,
        entity: Entity | None = None,
    ) -> PersistentEntityState:
        """Return the current area's persistent state for one entity."""
        if entity is not None and entity.scope == "global":
            entity_state = self.save_data.global_entities.get(entity_id)
            if entity_state is None:
                entity_state = PersistentEntityState()
                self.save_data.global_entities[entity_id] = entity_state
            return entity_state
        area_state = self._ensure_current_area_state()
        entity_state = area_state.entities.get(entity_id)
        if entity_state is None:
            entity_state = PersistentEntityState()
            area_state.entities[entity_id] = entity_state
        return entity_state

    def _ensure_area_entity_state(
        self,
        area_id: str,
        entity_id: str,
    ) -> PersistentEntityState:
        """Return one specific area's persistent state for one authored area entity."""
        resolved_entity_id = str(entity_id).strip()
        if not resolved_entity_id:
            raise ValueError("Area-targeted entity persistence updates require a non-empty entity_id.")
        area_state = self._ensure_area_state(area_id)
        entity_state = area_state.entities.get(resolved_entity_id)
        if entity_state is None:
            entity_state = PersistentEntityState()
            area_state.entities[resolved_entity_id] = entity_state
        return entity_state

    def _record_spawned_entity(self, *, entity: Entity | None, tile_size: int | None) -> None:
        """Store the full serialized state for one spawned entity."""
        if entity is None:
            raise ValueError("Persisting a spawned entity requires the runtime entity.")
        if tile_size is None:
            raise ValueError("Persisting a spawned entity requires the active area tile size.")
        entity_state = self._ensure_entity_state(entity.entity_id, entity=entity)
        entity_state.removed = False
        entity_state.spawned = _serialize_saved_entity(
            entity,
            tile_size,
            project=self.project,
        )
        entity_state.overrides.clear()
        self.dirty = True

    def _is_authored_entity(self, entity_id: str) -> bool:
        """Return True when the entity id belongs to the authored area document."""
        return entity_id in self._current_authored_entity_ids

    def _prune_current_area_state(self) -> None:
        """Drop the bound area's entry when it no longer stores anything."""
        area_state = self.current_area_state()
        if area_state is None:
            return
        if area_state.variables or area_state.entities:
            return
        self.save_data.areas.pop(self.current_area_id, None)

    def _remove_entity_from_area_state(self, area_id: str, entity_id: str) -> None:
        """Drop one entity override from one area's persistent state when it migrates away."""
        if not area_id:
            return
        area_state = self.save_data.areas.get(area_id)
        if area_state is None:
            return
        area_state.entities.pop(entity_id, None)
        if not area_state.variables and not area_state.entities:
            self.save_data.areas.pop(area_id, None)
