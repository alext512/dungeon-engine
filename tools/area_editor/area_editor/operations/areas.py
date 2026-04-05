"""Area geometry and tile-layer helpers for editor workflows."""

from __future__ import annotations

from area_editor.documents.area_document import AreaDocument, TileLayerDocument


def make_empty_area_document(
    *,
    width: int,
    height: int,
    tile_size: int,
    include_default_ground_layer: bool,
) -> AreaDocument:
    """Create a conservative new-area document."""
    width = max(1, int(width))
    height = max(1, int(height))
    tile_size = max(1, int(tile_size))

    tile_layers = []
    if include_default_ground_layer:
        tile_layers = [
            {
                "name": "ground",
                "render_order": 0,
                "y_sort": False,
                "stack_order": 0,
                "grid": [[0 for _ in range(width)] for _ in range(height)],
            }
        ]

    return AreaDocument.from_dict(
        {
            "tile_size": tile_size,
            "tilesets": [],
            "tile_layers": tile_layers,
            "entities": [],
            "variables": {},
        }
    )


def add_tile_layer(
    area: AreaDocument,
    *,
    name: str,
    insert_index: int | None = None,
    width: int | None = None,
    height: int | None = None,
) -> int:
    """Insert one empty tile layer and return its final index."""
    layer_width, layer_height = layer_dimensions(area)
    if width is not None:
        layer_width = max(0, int(width))
    if height is not None:
        layer_height = max(0, int(height))
    if layer_width <= 0 or layer_height <= 0:
        raise ValueError("Tile layer dimensions must be positive.")

    new_layer = TileLayerDocument(
        name=name.strip() or "layer",
        render_order=0,
        y_sort=False,
        sort_y_offset=0.0,
        stack_order=0,
        grid=[[0 for _ in range(layer_width)] for _ in range(layer_height)],
    )
    index = len(area.tile_layers) if insert_index is None else max(0, min(int(insert_index), len(area.tile_layers)))
    area.tile_layers.insert(index, new_layer)
    return index


def remove_tile_layer(area: AreaDocument, index: int) -> TileLayerDocument | None:
    """Remove and return one tile layer by index."""
    if not (0 <= index < len(area.tile_layers)):
        return None
    return area.tile_layers.pop(index)


def move_tile_layer(area: AreaDocument, index: int, new_index: int) -> int | None:
    """Move one tile layer to a new list position and return the final index."""
    if not (0 <= index < len(area.tile_layers)):
        return None
    layer = area.tile_layers.pop(index)
    bounded = max(0, min(int(new_index), len(area.tile_layers)))
    area.tile_layers.insert(bounded, layer)
    return bounded


def rename_tile_layer(area: AreaDocument, index: int, new_name: str) -> bool:
    """Rename one tile layer."""
    if not (0 <= index < len(area.tile_layers)):
        return False
    area.tile_layers[index].name = new_name.strip() or area.tile_layers[index].name
    return True


def layer_dimensions(area: AreaDocument) -> tuple[int, int]:
    """Return the best-known tile-layer dimensions for an area."""
    width = area.width
    height = area.height
    if width > 0 and height > 0:
        return width, height
    if area.cell_flags and area.cell_flags[0]:
        return len(area.cell_flags[0]), len(area.cell_flags)
    return 0, 0


def add_rows_above(
    area: AreaDocument,
    count: int,
    *,
    screen_entity_ids: set[str] | None = None,
) -> bool:
    count = _normalize_positive(count)
    if count == 0:
        return False
    _prepend_rows(area, count)
    for entity in area.entities:
        if _is_screen_entity(entity, screen_entity_ids):
            continue
        entity.grid_y += count
    return True


def add_rows_below(area: AreaDocument, count: int) -> bool:
    count = _normalize_positive(count)
    if count == 0:
        return False
    _append_rows(area, count)
    return True


def add_columns_left(
    area: AreaDocument,
    count: int,
    *,
    screen_entity_ids: set[str] | None = None,
) -> bool:
    count = _normalize_positive(count)
    if count == 0:
        return False
    _prepend_columns(area, count)
    for entity in area.entities:
        if _is_screen_entity(entity, screen_entity_ids):
            continue
        entity.grid_x += count
    return True


def add_columns_right(area: AreaDocument, count: int) -> bool:
    count = _normalize_positive(count)
    if count == 0:
        return False
    _append_columns(area, count)
    return True


def can_remove_top_rows(
    area: AreaDocument,
    count: int,
    *,
    screen_entity_ids: set[str] | None = None,
) -> bool:
    count = _normalize_positive(count)
    return _can_remove_rows(area, count, from_top=True, screen_entity_ids=screen_entity_ids)


def can_remove_bottom_rows(
    area: AreaDocument,
    count: int,
    *,
    screen_entity_ids: set[str] | None = None,
) -> bool:
    count = _normalize_positive(count)
    return _can_remove_rows(area, count, from_top=False, screen_entity_ids=screen_entity_ids)


