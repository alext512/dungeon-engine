"""Queue and execute command requests with lightweight async handles."""

from __future__ import annotations

from collections import deque
import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from random import Random

    from dungeon_engine.engine.asset_manager import AssetManager
    from dungeon_engine.project_context import ProjectContext

from dungeon_engine.commands.context_services import CommandServices
from dungeon_engine.commands.runner_query_values import load_area_owned_snapshot
from dungeon_engine.commands.runner_resolution import (
    dynamic_deferred_keys_for_spec as _dynamic_deferred_keys_for_spec,
    resolve_deferred_runtime_value as _resolve_deferred_runtime_value,
    resolve_run_project_command_spec as _resolve_run_project_command_spec,
    resolve_runtime_values as _resolve_runtime_values,
)
from dungeon_engine.logging_utils import get_logger


logger = get_logger(__name__)


@dataclass(slots=True)
class CommandContext:
    """Objects that command implementations need access to at runtime."""

    project: ProjectContext | None = None
    asset_manager: AssetManager | None = None
    services: CommandServices = field(default_factory=CommandServices)
    command_runner: CommandRunner | None = None
    random_generator: Random | None = None
    project_command_stack: list[str] = field(default_factory=list)
    command_trace: list[str] = field(default_factory=list)
    json_file_cache: dict[Path, Any] = field(default_factory=dict)
    command_execution_count: int = 0
    command_execution_budget_remaining: int | None = None


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
                "use explicit sequencing with 'run_sequence' instead."
            )
        else:
            formatted = ", ".join(f"'{key}'" for key in forbidden)
            message = (
                f"Command '{name}' must not use lifecycle wrapper field(s) {formatted}; "
                "use explicit sequencing with 'run_sequence', grouped overlap with "
                "'run_parallel', or fire-and-forget overlap with 'spawn_flow' instead."
            )
        raise ValueError(message)
    trace_entry = _describe_command(name, command_params)
    context.command_trace.append(trace_entry)
    try:
        if context.command_execution_budget_remaining is not None:
            if context.command_execution_budget_remaining <= 0:
                raise CommandExecutionError(
                    "Command settle exceeded the immediate-command safety limit.",
                    command_name=name,
                    params=command_params,
                    trace=list(context.command_trace),
                )
            context.command_execution_budget_remaining -= 1
        context.command_execution_count += 1
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
            runner = getattr(self.context, "command_runner", None)
            if bool(getattr(runner, "scene_boundary_requested", False)):
                self.complete = True
                return

            command_spec = dict(self.commands[self.current_index])
            self.current_index += 1
            self.current_handle = execute_command_spec(
                self.registry,
                self.context,
                command_spec,
                base_params=self.base_params,
            )
            if bool(getattr(runner, "scene_boundary_requested", False)):
                self.current_handle = None
                self.complete = True
                return
            if self.current_handle.complete:
                self.current_handle = None

        if self.current_handle is None and self.current_index >= len(self.commands):
            self.complete = True


