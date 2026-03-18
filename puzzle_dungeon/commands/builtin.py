"""Starter command implementations used by the first prototype slice."""

from __future__ import annotations

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
        return ImmediateHandle()

    @registry.register("set_solid")
    def set_solid(
        context: CommandContext,
        *,
        entity_id: str,
        solid: bool,
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
        return ImmediateHandle()

    @registry.register("set_enabled")
    def set_enabled(
        context: CommandContext,
        *,
        entity_id: str,
        enabled: bool,
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
        return ImmediateHandle()

    @registry.register("set_color")
    def set_color(
        context: CommandContext,
        *,
        entity_id: str,
        color: list[int],
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
        return ImmediateHandle()