def can_remove_left_columns(
    area: AreaDocument,
    count: int,
    *,
    screen_entity_ids: set[str] | None = None,
) -> bool:
    count = _normalize_positive(count)
    return _can_remove_columns(area, count, from_left=True, screen_entity_ids=screen_entity_ids)


def can_remove_right_columns(
    area: AreaDocument,
    count: int,
    *,
    screen_entity_ids: set[str] | None = None,
) -> bool:
    count = _normalize_positive(count)
    return _can_remove_columns(area, count, from_left=False, screen_entity_ids=screen_entity_ids)


def remove_top_rows(
    area: AreaDocument,
    count: int,
    *,
    screen_entity_ids: set[str] | None = None,
) -> bool:
    count = _normalize_positive(count)
    if count == 0 or not can_remove_top_rows(area, count, screen_entity_ids=screen_entity_ids):
        return False
    _remove_rows(area, count, from_top=True)
    for entity in area.entities:
        if _is_screen_entity(entity, screen_entity_ids):
            continue
        entity.grid_y -= count
    return True


def remove_bottom_rows(
    area: AreaDocument,
    count: int,
    *,
    screen_entity_ids: set[str] | None = None,
) -> bool:
    count = _normalize_positive(count)
    if count == 0 or not can_remove_bottom_rows(area, count, screen_entity_ids=screen_entity_ids):
        return False
    _remove_rows(area, count, from_top=False)
    return True


def remove_left_columns(
    area: AreaDocument,
    count: int,
    *,
    screen_entity_ids: set[str] | None = None,
) -> bool:
    count = _normalize_positive(count)
    if count == 0 or not can_remove_left_columns(area, count, screen_entity_ids=screen_entity_ids):
        return False
    _remove_columns(area, count, from_left=True)
    for entity in area.entities:
        if _is_screen_entity(entity, screen_entity_ids):
            continue
        entity.grid_x -= count
    return True


def remove_right_columns(
    area: AreaDocument,
    count: int,
    *,
    screen_entity_ids: set[str] | None = None,
) -> bool:
    count = _normalize_positive(count)
    if count == 0 or not can_remove_right_columns(area, count, screen_entity_ids=screen_entity_ids):
        return False
    _remove_columns(area, count, from_left=False)
    return True


def _normalize_positive(count: int) -> int:
    return max(0, int(count))


def _area_dimensions(area: AreaDocument) -> tuple[int, int]:
    return area.width, area.height


def _prepend_rows(area: AreaDocument, count: int) -> None:
    width, _height = _area_dimensions(area)
    filler = [[0 for _ in range(width)] for _ in range(count)]
    for layer in area.tile_layers:
        layer.grid = [row.copy() for row in filler] + [list(row) for row in layer.grid]


def _append_rows(area: AreaDocument, count: int) -> None:
    width, _height = _area_dimensions(area)
    filler = [[0 for _ in range(width)] for _ in range(count)]
    for layer in area.tile_layers:
        layer.grid = [list(row) for row in layer.grid] + [row.copy() for row in filler]


def _prepend_columns(area: AreaDocument, count: int) -> None:
    for layer in area.tile_layers:
        layer.grid = [[0 for _ in range(count)] + list(row) for row in layer.grid]


def _append_columns(area: AreaDocument, count: int) -> None:
    for layer in area.tile_layers:
        layer.grid = [list(row) + [0 for _ in range(count)] for row in layer.grid]


def _can_remove_rows(
    area: AreaDocument,
    count: int,
    *,
    from_top: bool,
    screen_entity_ids: set[str] | None = None,
) -> bool:
    _width, height = _area_dimensions(area)
    if count <= 0 or count >= height:
        return False
    for entity in area.entities:
        if _is_screen_entity(entity, screen_entity_ids):
            continue
        new_y = entity.grid_y - count if from_top else entity.grid_y
        if not (0 <= new_y < (height - count)):
            return False
    return True


def _can_remove_columns(
    area: AreaDocument,
    count: int,
    *,
    from_left: bool,
    screen_entity_ids: set[str] | None = None,
) -> bool:
    width, _height = _area_dimensions(area)
    if count <= 0 or count >= width:
        return False
    for entity in area.entities:
        if _is_screen_entity(entity, screen_entity_ids):
            continue
        new_x = entity.grid_x - count if from_left else entity.grid_x
        if not (0 <= new_x < (width - count)):
            return False
    return True


def _is_screen_entity(entity, screen_entity_ids: set[str] | None) -> bool:
    return entity.is_screen_space or (
        screen_entity_ids is not None and entity.id in screen_entity_ids
    )


def _remove_rows(area: AreaDocument, count: int, *, from_top: bool) -> None:
    for layer in area.tile_layers:
        if from_top:
            layer.grid = [list(row) for row in layer.grid[count:]]
        else:
            layer.grid = [list(row) for row in layer.grid[:-count]]


def _remove_columns(area: AreaDocument, count: int, *, from_left: bool) -> None:
    for layer in area.tile_layers:
        if from_left:
            layer.grid = [list(row[count:]) for row in layer.grid]
        else:
            layer.grid = [list(row[:-count]) for row in layer.grid]
