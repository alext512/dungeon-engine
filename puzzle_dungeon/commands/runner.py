"""Queue and execute command requests with lightweight async handles."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from puzzle_dungeon.systems.collision import CollisionSystem
from puzzle_dungeon.systems.interaction import InteractionSystem
from puzzle_dungeon.systems.animation import AnimationSystem
from puzzle_dungeon.systems.movement import MovementSystem
from puzzle_dungeon.world.area import Area
from puzzle_dungeon.world.world import World


@dataclass(slots=True)
class CommandContext:
    """Objects that command implementations need access to at runtime."""

    area: Area
    world: World
    collision_system: CollisionSystem
    movement_system: MovementSystem
    interaction_system: InteractionSystem
    animation_system: AnimationSystem
    camera: Any | None = None
    input_handler: Any | None = None
    persistence_runtime: Any | None = None


class CommandHandle:
    """Base handle for commands that may take more than one frame to finish."""

    def __init__(self) -> None:
        self.complete = False

    def update(self, dt: float) -> None:
        """Advance the command handle toward completion."""


class ImmediateHandle(CommandHandle):
    """A command handle that finishes immediately."""

    def __init__(self) -> None:
        super().__init__()
        self.complete = True


def _normalize_command_list(commands: Any) -> list[dict[str, Any]]:
    """Return a normalized list of command specs."""
    if commands is None:
        return []
    if isinstance(commands, dict):
        return [dict(commands)]
    if isinstance(commands, list):
        return [dict(command) for command in commands]
    raise TypeError("Command list must be a dict or list of dicts.")


class CompletionChainHandle(CommandHandle):
    """Run a follow-up command list after a primary handle completes."""

    def __init__(
        self,
        registry: Any,
        context: CommandContext,
        primary_handle: CommandHandle,
        on_complete: list[dict[str, Any]] | dict[str, Any] | None,
        *,
        base_params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.registry = registry
        self.context = context
        self.primary_handle = primary_handle
        self.on_complete_commands = _normalize_command_list(on_complete)
        self.base_params = dict(base_params or {})
        self.follow_up_handle: CommandHandle | None = None
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Advance the primary handle, then its completion chain."""
        if self.complete:
            return

        if self.follow_up_handle is None:
            self.primary_handle.update(dt)
            if not self.primary_handle.complete:
                return
            if not self.on_complete_commands:
                self.complete = True
                return
            self.follow_up_handle = SequenceCommandHandle(
                self.registry,
                self.context,
                self.on_complete_commands,
                base_params=self.base_params,
            )
            if self.follow_up_handle.complete:
                self.complete = True
                return

        self.follow_up_handle.update(dt)
        if self.follow_up_handle.complete:
            self.complete = True


@dataclass(slots=True)
class QueuedCommand:
    """A pending command request waiting to be executed by the runner."""

    name: str
    params: dict[str, Any]


def execute_registered_command(
    registry: Any,
    context: CommandContext,
    name: str,
    params: dict[str, Any],
) -> CommandHandle:
    """Execute a named command and wrap any generic completion chain."""
    command_params = dict(params)
    on_complete = command_params.pop("on_complete", None)
    handle = registry.execute(name, context, command_params) or ImmediateHandle()
    if on_complete:
        return CompletionChainHandle(
            registry,
            context,
            handle,
            on_complete,
            base_params=command_params,
        )
    return handle


def execute_command_spec(
    registry: Any,
    context: CommandContext,
    command_spec: dict[str, Any],
    *,
    base_params: dict[str, Any] | None = None,
) -> CommandHandle:
    """Execute a single command spec with optional inherited base parameters."""
    spec = dict(command_spec)
    command_name = str(spec.pop("type"))
    params = dict(base_params or {})
    params.update(spec)
    return execute_registered_command(
        registry,
        context,
        command_name,
        params,
    )


class SequenceCommandHandle(CommandHandle):
    """Execute a list of command specs one after another, waiting for async steps."""

    def __init__(
        self,
        registry: Any,
        context: CommandContext,
        commands: list[dict[str, Any]],
        base_params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.registry = registry
        self.context = context
        self.commands = commands
        self.base_params = dict(base_params or {})
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
            self.current_handle = execute_command_spec(
                self.registry,
                self.context,
                command_spec,
                base_params=self.base_params,
            )
            if self.current_handle.complete:
                self.current_handle = None

        if self.current_handle is None and self.current_index >= len(self.commands):
            self.complete = True


class CommandRunner:
    """A small single-lane command queue suitable for the first prototype."""

    def __init__(self, registry: Any, context: CommandContext) -> None:
        self.registry = registry
        self.context = context
        self.pending: deque[QueuedCommand] = deque()
        self.active_handle: CommandHandle | None = None

    def enqueue(self, name: str, **params: Any) -> None:
        """Add a command request to the end of the queue."""
        self.pending.append(QueuedCommand(name=name, params=params))

    def has_pending_work(self) -> bool:
        """Return True when a command is queued or still running."""
        return self.active_handle is not None or bool(self.pending)

    def update(self, dt: float) -> None:
        """Advance the active command and start the next queued command when possible."""
        if self.active_handle is not None:
            self.active_handle.update(dt)
            if self.active_handle.complete:
                self.active_handle = None

        if self.active_handle is None and self.pending:
            queued_command = self.pending.popleft()
            self.active_handle = execute_registered_command(
                self.registry,
                self.context,
                queued_command.name,
                queued_command.params,
            )
