"""Cell-flag editing helpers."""

from __future__ import annotations

from typing import Any

from area_editor.documents.area_document import AreaDocument

_MISSING = object()


def cell_is_walkable(area: AreaDocument, col: int, row: int) -> bool:
    """Return the effective walkability for one authored cell."""
    if not _in_bounds(area, col, row):
        return False
    return _flag_walkable(_raw_cell_flag(area, col, row))


def set_cell_walkable(
    area: AreaDocument,
    col: int,
    row: int,
    walkable: bool,
) -> bool:
    """Set one cell's effective walkability.

    Returns ``True`` when the authored document changed.
    """
    if not _in_bounds(area, col, row):
        return False

    current_flag = _raw_cell_flag(area, col, row)
    if _flag_walkable(current_flag) == walkable:
        return False

    _ensure_grid(area)
    existing = area.cell_flags[row][col]
    if isinstance(existing, dict):
        updated = dict(existing)
        updated["walkable"] = walkable
        area.cell_flags[row][col] = updated
    else:
        area.cell_flags[row][col] = walkable
    return True


def _ensure_grid(area: AreaDocument) -> None:
    width = area.width
    height = area.height
    grid = list(area.cell_flags or [])

    if len(grid) < height:
        grid.extend([] for _ in range(height - len(grid)))
    elif len(grid) > height:
        grid = grid[:height]

    normalized: list[list[Any]] = []
    for row_index in range(height):
        raw_row = grid[row_index] if row_index < len(grid) else []
        row_values = list(raw_row or [])
        if len(row_values) < width:
            row_values.extend(True for _ in range(width - len(row_values)))
        elif len(row_values) > width:
            row_values = row_values[:width]
        normalized.append(row_values)

    area.cell_flags = normalized


def _in_bounds(area: AreaDocument, col: int, row: int) -> bool:
    return 0 <= col < area.width and 0 <= row < area.height


def _raw_cell_flag(area: AreaDocument, col: int, row: int) -> object:
    if row >= len(area.cell_flags):
        return _MISSING
    row_values = area.cell_flags[row]
    if row_values is None or col >= len(row_values):
        return _MISSING
    return row_values[col]


def _flag_walkable(flag: object) -> bool:
    if flag is _MISSING or flag is None:
        return True
    if isinstance(flag, dict):
        return bool(flag.get("walkable", True))
    return bool(flag)
