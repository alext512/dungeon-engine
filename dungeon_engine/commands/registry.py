"""Registry for command callables used by the command runner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
import inspect
from typing import Literal
from typing import Any

from dungeon_engine.commands.runner import CommandContext, CommandHandle

CommandCallable = Callable[[CommandContext], CommandHandle | None]
CommandValidationMode = Literal["strict", "mixed", "passthrough"]
_CONTEXT_FIELD_NAMES = frozenset(field_info.name for field_info in fields(CommandContext))


@dataclass(frozen=True, slots=True)
class CommandRegistration:
    """Static metadata tracked for one registered command."""

    signature: inspect.Signature
    deferred_params: frozenset[str]
    validation_mode: CommandValidationMode
    authored_param_names: frozenset[str]
    additional_authored_params: frozenset[str]

    @property
    def allowed_authored_params(self) -> frozenset[str]:
        """Return top-level authored keys accepted by strict validation."""
        return frozenset(
            set(self.authored_param_names)
            | set(self.additional_authored_params)
            | set(self.deferred_params)
        )


class CommandRegistry:
    """Map command names to Python callables."""

    def __init__(self) -> None:
        self._commands: dict[str, Callable[..., CommandHandle | None]] = {}
        self._registrations: dict[str, CommandRegistration] = {}

    def register(
        self,
        name: str,
        *,
        deferred_params: set[str] | None = None,
        validation_mode: CommandValidationMode = "strict",
        additional_authored_params: set[str] | None = None,
    ) -> Callable[[Callable[..., CommandHandle | None]], Callable[..., CommandHandle | None]]:
        """Register a command function under a stable string key."""

        def decorator(
            func: Callable[..., CommandHandle | None],
        ) -> Callable[..., CommandHandle | None]:
            if validation_mode not in {"strict", "mixed", "passthrough"}:
                raise ValueError(
                    f"Command '{name}' uses unknown validation_mode '{validation_mode}'."
                )
            signature = inspect.signature(func)
            authored_param_names = frozenset(
                parameter_name
                for parameter_name, parameter in signature.parameters.items()
                if parameter_name not in _CONTEXT_FIELD_NAMES
                and parameter_name != "context"
                and parameter.kind
                not in {
                    inspect.Parameter.VAR_KEYWORD,
                    inspect.Parameter.VAR_POSITIONAL,
                }
            )
            self._commands[name] = func
            self._registrations[name] = CommandRegistration(
                signature=signature,
                deferred_params=frozenset(deferred_params or set()),
                validation_mode=validation_mode,
                authored_param_names=authored_param_names,
                additional_authored_params=frozenset(additional_authored_params or set()),
            )
            return func

        return decorator

    def get_deferred_params(self, name: str) -> set[str]:
        """Return command params that should only resolve top-level runtime tokens."""
        registration = self._registrations.get(name)
        if registration is None:
            return set()
        return set(registration.deferred_params)

    def has_command(self, name: str) -> bool:
        """Return True when a command name is registered."""
        return name in self._commands

    def get_validation_mode(self, name: str) -> CommandValidationMode:
        """Return how authored extra keys should be interpreted for one command."""
        registration = self._registrations.get(name)
        if registration is None:
            raise KeyError(f"Unknown command '{name}'.")
        return registration.validation_mode

    def get_allowed_authored_params(self, name: str) -> set[str]:
        """Return authored top-level keys accepted for strict validation."""
        registration = self._registrations.get(name)
        if registration is None:
            raise KeyError(f"Unknown command '{name}'.")
        return set(registration.allowed_authored_params)

    def get_unknown_authored_params(
        self,
        name: str,
        authored_param_names: set[str],
    ) -> set[str]:
        """Return authored keys that a strict command would reject."""
        registration = self._registrations.get(name)
        if registration is None:
            raise KeyError(f"Unknown command '{name}'.")
        if registration.validation_mode != "strict":
            return set()
        return set(authored_param_names) - set(registration.allowed_authored_params)

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
        registration = self._registrations[name]
        signature = registration.signature
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        injected_kwargs = {
            parameter_name: getattr(context, parameter_name)
            for parameter_name in signature.parameters
            if parameter_name in _CONTEXT_FIELD_NAMES
        }
        if "context" in signature.parameters:
            injected_kwargs["context"] = context
        if accepts_kwargs:
            filtered_params = {
                parameter_name: value
                for parameter_name, value in params.items()
                if parameter_name not in injected_kwargs
            }
        else:
            accepted_names = {
                parameter_name
                for parameter_name, parameter in signature.parameters.items()
                if parameter_name not in injected_kwargs
            }
            filtered_params = {
                parameter_name: value
                for parameter_name, value in params.items()
                if parameter_name in accepted_names
            }
        return command(**injected_kwargs, **filtered_params)


