"""Persistent state apply/capture helpers layered over authored world data."""

from __future__ import annotations

import copy
import math
from typing import Any

from dungeon_engine.inventory import clone_inventory_state, serialize_inventory_state
from dungeon_engine.project_context import ProjectContext
from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity, EntityVisual, VisualAnimationClip
from dungeon_engine.world.persistence_data import (
    PersistentAreaState,
    PersistentEntityState,
    SaveData,
)
from dungeon_engine.world.world import World


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
    skip_entity_ids: set[str] | None = None,
) -> None:
    """Suppress away travelers' origin placeholders and install travelers that belong here."""
    skipped_ids = set(skip_entity_ids or set())
    for entity_id, traveler_state in save_data.travelers.items():
        if traveler_state.origin_area == area.area_id:
            if traveler_state.current_area != area.area_id:
                world.remove_entity(entity_id)

        if traveler_state.current_area != area.area_id:
            continue
        if entity_id in skipped_ids:
            continue
        entity = _instantiate_saved_entity(
            traveler_state.entity_data,
            area.tile_size,
            project=project,
        )
        entity.origin_area_id = traveler_state.origin_area
        world.replace_entity(entity)


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


def _instantiate_saved_entity(
    entity_data: dict[str, Any],
    tile_size: int,
    *,
    project: ProjectContext,
) -> Entity:
    """Create an entity instance from saved serialized entity data."""
    from dungeon_engine.world.loader_entities import instantiate_entity

    return instantiate_entity(
        copy.deepcopy(entity_data),
        tile_size,
        project=project,
        source_name="<saved entity>",
        allow_missing_inventory_items=True,
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
        if entity.origin_area_id is not None
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
        if key == "grid_x":
            entity.grid_x = int(value)
            grid_position_changed = True
        elif key == "grid_y":
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
        elif key == "facing":
            entity.set_facing_value(str(value))  # type: ignore[arg-type]
        elif key == "solid":
            entity.set_solid_value(bool(value))
        elif key == "pushable":
            entity.set_pushable_value(bool(value))
        elif key == "weight":
            entity.weight = int(value)
        elif key == "push_strength":
            entity.push_strength = int(value)
        elif key == "collision_push_strength":
            entity.collision_push_strength = int(value)
        elif key == "interactable":
            entity.interactable = bool(value)
        elif key == "interaction_priority":
            entity.interaction_priority = int(value)
        elif key == "entity_commands_enabled":
            entity.entity_commands_enabled = bool(value)
        elif key == "inventory":
            entity.inventory = clone_inventory_state(
                _deserialize_inventory_state(value)
            )
        elif key == "render_order":
            entity.render_order = int(value)
        elif key == "y_sort":
            entity.y_sort = bool(value)
        elif key == "sort_y_offset":
            entity.sort_y_offset = float(value)
        elif key == "stack_order":
            entity.stack_order = int(value)
        elif key == "color":
            entity.color = (int(value[0]), int(value[1]), int(value[2]))
        elif key == "variables":
            entity.variables.update(copy.deepcopy(value))
        elif key == "entity_command_states":
            for command_id, command_enabled in value.items():
                entity_command = entity.get_entity_command(str(command_id))
                if entity_command is None:
                    continue
                entity_command.enabled = bool(command_enabled)
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
        serialized_visual = {
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
        if visual.default_animation is not None:
            serialized_visual["default_animation"] = visual.default_animation
        if visual.default_animation_by_facing:
            serialized_visual["default_animation_by_facing"] = {
                str(facing): str(animation_id)
                for facing, animation_id in sorted(visual.default_animation_by_facing.items())
            }
        if visual.animations:
            serialized_visual["animations"] = _serialize_persistent_visual_animations(visual)
        serialized.append(serialized_visual)
    return serialized


def _serialize_persistent_visual_animations(visual: EntityVisual) -> dict[str, dict[str, Any]]:
    """Serialize named animation clips for persistent visual snapshots."""
    serialized: dict[str, dict[str, Any]] = {}
    for animation_id, clip in visual.animations.items():
        serialized_clip: dict[str, Any] = {
            "frames": list(clip.frames),
            "preserve_phase": bool(clip.preserve_phase),
            "phase_index": int(clip.phase_index),
        }
        if clip.flip_x is not None:
            serialized_clip["flip_x"] = bool(clip.flip_x)
        serialized[str(animation_id)] = serialized_clip
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
        animations = _deserialize_persistent_visual_animations(
            raw_visual.get("animations", {}),
        )
        default_animation = raw_visual.get("default_animation")
        if default_animation is not None:
            default_animation = str(default_animation).strip() or None
        default_animation_by_facing = {
            str(raw_facing).strip().lower(): str(raw_animation_id).strip()
            for raw_facing, raw_animation_id in dict(
                raw_visual.get("default_animation_by_facing", {})
            ).items()
            if str(raw_facing).strip() and str(raw_animation_id).strip()
        }
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
                default_animation=default_animation,
                default_animation_by_facing=default_animation_by_facing,
                animations=animations,
            )
        )
    return visuals


