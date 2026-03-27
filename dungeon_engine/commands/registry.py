"""Registry for command callables used by the command runner."""

from __future__ import annotations

from collections.abc import Callable
import inspect
from typing import Any

from dungeon_engine.commands.runner import CommandContext, CommandHandle

CommandCallable = Callable[[CommandContext], CommandHandle | None]


class CommandRegistry:
    """Map command names to Python callables."""

    def __init__(self) -> None:
        self._commands: dict[str, Callable[..., CommandHandle | None]] = {}
        self._signatures: dict[str, inspect.Signature] = {}
        self._deferred_params: dict[str, set[str]] = {}

    def register(
        self,
        name: str,
        *,
        deferred_params: set[str] | None = None,
    ) -> Callable[[Callable[..., CommandHandle | None]], Callable[..., CommandHandle | None]]:
        """Register a command function under a stable string key."""

        def decorator(
            func: Callable[..., CommandHandle | None],
        ) -> Callable[..., CommandHandle | None]:
            self._commands[name] = func
            self._signatures[name] = inspect.signature(func)
            self._deferred_params[name] = set(deferred_params or set())
            return func

        return decorator

    def get_deferred_params(self, name: str) -> set[str]:
        """Return command params that should only resolve top-level runtime tokens."""
        return set(self._deferred_params.get(name, set()))

    def execute(
        self,
        name: str,
        context: CommandContext,
        params: dict[str, Any],
    ) -> CommandHandle | None:
        """Execute a command by name using the supplied parameters."""
        command = self._commands.get(name)
        if command is None:
            raise KeyError(f"Unknown command '{name}'.")
        signature = self._signatures[name]
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        if accepts_kwargs:
            filtered_params = dict(params)
        else:
            accepted_names = {
                parameter_name
                for parameter_name, parameter in signature.parameters.items()
                if parameter_name != "context"
            }
            filtered_params = {
                parameter_name: value
                for parameter_name, value in params.items()
                if parameter_name in accepted_names
            }
        return command(context, **filtered_params)


