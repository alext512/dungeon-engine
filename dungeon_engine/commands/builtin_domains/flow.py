"""Flow-oriented builtin commands and command-handle helpers."""

from __future__ import annotations

import copy
from collections.abc import Callable
from logging import Logger
from typing import Any

from dungeon_engine.commands.context_services import CommandServices
from dungeon_engine.commands.library import (
    instantiate_project_command_commands,
    load_project_command_definition,
)
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import (
    CommandContext,
    CommandHandle,
    ImmediateHandle,
    SequenceCommandHandle,
    execute_command_spec,
)


def _normalize_command_specs(
    commands: list[dict[str, Any]] | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return one normalized inline command list."""
    if commands is None:
        return []
    if isinstance(commands, dict):
        return [dict(commands)]
    if isinstance(commands, list):
        return [dict(command) for command in commands]
    raise TypeError("Command hooks must be a dict, list of dicts, or null.")


def _branch_with_runtime_context(
    registry: CommandRegistry,
    context: CommandContext,
    *,
    condition_met: bool,
    then: list[dict[str, Any]] | None = None,
    else_branch: list[dict[str, Any]] | None = None,
    runtime_params: dict[str, Any] | None = None,
    excluded_param_names: set[str] | None = None,
) -> CommandHandle:
    """Run one branch while preserving inherited runtime params for child commands."""
    branch = then if condition_met else else_branch
    if not branch:
        return ImmediateHandle()

    inherited_params = {
        key: value
        for key, value in dict(runtime_params or {}).items()
        if key not in (excluded_param_names or set())
    }
    return SequenceCommandHandle(registry, context, branch, base_params=inherited_params)


_COMPARE_OPS: dict[str, Any] = {
    "eq": lambda a, b: a == b,
    "neq": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and b is not None and a > b,
    "lt": lambda a, b: a is not None and b is not None and a < b,
    "gte": lambda a, b: a is not None and b is not None and a >= b,
    "lte": lambda a, b: a is not None and b is not None and a <= b,
}


class ForEachCommandHandle(CommandHandle):
    """Run one generic command list once for every item in a collection."""

    def __init__(
        self,
        registry: CommandRegistry,
        context: CommandContext,
        *,
        items: list[Any],
        commands: list[dict[str, Any]],
        item_param: str,
        index_param: str,
        base_params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.registry = registry
        self.context = context
        self.items = [copy.deepcopy(item) for item in items]
        self.commands = [dict(command) for command in commands]
        self.item_param = str(item_param)
        self.index_param = str(index_param)
        self.base_params = dict(base_params or {})
        self.current_index = 0
        self.current_handle: CommandHandle | None = None
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Advance the active iteration and start the next one when needed."""
        if self.complete:
            return

        if self.current_handle is not None:
            self.current_handle.update(dt)
            if not self.current_handle.complete:
                return
            self.current_handle = None

        while self.current_handle is None and self.current_index < len(self.items):
            item_index = self.current_index
            base_params = dict(self.base_params)
            base_params[self.item_param] = copy.deepcopy(self.items[item_index])
            base_params[self.index_param] = item_index
            self.current_index += 1
            self.current_handle = SequenceCommandHandle(
                self.registry,
                self.context,
                self.commands,
                base_params=base_params,
            )
            if self.current_handle.complete:
                self.current_handle = None
                continue
            return

        if self.current_handle is None and self.current_index >= len(self.items):
            self.complete = True


class ProjectCommandHandle(CommandHandle):
    """Run a reusable project command definition while tracking recursion."""

    def __init__(
        self,
        context: CommandContext,
        command_id: str,
        sequence_handle: CommandHandle,
    ) -> None:
        super().__init__()
        self.context = context
        self.command_id = command_id
        self.sequence_handle = sequence_handle
        self._stack_pushed = False
        self._push_stack()
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Advance the underlying command sequence and pop the call stack when done."""
        if self.complete:
            return

        self.sequence_handle.update(dt)
        if self.sequence_handle.complete:
            self._pop_stack()
            self.complete = True

    def _push_stack(self) -> None:
        """Record entry into one project command invocation."""
        if self._stack_pushed:
            return
        self.context.project_command_stack.append(self.command_id)
        self._stack_pushed = True

    def _pop_stack(self) -> None:
        """Remove this invocation from the project command call stack."""
        if not self._stack_pushed:
            return
        if self.context.project_command_stack and self.context.project_command_stack[-1] == self.command_id:
            self.context.project_command_stack.pop()
        self._stack_pushed = False


class ParallelCommandHandle(CommandHandle):
    """Run several command branches together with explicit completion rules."""

    def __init__(
        self,
        registry: CommandRegistry,
        context: CommandContext,
        *,
        command_specs: list[dict[str, Any]],
        completion: dict[str, Any] | None = None,
        base_params: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self.registry = registry
        self.context = context
        self.base_params = dict(base_params or {})
        self.children: list[dict[str, Any]] = []
        self.completion_mode = "all"
        self.completion_child_id: str | None = None
        self.remaining_policy = "keep_running"
        self._completion_triggered = False
        self._configure_completion(completion)
        self._build_children(command_specs)
        self.update(0.0)

    def _configure_completion(self, completion: dict[str, Any] | None) -> None:
        """Validate and store one explicit parallel completion policy."""
        if completion is None:
            return
        if not isinstance(completion, dict):
            raise TypeError("run_parallel completion must be a JSON object or null.")
        self.completion_mode = str(completion.get("mode", "all")).strip() or "all"
        if self.completion_mode not in {"all", "any", "child"}:
            raise ValueError(
                "run_parallel completion.mode must be 'all', 'any', or 'child'."
            )
        if self.completion_mode == "child":
            child_id = str(completion.get("child_id", "")).strip()
            if not child_id:
                raise ValueError(
                    "run_parallel completion.mode 'child' requires a non-empty child_id."
                )
            self.completion_child_id = child_id
        remaining_policy = str(completion.get("remaining", "keep_running")).strip() or "keep_running"
        if remaining_policy != "keep_running":
            raise ValueError(
                "run_parallel currently only supports completion.remaining = 'keep_running'."
            )
        self.remaining_policy = remaining_policy

    def _build_children(self, command_specs: list[dict[str, Any]]) -> None:
        """Create child handles from authored command specs."""
        seen_ids: set[str] = set()
        for raw_command in command_specs:
            child_spec = dict(raw_command)
            child_id = str(child_spec.pop("id", "")).strip() or None
            if child_id is not None:
                if child_id in seen_ids:
                    raise ValueError(f"run_parallel child id '{child_id}' is duplicated.")
                seen_ids.add(child_id)
            handle = execute_command_spec(
                self.registry,
                self.context,
                child_spec,
                base_params=self.base_params,
            )
            self.children.append(
                {
                    "id": child_id,
                    "handle": handle,
                    "promoted": False,
                }
            )
        if self.completion_mode == "child" and self.completion_child_id not in seen_ids:
            raise ValueError(
                f"run_parallel completion child_id '{self.completion_child_id}' does not match any child id."
            )

    def update(self, dt: float) -> None:
        """Advance child handles and complete according to the configured policy."""
        if self.complete:
            return

        for child in self.children:
            handle = child["handle"]
            if not handle.complete:
                handle.update(dt)

        if self._completion_triggered:
            return

        should_complete = False
        if self.completion_mode == "all":
            should_complete = all(child["handle"].complete for child in self.children)
        elif self.completion_mode == "any":
            should_complete = any(child["handle"].complete for child in self.children)
        elif self.completion_mode == "child":
            should_complete = any(
                child["id"] == self.completion_child_id and child["handle"].complete
                for child in self.children
            )

        if not should_complete:
            return

        self._completion_triggered = True
        if self.completion_mode != "all":
            self._promote_remaining_children()
        self.complete = True

    def _promote_remaining_children(self) -> None:
        """Let unfinished non-waited children continue as independent root flows."""
        if self.context.command_runner is None:
            raise ValueError("Cannot keep parallel children running without an active command runner.")
        for child in self.children:
            handle = child["handle"]
            if child["promoted"] or handle.complete:
                continue
            child["promoted"] = True
            self.context.command_runner.spawn_root_handle(handle)


def register_flow_commands(
    registry: CommandRegistry,
    *,
    logger: Logger,
    build_child_runtime_params: Callable[..., dict[str, Any]],
    resolve_entity_id: Callable[..., str | None],
) -> None:
    """Register builtin commands that orchestrate other commands and flows."""

    def _resolve_flow_world(
        *,
        services: CommandServices | None,
    ) -> Any:
        if services is None or services.world is None or services.world.world is None:
            raise ValueError("Flow commands require an active world service.")
        return services.world.world

    @registry.register(
        "spawn_flow",
        deferred_params={"commands"},
        validation_mode="mixed",
    )
    def spawn_flow(
        context: CommandContext,
        *,
        commands: list[dict[str, Any]] | dict[str, Any] | None = None,
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        refs_mode: str | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Start one independent flow and return immediately."""
        if context.command_runner is None:
            raise ValueError("Cannot spawn a flow without an active command runner.")
        normalized_commands = _normalize_command_specs(commands)
        if not normalized_commands:
            return ImmediateHandle()
        handle = SequenceCommandHandle(
            registry,
            context,
            normalized_commands,
            base_params=build_child_runtime_params(
                runtime_params,
                source_entity_id=source_entity_id,
                entity_refs=entity_refs,
                refs_mode=refs_mode,
            ),
        )
        context.command_runner.spawn_root_handle(handle)
        return ImmediateHandle()

    @registry.register(
        "run_sequence",
        deferred_params={"commands"},
        validation_mode="mixed",
    )
    def run_sequence(
        context: CommandContext,
        *,
        commands: list[dict[str, Any]] | dict[str, Any] | None = None,
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        refs_mode: str | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Execute one explicit command-list value in order, waiting for each child."""
        normalized_commands = _normalize_command_specs(commands)
        if not normalized_commands:
            return ImmediateHandle()
        return SequenceCommandHandle(
            registry,
            context,
            normalized_commands,
            base_params=build_child_runtime_params(
                runtime_params,
                source_entity_id=source_entity_id,
                entity_refs=entity_refs,
                refs_mode=refs_mode,
            ),
        )

    @registry.register(
        "run_parallel",
        deferred_params={"commands"},
        validation_mode="mixed",
    )
    def run_parallel(
        context: CommandContext,
        *,
        commands: list[dict[str, Any]] | dict[str, Any] | None = None,
        completion: dict[str, Any] | None = None,
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        refs_mode: str | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Start several child commands together with explicit completion semantics."""
        normalized_commands = _normalize_command_specs(commands)
        if not normalized_commands:
            return ImmediateHandle()
        return ParallelCommandHandle(
            registry,
            context,
            command_specs=normalized_commands,
            completion=copy.deepcopy(completion),
            base_params=build_child_runtime_params(
                runtime_params,
                source_entity_id=source_entity_id,
                entity_refs=entity_refs,
                refs_mode=refs_mode,
            ),
        )

    @registry.register(
        "run_commands_for_collection",
        deferred_params={"commands"},
        validation_mode="mixed",
    )
    def run_commands_for_collection(
        context: CommandContext,
        *,
        value: Any = None,
        commands: list[dict[str, Any]] | dict[str, Any] | None = None,
        item_param: str = "item",
        index_param: str = "index",
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        refs_mode: str | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Run the same inline command list once per item in a list/tuple value."""
        if value is None:
            items: list[Any] = []
        elif isinstance(value, (list, tuple)):
            items = list(value)
        else:
            raise TypeError("run_commands_for_collection requires a list, tuple, or null value.")
        normalized_commands = _normalize_command_specs(commands)
        if not items or not normalized_commands:
            return ImmediateHandle()
        return ForEachCommandHandle(
            registry,
            context,
            items=items,
            commands=normalized_commands,
            item_param=str(item_param),
            index_param=str(index_param),
            base_params=build_child_runtime_params(
                runtime_params,
                source_entity_id=source_entity_id,
                entity_refs=entity_refs,
                refs_mode=refs_mode,
            ),
        )

    @registry.register(
        "if",
        deferred_params={"then", "else"},
        validation_mode="mixed",
    )
    def if_command(
        context: CommandContext,
        *,
        left: Any = None,
        op: str = "eq",
        right: Any = None,
        then: list[dict[str, Any]] | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Branch using one small structured comparison between two resolved values."""
        comparator = _COMPARE_OPS.get(op)
        if comparator is None:
            raise ValueError(f"Unknown comparison operator '{op}'.")
        return _branch_with_runtime_context(
            registry,
            context,
            condition_met=comparator(left, right),
            then=then,
            else_branch=runtime_params.get("else"),
            runtime_params=runtime_params,
            excluded_param_names={"left", "op", "right", "then", "else"},
        )

    @registry.register(
        "run_entity_command",
        deferred_params={"dialogue_on_start", "dialogue_on_end", "segment_hooks"},
        validation_mode="mixed",
    )
    def run_entity_command(
        context: CommandContext,
        services: CommandServices | None,
        *,
        entity_id: str,
        command_id: str,
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        refs_mode: str | None = None,
        **runtime_params: Any,
    ) -> CommandHandle:
        """Execute a named entity command on a target entity when it is enabled."""
        resolved_id = resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
        )
        if not resolved_id:
            logger.warning("run_entity_command: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        resolved_world = _resolve_flow_world(services=services)
        entity = resolved_world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot run entity command on missing entity '{resolved_id}'.")
        if not entity.present:
            return ImmediateHandle()
        entity_command = entity.get_entity_command(command_id)
        if (
            not entity.has_enabled_entity_command(command_id)
            or entity_command is None
            or not entity_command.commands
        ):
            return ImmediateHandle()

        base_params = build_child_runtime_params(
            runtime_params,
            source_entity_id=resolved_id,
            entity_refs=entity_refs,
            refs_mode=refs_mode,
        )
        return SequenceCommandHandle(
            registry,
            context,
            entity_command.commands,
            base_params=base_params,
        )

    @registry.register("run_project_command", validation_mode="mixed")
    def run_project_command(
        context: CommandContext,
        *,
        command_id: str,
        source_entity_id: str | None = None,
        entity_refs: dict[str, str] | None = None,
        refs_mode: str | None = None,
        **command_parameters: Any,
    ) -> CommandHandle:
        """Execute a reusable project-level command definition from the command library."""
        if context.project is None:
            raise ValueError("Cannot run a project command without an active project context.")

        resolved_command_id = str(command_id).strip()
        if not resolved_command_id:
            logger.warning("run_project_command: skipping because command_id resolved to blank.")
            return ImmediateHandle()

        if resolved_command_id in context.project_command_stack:
            stack_preview = " -> ".join([*context.project_command_stack, resolved_command_id])
            raise ValueError(f"Detected recursive project command cycle: {stack_preview}")

        definition = load_project_command_definition(context.project, resolved_command_id)
        instantiated_commands = instantiate_project_command_commands(definition, command_parameters)
        if not instantiated_commands:
            return ImmediateHandle()

        base_params = build_child_runtime_params(
            command_parameters,
            source_entity_id=source_entity_id,
            entity_refs=entity_refs,
            refs_mode=refs_mode,
        )

        sequence_handle = SequenceCommandHandle(
            registry,
            context,
            instantiated_commands,
            base_params=base_params,
            auto_start=False,
        )
        if sequence_handle.complete:
            return ImmediateHandle()
        return ProjectCommandHandle(context, resolved_command_id, sequence_handle)
