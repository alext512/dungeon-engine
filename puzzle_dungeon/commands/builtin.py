"""Starter command implementations used by the first prototype slice."""

from __future__ import annotations

import copy
from typing import Any

from puzzle_dungeon.commands.registry import CommandRegistry
from puzzle_dungeon.commands.runner import CommandContext, CommandHandle, ImmediateHandle


class MovementCommandHandle(CommandHandle):
    """Wait until all entities started by a move command finish interpolating."""

    def __init__(self, context: CommandContext, entity_ids: list[str]) -> None:
        super().__init__()
        self.context = context
        self.entity_ids = entity_ids
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when every moved entity has stopped moving."""
        self.complete = not any(
            self.context.movement_system.is_entity_moving(entity_id)
            for entity_id in self.entity_ids
        )


class SequenceCommandHandle(CommandHandle):
    """Execute a list of command specs one after another, waiting for async steps."""

    def __init__(
        self,
        registry: CommandRegistry,
        context: CommandContext,
        commands: list[dict[str, Any]],
        base_params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.registry = registry
        self.context = context
        self.commands = commands
        self.base_params = base_params or {}
        self.current_index = 0
        self.current_handle: CommandHandle | None = None
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Advance the current child command and start the next one when ready."""
        if self.complete:
            return

        if self.current_handle is not None:
            self.current_handle.update(dt)
            if self.current_handle.complete:
                self.current_handle = None

        while self.current_handle is None and self.current_index < len(self.commands):
            command_spec = dict(self.commands[self.current_index])
            self.current_index += 1
            command_name = str(command_spec.pop("type"))
            params = dict(self.base_params)
            params.update(command_spec)
            self.current_handle = self.registry.execute(
                command_name,
                self.context,
                params,
            ) or ImmediateHandle()
            if self.current_handle.complete:
                self.current_handle = None

        if self.current_handle is None and self.current_index >= len(self.commands):
            self.complete = True


def _resolve_entity_id(
    entity_id: str,
    *,
    source_entity_id: str | None,
    actor_entity_id: str | None,
) -> str:
    """Resolve special entity references used inside command specs."""
    if entity_id == "self":
        if source_entity_id is None:
            raise ValueError("Command used 'self' without a source entity context.")
        return source_entity_id
    if entity_id == "actor":
        if actor_entity_id is None:
            raise ValueError("Command used 'actor' without an actor entity context.")
        return actor_entity_id
    return entity_id


def _resolve_variables(
    context: CommandContext,
    *,
    scope: str,
    entity_id: str | None = None,
    source_entity_id: str | None = None,
    actor_entity_id: str | None = None,
) -> dict[str, Any]:
    """Return the variables dict for the given scope."""
    if scope == "world":
        return context.world.variables
    if scope == "entity":
        if entity_id is None:
            raise ValueError("Entity scope requires entity_id.")
        resolved = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        entity = context.world.get_entity(resolved)
        if entity is None:
            raise KeyError(f"Entity '{resolved}' not found.")
        return entity.variables
    raise ValueError(f"Unknown variable scope '{scope}'.")


def _persist_entity_field(
    context: CommandContext,
    *,
    entity_id: str,
    field_name: str,
    value: Any,
) -> None:
    """Persist a single entity field when runtime persistence is available."""
    if context.persistence_runtime is None:
        return
    context.persistence_runtime.set_entity_field(entity_id, field_name, value)


_COMPARE_OPS: dict[str, Any] = {
    "eq": lambda a, b: a == b,
    "neq": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and b is not None and a > b,
    "lt": lambda a, b: a is not None and b is not None and a < b,
    "gte": lambda a, b: a is not None and b is not None and a >= b,
    "lte": lambda a, b: a is not None and b is not None and a <= b,
}


