"""Persistent save-state helpers layered on top of authored room data.

This module keeps persistent room state as compact per-area/per-entity overrides
instead of full duplicated room snapshots. Authored room JSON remains the source
of truth; save data records only playthrough-specific differences.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from puzzle_dungeon.world.area import Area
from puzzle_dungeon.world.entity import Entity
from puzzle_dungeon.world.world import World


SAVE_DATA_VERSION = 1


@dataclass(slots=True)
class PersistentEntityState:
    """Persistent changes for a single authored entity instance."""

    removed: bool = False
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
    areas: dict[str, PersistentAreaState] = field(default_factory=dict)


@dataclass(slots=True)
class ResetRequest:
    """A request to reset transient or persistent room state."""

    kind: str
    apply: str = "immediate"
    include_tags: tuple[str, ...] = ()
    exclude_tags: tuple[str, ...] = ()


class PersistenceRuntime:
    """Manage live persistent save data plus deferred reset requests."""

    def __init__(self, save_path: Path) -> None:
        self.save_path = save_path
        self.save_data = load_save_data(save_path)
        self.current_area_id: str = ""
        self.dirty = False
        self._pending_immediate_resets: list[ResetRequest] = []
        self._pending_reentry_resets: dict[str, list[ResetRequest]] = {}

    def bind_area(self, area_id: str) -> None:
        """Set the currently active area id for mutation commands."""
        self.current_area_id = area_id

    def flush(self) -> None:
        """Write the current save data to disk when it changed."""
        if not self.dirty:
            return
        save_save_data(self.save_path, self.save_data)
        self.dirty = False

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

    def set_entity_field(self, entity_id: str, field_name: str, value: Any) -> None:
        """Persist a top-level entity field override."""
        entity_state = self._ensure_entity_state(entity_id)
        entity_state.removed = False
        entity_state.overrides[field_name] = copy.deepcopy(value)
        self.dirty = True

    def set_entity_variable(self, entity_id: str, name: str, value: Any) -> None:
        """Persist an entity variable override."""
        entity_state = self._ensure_entity_state(entity_id)
        entity_state.removed = False
        variables = entity_state.overrides.setdefault("variables", {})
        variables[name] = copy.deepcopy(value)
        self.dirty = True

    def remove_entity(self, entity_id: str) -> None:
        """Mark an entity as removed in persistent state."""
        entity_state = self._ensure_entity_state(entity_id)
        entity_state.removed = True
        entity_state.overrides.clear()
        self.dirty = True

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
    areas: dict[str, PersistentAreaState] = {}
    for area_id, area_data in raw_data.get("areas", {}).items():
        entities: dict[str, PersistentEntityState] = {}
        for entity_id, entity_data in area_data.get("entities", {}).items():
            entity_overrides = copy.deepcopy(entity_data)
            removed = bool(entity_overrides.pop("removed", False))
            entities[str(entity_id)] = PersistentEntityState(
                removed=removed,
                overrides=entity_overrides,
            )
        areas[str(area_id)] = PersistentAreaState(
            variables=copy.deepcopy(area_data.get("variables", {})),
            entities=entities,
        )

    return SaveData(version=version, globals=globals_data, areas=areas)


def save_data_to_dict(save_data: SaveData) -> dict[str, Any]:
    """Convert structured save data into JSON-serializable dictionaries."""
    areas: dict[str, Any] = {}
    for area_id, area_state in save_data.areas.items():
        area_data: dict[str, Any] = {}
        if area_state.variables:
            area_data["variables"] = copy.deepcopy(area_state.variables)
        if area_state.entities:
            area_data["entities"] = {
                entity_id: _persistent_entity_state_to_dict(entity_state)
                for entity_id, entity_state in area_state.entities.items()
            }
        if area_data:
            areas[area_id] = area_data

    return {
        "version": save_data.version,
        "globals": copy.deepcopy(save_data.globals),
        "areas": areas,
    }


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
    for entity in authored_world.iter_entities():
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
        if entity is None:
            continue
        _apply_entity_overrides(area, entity, entity_state.overrides)


def capture_persistent_area_state(
    area: Area,
    authored_world: World,
    current_world: World,
) -> PersistentAreaState | None:
    """Capture persistent overrides by comparing current runtime state to authored defaults."""
    _ = area
    area_state = PersistentAreaState()

    variable_overrides = _capture_variable_overrides(
        authored_world.variables,
        current_world.variables,
    )
    if variable_overrides:
        area_state.variables = variable_overrides

    for authored_entity in authored_world.iter_entities():
        if authored_entity.entity_id == authored_world.player_id:
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

    if not area_state.variables and not area_state.entities:
        return None
    return area_state


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
    if entity_state.removed:
        data["removed"] = True
    return data


def _apply_entity_overrides(area: Area, entity: Entity, overrides: dict[str, Any]) -> None:
    """Apply persistent override fields to one entity instance."""
    position_changed = False
    for key, value in overrides.items():
        if key == "x":
            entity.grid_x = int(value)
            position_changed = True
        elif key == "y":
            entity.grid_y = int(value)
            position_changed = True
        elif key == "facing":
            entity.facing = str(value)
        elif key == "solid":
            entity.solid = bool(value)
        elif key == "pushable":
            entity.pushable = bool(value)
        elif key == "enabled":
            entity.enabled = bool(value)
        elif key == "visible":
            entity.visible = bool(value)
        elif key == "layer":
            entity.layer = int(value)
        elif key == "stack_order":
            entity.stack_order = int(value)
        elif key == "color":
            entity.color = (int(value[0]), int(value[1]), int(value[2]))
        elif key == "variables":
            entity.variables.update(copy.deepcopy(value))
        elif key == "interact_commands":
            entity.interact_commands = copy.deepcopy(value)
        elif key == "sprite":
            _apply_sprite_override(entity, value)
        else:
            raise ValueError(f"Unknown persistent entity override field '{key}'.")

    if position_changed:
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
    if current_entity.facing != authored_entity.facing:
        overrides["facing"] = current_entity.facing
    if current_entity.solid != authored_entity.solid:
        overrides["solid"] = current_entity.solid
    if current_entity.pushable != authored_entity.pushable:
        overrides["pushable"] = current_entity.pushable
    if current_entity.enabled != authored_entity.enabled:
        overrides["enabled"] = current_entity.enabled
    if current_entity.visible != authored_entity.visible:
        overrides["visible"] = current_entity.visible
    if current_entity.layer != authored_entity.layer:
        overrides["layer"] = current_entity.layer
    if current_entity.stack_order != authored_entity.stack_order:
        overrides["stack_order"] = current_entity.stack_order
    if current_entity.color != authored_entity.color:
        overrides["color"] = list(current_entity.color)

    variable_overrides = _capture_variable_overrides(
        authored_entity.variables,
        current_entity.variables,
    )
    if variable_overrides:
        overrides["variables"] = variable_overrides

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
