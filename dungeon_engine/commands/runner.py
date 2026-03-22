"""Queue and execute command requests with lightweight async handles."""

from __future__ import annotations

from collections import deque
import copy
from dataclasses import dataclass, field
from typing import Any

from dungeon_engine.systems.collision import CollisionSystem
from dungeon_engine.systems.interaction import InteractionSystem
from dungeon_engine.systems.animation import AnimationSystem
from dungeon_engine.systems.movement import MovementSystem
from dungeon_engine.world.area import Area
from dungeon_engine.world.world import World
from dungeon_engine.logging_utils import get_logger


logger = get_logger(__name__)


@dataclass(slots=True)
class CommandContext:
    """Objects that command implementations need access to at runtime."""

    area: Area
    world: World
    collision_system: CollisionSystem
    movement_system: MovementSystem
    interaction_system: InteractionSystem
    animation_system: AnimationSystem
    project: Any | None = None
    asset_manager: Any | None = None
    text_renderer: Any | None = None
    camera: Any | None = None
    audio_player: Any | None = None
    screen_manager: Any | None = None
    command_runner: Any | None = None
    input_handler: Any | None = None
    persistence_runtime: Any | None = None
    named_command_stack: list[str] = field(default_factory=list)
    command_trace: list[str] = field(default_factory=list)


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


class WaitFramesHandle(CommandHandle):
    """Complete after a fixed number of simulation ticks."""

    def __init__(self, frames: int) -> None:
        super().__init__()
        self.frames_remaining = max(0, int(frames))
        if self.frames_remaining == 0:
            self.complete = True

    def update(self, dt: float) -> None:
        """Advance only on real simulation ticks, not zero-dt bookkeeping updates."""
        if self.complete or dt <= 0:
            return
        self.frames_remaining -= 1
        if self.frames_remaining <= 0:
            self.complete = True


class CommandExecutionError(RuntimeError):
    """Wrap a command failure with execution-trace context for logging/UI hints."""

    def __init__(
        self,
        message: str,
        *,
        command_name: str,
        params: dict[str, Any],
        trace: list[str],
    ) -> None:
        super().__init__(message)
        self.command_name = command_name
        self.params = dict(params)
        self.trace = list(trace)


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


def _describe_command(name: str, params: dict[str, Any]) -> str:
    """Return a short readable label for command trace logging."""
    interesting_parts: list[str] = []
    for key in ("command_id", "event_id", "entity_id", "action"):
        if key in params and params[key] not in ("", None):
            interesting_parts.append(f"{key}={params[key]}")
    if interesting_parts:
        return f"{name}({', '.join(interesting_parts)})"
    return name


def _lookup_nested_value(value: Any, path_parts: list[str]) -> Any:
    """Resolve a nested dict/list path against a Python value."""
    current = value
    for part in path_parts:
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(f"Unknown key '{part}'.")
            current = current[part]
            continue
        if isinstance(current, list):
            try:
                index = int(part)
            except ValueError as exc:
                raise KeyError(f"Expected list index, got '{part}'.") from exc
            try:
                current = current[index]
            except IndexError as exc:
                raise KeyError(f"List index '{index}' is out of range.") from exc
            continue
        raise KeyError(f"Cannot descend into '{part}'.")
    return current


