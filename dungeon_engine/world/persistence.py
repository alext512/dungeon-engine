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

from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity
from dungeon_engine.world.world import World


SAVE_DATA_VERSION = 3


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
class SaveData:
    """Serializable save-slot data for persistent gameplay state."""

    version: int = SAVE_DATA_VERSION
    globals: dict[str, Any] = field(default_factory=dict)
    current_area: str = ""
    active_entity: str = ""
    areas: dict[str, PersistentAreaState] = field(default_factory=dict)
    current_area_state: PersistentAreaState | None = None


@dataclass(slots=True)
class ResetRequest:
    """A request to reset transient or persistent room state."""

    kind: str
    apply: str = "immediate"
    include_tags: tuple[str, ...] = ()
    exclude_tags: tuple[str, ...] = ()


class PersistenceRuntime:
    """Manage live persistent save data plus deferred reset requests."""

    def __init__(self, save_path: Path | None = None, *, load_existing: bool = False) -> None:
        self.save_path = save_path
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

    def set_world_variable(self, name: str, value: Any) -> None:
        """Persist a world-level variable override for the current area."""
        area_state = self._ensure_current_area_state()
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
        if not self._is_authored_entity(entity_id):
            self._record_spawned_entity(entity=entity, tile_size=tile_size)
            return
        entity_state = self._ensure_entity_state(entity_id)
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
        if not self._is_authored_entity(entity_id):
            self._record_spawned_entity(entity=entity, tile_size=tile_size)
            return
        entity_state = self._ensure_entity_state(entity_id)
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
        if not self._is_authored_entity(entity_id):
            self._record_spawned_entity(entity=entity, tile_size=tile_size)
            return
        entity_state = self._ensure_entity_state(entity_id)
        entity_state.removed = False
        entity_state.spawned = None
        event_states = entity_state.overrides.setdefault("event_states", {})
        event_states[str(event_id)] = bool(enabled)
        self.dirty = True

    def remove_entity(self, entity_id: str) -> None:
        """Mark an entity as removed in persistent state."""
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

    def _ensure_current_area_state(self) -> PersistentAreaState:
        """Return the current area state, creating it when missing."""
        if not self.current_area_id:
            raise ValueError("No current area is bound for persistence updates.")
        area_state = self.save_data.areas.get(self.current_area_id)
        if area_state is None:
            area_state = PersistentAreaState()
            self.save_data.areas[self.current_area_id] = area_state
        return area_state

    def _ensure_entity_state(self, entity_id: str) -> PersistentEntityState:
        """Return the current area's persistent state for one entity."""
        area_state = self._ensure_current_area_state()
        entity_state = area_state.entities.get(entity_id)
        if entity_state is None:
            entity_state = PersistentEntityState()
            area_state.entities[entity_id] = entity_state
        return entity_state

    def _record_spawned_entity(self, *, entity: Entity | None, tile_size: int | None) -> None:
        """Store the full serialized state for one spawned entity."""
        if entity is None:
            raise ValueError("Persisting a spawned entity requires the runtime entity.")
        if tile_size is None:
            raise ValueError("Persisting a spawned entity requires the active area tile size.")
        entity_state = self._ensure_entity_state(entity.entity_id)
        entity_state.removed = False
        entity_state.spawned = _serialize_saved_entity(entity, tile_size)
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
    legacy_session_data = copy.deepcopy(raw_data.get("session", {}))
    current_area = str(
        raw_data.get("current_area", legacy_session_data.get("current_area_path", ""))
    ).strip()
    active_entity = str(
        raw_data.get("active_entity", legacy_session_data.get("active_entity_id", ""))
    ).strip()
    areas = _load_area_state_mapping(raw_data.get("areas", {}))

    return SaveData(
        version=version,
        globals=globals_data if isinstance(globals_data, dict) else {},
        current_area=current_area,
        active_entity=active_entity,
        areas=areas,
        current_area_state=_area_state_from_dict(raw_data.get("current_area_state")),
    )


def save_data_to_dict(save_data: SaveData) -> dict[str, Any]:
    """Convert structured save data into JSON-serializable dictionaries."""
    data = {
        "version": save_data.version,
        "globals": copy.deepcopy(save_data.globals),
        "current_area": str(save_data.current_area),
        "active_entity": str(save_data.active_entity),
        "areas": _area_state_mapping_to_dict(save_data.areas),
    }
    if save_data.current_area_state is not None:
        data["current_area_state"] = _area_state_to_dict(save_data.current_area_state)
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
    for entity in authored_world.iter_entities(include_absent=True):
        if entity.entity_id == authored_world.player_id:
            continue

        entity_tags = set(entity.tags)
        if include and not (entity_tags & include):
            continue
        if exclude and (entity_tags & exclude):
            continue
        matched_ids.add(entity.entity_id)
    return matched_ids


def apply_persistent_area_state(area: Area, world: World, area_state: PersistentAreaState) -> None:
    """Layer persistent overrides on top of a freshly loaded authored room."""
    if area_state.variables:
        world.variables.update(copy.deepcopy(area_state.variables))

    for entity_id, entity_state in area_state.entities.items():
        if entity_state.removed:
            world.remove_entity(entity_id)
            continue

        entity = world.get_entity(entity_id)
        if entity_state.spawned is not None:
            entity = _instantiate_saved_entity(entity_state.spawned, area.tile_size)
            world.add_entity(entity)

        if entity is None:
            continue
        _apply_entity_overrides(area, entity, entity_state.overrides)


def capture_current_area_state(
    area: Area,
    base_world: World,
    current_world: World,
) -> PersistentAreaState | None:
    """Capture the exact saved diff for the current area over its persistent base."""
    return _capture_area_state(
        area,
        base_world,
        current_world,
        include_player=True,
        include_spawned_entities=True,
    )


