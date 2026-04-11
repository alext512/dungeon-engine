"""Cell-flag editing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from area_editor.documents.area_document import AreaDocument


@dataclass(frozen=True)
class CellFlagBrush:
    """One authored cell-flag paint operation."""

    key: str
    value: Any = True
    remove: bool = False

    @property
    def label(self) -> str:
        if self.remove:
            return f"remove {self.key}"
        return f"{self.key} = {self.value!r}"


def cell_is_blocked(area: AreaDocument, col: int, row: int) -> bool:
    """Return whether one authored cell blocks movement."""
    if not _in_bounds(area, col, row):
        return True
    flag = _raw_cell_flag(area, col, row)
    if not isinstance(flag, dict):
        return False
    return bool(flag.get("blocked", False))


def set_cell_blocked(
    area: AreaDocument,
    col: int,
    row: int,
    blocked: bool,
) -> bool:
    """Set one cell's built-in movement-blocking flag.

    Returns ``True`` when the authored document changed.
    """
    if not _in_bounds(area, col, row):
        return False

    current_flag = _raw_cell_flag(area, col, row)
    current_blocked = (
        bool(current_flag.get("blocked", False))
        if isinstance(current_flag, dict)
        else False
    )
    if current_blocked == blocked:
        return False

    _ensure_grid(area)
    updated = _cell_flag_dict(area.cell_flags[row][col])
    updated["blocked"] = blocked
    area.cell_flags[row][col] = updated
    return True


def apply_cell_flag_brush(
    area: AreaDocument,
    col: int,
    row: int,
    brush: CellFlagBrush,
) -> bool:
    """Apply a generic cell-flag brush to one authored cell."""
    if not _in_bounds(area, col, row):
        return False
    key = brush.key.strip()
    if not key:
        return False

    _ensure_grid(area)
    current = _cell_flag_dict(area.cell_flags[row][col])
    updated = dict(current)
    if brush.remove:
        updated.pop(key, None)
    else:
        updated[key] = brush.value

    if updated == current:
        return False
    area.cell_flags[row][col] = updated
    return True


def clear_cell_flag_for_brush(
    area: AreaDocument,
    col: int,
    row: int,
    brush: CellFlagBrush,
) -> bool:
    """Apply the right-click counterpart for a selected brush."""
    key = brush.key.strip()
    if key == "blocked":
        return apply_cell_flag_brush(area, col, row, CellFlagBrush("blocked", False))
    return apply_cell_flag_brush(area, col, row, CellFlagBrush(key, remove=True))


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
            row_values.extend({} for _ in range(width - len(row_values)))
        elif len(row_values) > width:
            row_values = row_values[:width]
        normalized.append(row_values)

    area.cell_flags = normalized


def _in_bounds(area: AreaDocument, col: int, row: int) -> bool:
    return 0 <= col < area.width and 0 <= row < area.height


def _raw_cell_flag(area: AreaDocument, col: int, row: int) -> object:
    if row >= len(area.cell_flags):
        return None
    row_values = area.cell_flags[row]
    if row_values is None or col >= len(row_values):
        return None
    return row_values[col]


def _cell_flag_dict(flag: object) -> dict[str, Any]:
    if isinstance(flag, dict):
        return dict(flag)
    return {}