def _resolve_runtime_token(
    token: str,
    context: CommandContext,
    runtime_params: dict[str, Any],
) -> Any:
    """Resolve a $token against event params, project values, or runtime variables."""
    if token.startswith("half:"):
        base_value = _resolve_runtime_token(token[5:], context, runtime_params)
        if not isinstance(base_value, (int, float)):
            raise TypeError(f"$half: expects a numeric value, got {type(base_value).__name__}.")
        if isinstance(base_value, int):
            return max(1, base_value // 2)
        return base_value / 2

    if token in runtime_params:
        return copy.deepcopy(runtime_params[token])

    parts = [part for part in token.split(".") if part]
    if not parts:
        raise KeyError("Empty runtime token.")

    head, tail = parts[0], parts[1:]
    if head in runtime_params:
        return copy.deepcopy(_lookup_nested_value(runtime_params[head], tail))

    if head == "project":
        if context.project is None:
            raise KeyError("No active project context for $project lookup.")
        return copy.deepcopy(context.project.resolve_shared_variable(tail))

    if head == "world":
        return copy.deepcopy(_lookup_nested_value(context.world.variables, tail))

    if head in {"self", "source"}:
        entity_id = runtime_params.get("source_entity_id")
        if not entity_id:
            raise KeyError(f"Token '${token}' requires a source entity context.")
        entity = context.world.get_entity(str(entity_id))
        if entity is None:
            raise KeyError(f"Token '${token}' references missing source entity '{entity_id}'.")
        return copy.deepcopy(_lookup_nested_value(entity.variables, tail))

    if head == "actor":
        entity_id = runtime_params.get("actor_entity_id")
        if not entity_id:
            raise KeyError(f"Token '${token}' requires an actor entity context.")
        entity = context.world.get_entity(str(entity_id))
        if entity is None:
            raise KeyError(f"Token '${token}' references missing actor entity '{entity_id}'.")
        return copy.deepcopy(_lookup_nested_value(entity.variables, tail))

    raise KeyError(f"Unknown runtime token '${token}'.")


def _resolve_runtime_values(
    value: Any,
    context: CommandContext,
    runtime_params: dict[str, Any],
) -> Any:
    """Resolve $tokens recursively inside a command spec before execution."""
    if isinstance(value, dict):
        return {
            key: _resolve_runtime_values(item, context, runtime_params)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            _resolve_runtime_values(item, context, runtime_params)
            for item in value
        ]

    if isinstance(value, str):
        token = None
        if value.startswith("${") and value.endswith("}"):
            token = value[2:-1]
        elif value.startswith("$"):
            token = value[1:]
        if token is not None:
            return _resolve_runtime_token(token, context, runtime_params)

    return value


def execute_registered_command(
    registry: Any,
    context: CommandContext,
    name: str,
    params: dict[str, Any],
) -> CommandHandle:
    """Execute a named command and wrap any generic completion chain."""
    command_params = dict(params)
    on_complete = command_params.pop("on_complete", None)
    trace_entry = _describe_command(name, command_params)
    context.command_trace.append(trace_entry)
    try:
        handle = registry.execute(name, context, command_params) or ImmediateHandle()
    except CommandExecutionError:
        raise
    except Exception as exc:
        trace_snapshot = list(context.command_trace)
        raise CommandExecutionError(
            f"Command '{name}' failed.",
            command_name=name,
            params=command_params,
            trace=trace_snapshot,
        ) from exc
    finally:
        if context.command_trace and context.command_trace[-1] == trace_entry:
            context.command_trace.pop()
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
    inherited_params = dict(base_params or {})
    spec = _resolve_runtime_values(dict(command_spec), context, inherited_params)
    command_name = str(spec.pop("type"))
    params = dict(inherited_params)
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
        *,
        auto_start: bool = True,
    ) -> None:
        super().__init__()
        self.registry = registry
        self.context = context
        self.commands = commands
        self.base_params = dict(base_params or {})
        self.current_index = 0
        self.current_handle: CommandHandle | None = None
        if auto_start:
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
        self.background_handles: list[CommandHandle] = []
        self.last_error_notice: str | None = None
        self.context.command_runner = self

    def enqueue(self, name: str, **params: Any) -> None:
        """Add a command request to the end of the queue."""
        self.pending.append(QueuedCommand(name=name, params=params))

    def has_pending_work(self) -> bool:
        """Return True when a command is queued or still running."""
        return self.active_handle is not None or bool(self.pending)

    def spawn_background_handle(self, handle: CommandHandle) -> None:
        """Run a handle in parallel with the main command lane."""
        if handle.complete:
            return
        self.background_handles.append(handle)

    def update(self, dt: float) -> None:
        """Advance the active command and start the next queued command when possible."""
        try:
            if self.background_handles:
                remaining_handles: list[CommandHandle] = []
                for handle in self.background_handles:
                    handle.update(dt)
                    if not handle.complete:
                        remaining_handles.append(handle)
                self.background_handles = remaining_handles

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
        except CommandExecutionError as exc:
            self._handle_command_error(exc)
        except Exception as exc:
            wrapped = CommandExecutionError(
                "Command runner update failed.",
                command_name="<runner>",
                params={},
                trace=list(self.context.command_trace),
            )
            wrapped.__cause__ = exc
            self._handle_command_error(wrapped)

    def _handle_command_error(self, exc: CommandExecutionError) -> None:
        """Log a command error once and stop the current lane cleanly."""
        cause = exc.__cause__
        trace_text = " -> ".join(exc.trace) if exc.trace else "<no trace>"
        logger.exception(
            "Command execution error: %s | trace=%s | params=%s",
            exc,
            trace_text,
            exc.params,
            exc_info=(type(cause), cause, cause.__traceback__) if cause is not None else None,
        )
        self.active_handle = None
        self.background_handles.clear()
        self.pending.clear()
        self.context.command_trace.clear()
        self.last_error_notice = "Command error: see logs/error.log"

