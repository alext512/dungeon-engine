"""Queue and execute command requests with lightweight async handles."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any

from puzzle_dungeon.systems.collision import CollisionSystem
from puzzle_dungeon.systems.interaction import InteractionSystem
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


@dataclass(slots=True)
class QueuedCommand:
    """A pending command request waiting to be executed by the runner."""

    name: str
    params: dict[str, Any]


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
            handle = self.registry.execute(
                queued_command.name,
                self.context,
                queued_command.params,
            )
            self.active_handle = handle or ImmediateHandle()
