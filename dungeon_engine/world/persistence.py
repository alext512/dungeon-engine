"""Persistent save-state helpers layered on top of authored room data.

This module keeps persistent room state as compact per-area/per-entity overrides
instead of full duplicated room snapshots. Authored room JSON remains the source
of truth; save data records only playthrough-specific differences.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dungeon_engine.project import ProjectContext
from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity, EntityVisual
from dungeon_engine.world.world import World


SAVE_DATA_VERSION = 6


@dataclass(slots=True)
class PersistentEntityState:
    """Saved changes for one entity instance in an area diff."""

    removed: bool = False
    spawned: dict[str, Any] | None = None
    overrides: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PersistentAreaState:
    """Persistent changes for one area."""

    variables: dict[str, Any] = field(default_factory=dict)
    entities: dict[str, PersistentEntityState] = field(default_factory=dict)


@dataclass(slots=True)
class TravelerState:
    """Saved state for one entity that currently lives outside its authored origin room."""

    session_entity_id: str
    current_area: str
    entity_data: dict[str, Any]
    origin_area: str | None = None
    origin_entity_id: str | None = None


@dataclass(slots=True)
class SaveData:
    """Serializable save-slot data for persistent gameplay state."""

    version: int = SAVE_DATA_VERSION
    next_session_entity_serial: int = 1
    globals: dict[str, Any] = field(default_factory=dict)
    global_entities: dict[str, PersistentEntityState] = field(default_factory=dict)
    current_area: str = ""
    current_input_targets: dict[str, str] | None = None
    current_camera: dict[str, Any] | None = None
    travelers: dict[str, TravelerState] = field(default_factory=dict)
    areas: dict[str, PersistentAreaState] = field(default_factory=dict)
    current_area_state: PersistentAreaState | None = None
    current_global_entities: dict[str, PersistentEntityState] | None = None


@dataclass(slots=True)
class ResetRequest:
    """A request to reset transient or persistent room state."""

    kind: str
    apply: str = "immediate"
    include_tags: tuple[str, ...] = ()
    exclude_tags: tuple[str, ...] = ()


class PersistenceRuntime:
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

    def allocate_session_entity_id(self) -> str:
        """Return a stable new runtime session id for a traveler-managed entity."""
        session_entity_id = f"traveler_{int(self.save_data.next_session_entity_serial)}"
        self.save_data.next_session_entity_serial += 1
        self.dirty = True
        return session_entity_id

    def prepare_traveler_for_area(
        self,
        entity: Entity,
        *,
        destination_area_id: str,
        tile_size: int,
    ) -> None:
        """Move one runtime entity into traveler-managed session state for a new area."""
        if entity.session_entity_id is None:
            entity.session_entity_id = self.allocate_session_entity_id()
        if entity.origin_area_id is None and self.current_area_id:
            entity.origin_area_id = self.current_area_id
        if entity.origin_entity_id is None and self._is_authored_entity(entity.entity_id):
            entity.origin_entity_id = entity.entity_id

        self.save_data.travelers[entity.session_entity_id] = TravelerState(
            session_entity_id=entity.session_entity_id,
            current_area=str(destination_area_id),
            entity_data=_serialize_saved_entity(
                entity,
                tile_size,
                project=self.project,
            ),
            origin_area=entity.origin_area_id,
            origin_entity_id=entity.origin_entity_id,
        )
        self._remove_entity_from_area_state(self.current_area_id, entity.entity_id)
        self.dirty = True

    def refresh_live_travelers(
        self,
        area: Area,
        world: World,
    ) -> None:
        """Refresh saved traveler payloads from the currently loaded room."""
        live_session_ids: set[str] = set()
        for entity in world.iter_area_entities(include_absent=True):
            if not entity.session_entity_id:
                continue
            live_session_ids.add(entity.session_entity_id)
            self.save_data.travelers[entity.session_entity_id] = TravelerState(
                session_entity_id=entity.session_entity_id,
                current_area=area.area_id,
                entity_data=_serialize_saved_entity(
                    entity,
                    area.tile_size,
                    project=self.project,
                ),
                origin_area=entity.origin_area_id,
                origin_entity_id=entity.origin_entity_id,
            )
            self.dirty = True
        stale_ids = [
            session_entity_id
            for session_entity_id, traveler_state in self.save_data.travelers.items()
            if traveler_state.current_area == area.area_id and session_entity_id not in live_session_ids
        ]
        for session_entity_id in stale_ids:
            self.save_data.travelers.pop(session_entity_id, None)
            self.dirty = True

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

    def set_entity_event_enabled(
        self,
        entity_id: str,
        event_id: str,
        enabled: bool,
        *,
        entity: Entity | None = None,
        tile_size: int | None = None,
    ) -> None:
        """Persist an entity event enabled-state override."""
        if entity is not None and entity.scope == "global":
            entity_state = self._ensure_entity_state(entity_id, entity=entity)
            entity_state.removed = False
            entity_state.spawned = None
            event_states = entity_state.overrides.setdefault("event_states", {})
            event_states[str(event_id)] = bool(enabled)
            self.dirty = True
            return
        if not self._is_authored_entity(entity_id):
            self._record_spawned_entity(entity=entity, tile_size=tile_size)
            return
        entity_state = self._ensure_entity_state(entity_id, entity=entity)
        entity_state.removed = False
        entity_state.spawned = None
        event_states = entity_state.overrides.setdefault("event_states", {})
        event_states[str(event_id)] = bool(enabled)
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


def load_save_data(path: Path) -> SaveData:
    """Load save data from disk, returning an empty slot when missing."""
    if not path.exists():
        return SaveData()

    raw_data = json.loads(path.read_text(encoding="utf-8"))
    return save_data_from_dict(raw_data)


def save_save_data(path: Path, save_data: SaveData) -> None:
    """Write a save slot to disk in a stable JSON format."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(save_data_to_dict(save_data), indent=2), encoding="utf-8")


