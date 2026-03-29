"""Tileset editing helpers for the external area editor."""

from __future__ import annotations

from area_editor.documents.area_document import AreaDocument, TilesetRef


def tileset_frame_count(
    image_width: int,
    image_height: int,
    tile_width: int,
    tile_height: int,
) -> int:
    """Return the number of whole frames available in a uniform sheet."""
    if tile_width <= 0 or tile_height <= 0:
        return 0
    cols = image_width // tile_width
    rows = image_height // tile_height
    return cols * rows


def append_tileset(
    area: AreaDocument,
    authored_path: str,
    tile_width: int,
    tile_height: int,
    *,
    existing_tile_counts: list[int],
) -> TilesetRef:
    """Append a new tileset using the next safe append-only ``firstgid``."""
    firstgid = next_tileset_firstgid(area, existing_tile_counts)
    tileset = TilesetRef(
        firstgid=firstgid,
        path=authored_path,
        tile_width=tile_width,
        tile_height=tile_height,
    )
    area.tilesets.append(tileset)
    return tileset


def next_tileset_firstgid(
    area: AreaDocument,
    existing_tile_counts: list[int],
) -> int:
    """Return the next safe ``firstgid`` for append-only tileset edits."""
    highest_end = 0
    for index, tileset in enumerate(area.tilesets):
        count = existing_tile_counts[index] if index < len(existing_tile_counts) else 0
        if count <= 0:
            end = tileset.firstgid
        else:
            end = tileset.firstgid + count
        highest_end = max(highest_end, end)
    return highest_end if highest_end > 0 else 1


def update_tileset_dimensions(
    area: AreaDocument,
    index: int,
    tile_width: int,
    tile_height: int,
) -> bool:
    """Update the slicing dimensions of one existing tileset."""
    if index < 0 or index >= len(area.tilesets):
        return False
    tileset = area.tilesets[index]
    if tileset.tile_width == tile_width and tileset.tile_height == tile_height:
        return False
    tileset.tile_width = tile_width
    tileset.tile_height = tile_height
    return True
