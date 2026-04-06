"""Queue and execute command requests with lightweight async handles."""

from __future__ import annotations

from collections import deque
import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from dungeon_engine.commands.runner_query_values import load_area_owned_snapshot
from dungeon_engine.commands.runner_resolution import (
    dynamic_deferred_keys_for_spec as _dynamic_deferred_keys_for_spec,
    resolve_deferred_runtime_value as _resolve_deferred_runtime_value,
    resolve_run_project_command_spec as _resolve_run_project_command_spec,
    resolve_runtime_values as _resolve_runtime_values,
)
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
    dialogue_runtime: Any | None = None
    inventory_runtime: Any | None = None
    command_runner: Any | None = None
    random_generator: Any | None = None
    persistence_runtime: Any | None = None
    request_area_change: Callable[["AreaTransitionRequest"], None] | None = None
    request_new_game: Callable[["AreaTransitionRequest"], None] | None = None
    request_load_game: Callable[[str | None], None] | None = None
    save_game: Callable[[str | None], bool] | None = None
    request_quit: Callable[[], None] | None = None
    debug_inspection_enabled: bool = False
    set_simulation_paused: Callable[[bool], None] | None = None
    get_simulation_paused: Callable[[], bool] | None = None
    request_step_simulation_tick: Callable[[], None] | None = None
    adjust_output_scale: Callable[[int], None] | None = None
    project_command_stack: list[str] = field(default_factory=list)
    command_trace: list[str] = field(default_factory=list)
    json_file_cache: dict[Path, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CameraFollowRequest:
    """Requested camera follow state to apply after a transition completes."""

    mode: str = "preserve"
    entity_id: str | None = None
    action: str | None = None
    offset_x: float = 0.0
    offset_y: float = 0.0


@dataclass(slots=True)
class AreaTransitionRequest:
    """One deferred area transition plus optional entity/camera transfer data."""

    area_id: str
    entry_id: str | None = None
    destination_entity_id: str | None = None
    transfer_entity_ids: list[str] = field(default_factory=list)
    camera_follow: CameraFollowRequest | None = None


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


def execute_registered_command(
    registry: Any,
    context: CommandContext,
    name: str,
    params: dict[str, Any],
) -> CommandHandle:
    """Execute a registered command with one already-resolved parameter dictionary."""
    command_params = dict(params)
    disallowed_lifecycle_keys = {"on_complete", "on_start", "on_end"} & set(command_params)
    if disallowed_lifecycle_keys:
        forbidden = sorted(disallowed_lifecycle_keys)
        if forbidden == ["on_complete"]:
            message = (
                f"Command '{name}' must not use 'on_complete'; "
                "use explicit sequencing with 'run_commands' instead."
            )
        else:
            formatted = ", ".join(f"'{key}'" for key in forbidden)
            message = (
                f"Command '{name}' must not use lifecycle wrapper field(s) {formatted}; "
                "use explicit sequencing with 'run_commands', grouped overlap with "
                "'run_parallel', or fire-and-forget overlap with 'spawn_flow' instead."
            )
        raise ValueError(message)
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
    raw_spec = dict(command_spec)
    command_name = str(raw_spec.get("type", ""))
    if command_name == "run_project_command":
        spec = _resolve_run_project_command_spec(raw_spec, context, inherited_params)
    else:
        deferred_keys = set()
        if hasattr(registry, "get_deferred_params"):
            deferred_keys = registry.get_deferred_params(command_name)
        deferred_keys |= _dynamic_deferred_keys_for_spec(command_name, raw_spec)
        if deferred_keys:
            spec = {
                key: _resolve_deferred_runtime_value(value, context, inherited_params)
                if key in deferred_keys
                else _resolve_runtime_values(value, context, inherited_params)
                for key, value in raw_spec.items()
            }
        else:
            spec = _resolve_runtime_values(raw_spec, context, inherited_params)
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
    """Execute pending commands as independent root flows."""

    def __init__(self, registry: Any, context: CommandContext) -> None:
        self.registry = registry
        self.context = context
        self.pending: deque[QueuedCommand] = deque()
        self.root_handles: list[CommandHandle] = []
        self._pending_spawned_root_handles: list[CommandHandle] = []
        self._updating_root_handles = False
        self.last_error_notice: str | None = None
        self.context.command_runner = self

    def enqueue(self, name: str, **params: Any) -> None:
        """Add a command request to the end of the queue."""
        self.pending.append(QueuedCommand(name=name, params=params))

    def dispatch_input_entity_command(
        self,
        entity_id: str,
        command_id: str,
    ) -> bool:
        """Queue one routed input command as an ordinary root flow."""
        params: dict[str, Any] = {
            "entity_id": entity_id,
            "command_id": command_id,
        }
        self.enqueue("run_entity_command", **params)
        return True

    def has_pending_work(self) -> bool:
        """Return True when a command is queued or still running."""
        return bool(self.pending or self.root_handles or self._pending_spawned_root_handles)

    def spawn_root_handle(self, handle: CommandHandle) -> None:
        """Run one handle as an independent root flow."""
        if handle.complete:
            return
        if self._updating_root_handles:
            self._pending_spawned_root_handles.append(handle)
            return
        self.root_handles.append(handle)

    def update(self, dt: float) -> None:
        """Advance all root flows and materialize queued dispatches."""
        try:
            self._materialize_pending_commands()

            if self.root_handles:
                self._updating_root_handles = True
                try:
                    remaining_handles: list[CommandHandle] = []
                    for handle in self.root_handles:
                        handle.update(dt)
                        if not handle.complete:
                            remaining_handles.append(handle)
                    self.root_handles = remaining_handles
                finally:
                    self._updating_root_handles = False

            if self._pending_spawned_root_handles:
                self.root_handles.extend(self._pending_spawned_root_handles)
                self._pending_spawned_root_handles.clear()

            self._materialize_pending_commands()
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
        self.root_handles.clear()
        self._pending_spawned_root_handles.clear()
        self._updating_root_handles = False
        self.pending.clear()
        self.context.command_trace.clear()
        self.last_error_notice = "Command error: see logs/error.log"

    def _materialize_pending_commands(self) -> None:
        """Turn queued requests into root flows or immediate effects."""
        while self.pending:
            queued_command = self.pending.popleft()
            handle = execute_registered_command(
                self.registry,
                self.context,
                queued_command.name,
                queued_command.params,
            )
            self.spawn_root_handle(handle)