def save_data_from_dict(raw_data: dict[str, Any]) -> SaveData:
    """Parse a JSON-like dict into structured save data."""
    version = int(raw_data.get("version", SAVE_DATA_VERSION))
    next_session_entity_serial = int(raw_data.get("next_session_entity_serial", 1))
    globals_data = copy.deepcopy(raw_data.get("globals", {}))
    current_area = str(raw_data.get("current_area", "")).strip()
    raw_current_input_targets = raw_data.get("current_input_targets")
    raw_current_camera = raw_data.get("current_camera")
    areas = _load_area_state_mapping(raw_data.get("areas", {}))
    travelers = _load_traveler_state_mapping(raw_data.get("travelers", {}))
    global_entities = _load_entity_state_mapping(
        globals_data.get("entities", {}) if isinstance(globals_data, dict) else {}
    )
    current_global_entities = _load_entity_state_mapping(raw_data.get("current_global_entities", {}))
    if isinstance(globals_data, dict):
        globals_data.pop("entities", None)
    current_input_targets = None
    if isinstance(raw_current_input_targets, dict):
        current_input_targets = {
            str(action): str(entity_id)
            for action, entity_id in raw_current_input_targets.items()
        }
    current_camera = copy.deepcopy(raw_current_camera) if isinstance(raw_current_camera, dict) else None

    return SaveData(
        version=version,
        next_session_entity_serial=max(1, next_session_entity_serial),
        globals=globals_data if isinstance(globals_data, dict) else {},
        global_entities=global_entities,
        current_area=current_area,
        current_input_targets=current_input_targets,
        current_camera=current_camera,
        travelers=travelers,
        areas=areas,
        current_area_state=_area_state_from_dict(raw_data.get("current_area_state")),
        current_global_entities=current_global_entities or None,
    )


def save_data_to_dict(save_data: SaveData) -> dict[str, Any]:
    """Convert structured save data into JSON-serializable dictionaries."""
    globals_payload = copy.deepcopy(save_data.globals)
    if save_data.global_entities:
        globals_payload["entities"] = _entity_state_mapping_to_dict(save_data.global_entities)
    data = {
        "version": save_data.version,
        "next_session_entity_serial": max(1, int(save_data.next_session_entity_serial)),
        "globals": globals_payload,
        "current_area": str(save_data.current_area),
        "areas": _area_state_mapping_to_dict(save_data.areas),
    }
    if save_data.current_input_targets:
        data["current_input_targets"] = {
            str(action): str(entity_id)
            for action, entity_id in save_data.current_input_targets.items()
        }
    if save_data.current_camera:
        data["current_camera"] = copy.deepcopy(save_data.current_camera)
    if save_data.travelers:
        data["travelers"] = _traveler_state_mapping_to_dict(save_data.travelers)
    if save_data.current_area_state is not None:
        data["current_area_state"] = _area_state_to_dict(save_data.current_area_state)
    if save_data.current_global_entities:
        data["current_global_entities"] = _entity_state_mapping_to_dict(
            save_data.current_global_entities
        )
    return data


