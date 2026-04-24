"""Inventory-oriented builtin commands."""

from __future__ import annotations

import copy
from collections.abc import Callable
from logging import Logger
from typing import Any

from dungeon_engine.commands.context_services import CommandServices
from dungeon_engine.commands.context_types import PersistenceRuntimeLike

from dungeon_engine.inventory import (
    add_inventory_item_to_state,
    inventory_has_item,
    make_inventory_change_result,
    normalize_quantity_mode,
    remove_inventory_item_from_state,
    serialize_inventory_state,
    set_inventory_max_stacks_on_state,
)
from dungeon_engine.items import load_item_definition
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import CommandContext, CommandHandle, ImmediateHandle, SequenceCommandHandle


def _persist_inventory_state(
    *,
    area: Any,
    persistence_runtime: PersistenceRuntimeLike | None,
    entity: Any,
    persist_entity_field: Callable[..., None],
    persistent: bool | None,
) -> None:
    """Persist one entity inventory payload using the shared entity-field helper."""
    if entity.inventory is None:
        return
    if not entity.persistence.resolve_field(explicit=persistent):
        return
    persist_entity_field(
        area=area,
        persistence_runtime=persistence_runtime,
        entity_id=entity.entity_id,
        field_name="inventory",
        value=serialize_inventory_state(entity.inventory),
        entity=entity,
    )


def _write_inventory_result_if_requested(
    *,
    require_exact_entity: Callable[[Any, str], Any],
    world: Any,
    source_entity_id: str | None,
    result_var_name: str | None,
    result: dict[str, Any],
) -> None:
    """Write one inventory result payload onto the current command owner when requested."""
    if result_var_name in (None, ""):
        return
    if source_entity_id in (None, ""):
        raise ValueError(
            "Inventory commands that use result_var_name require a source entity context."
        )
    owner_entity = require_exact_entity(world, str(source_entity_id))
    owner_entity.variables[str(result_var_name)] = copy.deepcopy(result)


def _load_runtime_item_definition(
    *,
    logger: Logger,
    project: Any | None,
    item_id: str,
    command_name: str,
) -> Any | None:
    """Return one item definition when it exists, logging a warning otherwise."""
    if project is None:
        logger.warning("%s: skipping because no active project context exists.", command_name)
        return None
    try:
        return load_item_definition(project, item_id)
    except FileNotFoundError:
        logger.warning("%s: skipping because item '%s' was not found.", command_name, item_id)
        return None