def _deserialize_persistent_visual_animations(raw_animations: Any) -> dict[str, VisualAnimationClip]:
    """Parse saved visual animation clips."""
    if raw_animations is None:
        return {}
    if not isinstance(raw_animations, dict):
        raise ValueError("Persistent visual animations override must be a JSON object.")
    animations: dict[str, VisualAnimationClip] = {}
    for raw_animation_id, raw_clip in raw_animations.items():
        if not isinstance(raw_clip, dict):
            continue
        frames = [int(frame) for frame in raw_clip.get("frames", [])]
        if not frames:
            continue
        raw_flip_x = raw_clip.get("flip_x")
        animations[str(raw_animation_id)] = VisualAnimationClip(
            frames=frames,
            flip_x=None if raw_flip_x is None else bool(raw_flip_x),
            preserve_phase=bool(raw_clip.get("preserve_phase", False)),
            phase_index=int(raw_clip.get("phase_index", 0)),
        )
    return animations


def _deserialize_inventory_state(raw_inventory: Any) -> Any:
    """Parse one persisted inventory payload back into a runtime inventory state."""
    if raw_inventory is None:
        return None
    if not isinstance(raw_inventory, dict):
        raise ValueError("Persistent 'inventory' override must be a JSON object or null.")
    max_stacks = int(raw_inventory.get("max_stacks", 0))
    if max_stacks < 0:
        raise ValueError("Persistent 'inventory.max_stacks' must be zero or positive.")
    raw_stacks = raw_inventory.get("stacks", [])
    if raw_stacks is None:
        raw_stacks = []
    if not isinstance(raw_stacks, list):
        raise ValueError("Persistent 'inventory.stacks' override must be a JSON array.")

    from dungeon_engine.world.entity import InventoryStack, InventoryState

    stacks: list[InventoryStack] = []
    for index, raw_stack in enumerate(raw_stacks):
        if not isinstance(raw_stack, dict):
            raise ValueError(f"Persistent inventory.stacks[{index}] must be a JSON object.")
        item_id = str(raw_stack.get("item_id", "")).strip()
        if not item_id:
            raise ValueError(
                f"Persistent inventory.stacks[{index}] requires a non-empty item_id."
            )
        quantity = int(raw_stack.get("quantity", 0))
        if quantity <= 0:
            raise ValueError(
                f"Persistent inventory.stacks[{index}] quantity must be positive."
            )
        stacks.append(InventoryStack(item_id=item_id, quantity=quantity))
    if len(stacks) > max_stacks:
        raise ValueError(
            f"Persistent inventory uses {len(stacks)} stack(s) but max_stacks is {max_stacks}."
        )
    return InventoryState(max_stacks=max_stacks, stacks=stacks)