def get_persistent_area_state(save_data: SaveData, area_id: str) -> PersistentAreaState | None:
    """Return the stored persistent state for an area, if any."""
    return save_data.areas.get(area_id)


def select_entity_ids_by_tags(
    authored_world: World,
    *,
    include_tags: tuple[str, ...] = (),
    exclude_tags: tuple[str, ...] = (),
) -> set[str]:
    """Return authored entity ids matching the requested include/exclude tags."""
    include = set(include_tags)
    exclude = set(exclude_tags)
    matched_ids: set[str] = set()
    for entity in authored_world.iter_area_entities(include_absent=True):
        entity_tags = set(entity.tags)
        if include and not (entity_tags & include):
            continue
        if exclude and (entity_tags & exclude):
            continue
        matched_ids.add(entity.entity_id)
    return matched_ids


def apply_persistent_area_state(
    area: Area,
    world: World,
    area_state: PersistentAreaState,
    *,
    project: ProjectContext,
) -> None:
    """Layer persistent overrides on top of a freshly loaded authored room."""
    if area_state.variables:
        world.variables.update(copy.deepcopy(area_state.variables))
    _apply_entity_state_mapping(
        area,
        world,
        area_state.entities,
        project=project,
    )


def apply_persistent_global_state(
    area: Area,
    world: World,
    save_data: SaveData,
    *,
    project: ProjectContext,
) -> None:
    """Layer persistent global-entity overrides on top of installed project globals."""
    _apply_entity_state_mapping(
        area,
        world,
        save_data.global_entities,
        project=project,
    )


def apply_current_global_state(
    area: Area,
    world: World,
    current_global_entities: dict[str, PersistentEntityState] | None,
    *,
    project: ProjectContext,
) -> None:
    """Apply the exact saved runtime snapshot for global entities."""
    if not current_global_entities:
        return
    _apply_entity_state_mapping(
        area,
        world,
        current_global_entities,
        project=project,
    )


def apply_area_travelers(
    area: Area,
    world: World,
    save_data: SaveData,
    *,
    project: ProjectContext,
    skip_session_entity_ids: set[str] | None = None,
) -> None:
    """Suppress away travelers' origin placeholders and install travelers that belong here."""
    skipped_ids = set(skip_session_entity_ids or set())
    for traveler_state in save_data.travelers.values():
        if traveler_state.origin_area == area.area_id and traveler_state.origin_entity_id:
            if traveler_state.current_area != area.area_id:
                world.remove_entity(traveler_state.origin_entity_id)

        if traveler_state.current_area != area.area_id:
            continue
        if traveler_state.session_entity_id in skipped_ids:
            continue
        entity = _instantiate_saved_entity(
            traveler_state.entity_data,
            area.tile_size,
            project=project,
        )
        entity.session_entity_id = traveler_state.session_entity_id
        entity.origin_area_id = traveler_state.origin_area
        entity.origin_entity_id = traveler_state.origin_entity_id
        world.add_entity(entity)


def capture_current_area_state(
    area: Area,
    base_world: World,
    current_world: World,
    *,
    project: ProjectContext,
) -> PersistentAreaState | None:
    """Capture the exact saved diff for the current area over its persistent base."""
    return _capture_area_state(
        area,
        base_world,
        current_world,
        include_spawned_entities=True,
        project=project,
    )


def capture_current_global_state(
    area: Area,
    base_world: World,
    current_world: World,
    *,
    project: ProjectContext,
) -> dict[str, PersistentEntityState] | None:
    """Capture the exact saved diff for global entities over their persistent base."""
    authored_entities = {
        entity.entity_id: entity
        for entity in base_world.iter_global_entities(include_absent=True)
    }
    current_entities = {
        entity.entity_id: entity
        for entity in current_world.iter_global_entities(include_absent=True)
    }
    entity_states = _capture_entity_state_mapping(
        area,
        authored_entities,
        current_entities,
        include_spawned_entities=True,
        project=project,
    )
    return entity_states or None


def capture_persistent_area_state(
    area: Area,
    authored_world: World,
    current_world: World,
    *,
    project: ProjectContext,
) -> PersistentAreaState | None:
    """Capture persistent overrides by comparing current runtime state to authored defaults."""
    return _capture_area_state(
        area,
        authored_world,
        current_world,
        include_spawned_entities=False,
        project=project,
    )