def register_inventory_commands(
    registry: CommandRegistry,
    *,
    logger: Logger,
    require_exact_entity: Callable[[Any, str], Any],
    persist_entity_field: Callable[..., None],
    build_child_runtime_params: Callable[..., dict[str, Any]],
    post_action_handle_factory: Callable[[CommandHandle, Callable[[], None]], CommandHandle],
) -> None:
    """Register builtin commands that manipulate inventories and item usage."""

    def _resolve_inventory_services(
        *,
        services: CommandServices | None,
        world: Any,
        area: Any | None,
        persistence_runtime: PersistenceRuntimeLike | None,
    ) -> tuple[Any, Any | None, PersistenceRuntimeLike | None]:
        resolved_world = world
        resolved_area = area
        if services is not None and services.world is not None:
            resolved_world = services.world.world
            resolved_area = services.world.area
        resolved_persistence = persistence_runtime
        if services is not None and services.persistence is not None:
            resolved_persistence = services.persistence.persistence_runtime
        return resolved_world, resolved_area, resolved_persistence

    def _resolve_inventory_runtime(
        *,
        inventory_runtime: Any | None,
    ) -> Any | None:
        return inventory_runtime

    @registry.register("add_inventory_item")
    def add_inventory_item(
        services: CommandServices | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        project: Any | None,
        *,
        entity_id: str,
        item_id: str,
        quantity: int = 1,
        quantity_mode: str,
        result_var_name: str | None = None,
        source_entity_id: str | None = None,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Add item quantity to one entity-owned inventory."""
        resolved_world, resolved_area, resolved_persistence = _resolve_inventory_services(
            services=services,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
        )
        resolved_entity_id = str(entity_id).strip()
        resolved_item_id = str(item_id).strip()
        requested_quantity = int(quantity)
        if not resolved_entity_id:
            logger.warning("add_inventory_item: skipping because entity_id resolved to blank.")
            _write_inventory_result_if_requested(
                require_exact_entity=require_exact_entity,
                world=resolved_world,
                source_entity_id=source_entity_id,
                result_var_name=result_var_name,
                result=make_inventory_change_result(
                    success=False,
                    item_id=resolved_item_id,
                    requested_quantity=requested_quantity,
                    changed_quantity=0,
                    remaining_quantity=max(0, requested_quantity),
                ),
            )
            return ImmediateHandle()
        item_definition = _load_runtime_item_definition(
            logger=logger,
            project=project,
            item_id=resolved_item_id,
            command_name="add_inventory_item",
        )
        if item_definition is None:
            _write_inventory_result_if_requested(
                require_exact_entity=require_exact_entity,
                world=resolved_world,
                source_entity_id=source_entity_id,
                result_var_name=result_var_name,
                result=make_inventory_change_result(
                    success=False,
                    item_id=resolved_item_id,
                    requested_quantity=requested_quantity,
                    changed_quantity=0,
                    remaining_quantity=max(0, requested_quantity),
                ),
            )
            return ImmediateHandle()

        entity = require_exact_entity(resolved_world, resolved_entity_id)
        result = add_inventory_item_to_state(
            entity.inventory,
            item_id=resolved_item_id,
            quantity=requested_quantity,
            max_stack=int(item_definition.max_stack),
            quantity_mode=normalize_quantity_mode(quantity_mode),
        )
        if entity.inventory is not None and int(result.get("changed_quantity", 0)) > 0:
            _persist_inventory_state(
                area=resolved_area,
                persistence_runtime=resolved_persistence,
                entity=entity,
                persist_entity_field=persist_entity_field,
                persistent=persistent,
            )
        _write_inventory_result_if_requested(
            require_exact_entity=require_exact_entity,
            world=resolved_world,
            source_entity_id=source_entity_id,
            result_var_name=result_var_name,
            result=result,
        )
        return ImmediateHandle()

    @registry.register("remove_inventory_item")
    def remove_inventory_item(
        services: CommandServices | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        entity_id: str,
        item_id: str,
        quantity: int = 1,
        quantity_mode: str,
        result_var_name: str | None = None,
        source_entity_id: str | None = None,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Remove item quantity from one entity-owned inventory."""
        resolved_world, resolved_area, resolved_persistence = _resolve_inventory_services(
            services=services,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
        )
        resolved_entity_id = str(entity_id).strip()
        resolved_item_id = str(item_id).strip()
        requested_quantity = int(quantity)
        if not resolved_entity_id:
            logger.warning("remove_inventory_item: skipping because entity_id resolved to blank.")
            _write_inventory_result_if_requested(
                require_exact_entity=require_exact_entity,
                world=resolved_world,
                source_entity_id=source_entity_id,
                result_var_name=result_var_name,
                result=make_inventory_change_result(
                    success=False,
                    item_id=resolved_item_id,
                    requested_quantity=requested_quantity,
                    changed_quantity=0,
                    remaining_quantity=max(0, requested_quantity),
                ),
            )
            return ImmediateHandle()

        entity = require_exact_entity(resolved_world, resolved_entity_id)
        result = remove_inventory_item_from_state(
            entity.inventory,
            item_id=resolved_item_id,
            quantity=requested_quantity,
            quantity_mode=normalize_quantity_mode(quantity_mode),
        )
        if entity.inventory is not None and int(result.get("changed_quantity", 0)) > 0:
            _persist_inventory_state(
                area=resolved_area,
                persistence_runtime=resolved_persistence,
                entity=entity,
                persist_entity_field=persist_entity_field,
                persistent=persistent,
            )
        _write_inventory_result_if_requested(
            require_exact_entity=require_exact_entity,
            world=resolved_world,
            source_entity_id=source_entity_id,
            result_var_name=result_var_name,
            result=result,
        )
        return ImmediateHandle()

    @registry.register("use_inventory_item")
    def use_inventory_item(
        context: CommandContext,
        services: CommandServices | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        project: Any | None,
        *,
        entity_id: str,
        item_id: str,
        quantity: int = 1,
        result_var_name: str | None = None,
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Run one item's authored use-commands and consume it only on clean success."""
        resolved_world, resolved_area, resolved_persistence = _resolve_inventory_services(
            services=services,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
        )
        resolved_entity_id = str(entity_id).strip()
        resolved_item_id = str(item_id).strip()
        requested_quantity = int(quantity)
        failure_result = make_inventory_change_result(
            success=False,
            item_id=resolved_item_id,
            requested_quantity=requested_quantity,
            changed_quantity=0,
            remaining_quantity=max(0, requested_quantity),
        )
        if not resolved_entity_id:
            logger.warning("use_inventory_item: skipping because entity_id resolved to blank.")
            _write_inventory_result_if_requested(
                require_exact_entity=require_exact_entity,
                world=resolved_world,
                source_entity_id=source_entity_id,
                result_var_name=result_var_name,
                result=failure_result,
            )
            return ImmediateHandle()

        entity = require_exact_entity(resolved_world, resolved_entity_id)
        item_definition = _load_runtime_item_definition(
            logger=logger,
            project=project,
            item_id=resolved_item_id,
            command_name="use_inventory_item",
        )
        if item_definition is None:
            _write_inventory_result_if_requested(
                require_exact_entity=require_exact_entity,
                world=resolved_world,
                source_entity_id=source_entity_id,
                result_var_name=result_var_name,
                result=failure_result,
            )
            return ImmediateHandle()
        if requested_quantity <= 0:
            raise ValueError("use_inventory_item quantity must be positive.")
        if not item_definition.use_commands:
            _write_inventory_result_if_requested(
                require_exact_entity=require_exact_entity,
                world=resolved_world,
                source_entity_id=source_entity_id,
                result_var_name=result_var_name,
                result=failure_result,
            )
            return ImmediateHandle()

        consume_total = int(item_definition.consume_quantity_on_use) * requested_quantity
        required_quantity = max(requested_quantity, consume_total)
        if not inventory_has_item(entity.inventory, resolved_item_id, quantity=required_quantity):
            _write_inventory_result_if_requested(
                require_exact_entity=require_exact_entity,
                world=resolved_world,
                source_entity_id=source_entity_id,
                result_var_name=result_var_name,
                result=make_inventory_change_result(
                    success=True,
                    item_id=resolved_item_id,
                    requested_quantity=requested_quantity,
                    changed_quantity=0,
                    remaining_quantity=requested_quantity,
                ),
            )
            return ImmediateHandle()

        child_runtime_params = build_child_runtime_params(
            {
                "source_entity_id": source_entity_id,
                "entity_refs": copy.deepcopy(entity_refs or {}),
                "instigator_id": entity.entity_id,
            },
        )
        sequence_handle = SequenceCommandHandle(
            registry,
            context,
            item_definition.use_commands,
            base_params=child_runtime_params,
        )

        def _finalize_use() -> None:
            if consume_total > 0:
                consumption_result = remove_inventory_item_from_state(
                    entity.inventory,
                    item_id=resolved_item_id,
                    quantity=consume_total,
                    quantity_mode="atomic",
                )
                if entity.inventory is not None and int(consumption_result.get("changed_quantity", 0)) > 0:
                    _persist_inventory_state(
                        area=resolved_area,
                        persistence_runtime=resolved_persistence,
                        entity=entity,
                        persist_entity_field=persist_entity_field,
                        persistent=persistent,
                    )
                if int(consumption_result.get("changed_quantity", 0)) != consume_total:
                    logger.warning(
                        "use_inventory_item: item '%s' use completed but post-use consumption did not remove the expected quantity.",
                        resolved_item_id,
                    )
                    _write_inventory_result_if_requested(
                        require_exact_entity=require_exact_entity,
                        world=resolved_world,
                        source_entity_id=source_entity_id,
                        result_var_name=result_var_name,
                        result=failure_result,
                    )
                    return

            _write_inventory_result_if_requested(
                require_exact_entity=require_exact_entity,
                world=resolved_world,
                source_entity_id=source_entity_id,
                result_var_name=result_var_name,
                result=make_inventory_change_result(
                    success=True,
                    item_id=resolved_item_id,
                    requested_quantity=requested_quantity,
                    changed_quantity=consume_total,
                    remaining_quantity=0,
                ),
            )

        return post_action_handle_factory(sequence_handle, _finalize_use)

    @registry.register("open_inventory_session")
    def open_inventory_session(
        inventory_runtime: Any | None,
        *,
        entity_id: str,
        ui_preset: str | None = None,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Open one engine-owned inventory session for an entity-owned inventory."""
        from dungeon_engine.engine.inventory_runtime import InventorySessionWaitHandle

        inventory_runtime = _resolve_inventory_runtime(
            inventory_runtime=inventory_runtime,
        )
        if inventory_runtime is None:
            raise ValueError("open_inventory_session requires an active inventory runtime.")

        session = inventory_runtime.open_session(
            entity_id=str(entity_id),
            ui_preset_name=None if ui_preset in (None, "") else str(ui_preset).strip(),
        )
        if not bool(wait):
            return ImmediateHandle()
        return InventorySessionWaitHandle(inventory_runtime, session)

    @registry.register("close_inventory_session")
    def close_inventory_session(
        inventory_runtime: Any | None,
        **_: Any,
    ) -> CommandHandle:
        """Close the currently active engine-owned inventory session when one exists."""
        inventory_runtime = _resolve_inventory_runtime(
            inventory_runtime=inventory_runtime,
        )
        if inventory_runtime is None:
            raise ValueError("close_inventory_session requires an active inventory runtime.")
        inventory_runtime.close_current_session()
        return ImmediateHandle()

    @registry.register("set_inventory_max_stacks")
    def set_inventory_max_stacks(
        services: CommandServices | None,
        world: Any,
        area: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        entity_id: str,
        max_stacks: int,
        persistent: bool | None = None,
    ) -> CommandHandle:
        """Create or resize one entity-owned inventory capacity without discarding items."""
        resolved_world, resolved_area, resolved_persistence = _resolve_inventory_services(
            services=services,
            world=world,
            area=area,
            persistence_runtime=persistence_runtime,
        )
        entity = require_exact_entity(resolved_world, entity_id)
        resolved_max_stacks = int(max_stacks)
        if entity.inventory is None:
            from dungeon_engine.world.entity import InventoryState

            if resolved_max_stacks < 0:
                raise ValueError("set_inventory_max_stacks max_stacks must be zero or positive.")
            entity.inventory = InventoryState(max_stacks=resolved_max_stacks, stacks=[])
            _persist_inventory_state(
                area=resolved_area,
                persistence_runtime=resolved_persistence,
                entity=entity,
                persist_entity_field=persist_entity_field,
                persistent=persistent,
            )
            return ImmediateHandle()
        if not set_inventory_max_stacks_on_state(entity.inventory, max_stacks=resolved_max_stacks):
            logger.warning(
                "set_inventory_max_stacks: refusing to shrink inventory for entity '%s' below the number of occupied stacks.",
                entity.entity_id,
            )
            return ImmediateHandle()
        _persist_inventory_state(
            area=resolved_area,
            persistence_runtime=resolved_persistence,
            entity=entity,
            persist_entity_field=persist_entity_field,
            persistent=persistent,
        )
        return ImmediateHandle()


__all__ = ["register_inventory_commands"]