def capture_persistent_area_state(
    area: Area,
    authored_world: World,
    current_world: World,
) -> PersistentAreaState | None:
    """Capture persistent overrides by comparing current runtime state to authored defaults."""
    return _capture_area_state(
        area,
        authored_world,
        current_world,
        include_player=False,
        include_spawned_entities=False,
    )


def update_save_data_for_area(
    save_data: SaveData,
    area: Area,
    authored_world: World,
    current_world: World,
) -> None:
    """Refresh one area's persistent save entry from the current runtime state."""
    area_state = capture_persistent_area_state(area, authored_world, current_world)
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

    entities: dict[str, PersistentEntityState] = {}
    raw_entities = raw_state.get("entities", {})
    if isinstance(raw_entities, dict):
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

    variables = raw_state.get("variables", {})
    return PersistentAreaState(
        variables=copy.deepcopy(variables) if isinstance(variables, dict) else {},
        entities=entities,
    )


def _area_state_to_dict(area_state: PersistentAreaState) -> dict[str, Any]:
    """Convert one saved area state into a JSON-friendly dict."""
    data: dict[str, Any] = {}
    if area_state.variables:
        data["variables"] = copy.deepcopy(area_state.variables)
    if area_state.entities:
        data["entities"] = {
            entity_id: _persistent_entity_state_to_dict(entity_state)
            for entity_id, entity_state in area_state.entities.items()
        }
    return data


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


def _area_state_mapping_to_dict(areas: dict[str, PersistentAreaState]) -> dict[str, Any]:
    """Serialize the save file's area-state mapping."""
    serialized: dict[str, Any] = {}
    for area_id, area_state in areas.items():
        area_data = _area_state_to_dict(area_state)
        if area_data:
            serialized[str(area_id)] = area_data
    return serialized


def _instantiate_saved_entity(entity_data: dict[str, Any], tile_size: int) -> Entity:
    """Create an entity instance from saved serialized entity data."""
    from dungeon_engine.world.loader import instantiate_entity

    return instantiate_entity(copy.deepcopy(entity_data), tile_size)


def _serialize_saved_entity(entity: Entity, tile_size: int) -> dict[str, Any]:
    """Serialize one runtime entity for save-state storage."""
    from dungeon_engine.world.serializer import serialize_entity_instance

    return serialize_entity_instance(entity, tile_size)


def _capture_area_state(
    area: Area,
    authored_world: World,
    current_world: World,
    *,
    include_player: bool,
    include_spawned_entities: bool,
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
        for entity in authored_world.iter_entities(include_absent=True)
    }
    for authored_entity in authored_entities.values():
        if not include_player and authored_entity.entity_id == authored_world.player_id:
            continue

        current_entity = current_world.get_entity(authored_entity.entity_id)
        if current_entity is None:
            area_state.entities[authored_entity.entity_id] = PersistentEntityState(removed=True)
            continue

        entity_overrides = _capture_entity_overrides(authored_entity, current_entity)
        if entity_overrides:
            area_state.entities[authored_entity.entity_id] = PersistentEntityState(
                overrides=entity_overrides,
            )

    if include_spawned_entities:
        for current_entity in current_world.iter_entities(include_absent=True):
            if not include_player and current_entity.entity_id == current_world.player_id:
                continue
            if current_entity.entity_id in authored_entities:
                continue
            area_state.entities[current_entity.entity_id] = PersistentEntityState(
                spawned=_serialize_saved_entity(current_entity, area.tile_size),
            )

    if not area_state.variables and not area_state.entities:
        return None
    return area_state


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
        elif key == "facing":
            entity.facing = str(value)
        elif key == "solid":
            entity.solid = bool(value)
        elif key == "pushable":
            entity.pushable = bool(value)
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
        elif key == "sprite_flip_x":
            entity.sprite_flip_x = bool(value)
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
        elif key == "interact_commands":
            entity.interact_commands = copy.deepcopy(value)
        elif key == "sprite":
            _apply_sprite_override(entity, value)
        else:
            raise ValueError(f"Unknown persistent entity override field '{key}'.")

    if grid_position_changed and not pixel_position_changed:
        entity.sync_pixel_position(area.tile_size)


def _apply_sprite_override(entity: Entity, sprite_data: dict[str, Any]) -> None:
    """Apply a sprite override dict to an entity."""
    entity.sprite_path = str(sprite_data.get("path", ""))
    entity.sprite_frame_width = int(sprite_data.get("frame_width", entity.sprite_frame_width))
    entity.sprite_frame_height = int(sprite_data.get("frame_height", entity.sprite_frame_height))
    frames = sprite_data.get("frames")
    if frames is not None:
        entity.animation_frames = [int(frame) for frame in frames]
        if entity.animation_frames:
            entity.current_frame = int(entity.animation_frames[0])
    entity.animation_fps = float(sprite_data.get("animation_fps", entity.animation_fps))
    entity.animate_when_moving = bool(
        sprite_data.get("animate_when_moving", entity.animate_when_moving)
    )


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
    if current_entity.facing != authored_entity.facing:
        overrides["facing"] = current_entity.facing
    if current_entity.solid != authored_entity.solid:
        overrides["solid"] = current_entity.solid
    if current_entity.pushable != authored_entity.pushable:
        overrides["pushable"] = current_entity.pushable
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
    if current_entity.sprite_flip_x != authored_entity.sprite_flip_x:
        overrides["sprite_flip_x"] = current_entity.sprite_flip_x
    if current_entity.input_map != authored_entity.input_map:
        overrides["input_map"] = copy.deepcopy(current_entity.input_map)

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