def update_save_data_for_area(
    save_data: SaveData,
    area: Area,
    authored_world: World,
    current_world: World,
    *,
    project: ProjectContext,
) -> None:
    """Refresh one area's persistent save entry from the current runtime state."""
    area_state = capture_persistent_area_state(
        area,
        authored_world,
        current_world,
        project=project,
    )
    if area_state is None:
        save_data.areas.pop(area.area_id, None)
        return
    save_data.areas[area.area_id] = area_state


def _persistent_entity_state_to_dict(entity_state: PersistentEntityState) -> dict[str, Any]:
    """Serialize a persistent entity state using flat override keys."""
    data = copy.deepcopy(entity_state.overrides)
    if entity_state.spawned is not None:
        data["spawned"] = copy.deepcopy(entity_state.spawned)
    if entity_state.removed:
        data["removed"] = True
    return data


def _area_state_from_dict(raw_state: Any) -> PersistentAreaState | None:
    """Parse one saved area-state payload from a JSON-like dict."""
    if not isinstance(raw_state, dict):
        return None

    variables = raw_state.get("variables", {})
    return PersistentAreaState(
        variables=copy.deepcopy(variables) if isinstance(variables, dict) else {},
        entities=_load_entity_state_mapping(raw_state.get("entities", {})),
    )


def _area_state_to_dict(area_state: PersistentAreaState) -> dict[str, Any]:
    """Convert one saved area state into a JSON-friendly dict."""
    data: dict[str, Any] = {}
    if area_state.variables:
        data["variables"] = copy.deepcopy(area_state.variables)
    if area_state.entities:
        data["entities"] = _entity_state_mapping_to_dict(area_state.entities)
    return data


def _load_entity_state_mapping(raw_entities: Any) -> dict[str, PersistentEntityState]:
    """Parse a JSON-like entity-state mapping into structured persistent states."""
    if not isinstance(raw_entities, dict):
        return {}

    entities: dict[str, PersistentEntityState] = {}
    for entity_id, entity_data in raw_entities.items():
        if not isinstance(entity_data, dict):
            continue
        entity_payload = copy.deepcopy(entity_data)
        removed = bool(entity_payload.pop("removed", False))
        spawned = copy.deepcopy(entity_payload.pop("spawned", None))
        entities[str(entity_id)] = PersistentEntityState(
            removed=removed,
            spawned=spawned if isinstance(spawned, dict) else None,
            overrides=entity_payload,
        )
    return entities


def _entity_state_mapping_to_dict(
    entities: dict[str, PersistentEntityState],
) -> dict[str, Any]:
    """Serialize a persistent entity-state mapping into JSON-like dictionaries."""
    serialized: dict[str, Any] = {}
    for entity_id, entity_state in entities.items():
        entity_data = _persistent_entity_state_to_dict(entity_state)
        if entity_data:
            serialized[str(entity_id)] = entity_data
    return serialized


def _load_area_state_mapping(raw_areas: Any) -> dict[str, PersistentAreaState]:
    """Parse the save file's area-state mapping."""
    if not isinstance(raw_areas, dict):
        return {}

    areas: dict[str, PersistentAreaState] = {}
    for area_id, area_data in raw_areas.items():
        area_state = _area_state_from_dict(area_data)
        if area_state is None:
            continue
        areas[str(area_id)] = area_state
    return areas


def _traveler_state_from_dict(raw_state: Any, *, fallback_id: str) -> TravelerState | None:
    """Parse one saved traveler payload from a JSON-like dict."""
    if not isinstance(raw_state, dict):
        return None
    current_area = str(raw_state.get("current_area", "")).strip()
    raw_entity_data = raw_state.get("entity")
    if not current_area or not isinstance(raw_entity_data, dict):
        return None
    origin_area = raw_state.get("origin_area")
    origin_entity_id = raw_state.get("origin_entity_id")
    normalized_origin_area = (
        str(origin_area).strip()
        if origin_area is not None
        else ""
    )
    normalized_origin_entity_id = (
        str(origin_entity_id).strip()
        if origin_entity_id is not None
        else ""
    )
    return TravelerState(
        session_entity_id=str(raw_state.get("session_entity_id", fallback_id)).strip() or fallback_id,
        current_area=current_area,
        entity_data=copy.deepcopy(raw_entity_data),
        origin_area=normalized_origin_area or None,
        origin_entity_id=normalized_origin_entity_id or None,
    )


