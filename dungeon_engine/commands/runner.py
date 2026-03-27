"""Queue and execute command requests with lightweight async handles."""

from __future__ import annotations

from collections import deque
import copy
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Callable

from dungeon_engine import config
from dungeon_engine.systems.collision import CollisionSystem
from dungeon_engine.systems.interaction import InteractionSystem
from dungeon_engine.systems.animation import AnimationSystem
from dungeon_engine.systems.movement import MovementSystem
from dungeon_engine.world.area import Area
from dungeon_engine.world.world import World
from dungeon_engine.logging_utils import get_logger


logger = get_logger(__name__)
_JSON_FILE_CACHE: dict[Path, Any] = {}


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
    request_area_change: Callable[["AreaTransitionRequest"], None] | None = None
    request_new_game: Callable[["AreaTransitionRequest"], None] | None = None
    request_load_game: Callable[[str | None], None] | None = None
    save_game: Callable[[str | None], bool] | None = None
    request_quit: Callable[[], None] | None = None
    named_command_stack: list[str] = field(default_factory=list)
    command_trace: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CameraFollowRequest:
    """Requested camera follow state to apply after a transition completes."""

    mode: str = "preserve"
    entity_id: str | None = None
    input_action: str | None = None
    offset_x: float = 0.0
    offset_y: float = 0.0


@dataclass(slots=True)
class AreaTransitionRequest:
    """One deferred area transition plus optional entity/camera transfer data."""

    area_id: str
    entry_id: str | None = None
    transfer_entity_ids: list[str] = field(default_factory=list)
    camera_follow: CameraFollowRequest | None = None


class CommandHandle:
    """Base handle for commands that may take more than one frame to finish."""

    def __init__(self) -> None:
        self.complete = False
        self.captures_menu_input = False
        self.allow_entity_input = False

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