def _capture_entity_overrides(authored_entity: Entity, current_entity: Entity) -> dict[str, Any]:
    """Return only the persistent fields that differ from authored defaults."""
    overrides: dict[str, Any] = {}

    if current_entity.grid_x != authored_entity.grid_x:
        overrides["grid_x"] = current_entity.grid_x
    if current_entity.grid_y != authored_entity.grid_y:
        overrides["grid_y"] = current_entity.grid_y
    if not math.isclose(current_entity.pixel_x, authored_entity.pixel_x, abs_tol=0.001):
        overrides["pixel_x"] = current_entity.pixel_x
    if not math.isclose(current_entity.pixel_y, authored_entity.pixel_y, abs_tol=0.001):
        overrides["pixel_y"] = current_entity.pixel_y
    if current_entity.present != authored_entity.present:
        overrides["present"] = current_entity.present
    if current_entity.visible != authored_entity.visible:
        overrides["visible"] = current_entity.visible
    if current_entity.get_effective_facing() != authored_entity.get_effective_facing():
        overrides["facing"] = current_entity.get_effective_facing()
    if current_entity.is_effectively_solid() != authored_entity.is_effectively_solid():
        overrides["solid"] = current_entity.is_effectively_solid()
    if current_entity.is_effectively_pushable() != authored_entity.is_effectively_pushable():
        overrides["pushable"] = current_entity.is_effectively_pushable()
    if int(current_entity.weight) != int(authored_entity.weight):
        overrides["weight"] = int(current_entity.weight)
    if int(current_entity.push_strength) != int(authored_entity.push_strength):
        overrides["push_strength"] = int(current_entity.push_strength)
    if int(current_entity.collision_push_strength) != int(authored_entity.collision_push_strength):
        overrides["collision_push_strength"] = int(current_entity.collision_push_strength)
    if current_entity.is_effectively_interactable() != authored_entity.is_effectively_interactable():
        overrides["interactable"] = current_entity.is_effectively_interactable()
    if int(current_entity.interaction_priority) != int(authored_entity.interaction_priority):
        overrides["interaction_priority"] = int(current_entity.interaction_priority)
    if current_entity.entity_commands_enabled != authored_entity.entity_commands_enabled:
        overrides["entity_commands_enabled"] = current_entity.entity_commands_enabled
    if serialize_inventory_state(current_entity.inventory) != serialize_inventory_state(authored_entity.inventory):
        overrides["inventory"] = serialize_inventory_state(current_entity.inventory)
    if current_entity.render_order != authored_entity.render_order:
        overrides["render_order"] = current_entity.render_order
    if current_entity.y_sort != authored_entity.y_sort:
        overrides["y_sort"] = current_entity.y_sort
    if not math.isclose(current_entity.sort_y_offset, authored_entity.sort_y_offset, abs_tol=0.001):
        overrides["sort_y_offset"] = current_entity.sort_y_offset
    if current_entity.stack_order != authored_entity.stack_order:
        overrides["stack_order"] = current_entity.stack_order
    if current_entity.color != authored_entity.color:
        overrides["color"] = list(current_entity.color)
    if _serialize_persistent_visuals(current_entity) != _serialize_persistent_visuals(authored_entity):
        overrides["visuals"] = _serialize_persistent_visuals(current_entity)

    variable_overrides = _capture_variable_overrides(
        authored_entity.variables,
        current_entity.variables,
    )
    if variable_overrides:
        overrides["variables"] = variable_overrides

    entity_command_state_overrides = _capture_entity_command_state_overrides(
        authored_entity,
        current_entity,
    )
    if entity_command_state_overrides:
        overrides["entity_command_states"] = entity_command_state_overrides

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


def _capture_entity_command_state_overrides(
    authored_entity: Entity,
    current_entity: Entity,
) -> dict[str, bool]:
    """Capture entity-command enabled-state changes as persistent overrides."""
    overrides: dict[str, bool] = {}
    command_ids = set(authored_entity.entity_commands.keys()) | set(current_entity.entity_commands.keys())
    for command_id in command_ids:
        authored_command = authored_entity.get_entity_command(command_id)
        current_command = current_entity.get_entity_command(command_id)
        if authored_command is None or current_command is None:
            continue
        if current_command.enabled != authored_command.enabled:
            overrides[command_id] = current_command.enabled
    return overrides