def _traveler_state_to_dict(traveler_state: TravelerState) -> dict[str, Any]:
    """Convert one traveler state into a JSON-friendly dict."""
    data: dict[str, Any] = {
        "session_entity_id": traveler_state.session_entity_id,
        "current_area": traveler_state.current_area,
        "entity": copy.deepcopy(traveler_state.entity_data),
    }
    if traveler_state.origin_area is not None:
        data["origin_area"] = traveler_state.origin_area
    if traveler_state.origin_entity_id is not None:
        data["origin_entity_id"] = traveler_state.origin_entity_id
    return data


def _load_traveler_state_mapping(raw_travelers: Any) -> dict[str, TravelerState]:
    """Parse the save file's traveler-state mapping."""
    if not isinstance(raw_travelers, dict):
        return {}
    travelers: dict[str, TravelerState] = {}
    for session_entity_id, raw_state in raw_travelers.items():
        traveler_state = _traveler_state_from_dict(raw_state, fallback_id=str(session_entity_id))
        if traveler_state is None:
            continue
        travelers[traveler_state.session_entity_id] = traveler_state
    return travelers


def _traveler_state_mapping_to_dict(
    travelers: dict[str, TravelerState],
) -> dict[str, Any]:
    """Serialize the save file's traveler-state mapping."""
    serialized: dict[str, Any] = {}
    for session_entity_id, traveler_state in travelers.items():
        serialized[str(session_entity_id)] = _traveler_state_to_dict(traveler_state)
    return serialized


def _area_state_mapping_to_dict(areas: dict[str, PersistentAreaState]) -> dict[str, Any]:
    """Serialize the save file's area-state mapping."""
    serialized: dict[str, Any] = {}
    for area_id, area_state in areas.items():
        area_data = _area_state_to_dict(area_state)
        if area_data:
            serialized[str(area_id)] = area_data
    return serialized


def _instantiate_saved_entity(
    entity_data: dict[str, Any],
    tile_size: int,
    *,
    project: ProjectContext,
) -> Entity:
    """Create an entity instance from saved serialized entity data."""
    from dungeon_engine.world.loader import instantiate_entity

    return instantiate_entity(
        copy.deepcopy(entity_data),
        tile_size,
        project=project,
        source_name="<saved entity>",
    )


def _serialize_saved_entity(
    entity: Entity,
    tile_size: int,
    *,
    project: ProjectContext,
) -> dict[str, Any]:
    """Serialize one runtime entity for save-state storage."""
    from dungeon_engine.world.serializer import serialize_entity_instance
    serialized = serialize_entity_instance(entity, tile_size, project=project)
    if entity.visuals:
        serialized["visuals"] = _serialize_persistent_visuals(entity)
    return serialized


def _capture_area_state(
    area: Area,
    authored_world: World,
    current_world: World,
    *,
    include_spawned_entities: bool,
    project: ProjectContext,
) -> PersistentAreaState | None:
    """Capture one area diff against authored data with configurable scope."""
    area_state = PersistentAreaState()

    variable_overrides = _capture_variable_overrides(
        authored_world.variables,
        current_world.variables,
    )
    if variable_overrides:
        area_state.variables = variable_overrides

    authored_entities = {
        entity.entity_id: entity
        for entity in authored_world.iter_area_entities(include_absent=True)
    }
    current_entities = {
        entity.entity_id: entity
        for entity in current_world.iter_area_entities(include_absent=True)
    }
    traveler_entity_ids = {
        entity_id
        for entity_id, entity in current_entities.items()
        if entity.session_entity_id is not None
    }
    for entity_id in traveler_entity_ids:
        authored_entities.pop(entity_id, None)
        current_entities.pop(entity_id, None)
    area_state.entities = _capture_entity_state_mapping(
        area,
        authored_entities,
        current_entities,
        include_spawned_entities=include_spawned_entities,
        project=project,
    )

    if not area_state.variables and not area_state.entities:
        return None
    return area_state


def _apply_entity_state_mapping(
    area: Area,
    world: World,
    entity_states: dict[str, PersistentEntityState],
    *,
    project: ProjectContext,
) -> None:
    """Apply one saved entity-state mapping onto the current world."""
    for entity_id, entity_state in entity_states.items():
        if entity_state.removed:
            world.remove_entity(entity_id)
            continue

        entity = world.get_entity(entity_id)
        if entity_state.spawned is not None:
            entity = _instantiate_saved_entity(
                entity_state.spawned,
                area.tile_size,
                project=project,
            )
            world.add_entity(entity)

        if entity is None:
            continue
        _apply_entity_overrides(area, entity, entity_state.overrides)