class LifecycleChainHandle(CommandHandle):
    """Run optional on_start/on_end command lists around a primary handle."""

    def __init__(
        self,
        registry: Any,
        context: CommandContext,
        primary_handle: CommandHandle,
        on_start: list[dict[str, Any]] | dict[str, Any] | None,
        on_end: list[dict[str, Any]] | dict[str, Any] | None,
        *,
        base_params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.registry = registry
        self.context = context
        self.primary_handle = primary_handle
        self.on_start_commands = _normalize_command_list(on_start)
        self.on_end_commands = _normalize_command_list(on_end)
        self.base_params = dict(base_params or {})
        self.start_handle: CommandHandle | None = None
        self.end_handle: CommandHandle | None = None
        self._start_finished = False
        self._primary_finished = False
        if self.on_start_commands:
            self.start_handle = SequenceCommandHandle(
                self.registry,
                self.context,
                self.on_start_commands,
                base_params=self.base_params,
            )
        else:
            self._start_finished = True
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Advance the on_start hooks, primary handle, then on_end hooks."""
        if self.complete:
            return

        if not self._start_finished:
            assert self.start_handle is not None
            self.start_handle.update(dt)
            self.captures_menu_input = self.start_handle.captures_menu_input
            self.allow_entity_input = self.start_handle.allow_entity_input
            if not self.start_handle.complete:
                return
            self.start_handle = None
            self._start_finished = True

        if not self._primary_finished:
            self.primary_handle.update(dt)
            self.captures_menu_input = self.primary_handle.captures_menu_input
            self.allow_entity_input = self.primary_handle.allow_entity_input
            if not self.primary_handle.complete:
                return
            self._primary_finished = True
            if not self.on_end_commands:
                self.complete = True
                self.captures_menu_input = False
                self.allow_entity_input = False
                return
            self.end_handle = SequenceCommandHandle(
                self.registry,
                self.context,
                self.on_end_commands,
                base_params=self.base_params,
            )
            self.captures_menu_input = self.end_handle.captures_menu_input
            self.allow_entity_input = self.end_handle.allow_entity_input
            if self.end_handle.complete:
                self.complete = True
                self.captures_menu_input = False
                self.allow_entity_input = False
                return

        assert self.end_handle is not None
        self.end_handle.update(dt)
        self.captures_menu_input = self.end_handle.captures_menu_input
        self.allow_entity_input = self.end_handle.allow_entity_input
        if self.end_handle.complete:
            self.complete = True
            self.captures_menu_input = False
            self.allow_entity_input = False


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


def _resolve_json_file_path(context: CommandContext, path: str) -> Path:
    """Resolve one JSON file path relative to the active project when needed."""
    resolved_path = Path(str(path).strip())
    if not resolved_path.is_absolute():
        if context.project is not None:
            resolved_path = context.project.project_root / resolved_path
        else:
            resolved_path = Path.cwd() / resolved_path
    return resolved_path.resolve()


def _load_json_file(path: Path) -> Any:
    """Load one JSON file through a small in-memory cache."""
    cached = _JSON_FILE_CACHE.get(path)
    if cached is None:
        cached = json.loads(path.read_text(encoding="utf-8"))
        _JSON_FILE_CACHE[path] = cached
    return copy.deepcopy(cached)


def _build_text_window(
    lines: Any,
    *,
    start: int = 0,
    max_lines: int = 1,
    separator: str = "\n",
) -> dict[str, Any]:
    """Return one visible text window plus simple metadata."""
    if lines is None:
        normalized_lines: list[str] = []
    elif isinstance(lines, str):
        normalized_lines = [str(lines)]
    elif isinstance(lines, (list, tuple)):
        normalized_lines = [str(item) for item in lines]
    else:
        raise TypeError(
            "Text-window value source requires lines to be a list, tuple, string, or null."
        )

    resolved_start = max(0, int(start))
    resolved_max_lines = max(0, int(max_lines))
    visible_lines = normalized_lines[resolved_start : resolved_start + resolved_max_lines]
    return {
        "visible_lines": visible_lines,
        "visible_text": str(separator).join(visible_lines),
        "has_more": resolved_start + resolved_max_lines < len(normalized_lines),
        "total_lines": len(normalized_lines),
    }


def _resolve_runtime_value_source(
    source_name: str,
    source_value: Any,
    context: CommandContext,
    runtime_params: dict[str, Any],
) -> Any:
    """Resolve one structured value source before primitive execution."""
    resolved_source = _resolve_runtime_values(source_value, context, runtime_params)

    if source_name == "$json_file":
        if resolved_source in (None, ""):
            raise ValueError("JSON file value source requires a non-empty path.")
        return _load_json_file(_resolve_json_file_path(context, str(resolved_source)))

    if source_name == "$wrapped_lines":
        if context.text_renderer is None:
            raise ValueError("Cannot wrap text without an active text renderer.")
        if not isinstance(resolved_source, dict):
            raise TypeError("$wrapped_lines value source requires a JSON object.")
        return context.text_renderer.wrap_lines(
            "" if resolved_source.get("text") is None else str(resolved_source.get("text")),
            int(resolved_source.get("max_width", 0)),
            font_id=str(resolved_source.get("font_id", config.DEFAULT_UI_FONT_ID)),
        )

    if source_name == "$text_window":
        if not isinstance(resolved_source, dict):
            raise TypeError("$text_window value source requires a JSON object.")
        return _build_text_window(
            resolved_source.get("lines"),
            start=int(resolved_source.get("start", 0)),
            max_lines=int(resolved_source.get("max_lines", 1)),
            separator=str(resolved_source.get("separator", "\n")),
        )

    raise KeyError(f"Unknown value source '{source_name}'.")


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

    if token == "self_id":
        entity_id = runtime_params.get("source_entity_id")
        if not entity_id:
            raise KeyError("Token '$self_id' requires a source entity context.")
        return str(entity_id)

    if token == "actor_id":
        entity_id = runtime_params.get("actor_entity_id")
        if not entity_id:
            raise KeyError("Token '$actor_id' requires an actor entity context.")
        return str(entity_id)

    if token == "caller_id":
        entity_id = runtime_params.get("caller_entity_id")
        if not entity_id:
            raise KeyError("Token '$caller_id' requires a caller entity context.")
        return str(entity_id)

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

    if head == "camera":
        if context.camera is None:
            raise KeyError("No active camera context for $camera lookup.")
        camera_state = context.camera.to_state_dict()
        camera_state.setdefault("follow_mode", "none")
        camera_state.setdefault("follow_entity_id", None)
        camera_state.setdefault("follow_input_action", None)
        camera_state.setdefault("x", None)
        camera_state.setdefault("y", None)
        camera_state.setdefault("follow_offset_x", 0.0)
        camera_state.setdefault("follow_offset_y", 0.0)
        camera_state.setdefault("bounds", None)
        camera_state.setdefault("deadzone", None)
        camera_state["has_bounds"] = camera_state.get("bounds") is not None
        camera_state["has_deadzone"] = camera_state.get("deadzone") is not None
        camera_state["mode"] = camera_state.get("follow_mode")
        if not tail:
            return copy.deepcopy(camera_state)
        return copy.deepcopy(_lookup_nested_value(camera_state, tail))

    if head == "world":
        return copy.deepcopy(_lookup_nested_value(context.world.variables, tail))

    if head == "entity":
        if len(parts) < 3:
            raise KeyError(f"Token '${token}' requires an entity id and variable path.")
        entity_id = parts[1]
        entity = context.world.get_entity(str(entity_id))
        if entity is None:
            raise KeyError(f"Token '${token}' references missing entity '{entity_id}'.")
        return copy.deepcopy(_lookup_nested_value(entity.variables, parts[2:]))

    if head == "self":
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

    if head == "caller":
        entity_id = runtime_params.get("caller_entity_id")
        if not entity_id:
            raise KeyError(f"Token '${token}' requires a caller entity context.")
        entity = context.world.get_entity(str(entity_id))
        if entity is None:
            raise KeyError(f"Token '${token}' references missing caller entity '{entity_id}'.")
        return copy.deepcopy(_lookup_nested_value(entity.variables, tail))

    raise KeyError(f"Unknown runtime token '${token}'.")


def _resolve_runtime_values(
    value: Any,
    context: CommandContext,
    runtime_params: dict[str, Any],
) -> Any:
    """Resolve $tokens recursively inside a command spec before execution."""
    if isinstance(value, dict):
        if len(value) == 1:
            source_name, source_value = next(iter(value.items()))
            if isinstance(source_name, str) and source_name in {
                "$json_file",
                "$wrapped_lines",
                "$text_window",
            }:
                return _resolve_runtime_value_source(
                    source_name,
                    source_value,
                    context,
                    runtime_params,
                )
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


def _resolve_deferred_runtime_value(
    value: Any,
    context: CommandContext,
    runtime_params: dict[str, Any],
) -> Any:
    """Resolve one top-level token while leaving nested command specs untouched."""
    if isinstance(value, str):
        token = None
        if value.startswith("${") and value.endswith("}"):
            token = value[2:-1]
        elif value.startswith("$"):
            token = value[1:]
        if token is not None:
            return _resolve_runtime_token(token, context, runtime_params)
    return copy.deepcopy(value)


_DEFERRED_RUNTIME_COMMAND_KEYS: dict[str, set[str]] = {
    "check_var": {"then", "else"},
    "check_world_var": {"then", "else"},
    "check_entity_var": {"then", "else"},
    "run_event": {"dialogue_on_start", "dialogue_on_end", "segment_hooks"},
    "run_commands": {"commands"},
    "run_detached_commands": {"commands"},
    "run_commands_for_collection": {"commands"},
}


def execute_registered_command(
    registry: Any,
    context: CommandContext,
    name: str,
    params: dict[str, Any],
) -> CommandHandle:
    """Execute a named command and wrap any generic completion chain."""
    command_params = dict(params)
    if "on_complete" in command_params:
        raise ValueError(
            f"Command '{name}' must not use 'on_complete'; use 'on_start' and 'on_end'."
        )
    on_start = command_params.pop("on_start", None)
    on_end = command_params.pop("on_end", None)
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
    if on_start or on_end:
        return LifecycleChainHandle(
            registry,
            context,
            handle,
            on_start,
            on_end,
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
    raw_spec = dict(command_spec)
    command_name = str(raw_spec.get("type", ""))
    deferred_keys = _DEFERRED_RUNTIME_COMMAND_KEYS.get(command_name, set())
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
            self.captures_menu_input = self.current_handle.captures_menu_input
            self.allow_entity_input = self.current_handle.allow_entity_input
            if self.current_handle.complete:
                self.current_handle = None
                self.captures_menu_input = False
                self.allow_entity_input = False

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
                self.captures_menu_input = False
                self.allow_entity_input = False
            else:
                self.captures_menu_input = self.current_handle.captures_menu_input
                self.allow_entity_input = self.current_handle.allow_entity_input

        if self.current_handle is None and self.current_index >= len(self.commands):
            self.complete = True
            self.captures_menu_input = False
            self.allow_entity_input = False


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

    def dispatch_input_event(
        self,
        entity_id: str,
        event_id: str,
        *,
        actor_entity_id: str | None = None,
    ) -> bool:
        """Run one routed input event now when the active handle allows it, else queue it."""
        params: dict[str, Any] = {
            "entity_id": entity_id,
            "event_id": event_id,
        }
        if actor_entity_id is not None:
            params["actor_entity_id"] = actor_entity_id

        if self.active_handle is not None and self.active_handle.allow_entity_input:
            return self._execute_background_command("run_event", params)

        self.enqueue("run_event", **params)
        return True

    def has_pending_work(self) -> bool:
        """Return True when a command is queued or still running."""
        return (
            self.active_handle is not None
            or bool(self.background_handles)
            or bool(self.pending)
        )

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

    def _execute_background_command(self, name: str, params: dict[str, Any]) -> bool:
        """Execute one command immediately and keep any async work alongside the main lane."""
        try:
            handle = execute_registered_command(
                self.registry,
                self.context,
                name,
                dict(params),
            )
        except CommandExecutionError as exc:
            self._handle_command_error(exc)
            return False
        except Exception as exc:
            wrapped = CommandExecutionError(
                f"Command '{name}' failed.",
                command_name=name,
                params=dict(params),
                trace=list(self.context.command_trace),
            )
            wrapped.__cause__ = exc
            self._handle_command_error(wrapped)
            return False

        self.spawn_background_handle(handle)
        return True

