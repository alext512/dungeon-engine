"""Tile painting helpers.

Follows the same pattern as ``cell_flags.py``: stateless functions that
mutate the area document in-place and return whether anything changed.
"""

from __future__ import annotations

from area_editor.documents.area_document import AreaDocument


def paint_tile(
    area: AreaDocument,
    layer_index: int,
    col: int,
    row: int,
    gid: int,
) -> bool:
    """Set one cell's GID on the given tile layer.

    Returns ``True`` when the document actually changed.
    """
    if not _in_bounds(area, col, row):
        return False
    if layer_index < 0 or layer_index >= len(area.tile_layers):
        return False

    grid = area.tile_layers[layer_index].grid
    if grid[row][col] == gid:
        return False
    grid[row][col] = gid
    return True


def eyedrop_tile(
    area: AreaDocument,
    layer_index: int,
    col: int,
    row: int,
) -> int:
    """Read the GID at one cell on the given tile layer.

    Returns 0 for out-of-bounds or missing data.
    """
    if not _in_bounds(area, col, row):
        return 0
    if layer_index < 0 or layer_index >= len(area.tile_layers):
        return 0
    return area.tile_layers[layer_index].grid[row][col]


def _in_bounds(area: AreaDocument, col: int, row: int) -> bool:
    return 0 <= col < area.width and 0 <= row < area.height