def _capture_entity_state_mapping(
    area: Area,
    authored_entities: dict[str, Entity],
    current_entities: dict[str, Entity],
    *,
    include_spawned_entities: bool,
    project: ProjectContext,
) -> dict[str, PersistentEntityState]:
    """Capture one entity-state diff mapping against a reference set."""
    entity_states: dict[str, PersistentEntityState] = {}

    for authored_entity in authored_entities.values():
        current_entity = current_entities.get(authored_entity.entity_id)
        if current_entity is None:
            entity_states[authored_entity.entity_id] = PersistentEntityState(removed=True)
            continue

        entity_overrides = _capture_entity_overrides(authored_entity, current_entity)
        if entity_overrides:
            entity_states[authored_entity.entity_id] = PersistentEntityState(
                overrides=entity_overrides,
            )

    if not include_spawned_entities:
        return entity_states

    for current_entity in current_entities.values():
        if current_entity.entity_id in authored_entities:
            continue
        entity_states[current_entity.entity_id] = PersistentEntityState(
            spawned=_serialize_saved_entity(
                current_entity,
                area.tile_size,
                project=project,
            ),
        )

    return entity_states


def _apply_entity_overrides(area: Area, entity: Entity, overrides: dict[str, Any]) -> None:
    """Apply persistent override fields to one entity instance."""
    grid_position_changed = False
    pixel_position_changed = False
    for key, value in overrides.items():
        if key == "x":
            entity.grid_x = int(value)
            grid_position_changed = True
        elif key == "y":
            entity.grid_y = int(value)
            grid_position_changed = True
        elif key == "pixel_x":
            entity.pixel_x = float(value)
            pixel_position_changed = True
        elif key == "pixel_y":
            entity.pixel_y = float(value)
            pixel_position_changed = True
        elif key == "present":
            entity.present = bool(value)
        elif key == "visible":
            entity.visible = bool(value)
        elif key == "events_enabled":
            entity.events_enabled = bool(value)
        elif key == "layer":
            entity.layer = int(value)
        elif key == "stack_order":
            entity.stack_order = int(value)
        elif key == "color":
            entity.color = (int(value[0]), int(value[1]), int(value[2]))
        elif key == "input_map":
            entity.input_map = {
                str(action): str(event_name)
                for action, event_name in dict(value).items()
            }
        elif key == "variables":
            entity.variables.update(copy.deepcopy(value))
        elif key == "event_states":
            for event_id, event_enabled in value.items():
                event = entity.get_event(str(event_id))
                if event is None:
                    continue
                event.enabled = bool(event_enabled)
        elif key == "visuals":
            entity.visuals = _deserialize_persistent_visuals(value)
        else:
            raise ValueError(f"Unknown persistent entity override field '{key}'.")

    if grid_position_changed and not pixel_position_changed:
        entity.sync_pixel_position(area.tile_size)


def _serialize_persistent_visuals(entity: Entity) -> list[dict[str, Any]]:
    """Serialize full runtime visual state for saves and persistent diffs."""
    serialized: list[dict[str, Any]] = []
    for visual in entity.visuals:
        serialized.append(
            {
                "id": visual.visual_id,
                "path": visual.path,
                "frame_width": visual.frame_width,
                "frame_height": visual.frame_height,
                "frames": list(visual.frames),
                "animation_fps": visual.animation_fps,
                "animate_when_moving": visual.animate_when_moving,
                "current_frame": visual.current_frame,
                "flip_x": visual.flip_x,
                "visible": visual.visible,
                "tint": list(visual.tint),
                "offset_x": visual.offset_x,
                "offset_y": visual.offset_y,
                "draw_order": visual.draw_order,
            }
        )
    return serialized


