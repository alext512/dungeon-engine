"""Entity-state builtin commands."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

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

    @registry.register("set_entity_command_enabled")
    def set_entity_command_enabled(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        command_id: str,
        enabled: bool,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Enable or disable one named entity command on an entity."""
        entity = require_exact_entity(world, entity_id)
        entity.set_entity_command_enabled(command_id, enabled)
        if should_persist_entity_field(entity, persistent=persistent):
            persist_entity_command_enabled(
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity.entity_id,
                command_id=command_id,
                enabled=enabled,
                entity=entity,
            )
        return ImmediateHandle()

    @registry.register("set_entity_commands_enabled")
    def set_entity_commands_enabled(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        enabled: bool,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Enable or disable all named entity commands on an entity at once."""
        return set_exact_entity_field_handle(
            context=None,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
            entity_id=entity_id,
            field_name="entity_commands_enabled",
            value=enabled,
            persistent=persistent,
        )

    @registry.register("set_entity_field")
    def set_entity_field(
        context: CommandContext,
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        field_name: str,
        value: Any,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Change one supported runtime field on an entity."""
        return set_exact_entity_field_handle(
            context=context,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
            entity_id=entity_id,
            field_name=field_name,
            value=value,
            persistent=persistent,
        )

    @registry.register("set_entity_fields")
    def set_entity_fields(
        context: CommandContext,
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        set: dict[str, Any],
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Change several supported runtime fields, variables, and visuals at once."""
        return set_exact_entity_fields_handle(
            context=context,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
            entity_id=entity_id,
            set_payload=set,
            persistent=persistent,
        )

    @registry.register("set_visible")
    def set_visible(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        visible: bool,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Change whether an entity is rendered and targetable."""
        return set_exact_entity_field_handle(
            context=None,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
            entity_id=entity_id,
            field_name="visible",
            value=visible,
            persistent=persistent,
        )

    @registry.register("set_present")
    def set_present(
        context: CommandContext,
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        present: bool,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Change whether an entity participates in the current scene."""
        return set_exact_entity_field_handle(
            context=context,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
            entity_id=entity_id,
            field_name="present",
            value=present,
            persistent=persistent,
        )

    @registry.register("set_color")
    def set_color(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        color: list[int],
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Change an entity's debug-render color."""
        return set_exact_entity_field_handle(
            context=None,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
            entity_id=entity_id,
            field_name="color",
            value=color,
            persistent=persistent,
        )

    @registry.register("destroy_entity")
    def destroy_entity(
        context: CommandContext,
        world: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Destroy an entity instance completely."""
        entity = require_exact_entity(world, entity_id)
        persist_destroy = should_persist_entity_field(entity, persistent=persistent)
        previous_cell = occupancy_cell_for(entity)
        if previous_cell is None:
            world.remove_entity(entity.entity_id)
            if persist_destroy and persistence_runtime is not None:
                persistence_runtime.remove_entity(entity.entity_id, entity=entity)
            return ImmediateHandle()

        entity.set_present(False)
        leave_handle = build_occupancy_transition_handle(
            context=context,
            instigator=entity,
            previous_cell=previous_cell,
            next_cell=None,
        )

        def _finalize_destroy() -> None:
            world.remove_entity(entity.entity_id)
            if persist_destroy and persistence_runtime is not None:
                persistence_runtime.remove_entity(entity.entity_id, entity=entity)

        if leave_handle.complete:
            _finalize_destroy()
            return ImmediateHandle()
        return post_action_handle_factory(leave_handle, _finalize_destroy)

    @registry.register("spawn_entity")
    def spawn_entity(
        world: Any,
        area: Any,
        project: Any | None,
        persistence_runtime: Any | None,
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
        if world.get_entity(new_entity_id) is not None:
            raise KeyError(f"Cannot spawn duplicate entity '{new_entity_id}'.")

        new_entity = instantiate_entity(
            entity_data,
            area.tile_size,
            project=project,
            source_name=f"spawned entity '{new_entity_id}'",
        )
        world.add_entity(new_entity)
        if should_persist_entity_field(new_entity, persistent=persistent) and persistence_runtime is not None:
            persistence_runtime.record_spawned_entity(
                new_entity,
                tile_size=area.tile_size,
            )
        return ImmediateHandle()

    @registry.register(
        "set_current_area_var",
        additional_authored_params={"value_mode"},
    )
    def set_current_area_var(
        world: Any,
        persistence_runtime: Any | None,
        *,
        name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Set one explicit current-area variable to a value."""
        persisted_value = copy.deepcopy(value)
        world.variables[name] = persisted_value
        if persistent:
            persist_current_area_variable_value(
                persistence_runtime,
                name=name,
                value=persisted_value,
            )
        return ImmediateHandle()

    @registry.register(
        "set_entity_var",
        additional_authored_params={"value_mode"},
    )
    def set_entity_var(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        name: str,
        value: Any,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Set one explicit entity variable to a value."""
        persisted_value = copy.deepcopy(value)
        entity = require_exact_entity(world, entity_id)
        entity.variables[name] = persisted_value
        if should_persist_entity_variable(entity, name=name, persistent=persistent):
            persist_exact_entity_variable_value(
                world=world,
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity_id,
                name=name,
                value=persisted_value,
            )
        return ImmediateHandle()

    @registry.register("add_current_area_var")
    def add_current_area_var(
        world: Any,
        persistence_runtime: Any | None,
        *,
        name: str,
        amount: int | float = 1,
        persistent: bool = False,
    ) -> CommandHandle:
        """Add an amount to one explicit current-area variable."""
        current_value = world.variables.get(name, 0) + amount
        world.variables[name] = current_value
        if persistent:
            persist_current_area_variable_value(
                persistence_runtime,
                name=name,
                value=current_value,
            )
        return ImmediateHandle()

    @registry.register("add_entity_var")
    def add_entity_var(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        name: str,
        amount: int | float = 1,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Add an amount to one explicit entity variable."""
        entity = require_exact_entity(world, entity_id)
        current_value = entity.variables.get(name, 0) + amount
        entity.variables[name] = current_value
        if should_persist_entity_variable(entity, name=name, persistent=persistent):
            persist_exact_entity_variable_value(
                world=world,
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity_id,
                name=name,
                value=current_value,
            )
        return ImmediateHandle()

    @registry.register("toggle_current_area_var")
    def toggle_current_area_var(
        world: Any,
        persistence_runtime: Any | None,
        *,
        name: str,
        persistent: bool = False,
    ) -> CommandHandle:
        """Flip one explicit current-area variable between True and False."""
        current_value = world.variables.get(name, False)
        if current_value is None:
            current_value = False
        if not isinstance(current_value, bool):
            raise TypeError(
                "toggle_current_area_var requires boolean state "
                f"for '{name}', got {type(current_value).__name__}."
            )
        next_value = not current_value
        world.variables[name] = next_value
        if persistent:
            persist_current_area_variable_value(
                persistence_runtime,
                name=name,
                value=next_value,
            )
        return ImmediateHandle()

    @registry.register("toggle_entity_var")
    def toggle_entity_var(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        name: str,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Flip one explicit entity variable between True and False."""
        entity = require_exact_entity(world, entity_id)
        current_value = entity.variables.get(name, False)
        if current_value is None:
            current_value = False
        if not isinstance(current_value, bool):
            raise TypeError(
                f"toggle_entity_var requires boolean state for '{name}', got {type(current_value).__name__}."
            )
        next_value = not current_value
        entity.variables[name] = next_value
        if should_persist_entity_variable(entity, name=name, persistent=persistent):
            persist_exact_entity_variable_value(
                world=world,
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity_id,
                name=name,
                value=next_value,
            )
        return ImmediateHandle()

    @registry.register("set_current_area_var_length")
    def set_current_area_var_length(
        world: Any,
        persistence_runtime: Any | None,
        *,
        name: str,
        value: Any = None,
        persistent: bool = False,
    ) -> CommandHandle:
        """Store the length of a value into one explicit current-area variable."""
        if value is None:
            length_value = 0
        else:
            try:
                length_value = len(value)
            except TypeError as exc:
                raise TypeError("set_current_area_var_length requires a sized value or null.") from exc
        world.variables[name] = length_value
        if persistent:
            persist_current_area_variable_value(
                persistence_runtime,
                name=name,
                value=length_value,
            )
        return ImmediateHandle()

    @registry.register("set_entity_var_length")
    def set_entity_var_length(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        name: str,
        value: Any = None,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Store the length of a value into one explicit entity variable."""
        if value is None:
            length_value = 0
        else:
            try:
                length_value = len(value)
            except TypeError as exc:
                raise TypeError("set_entity_var_length requires a sized value or null.") from exc
        entity = require_exact_entity(world, entity_id)
        entity.variables[name] = length_value
        if should_persist_entity_variable(entity, name=name, persistent=persistent):
            persist_exact_entity_variable_value(
                world=world,
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity_id,
                name=name,
                value=length_value,
            )
        return ImmediateHandle()

    @registry.register(
        "append_current_area_var",
        additional_authored_params={"value_mode"},
    )
    def append_current_area_var(
        world: Any,
        persistence_runtime: Any | None,
        *,
        name: str,
        value: Any,
        persistent: bool = False,
    ) -> CommandHandle:
        """Append one item to one explicit current-area list variable."""
        current_value = world.variables.get(name)
        if current_value is None:
            current_items: list[Any] = []
        elif isinstance(current_value, list):
            current_items = [copy.deepcopy(item) for item in current_value]
        else:
            raise TypeError(
                "append_current_area_var requires the target variable to be a list or null."
            )
        current_items.append(copy.deepcopy(value))
        world.variables[name] = current_items
        if persistent:
            persist_current_area_variable_value(
                persistence_runtime,
                name=name,
                value=current_items,
            )
        return ImmediateHandle()

    @registry.register(
        "append_entity_var",
        additional_authored_params={"value_mode"},
    )
    def append_entity_var(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        name: str,
        value: Any,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Append one item to one explicit entity list variable."""
        entity = require_exact_entity(world, entity_id)
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
                world=world,
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity_id,
                name=name,
                value=current_items,
            )
        return ImmediateHandle()

    @registry.register("pop_current_area_var")
    def pop_current_area_var(
        world: Any,
        persistence_runtime: Any | None,
        *,
        name: str,
        store_var: str | None = None,
        default: Any = None,
        persistent: bool = False,
    ) -> CommandHandle:
        """Pop the last item from one explicit current-area list variable."""
        current_value = world.variables.get(name)
        if current_value is None:
            current_items: list[Any] = []
        elif isinstance(current_value, list):
            current_items = [copy.deepcopy(item) for item in current_value]
        else:
            raise TypeError("pop_current_area_var requires the target variable to be a list or null.")

        popped_value = copy.deepcopy(default)
        if current_items:
            popped_value = current_items.pop()
        world.variables[name] = current_items
        if store_var:
            world.variables[store_var] = copy.deepcopy(popped_value)

        if persistent:
            persist_current_area_variable_value(
                persistence_runtime,
                name=name,
                value=current_items,
            )
            if store_var:
                persist_current_area_variable_value(
                    persistence_runtime,
                    name=store_var,
                    value=popped_value,
                )
        return ImmediateHandle()

    @registry.register("pop_entity_var")
    def pop_entity_var(
        world: Any,
        area: Any,
        persistence_runtime: Any | None,
        *,
        entity_id: str,
        name: str,
        store_var: str | None = None,
        default: Any = None,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Pop the last item from one explicit entity list variable."""
        entity = require_exact_entity(world, entity_id)
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
                world=world,
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity_id,
                name=name,
                value=current_items,
            )
        if store_var and should_persist_entity_variable(entity, name=store_var, persistent=persistent):
            persist_exact_entity_variable_value(
                world=world,
                area=area,
                persistence_runtime=persistence_runtime,
                entity_id=entity_id,
                name=store_var,
                value=popped_value,
            )
        return ImmediateHandle()