def register_builtin_commands(registry: CommandRegistry) -> None:
    """Register the minimal command set needed for the first movement slice."""

    def _step_entity(
        context: CommandContext,
        *,
        entity_id: str,
        direction: str,
        **_: Any,
    ) -> CommandHandle:
        moved_entity_ids = context.movement_system.request_step(entity_id, direction)  # type: ignore[arg-type]
        if not moved_entity_ids:
            return ImmediateHandle()
        return MovementCommandHandle(context, moved_entity_ids)

    @registry.register("player_step")
    def player_step(
        context: CommandContext,
        *,
        entity_id: str,
        direction: str,
        **_: Any,
    ) -> CommandHandle:
        """Top-level player movement command triggered by input."""
        return _step_entity(context, entity_id=entity_id, direction=direction)

    @registry.register("step_entity")
    def step_entity(
        context: CommandContext,
        *,
        entity_id: str,
        direction: str,
        **_: Any,
    ) -> CommandHandle:
        """Reusable generic entity step command for future AI and cinematics."""
        return _step_entity(context, entity_id=entity_id, direction=direction)

    @registry.register("player_interact")
    def player_interact(
        context: CommandContext,
        *,
        entity_id: str,
        **_: Any,
    ) -> CommandHandle:
        """Activate the first enabled entity in front of the actor."""
        target_entity = context.interaction_system.get_facing_target(entity_id)
        if target_entity is None or not target_entity.interact_commands:
            return ImmediateHandle()
        return SequenceCommandHandle(
            registry,
            context,
            target_entity.interact_commands,
            base_params={
                "source_entity_id": target_entity.entity_id,
                "actor_entity_id": entity_id,
            },
        )

    @registry.register("set_visible")
    def set_visible(
        context: CommandContext,
        *,
        entity_id: str,
        visible: bool,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Change whether an entity is rendered and targetable."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set visibility on missing entity '{resolved_id}'.")
        entity.visible = visible
        if persistent:
            _persist_entity_field(
                context,
                entity_id=resolved_id,
                field_name="visible",
                value=visible,
            )
        return ImmediateHandle()

    @registry.register("set_solid")
    def set_solid(
        context: CommandContext,
        *,
        entity_id: str,
        solid: bool,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Change whether an entity blocks movement."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set solidity on missing entity '{resolved_id}'.")
        entity.solid = solid
        if persistent:
            _persist_entity_field(
                context,
                entity_id=resolved_id,
                field_name="solid",
                value=solid,
            )
        return ImmediateHandle()

    @registry.register("set_enabled")
    def set_enabled(
        context: CommandContext,
        *,
        entity_id: str,
        enabled: bool,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Change whether an entity can still be interacted with."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set enabled state on missing entity '{resolved_id}'.")
        entity.enabled = enabled
        if persistent:
            _persist_entity_field(
                context,
                entity_id=resolved_id,
                field_name="enabled",
                value=enabled,
            )
        return ImmediateHandle()

    @registry.register("set_color")
    def set_color(
        context: CommandContext,
        *,
        entity_id: str,
        color: list[int],
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Change an entity's debug-render color."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set color on missing entity '{resolved_id}'.")
        entity.color = (int(color[0]), int(color[1]), int(color[2]))
        if persistent:
            _persist_entity_field(
                context,
                entity_id=resolved_id,
                field_name="color",
                value=list(entity.color),
            )
        return ImmediateHandle()

    @registry.register("remove_entity")
    def remove_entity(
        context: CommandContext,
        *,
        entity_id: str,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Remove an entity from the current room."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        if context.world.get_entity(resolved_id) is None:
            raise KeyError(f"Cannot remove missing entity '{resolved_id}'.")
        context.world.remove_entity(resolved_id)
        if persistent and context.persistence_runtime is not None:
            context.persistence_runtime.remove_entity(resolved_id)
        return ImmediateHandle()

    @registry.register("set_var")
    def set_var(
        context: CommandContext,
        *,
        name: str,
        value: Any,
        scope: str = "entity",
        persistent: bool = False,
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Set a variable to a value in the given scope."""
        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        persisted_value = copy.deepcopy(value)
        variables[name] = persisted_value
        if persistent and context.persistence_runtime is not None:
            if scope == "world":
                context.persistence_runtime.set_world_variable(name, persisted_value)
            else:
                if entity_id is None:
                    raise ValueError("Persistent entity variable set requires entity_id.")
                resolved_id = _resolve_entity_id(
                    entity_id,
                    source_entity_id=source_entity_id,
                    actor_entity_id=actor_entity_id,
                )
                context.persistence_runtime.set_entity_variable(resolved_id, name, persisted_value)
        return ImmediateHandle()

    @registry.register("increment_var")
    def increment_var(
        context: CommandContext,
        *,
        name: str,
        amount: int | float = 1,
        scope: str = "entity",
        persistent: bool = False,
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Add an amount to a numeric variable (defaults to 0 if missing)."""
        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        variables[name] = variables.get(name, 0) + amount
        if persistent and context.persistence_runtime is not None:
            if scope == "world":
                context.persistence_runtime.set_world_variable(name, variables[name])
            else:
                if entity_id is None:
                    raise ValueError("Persistent entity variable increment requires entity_id.")
                resolved_id = _resolve_entity_id(
                    entity_id,
                    source_entity_id=source_entity_id,
                    actor_entity_id=actor_entity_id,
                )
                context.persistence_runtime.set_entity_variable(resolved_id, name, variables[name])
        return ImmediateHandle()

    @registry.register("check_var")
    def check_var(
        context: CommandContext,
        *,
        name: str,
        op: str = "eq",
        value: Any = None,
        scope: str = "entity",
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        then: list[dict[str, Any]] | None = None,
        **kw: Any,
    ) -> CommandHandle:
        """Branch based on a variable condition."""
        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
        )
        current = variables.get(name)
        comparator = _COMPARE_OPS.get(op)
        if comparator is None:
            raise ValueError(f"Unknown comparison operator '{op}'.")
        condition_met = comparator(current, value)
        branch = then if condition_met else kw.get("else")
        if branch:
            base_params: dict[str, Any] = {}
            if source_entity_id is not None:
                base_params["source_entity_id"] = source_entity_id
            if actor_entity_id is not None:
                base_params["actor_entity_id"] = actor_entity_id
            return SequenceCommandHandle(registry, context, branch, base_params=base_params)
        return ImmediateHandle()

    @registry.register("reset_transient_state")
    def reset_transient_state(
        context: CommandContext,
        *,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        apply: str = "immediate",
        **_: Any,
    ) -> CommandHandle:
        """Reset the current room against authored data plus persistent overrides."""
        if context.persistence_runtime is None:
            return ImmediateHandle()
        context.persistence_runtime.request_reset(
            kind="transient",
            apply=apply,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
        )
        return ImmediateHandle()

    @registry.register("reset_persistent_state")
    def reset_persistent_state(
        context: CommandContext,
        *,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        apply: str = "immediate",
        **_: Any,
    ) -> CommandHandle:
        """Clear persistent overrides for the current room or matching tagged entities."""
        if context.persistence_runtime is None:
            return ImmediateHandle()
        context.persistence_runtime.request_reset(
            kind="persistent",
            apply=apply,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
        )
        return ImmediateHandle()