class CommandRunner:
    """Execute pending commands as independent root flows."""

    def __init__(
        self,
        registry: Any,
        context: CommandContext,
        *,
        max_settle_passes: int | None = None,
        max_immediate_commands_per_settle: int | None = None,
        log_settle_usage_peaks: bool | None = None,
        settle_warning_ratio: float | None = None,
    ) -> None:
        self.registry = registry
        self.context = context
        self.pending: deque[QueuedCommand] = deque()
        self.root_handles: list[CommandHandle] = []
        self._pending_spawned_root_handles: list[CommandHandle] = []
        self._updating_root_handles = False
        self._scene_boundary_requested = False
        self.last_error_notice: str | None = None
        self.context.command_runner = self
        runtime_config = getattr(context.project, "command_runtime", None)
        self.max_settle_passes = max(
            1,
            int(
                max_settle_passes
                if max_settle_passes is not None
                else getattr(runtime_config, "max_settle_passes", 128)
            ),
        )
        self.max_immediate_commands_per_settle = max(
            1,
            int(
                max_immediate_commands_per_settle
                if max_immediate_commands_per_settle is not None
                else getattr(runtime_config, "max_immediate_commands_per_settle", 8192)
            ),
        )
        self.log_settle_usage_peaks = bool(
            log_settle_usage_peaks
            if log_settle_usage_peaks is not None
            else getattr(runtime_config, "log_settle_usage_peaks", False)
        )
        self.settle_warning_ratio = max(
            0.0,
            min(
                1.0,
                float(
                    settle_warning_ratio
                    if settle_warning_ratio is not None
                    else getattr(runtime_config, "settle_warning_ratio", 0.75)
                ),
            ),
        )
        self.peak_settle_passes = 0
        self.peak_immediate_commands_per_settle = 0
        self._settle_pass_warning_emitted = False
        self._immediate_command_warning_emitted = False

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

    @property
    def scene_boundary_requested(self) -> bool:
        """Return whether a scene-changing command requested a runtime boundary."""
        return bool(self._scene_boundary_requested)

    def request_scene_boundary(self) -> None:
        """Mark current command work as obsolete because the scene will change."""
        self._scene_boundary_requested = True
        self.pending.clear()
        self._pending_spawned_root_handles.clear()
        if not self._updating_root_handles:
            self.root_handles.clear()

    def clear_scene_boundary_request(self) -> None:
        """Clear the scene-boundary marker after the game applies the boundary."""
        self._scene_boundary_requested = False

    def cancel_all_work(self) -> None:
        """Cancel queued and active command work without reporting an error."""
        self.pending.clear()
        self.root_handles.clear()
        self._pending_spawned_root_handles.clear()
        self._updating_root_handles = False
        self.context.command_trace.clear()

    def spawn_root_handle(self, handle: CommandHandle) -> None:
        """Run one handle as an independent root flow."""
        if handle.complete:
            return
        if self._updating_root_handles:
            self._pending_spawned_root_handles.append(handle)
            return
        self.root_handles.append(handle)

    def settle(self) -> None:
        """Run ready command work until every remaining flow is genuinely waiting."""
        try:
            self._settle()
        except CommandExecutionError as exc:
            self._handle_command_error(exc)
        except Exception as exc:
            wrapped = CommandExecutionError(
                "Command runner settle failed.",
                command_name="<runner>",
                params={},
                trace=list(self.context.command_trace),
            )
            wrapped.__cause__ = exc
            self._handle_command_error(wrapped)

    def advance_tick(self, dt: float) -> None:
        """Advance waiting command handles by one simulation tick."""
        try:
            self._with_command_budget(
                lambda: self._update_once(dt),
                limit=self.max_immediate_commands_per_settle,
            )
        except CommandExecutionError as exc:
            self._handle_command_error(exc)
        except Exception as exc:
            wrapped = CommandExecutionError(
                "Command runner tick advance failed.",
                command_name="<runner>",
                params={},
                trace=list(self.context.command_trace),
            )
            wrapped.__cause__ = exc
            self._handle_command_error(wrapped)

    def update(self, dt: float) -> None:
        """Advance the runner, settling on zero-dt passes and ticking otherwise."""
        if dt <= 0:
            self.settle()
            return
        self.advance_tick(dt)

    def _settle(self) -> None:
        command_count_before = self.context.command_execution_count
        passes_used = 0
        try:
            self.context.command_execution_budget_remaining = (
                self.max_immediate_commands_per_settle
            )
            for pass_index in range(self.max_settle_passes):
                passes_used = pass_index + 1
                signature_before = self._settle_signature()
                command_count_before_pass = self.context.command_execution_count
                self._update_once(0.0)
                command_count_after_pass = self.context.command_execution_count
                signature_after = self._settle_signature()
                commands_ran = command_count_after_pass > command_count_before_pass
                if not commands_ran and signature_after == signature_before:
                    self._record_settle_usage(
                        passes_used=passes_used,
                        command_count=self.context.command_execution_count - command_count_before,
                    )
                    return

            raise CommandExecutionError(
                f"Command settle exceeded max_settle_passes={self.max_settle_passes}.",
                command_name="<runner>",
                params={},
                trace=list(self.context.command_trace),
            )
        finally:
            self.context.command_execution_budget_remaining = None

    def _with_command_budget(self, callback: Callable[[], None], *, limit: int) -> None:
        previous_budget = self.context.command_execution_budget_remaining
        self.context.command_execution_budget_remaining = int(limit)
        try:
            callback()
        finally:
            self.context.command_execution_budget_remaining = previous_budget

    def _update_once(self, dt: float) -> None:
        """Advance all root flows once and materialize queued dispatches."""
        try:
            self._materialize_pending_commands()

            if self.root_handles:
                self._updating_root_handles = True
                try:
                    remaining_handles: list[CommandHandle] = []
                    for handle in self.root_handles:
                        if self._scene_boundary_requested:
                            break
                        handle.update(dt)
                        if self._scene_boundary_requested:
                            break
                        if not handle.complete:
                            remaining_handles.append(handle)
                    self.root_handles = remaining_handles
                finally:
                    self._updating_root_handles = False

            if self._scene_boundary_requested:
                self.pending.clear()
                self.root_handles.clear()
                self._pending_spawned_root_handles.clear()
                return

            if self._pending_spawned_root_handles:
                self.root_handles.extend(self._pending_spawned_root_handles)
                self._pending_spawned_root_handles.clear()

            self._materialize_pending_commands()
        except CommandExecutionError as exc:
            raise
        except Exception as exc:
            wrapped = CommandExecutionError(
                "Command runner update failed.",
                command_name="<runner>",
                params={},
                trace=list(self.context.command_trace),
            )
            wrapped.__cause__ = exc
            raise wrapped

    def _settle_signature(self) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        """Return a compact snapshot for detecting settle progress."""
        return (
            tuple(queued.name for queued in self.pending),
            tuple(
                f"{id(handle)}:{type(handle).__name__}:{handle.complete}"
                for handle in self.root_handles
            ),
            tuple(
                f"{id(handle)}:{type(handle).__name__}:{handle.complete}"
                for handle in self._pending_spawned_root_handles
            ),
        )

    def _record_settle_usage(self, *, passes_used: int, command_count: int) -> None:
        """Track and optionally log peak settle workload for diagnostics."""
        previous_peak = (
            self.peak_settle_passes,
            self.peak_immediate_commands_per_settle,
        )
        self.peak_settle_passes = max(self.peak_settle_passes, int(passes_used))
        self.peak_immediate_commands_per_settle = max(
            self.peak_immediate_commands_per_settle,
            int(command_count),
        )
        self._warn_on_high_settle_usage(
            passes_used=passes_used,
            command_count=command_count,
        )
        if (
            not self.log_settle_usage_peaks
            or previous_peak
            == (
                self.peak_settle_passes,
                self.peak_immediate_commands_per_settle,
            )
        ):
            return
        logger.info(
            "Command settle usage peak: passes=%s immediate_commands=%s",
            self.peak_settle_passes,
            self.peak_immediate_commands_per_settle,
        )

    def _warn_on_high_settle_usage(self, *, passes_used: int, command_count: int) -> None:
        """Log a warning once when a settle workload gets close to a safety fuse."""
        if self.settle_warning_ratio <= 0:
            return
        pass_threshold = max(1, int(self.max_settle_passes * self.settle_warning_ratio))
        command_threshold = max(
            1,
            int(self.max_immediate_commands_per_settle * self.settle_warning_ratio),
        )
        if not self._settle_pass_warning_emitted and passes_used >= pass_threshold:
            self._settle_pass_warning_emitted = True
            logger.warning(
                "Command settle used %s/%s passes; check for large immediate command cascades.",
                passes_used,
                self.max_settle_passes,
            )
        if (
            not self._immediate_command_warning_emitted
            and command_count >= command_threshold
        ):
            self._immediate_command_warning_emitted = True
            logger.warning(
                "Command settle executed %s/%s immediate commands; check for large command cascades.",
                command_count,
                self.max_immediate_commands_per_settle,
            )

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
        self.cancel_all_work()
        self._scene_boundary_requested = False
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
            if self._scene_boundary_requested:
                self.pending.clear()
                return

