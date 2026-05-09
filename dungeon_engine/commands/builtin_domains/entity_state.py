"""Entity-state builtin commands."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from dungeon_engine.commands.context_services import CommandServices

from dungeon_engine.commands.context_types import PersistenceRuntimeLike

from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import CommandContext, CommandHandle, ImmediateHandle


def register_entity_state_commands(
    registry: CommandRegistry,
    *,
    instantiate_entity: Callable[..., Any],
    require_exact_entity: Callable[[Any, str], Any],
    should_persist_entity_field: Callable[..., bool],
    should_persist_entity_variable: Callable[..., bool],
    persist_current_area_variable_value: Callable[..., None],
    persist_exact_entity_variable_value: Callable[..., None],
    persist_entity_command_enabled: Callable[..., None],
    set_exact_entity_field_handle: Callable[..., CommandHandle],
    set_exact_entity_fields_handle: Callable[..., CommandHandle],
    occupancy_cell_for: Callable[[Any], tuple[int, int] | None],
    build_occupancy_transition_handle: Callable[..., CommandHandle],
    post_action_handle_factory: Callable[[CommandHandle, Callable[[], None]], CommandHandle],
) -> None:
    """Register builtin commands that mutate live entity and area-owned state."""

    def _resolve_state_services(
        *,
        services: CommandServices | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
    ) -> tuple[Any, Any, PersistenceRuntimeLike | None]:
        resolved_world = world
        resolved_area = area
        if services is not None and services.world is not None:
            resolved_world = services.world.world
            resolved_area = services.world.area
        resolved_persistence = persistence_runtime
        if services is not None and services.persistence is not None:
            resolved_persistence = services.persistence.persistence_runtime
        return resolved_world, resolved_area, resolved_persistence

    def _require_entity_dialogue_ids(entity: Any, *, command_name: str) -> list[str]:
        """Return one entity's authored dialogue ids in authored order."""
        dialogue_ids = list(getattr(entity, "dialogues", {}).keys())
        if not dialogue_ids:
            raise ValueError(
                f"{command_name} requires entity '{entity.entity_id}' to define a non-empty 'dialogues' map."
            )
        return dialogue_ids

    def _require_known_entity_dialogue_id(
        entity: Any,
        dialogue_id: Any,
        *,
        command_name: str,
    ) -> str:
        """Return one explicit dialogue id when the entity owns it."""
        resolved_dialogue_id = str(dialogue_id).strip()
        if not resolved_dialogue_id:
            raise ValueError(f"{command_name} requires a non-empty dialogue_id.")
        if resolved_dialogue_id not in getattr(entity, "dialogues", {}):
            raise KeyError(
                f"Entity '{entity.entity_id}' has no dialogue '{resolved_dialogue_id}'."
            )
        return resolved_dialogue_id

    def _require_current_entity_dialogue_index(
        entity: Any,
        *,
        command_name: str,
    ) -> tuple[list[str], int]:
        """Return the authored dialogue ids plus the current active-dialogue index."""
        dialogue_ids = _require_entity_dialogue_ids(entity, command_name=command_name)
        current_dialogue_id = entity.variables.get("active_dialogue")
        if not isinstance(current_dialogue_id, str) or not current_dialogue_id.strip():
            raise ValueError(
                f"{command_name} requires entity '{entity.entity_id}' to have a non-empty "
                "'active_dialogue' variable."
            )
        resolved_current_dialogue_id = current_dialogue_id.strip()
        if resolved_current_dialogue_id not in entity.dialogues:
            raise KeyError(
                f"Entity '{entity.entity_id}' active_dialogue '{resolved_current_dialogue_id}' "
                "does not exist in its 'dialogues' map."
            )
        return dialogue_ids, dialogue_ids.index(resolved_current_dialogue_id)

    def _set_active_dialogue_value(
        *,
        entity: Any,
        dialogue_id: str,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        persistent: bool | None,
    ) -> None:
        """Store one active-dialogue id and persist it when policy requires."""
        entity.variables["active_dialogue"] = dialogue_id
        if should_persist_entity_variable(entity, name="active_dialogue", persistent=persistent):
            persist_exact_entity_variable_value(
                world=world,
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity.entity_id,
                name="active_dialogue",
                value=dialogue_id,
            )

    @registry.register("set_entity_command_enabled")
    def set_entity_command_enabled(
        services: CommandServices | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        entity_id: str,
        command_id: str,
        enabled: bool,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Enable or disable one named entity command on an entity."""
        resolved_world, resolved_area, resolved_persistence = _resolve_state_services(
            services=services,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
        )
        entity = require_exact_entity(resolved_world, entity_id)
        entity.set_entity_command_enabled(command_id, enabled)
        if should_persist_entity_field(entity, persistent=persistent):
            persist_entity_command_enabled(
                area=resolved_area,
                persistence_runtime=resolved_persistence,
                entity_id=entity.entity_id,
                command_id=command_id,
                enabled=enabled,
                entity=entity,
            )
        return ImmediateHandle()

    @registry.register("set_entity_field")
    def set_entity_field(
        context: CommandContext,
        services: CommandServices | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        entity_id: str,
        field_name: str,
        value: Any,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Change one supported runtime field on an entity."""
        resolved_world, resolved_area, resolved_persistence = _resolve_state_services(
            services=services,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
        )
        return set_exact_entity_field_handle(
            context=context,
            world=resolved_world,
            area=resolved_area,
            persistence_runtime=resolved_persistence,
            entity_id=entity_id,
            field_name=field_name,
            value=value,
            persistent=persistent,
        )

    @registry.register("set_entity_fields")
    def set_entity_fields(
        context: CommandContext,
        services: CommandServices | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        entity_id: str,
        set: dict[str, Any],
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Change several supported runtime fields, variables, and visuals at once."""
        resolved_world, resolved_area, resolved_persistence = _resolve_state_services(
            services=services,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
        )
        return set_exact_entity_fields_handle(
            context=context,
            world=resolved_world,
            area=resolved_area,
            persistence_runtime=resolved_persistence,
            entity_id=entity_id,
            set_payload=set,
            persistent=persistent,
        )

    @registry.register("destroy_entity")
    def destroy_entity(
        context: CommandContext,
        services: CommandServices | None,
        world: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        entity_id: str,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Destroy an entity instance completely."""
        resolved_world, _, resolved_persistence = _resolve_state_services(
            services=services,
            world=world,
            area=None,
            persistence_runtime=persistence_runtime,
        )
        entity = require_exact_entity(resolved_world, entity_id)
        persist_destroy = should_persist_entity_field(entity, persistent=persistent)
        previous_cell = occupancy_cell_for(entity)
        if previous_cell is None:
            resolved_world.remove_entity(entity.entity_id)
            if persist_destroy and resolved_persistence is not None:
                resolved_persistence.remove_entity(entity.entity_id, entity=entity)
            return ImmediateHandle()

        entity.set_present(False)
        leave_handle = build_occupancy_transition_handle(
            context=context,
            instigator=entity,
            previous_cell=previous_cell,
            next_cell=None,
        )

        def _finalize_destroy() -> None:
            resolved_world.remove_entity(entity.entity_id)
            if persist_destroy and resolved_persistence is not None:
                resolved_persistence.remove_entity(entity.entity_id, entity=entity)

        if leave_handle.complete:
            _finalize_destroy()
            return ImmediateHandle()
        return post_action_handle_factory(leave_handle, _finalize_destroy)

    @registry.register("spawn_entity")
    def spawn_entity(
        services: CommandServices | None,
        world: Any,
        area: Any,
        project: Any | None,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        entity: dict[str, Any] | None = None,
        entity_id: str | None = None,
        template: str | None = None,
        kind: str | None = None,
        x: int | None = None,
        y: int | None = None,
        parameters: dict[str, Any] | None = None,
        present: bool = True,
        persistent: bool | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Create a new entity instance in the current world."""
        resolved_world, resolved_area, resolved_persistence = _resolve_state_services(
            services=services,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
        )
        entity_data = copy.deepcopy(entity) if entity is not None else {}
        if not entity_data:
            if entity_id is None:
                raise ValueError("spawn_entity requires entity_id when no entity dict is provided.")
            if x is None or y is None:
                raise ValueError("spawn_entity requires x and y when no entity dict is provided.")
            entity_data = {
                "id": entity_id,
                "x": int(x),
                "y": int(y),
                "present": bool(present),
            }
            if template is not None:
                entity_data["template"] = template
            if kind is not None:
                entity_data["kind"] = kind
            if parameters:
                entity_data["parameters"] = copy.deepcopy(parameters)
        else:
            entity_data.setdefault("present", bool(present))

        new_entity_id = str(entity_data.get("id", "")).strip()
        if not new_entity_id:
            raise ValueError("spawn_entity requires an entity id.")
        if resolved_world.get_entity(new_entity_id) is not None:
            raise KeyError(f"Cannot spawn duplicate entity '{new_entity_id}'.")

        new_entity = instantiate_entity(
            entity_data,
            resolved_area.tile_size,
            project=project,
            source_name=f"spawned entity '{new_entity_id}'",
        )
        resolved_world.add_entity(new_entity)
        if should_persist_entity_field(new_entity, persistent=persistent) and resolved_persistence is not None:
            resolved_persistence.record_spawned_entity(
                new_entity,
                tile_size=resolved_area.tile_size,
            )
        return ImmediateHandle()

    @registry.register(
        "set_current_area_var",
        additional_authored_params={"value_mode"},
    )
    def set_current_area_var(
        services: CommandServices | None,
        world: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Set one explicit current-area variable to a value."""
        resolved_world, _, resolved_persistence = _resolve_state_services(
            services=services,
            world=world,
            area=None,
            persistence_runtime=persistence_runtime,
        )
        persisted_value = copy.deepcopy(value)
        resolved_world.variables[name] = persisted_value
        if persistent:
            persist_current_area_variable_value(
                resolved_persistence,
                name=name,
                value=persisted_value,
            )
        return ImmediateHandle()

    @registry.register(
        "set_entity_var",
        additional_authored_params={"value_mode"},
    )
    def set_entity_var(
        services: CommandServices | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        entity_id: str,
        name: str,
        value: Any,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Set one explicit entity variable to a value."""
        resolved_world, resolved_area, resolved_persistence = _resolve_state_services(
            services=services,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
        )
        persisted_value = copy.deepcopy(value)
        entity = require_exact_entity(resolved_world, entity_id)
        entity.variables[name] = persisted_value
        if should_persist_entity_variable(entity, name=name, persistent=persistent):
            persist_exact_entity_variable_value(
                world=resolved_world,
                area=resolved_area,
                persistence_runtime=resolved_persistence,
                entity_id=entity_id,
                name=name,
                value=persisted_value,
            )
        return ImmediateHandle()

    @registry.register("set_entity_active_dialogue")
    def set_entity_active_dialogue(
        services: CommandServices | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        entity_id: str,
        dialogue_id: str,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Set one entity's active_dialogue variable to a named authored dialogue."""
        resolved_world, resolved_area, resolved_persistence = _resolve_state_services(
            services=services,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
        )
        entity = require_exact_entity(resolved_world, entity_id)
        resolved_dialogue_id = _require_known_entity_dialogue_id(
            entity,
            dialogue_id,
            command_name="set_entity_active_dialogue",
        )
        _set_active_dialogue_value(
            entity=entity,
            dialogue_id=resolved_dialogue_id,
            world=resolved_world,
            area=resolved_area,
            persistence_runtime=resolved_persistence,
            persistent=persistent,
        )
        return ImmediateHandle()

    @registry.register("step_entity_active_dialogue")
    def step_entity_active_dialogue(
        services: CommandServices | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        entity_id: str,
        delta: int = 1,
        wrap: bool = False,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Move an entity's active dialogue forward/backward in authored order."""
        resolved_world, resolved_area, resolved_persistence = _resolve_state_services(
            services=services,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
        )
        entity = require_exact_entity(resolved_world, entity_id)
        dialogue_ids, current_index = _require_current_entity_dialogue_index(
            entity,
            command_name="step_entity_active_dialogue",
        )
        next_index = current_index + int(delta)
        if wrap:
            next_index %= len(dialogue_ids)
        elif next_index < 0 or next_index >= len(dialogue_ids):
            raise IndexError(
                f"step_entity_active_dialogue would move entity '{entity.entity_id}' outside "
                f"its dialogue range (size {len(dialogue_ids)})."
            )
        _set_active_dialogue_value(
            entity=entity,
            dialogue_id=dialogue_ids[next_index],
            world=resolved_world,
            area=resolved_area,
            persistence_runtime=resolved_persistence,
            persistent=persistent,
        )
        return ImmediateHandle()

    @registry.register("set_entity_active_dialogue_by_order")
    def set_entity_active_dialogue_by_order(
        services: CommandServices | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        entity_id: str,
        order: int,
        wrap: bool = False,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Set one entity's active dialogue using 1-based authored order."""
        resolved_world, resolved_area, resolved_persistence = _resolve_state_services(
            services=services,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
        )
        entity = require_exact_entity(resolved_world, entity_id)
        dialogue_ids = _require_entity_dialogue_ids(
            entity,
            command_name="set_entity_active_dialogue_by_order",
        )
        resolved_order = int(order)
        if wrap:
            next_index = (resolved_order - 1) % len(dialogue_ids)
        else:
            if resolved_order < 1 or resolved_order > len(dialogue_ids):
                raise IndexError(
                    f"set_entity_active_dialogue_by_order requires order between 1 and "
                    f"{len(dialogue_ids)} for entity '{entity.entity_id}'."
                )
            next_index = resolved_order - 1
        _set_active_dialogue_value(
            entity=entity,
            dialogue_id=dialogue_ids[next_index],
            world=resolved_world,
            area=resolved_area,
            persistence_runtime=resolved_persistence,
            persistent=persistent,
        )
        return ImmediateHandle()

    @registry.register(
        "append_current_area_var",
        additional_authored_params={"value_mode"},
    )
    def append_current_area_var(
        services: CommandServices | None,
        world: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Append one item to one explicit current-area list variable."""
        resolved_world, _, resolved_persistence = _resolve_state_services(
            services=services,
            world=world,
            area=None,
            persistence_runtime=persistence_runtime,
        )
        current_value = resolved_world.variables.get(name)
        if current_value is None:
            current_items: list[Any] = []
        elif isinstance(current_value, list):
            current_items = [copy.deepcopy(item) for item in current_value]
        else:
            raise TypeError(
                "append_current_area_var requires the target variable to be a list or null."
            )
        current_items.append(copy.deepcopy(value))
        resolved_world.variables[name] = current_items
        if persistent:
            persist_current_area_variable_value(
                resolved_persistence,
                name=name,
                value=current_items,
            )
        return ImmediateHandle()

    @registry.register(
        "append_entity_var",
        additional_authored_params={"value_mode"},
    )
    def append_entity_var(
        services: CommandServices | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        entity_id: str,
        name: str,
        value: Any,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Append one item to one explicit entity list variable."""
        resolved_world, resolved_area, resolved_persistence = _resolve_state_services(
            services=services,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
        )
        entity = require_exact_entity(resolved_world, entity_id)
        current_value = entity.variables.get(name)
        if current_value is None:
            current_items: list[Any] = []
        elif isinstance(current_value, list):
            current_items = [copy.deepcopy(item) for item in current_value]
        else:
            raise TypeError("append_entity_var requires the target variable to be a list or null.")
        current_items.append(copy.deepcopy(value))
        entity.variables[name] = current_items
        if should_persist_entity_variable(entity, name=name, persistent=persistent):
            persist_exact_entity_variable_value(
                world=resolved_world,
                area=resolved_area,
                persistence_runtime=resolved_persistence,
                entity_id=entity_id,
                name=name,
                value=current_items,
            )
        return ImmediateHandle()

    @registry.register("pop_current_area_var")
    def pop_current_area_var(
        services: CommandServices | None,
        world: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        name: str,
        store_var: str | None = None,
        default: Any = None,
        persistent: bool = False,
    ) -> CommandHandle:
        """Pop the last item from one explicit current-area list variable."""
        resolved_world, _, resolved_persistence = _resolve_state_services(
            services=services,
            world=world,
            area=None,
            persistence_runtime=persistence_runtime,
        )
        current_value = resolved_world.variables.get(name)
        if current_value is None:
            current_items: list[Any] = []
        elif isinstance(current_value, list):
            current_items = [copy.deepcopy(item) for item in current_value]
        else:
            raise TypeError("pop_current_area_var requires the target variable to be a list or null.")

        popped_value = copy.deepcopy(default)
        if current_items:
            popped_value = current_items.pop()
        resolved_world.variables[name] = current_items
        if store_var:
            resolved_world.variables[store_var] = copy.deepcopy(popped_value)

        if persistent:
            persist_current_area_variable_value(
                resolved_persistence,
                name=name,
                value=current_items,
            )
            if store_var:
                persist_current_area_variable_value(
                    resolved_persistence,
                    name=store_var,
                    value=popped_value,
                )
        return ImmediateHandle()

    @registry.register("pop_entity_var")
    def pop_entity_var(
        services: CommandServices | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        entity_id: str,
        name: str,
        store_var: str | None = None,
        default: Any = None,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Pop the last item from one explicit entity list variable."""
        resolved_world, resolved_area, resolved_persistence = _resolve_state_services(
            services=services,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
        )
        entity = require_exact_entity(resolved_world, entity_id)
        current_value = entity.variables.get(name)
        if current_value is None:
            current_items: list[Any] = []
        elif isinstance(current_value, list):
            current_items = [copy.deepcopy(item) for item in current_value]
        else:
            raise TypeError("pop_entity_var requires the target variable to be a list or null.")

        popped_value = copy.deepcopy(default)
        if current_items:
            popped_value = current_items.pop()
        entity.variables[name] = current_items
        if store_var:
            entity.variables[store_var] = copy.deepcopy(popped_value)

        if should_persist_entity_variable(entity, name=name, persistent=persistent):
            persist_exact_entity_variable_value(
                world=resolved_world,
                area=resolved_area,
                persistence_runtime=resolved_persistence,
                entity_id=entity_id,
                name=name,
                value=current_items,
            )
        if store_var and should_persist_entity_variable(entity, name=store_var, persistent=persistent):
            persist_exact_entity_variable_value(
                world=resolved_world,
                area=resolved_area,
                persistence_runtime=resolved_persistence,
                entity_id=entity_id,
                name=store_var,
                value=popped_value,
            )
        return ImmediateHandle()