def _deserialize_persistent_visuals(raw_visuals: Any) -> list[EntityVisual]:
    """Parse one saved visual-state list back into runtime visuals."""
    if not isinstance(raw_visuals, list):
        raise ValueError("Persistent 'visuals' override must be a JSON array.")
    visuals: list[EntityVisual] = []
    for index, raw_visual in enumerate(raw_visuals):
        if not isinstance(raw_visual, dict):
            raise ValueError(f"Persistent visuals[{index}] must be a JSON object.")
        frames = [int(frame) for frame in raw_visual.get("frames", [0])]
        if not frames:
            frames = [0]
        visuals.append(
            EntityVisual(
                visual_id=str(raw_visual.get("id", "")).strip() or f"visual_{index}",
                path=str(raw_visual.get("path", "")),
                frame_width=int(raw_visual.get("frame_width", 16)),
                frame_height=int(raw_visual.get("frame_height", 16)),
                frames=frames,
                animation_fps=float(raw_visual.get("animation_fps", 0.0)),
                animate_when_moving=bool(raw_visual.get("animate_when_moving", False)),
                current_frame=int(raw_visual.get("current_frame", frames[0])),
                flip_x=bool(raw_visual.get("flip_x", False)),
                visible=bool(raw_visual.get("visible", True)),
                tint=(
                    int(raw_visual.get("tint", [255, 255, 255])[0]),
                    int(raw_visual.get("tint", [255, 255, 255])[1]),
                    int(raw_visual.get("tint", [255, 255, 255])[2]),
                ),
                offset_x=float(raw_visual.get("offset_x", 0.0)),
                offset_y=float(raw_visual.get("offset_y", 0.0)),
                draw_order=int(raw_visual.get("draw_order", index)),
            )
        )
    return visuals


def _capture_entity_overrides(authored_entity: Entity, current_entity: Entity) -> dict[str, Any]:
    """Return only the persistent fields that differ from authored defaults."""
    overrides: dict[str, Any] = {}

    if current_entity.grid_x != authored_entity.grid_x:
        overrides["x"] = current_entity.grid_x
    if current_entity.grid_y != authored_entity.grid_y:
        overrides["y"] = current_entity.grid_y
    if not math.isclose(current_entity.pixel_x, authored_entity.pixel_x, abs_tol=0.001):
        overrides["pixel_x"] = current_entity.pixel_x
    if not math.isclose(current_entity.pixel_y, authored_entity.pixel_y, abs_tol=0.001):
        overrides["pixel_y"] = current_entity.pixel_y
    if current_entity.present != authored_entity.present:
        overrides["present"] = current_entity.present
    if current_entity.visible != authored_entity.visible:
        overrides["visible"] = current_entity.visible
    if current_entity.events_enabled != authored_entity.events_enabled:
        overrides["events_enabled"] = current_entity.events_enabled
    if current_entity.layer != authored_entity.layer:
        overrides["layer"] = current_entity.layer
    if current_entity.stack_order != authored_entity.stack_order:
        overrides["stack_order"] = current_entity.stack_order
    if current_entity.color != authored_entity.color:
        overrides["color"] = list(current_entity.color)
    if current_entity.input_map != authored_entity.input_map:
        overrides["input_map"] = copy.deepcopy(current_entity.input_map)
    if _serialize_persistent_visuals(current_entity) != _serialize_persistent_visuals(authored_entity):
        overrides["visuals"] = _serialize_persistent_visuals(current_entity)

    variable_overrides = _capture_variable_overrides(
        authored_entity.variables,
        current_entity.variables,
    )
    if variable_overrides:
        overrides["variables"] = variable_overrides

    event_state_overrides = _capture_event_state_overrides(authored_entity, current_entity)
    if event_state_overrides:
        overrides["event_states"] = event_state_overrides

    return overrides


def _capture_variable_overrides(
    authored_variables: dict[str, Any],
    current_variables: dict[str, Any],
) -> dict[str, Any]:
    """Capture changed top-level variable keys as persistent overrides."""
    overrides: dict[str, Any] = {}
    for key, value in current_variables.items():
        if authored_variables.get(key) != value:
            overrides[key] = copy.deepcopy(value)
    return overrides


def _capture_event_state_overrides(
    authored_entity: Entity,
    current_entity: Entity,
) -> dict[str, bool]:
    """Capture event enabled-state changes as persistent overrides."""
    overrides: dict[str, bool] = {}
    event_ids = set(authored_entity.events.keys()) | set(current_entity.events.keys())
    for event_id in event_ids:
        authored_event = authored_entity.get_event(event_id)
        current_event = current_entity.get_event(event_id)
        if authored_event is None or current_event is None:
            continue
        if current_event.enabled != authored_event.enabled:
            overrides[event_id] = current_event.enabled
    return overrides

