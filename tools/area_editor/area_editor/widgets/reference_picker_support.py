"""Shared picker callback helpers for focused editor widgets."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class EntityReferencePickerRequest:
    parameter_name: str
    current_value: str
    parameter_spec: dict[str, Any] | None
    current_area_id: str | None
    entity_id: str | None
    entity_template_id: str | None
    parameter_values: dict[str, object] | None = None
    entity_command_names_override: tuple[str, ...] | None = None
    entity_dialogue_names_override: tuple[str, ...] | None = None


def call_reference_picker_callback(
    callback: Callable[..., str | None] | None,
    current_value: str,
    *,
    request: EntityReferencePickerRequest | None = None,
) -> str | None:
    if callback is None:
        return None
    if request is None:
        return callback(current_value)
    try:
        signature = inspect.signature(callback)
    except (TypeError, ValueError):
        return callback(current_value)

    positional_count = 0
    has_varargs = False
    for parameter in signature.parameters.values():
        if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
            has_varargs = True
            break
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            positional_count += 1
    if has_varargs or positional_count >= 2:
        return callback(current_value, request)
    return callback(current_value)
