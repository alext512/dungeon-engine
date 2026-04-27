"""Persistent save-data models and JSON codec helpers."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SAVE_DATA_VERSION = 9


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

    current_area: str
    entity_data: dict[str, Any]
    origin_area: str | None = None


@dataclass(slots=True)
class SaveData:
    """Serializable save-slot data for persistent gameplay state."""

    version: int = SAVE_DATA_VERSION
    globals: dict[str, Any] = field(default_factory=dict)
    global_entities: dict[str, PersistentEntityState] = field(default_factory=dict)
    current_area: str = ""
    current_input_routes: dict[str, dict[str, str]] | None = None
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
    entity_ids: tuple[str, ...] = ()
    include_tags: tuple[str, ...] = ()
    exclude_tags: tuple[str, ...] = ()


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
    globals_data = copy.deepcopy(raw_data.get("globals", {}))
    current_area = str(raw_data.get("current_area", "")).strip()
    raw_current_input_routes = raw_data.get("current_input_routes")
    raw_current_camera = raw_data.get("current_camera")
    areas = _load_area_state_mapping(raw_data.get("areas", {}))
    travelers = _load_traveler_state_mapping(raw_data.get("travelers", {}))
    global_entities = _load_entity_state_mapping(
        globals_data.get("entities", {}) if isinstance(globals_data, dict) else {}
    )
    current_global_entities = _load_entity_state_mapping(raw_data.get("current_global_entities", {}))
    if isinstance(globals_data, dict):
        globals_data.pop("entities", None)
    current_input_routes = _load_input_routes(raw_current_input_routes)
    current_camera = copy.deepcopy(raw_current_camera) if isinstance(raw_current_camera, dict) else None

    return SaveData(
        version=version,
        globals=globals_data if isinstance(globals_data, dict) else {},
        global_entities=global_entities,
        current_area=current_area,
        current_input_routes=current_input_routes,
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
        "globals": globals_payload,
        "current_area": str(save_data.current_area),
        "areas": _area_state_mapping_to_dict(save_data.areas),
    }
    if save_data.current_input_routes:
        data["current_input_routes"] = _input_routes_to_dict(save_data.current_input_routes)
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


def _load_input_routes(raw_routes: Any) -> dict[str, dict[str, str]] | None:
    if not isinstance(raw_routes, dict):
        return None
    routes: dict[str, dict[str, str]] = {}
    for raw_action, raw_route in raw_routes.items():
        action = str(raw_action).strip()
        if not action or not isinstance(raw_route, dict):
            continue
        entity_id = str(raw_route.get("entity_id", "")).strip()
        command_id = str(raw_route.get("command_id", "")).strip()
        if bool(entity_id) != bool(command_id):
            continue
        routes[action] = {
            "entity_id": entity_id,
            "command_id": command_id,
        }
    return routes or None


def _input_routes_to_dict(routes: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    return {
        str(action): {
            "entity_id": str(route.get("entity_id", "")),
            "command_id": str(route.get("command_id", "")),
        }
        for action, route in routes.items()
    }


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
    entity_data = copy.deepcopy(raw_entity_data)
    entity_id = str(entity_data.get("id", fallback_id)).strip() or fallback_id
    entity_data["id"] = entity_id
    origin_area = raw_state.get("origin_area")
    normalized_origin_area = (
        str(origin_area).strip()
        if origin_area is not None
        else ""
    )
    return TravelerState(
        current_area=current_area,
        entity_data=entity_data,
        origin_area=normalized_origin_area or None,
    )


def _traveler_state_to_dict(traveler_state: TravelerState) -> dict[str, Any]:
    """Convert one traveler state into a JSON-friendly dict."""
    data: dict[str, Any] = {
        "current_area": traveler_state.current_area,
        "entity": copy.deepcopy(traveler_state.entity_data),
    }
    if traveler_state.origin_area is not None:
        data["origin_area"] = traveler_state.origin_area
    return data


def _load_traveler_state_mapping(raw_travelers: Any) -> dict[str, TravelerState]:
    """Parse the save file's traveler-state mapping."""
    if not isinstance(raw_travelers, dict):
        return {}
    travelers: dict[str, TravelerState] = {}
    for fallback_id, raw_state in raw_travelers.items():
        traveler_state = _traveler_state_from_dict(raw_state, fallback_id=str(fallback_id))
        if traveler_state is None:
            continue
        entity_id = str(traveler_state.entity_data.get("id", fallback_id)).strip() or str(fallback_id)
        travelers[entity_id] = traveler_state
    return travelers


def _traveler_state_mapping_to_dict(
    travelers: dict[str, TravelerState],
) -> dict[str, Any]:
    """Serialize the save file's traveler-state mapping."""
    serialized: dict[str, Any] = {}
    for entity_id, traveler_state in travelers.items():
        serialized[str(entity_id)] = _traveler_state_to_dict(traveler_state)
    return serialized


def _area_state_mapping_to_dict(areas: dict[str, PersistentAreaState]) -> dict[str, Any]:
    """Serialize the save file's area-state mapping."""
    serialized: dict[str, Any] = {}
    for area_id, area_state in areas.items():
        area_data = _area_state_to_dict(area_state)
        if area_data:
            serialized[str(area_id)] = area_data
    return serialized
