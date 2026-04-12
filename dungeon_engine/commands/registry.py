"""Registry for command callables used by the command runner."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
import inspect
from typing import Literal
from typing import Any

from dungeon_engine.commands.context_services import (
    COMMAND_SERVICE_INJECTION_NAMES,
    resolve_service_injection,
)
from dungeon_engine.commands.runner import CommandContext, CommandHandle

CommandCallable = Callable[[CommandContext], CommandHandle | None]
CommandValidationMode = Literal["strict", "mixed", "passthrough"]
DeferredCommandPayloadShape = Literal["command_payload", "dialogue_segment_hooks"]
_DEFERRED_COMMAND_PAYLOAD_SHAPES = frozenset(
    {
        "command_payload",
        "dialogue_segment_hooks",
    }
)
_CONTEXT_FIELD_NAMES = frozenset(
    field_info.name for field_info in fields(CommandContext)
)
_INJECTABLE_ARGUMENT_NAMES = _CONTEXT_FIELD_NAMES | COMMAND_SERVICE_INJECTION_NAMES


def _resolve_injected_argument(
    context: CommandContext,
    parameter_name: str,
) -> Any:
    """Return one injected command argument from context fields or services."""

    if parameter_name in _CONTEXT_FIELD_NAMES:
        return getattr(context, parameter_name)
    if parameter_name in COMMAND_SERVICE_INJECTION_NAMES:
        return resolve_service_injection(context.services, parameter_name)
    raise KeyError(f"Unknown injected argument '{parameter_name}'.")


@dataclass(frozen=True, slots=True)
class DeferredCommandParam:
    """Shape metadata for a command param that keeps nested command data raw."""

    name: str
    payload_shape: DeferredCommandPayloadShape


@dataclass(frozen=True, slots=True)
class CommandContract:
    """Public immutable snapshot of one registered command's authoring contract."""

    name: str
    validation_mode: CommandValidationMode
    authored_param_names: frozenset[str]
    additional_authored_params: frozenset[str]
    deferred_param_specs: tuple[DeferredCommandParam, ...]
    accepts_runtime_kwargs: bool

    @property
    def deferred_param_shapes(self) -> dict[str, DeferredCommandPayloadShape]:
        """Return deferred params by name with their nested payload shape."""
        return {
            deferred_param.name: deferred_param.payload_shape
            for deferred_param in self.deferred_param_specs
        }

    @property
    def allowed_authored_params(self) -> frozenset[str]:
        """Return top-level authored keys accepted by strict validation."""
        return frozenset(
            set(self.authored_param_names)
            | set(self.additional_authored_params)
            | {deferred_param.name for deferred_param in self.deferred_param_specs}
        )


@dataclass(frozen=True, slots=True)
class CommandRegistration:
    """Static metadata tracked for one registered command."""

    signature: inspect.Signature
    deferred_param_specs: tuple[DeferredCommandParam, ...]
    validation_mode: CommandValidationMode
    authored_param_names: frozenset[str]
    additional_authored_params: frozenset[str]

    @property
    def allowed_authored_params(self) -> frozenset[str]:
        """Return top-level authored keys accepted by strict validation."""
        return frozenset(
            set(self.authored_param_names)
            | set(self.additional_authored_params)
            | {deferred_param.name for deferred_param in self.deferred_param_specs}
        )

    @property
    def accepts_runtime_kwargs(self) -> bool:
        """Return True when this command accepts caller-supplied runtime kwargs."""
        return any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in self.signature.parameters.values()
        )

    def to_contract(self, name: str) -> CommandContract:
        """Return the public authoring contract snapshot for this command."""
        return CommandContract(
            name=name,
            validation_mode=self.validation_mode,
            authored_param_names=self.authored_param_names,
            additional_authored_params=self.additional_authored_params,
            deferred_param_specs=self.deferred_param_specs,
            accepts_runtime_kwargs=self.accepts_runtime_kwargs,
        )


def _normalize_deferred_param_shapes(
    *,
    command_name: str,
    deferred_param_shapes: dict[str, DeferredCommandPayloadShape] | None,
) -> tuple[DeferredCommandParam, ...]:
    """Validate and normalize deferred command payload metadata."""
    if not deferred_param_shapes:
        return ()

    normalized: list[DeferredCommandParam] = []
    for raw_name, raw_shape in sorted(deferred_param_shapes.items()):
        name = str(raw_name).strip()
        if not name:
            raise ValueError(f"Command '{command_name}' declares a blank deferred param name.")
        if raw_shape not in _DEFERRED_COMMAND_PAYLOAD_SHAPES:
            raise ValueError(
                f"Command '{command_name}' declares unknown deferred payload shape "
                f"'{raw_shape}' for param '{name}'."
            )
        normalized.append(
            DeferredCommandParam(
                name=name,
                payload_shape=raw_shape,
            )
        )
    return tuple(normalized)


class CommandRegistry:
    """Map command names to Python callables."""

    def __init__(self) -> None:
        self._commands: dict[str, Callable[..., CommandHandle | None]] = {}
        self._registrations: dict[str, CommandRegistration] = {}

    def register(
        self,
        name: str,
        *,
        deferred_param_shapes: dict[str, DeferredCommandPayloadShape] | None = None,
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
                if parameter_name not in _INJECTABLE_ARGUMENT_NAMES
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
                deferred_param_specs=_normalize_deferred_param_shapes(
                    command_name=name,
                    deferred_param_shapes=deferred_param_shapes,
                ),
                validation_mode=validation_mode,
                authored_param_names=authored_param_names,
                additional_authored_params=frozenset(additional_authored_params or set()),
            )
            return func

        return decorator

    def get_deferred_param_shapes(self, name: str) -> dict[str, DeferredCommandPayloadShape]:
        """Return deferred command params by name with their nested payload shape."""
        registration = self._registrations.get(name)
        if registration is None:
            return {}
        return {
            deferred_param.name: deferred_param.payload_shape
            for deferred_param in registration.deferred_param_specs
        }

    def iter_command_contracts(self) -> tuple[CommandContract, ...]:
        """Return immutable authoring-contract snapshots for all registered commands."""
        return tuple(
            self._registrations[name].to_contract(name)
            for name in sorted(self._registrations)
        )

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
            parameter_name: _resolve_injected_argument(context, parameter_name)
            for parameter_name in signature.parameters
            if parameter_name in _INJECTABLE_ARGUMENT_NAMES
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


