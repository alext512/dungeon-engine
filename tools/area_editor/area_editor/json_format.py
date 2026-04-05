"""Editor-facing JSON formatting helpers."""

from __future__ import annotations

import json
from typing import Any

_MATRIX_KEYS = frozenset({"grid", "cell_flags"})


def format_json_for_editor(data: Any) -> str:
    """Return friendly, stable JSON text for editor display/save paths."""

    return "\n".join(_format_lines(data, level=0))


def _format_lines(value: Any, *, level: int, parent_key: str | None = None) -> list[str]:
    indent = "  " * level
    child_indent = "  " * (level + 1)

    if isinstance(value, dict):
        if not value:
            return [f"{indent}{{}}"]
        lines = [f"{indent}{{"]
        items = list(value.items())
        for index, (key, child) in enumerate(items):
            child_lines = _format_lines(child, level=level + 1, parent_key=key)
            key_text = json.dumps(key, ensure_ascii=False)
            if len(child_lines) == 1:
                line = f"{child_indent}{key_text}: {child_lines[0].lstrip()}"
                if index < len(items) - 1:
                    line += ","
                lines.append(line)
                continue
            lines.append(f"{child_indent}{key_text}: {child_lines[0].lstrip()}")
            lines.extend(child_lines[1:])
            if index < len(items) - 1:
                lines[-1] += ","
        lines.append(f"{indent}}}")
        return lines

    if isinstance(value, list):
        if parent_key in _MATRIX_KEYS and _is_matrix(value):
            return _format_matrix_lines(value, level=level)
        if not value:
            return [f"{indent}[]"]
        lines = [f"{indent}["]
        for index, child in enumerate(value):
            child_lines = _format_lines(child, level=level + 1)
            lines.extend(child_lines)
            if index < len(value) - 1:
                lines[-1] += ","
        lines.append(f"{indent}]")
        return lines

    return [f"{indent}{json.dumps(value, ensure_ascii=False)}"]


def _format_matrix_lines(rows: list[Any], *, level: int) -> list[str]:
    indent = "  " * level
    child_indent = "  " * (level + 1)
    if not rows:
        return [f"{indent}[]"]
    lines = [f"{indent}["]
    for index, row in enumerate(rows):
        row_text = json.dumps(row, ensure_ascii=False, separators=(", ", ": "))
        if index < len(rows) - 1:
            row_text += ","
        lines.append(f"{child_indent}{row_text}")
    lines.append(f"{indent}]")
    return lines


def _is_matrix(value: list[Any]) -> bool:
    return all(isinstance(row, list) for row in value)
