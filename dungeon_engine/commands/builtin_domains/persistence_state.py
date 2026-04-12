"""Cross-area persistence and reset builtin commands."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from dungeon_engine.commands.context_services import CommandServices
from dungeon_engine.commands.context_types import PersistenceRuntimeLike

from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import CommandContext, CommandHandle, ImmediateHandle


def register_persistence_state_commands(
    registry: CommandRegistry,
    *,
    require_cross_area_persistence_runtime: Callable[..., Any],
    require_area_reference: Callable[..., str],
    resolve_authored_area_entity_snapshot: Callable[..., Any],
    normalize_entity_field_mutation: Callable[..., Any],
    apply_normalized_entity_field_mutation: Callable[..., tuple[str, Any]],
) -> None:
    """Register commands that mutate persisted state outside the current live area."""

    def _resolve_persistence_runtime(
        *,
        services: CommandServices | None,
        persistence_runtime: PersistenceRuntimeLike | None,
    ) -> PersistenceRuntimeLike | None:
        if services is not None and services.persistence is not None:
            return services.persistence.persistence_runtime
        return persistence_runtime

    def _resolve_world(
        *,
        services: CommandServices | None,
        world: Any,
    ) -> Any:
        if services is not None and services.world is not None:
            return services.world.world
        return world

    @registry.register("set_area_var")
    def set_area_var(
        context: CommandContext,
        services: CommandServices | None,
        world: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        area_id: str,
        name: str,
        value: Any,
    ) -> CommandHandle:
        """Persist one area-level variable override for an explicitly chosen area."""
        resolved_world = _resolve_world(services=services, world=world)
        resolved_persistence = _resolve_persistence_runtime(
            services=services,
            persistence_runtime=persistence_runtime,
        )
        runtime = require_cross_area_persistence_runtime(
            resolved_persistence,
            command_name="set_area_var",
        )
        resolved_area_id = require_area_reference(
            context.project,
            area_id,
            command_name="set_area_var",
        )
        persisted_value = copy.deepcopy(value)
        runtime.set_area_variable(resolved_area_id, name, persisted_value)
        if context.area is not None and context.area.area_id == resolved_area_id:
            resolved_world.variables[name] = copy.deepcopy(persisted_value)
        return ImmediateHandle()

    @registry.register("set_area_entity_var")
    def set_area_entity_var(
        context: CommandContext,
        services: CommandServices | None,
        world: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        area_id: str,
        entity_id: str,
        name: str,
        value: Any,
    ) -> CommandHandle:
        """Persist one variable override for an authored area entity in an explicit area."""
        resolved_world = _resolve_world(services=services, world=world)
        resolved_persistence = _resolve_persistence_runtime(
            services=services,
            persistence_runtime=persistence_runtime,
        )
        runtime = require_cross_area_persistence_runtime(
            resolved_persistence,
            command_name="set_area_entity_var",
        )
        resolved_area_id = require_area_reference(
            context.project,
            area_id,
            command_name="set_area_entity_var",
        )
        resolved_entity_id = str(entity_id).strip()
        if not resolved_entity_id:
            raise ValueError("set_area_entity_var requires a non-empty entity_id.")
        live_entity = None
        if context.area is not None and context.area.area_id == resolved_area_id:
            live_entity = resolved_world.area_entities.get(resolved_entity_id)
        if live_entity is None:
            resolve_authored_area_entity_snapshot(
                project=context.project,
                area_id=resolved_area_id,
                entity_id=resolved_entity_id,
                asset_manager=context.asset_manager,
            )
        persisted_value = copy.deepcopy(value)
        runtime.set_area_entity_variable(
            resolved_area_id,
            resolved_entity_id,
            name,
            persisted_value,
        )
        if live_entity is not None:
            live_entity.variables[name] = copy.deepcopy(persisted_value)
        return ImmediateHandle()

    @registry.register("set_area_entity_field")
    def set_area_entity_field(
        context: CommandContext,
        services: CommandServices | None,
        world: Any,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        area_id: str,
        entity_id: str,
        field_name: str,
        value: Any,
    ) -> CommandHandle:
        """Persist one field override for an authored area entity in an explicit area."""
        resolved_world = _resolve_world(services=services, world=world)
        resolved_persistence = _resolve_persistence_runtime(
            services=services,
            persistence_runtime=persistence_runtime,
        )
        runtime = require_cross_area_persistence_runtime(
            resolved_persistence,
            command_name="set_area_entity_field",
        )
        resolved_area_id = require_area_reference(
            context.project,
            area_id,
            command_name="set_area_entity_field",
        )
        resolved_entity_id = str(entity_id).strip()
        if not resolved_entity_id:
            raise ValueError("set_area_entity_field requires a non-empty entity_id.")

        live_entity = None
        if context.area is not None and context.area.area_id == resolved_area_id:
            live_entity = resolved_world.area_entities.get(resolved_entity_id)

        validation_entity = live_entity
        if validation_entity is None:
            validation_entity = resolve_authored_area_entity_snapshot(
                project=context.project,
                area_id=resolved_area_id,
                entity_id=resolved_entity_id,
                asset_manager=context.asset_manager,
            )

        mutation = normalize_entity_field_mutation(validation_entity, field_name, value)
        if live_entity is not None:
            persisted_field_name, persisted_value = apply_normalized_entity_field_mutation(
                live_entity,
                mutation,
            )
        else:
            persisted_field_name, persisted_value = apply_normalized_entity_field_mutation(
                copy.deepcopy(validation_entity),
                mutation,
            )

        runtime.set_area_entity_field(
            resolved_area_id,
            resolved_entity_id,
            persisted_field_name,
            persisted_value,
        )
        return ImmediateHandle()

    @registry.register("reset_transient_state")
    def reset_transient_state(
        services: CommandServices | None,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        entity_id: str | None = None,
        entity_ids: list[str] | None = None,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        apply: str = "immediate",
        **_: Any,
    ) -> CommandHandle:
        """Reset the current room against authored data plus persistent overrides."""
        resolved_persistence = _resolve_persistence_runtime(
            services=services,
            persistence_runtime=persistence_runtime,
        )
        if resolved_persistence is None:
            return ImmediateHandle()
        requested_entity_ids = list(entity_ids or [])
        if entity_id not in (None, ""):
            requested_entity_ids.append(str(entity_id))
        resolved_persistence.request_reset(
            kind="transient",
            apply=apply,
            entity_ids=requested_entity_ids,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
        )
        return ImmediateHandle()

    @registry.register("reset_persistent_state")
    def reset_persistent_state(
        services: CommandServices | None,
        persistence_runtime: PersistenceRuntimeLike | None,
        *,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        apply: str = "immediate",
        **_: Any,
    ) -> CommandHandle:
        """Clear persistent overrides for the current room or matching tagged entities."""
        resolved_persistence = _resolve_persistence_runtime(
            services=services,
            persistence_runtime=persistence_runtime,
        )
        if resolved_persistence is None:
            return ImmediateHandle()
        resolved_persistence.request_reset(
            kind="persistent",
            apply=apply,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
        )
        return ImmediateHandle()
