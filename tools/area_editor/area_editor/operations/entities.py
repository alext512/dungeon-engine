"""Entity placement helpers for area-editing workflows."""

from __future__ import annotations

from area_editor.documents.area_document import AreaDocument, EntityDocument


def _entity_sort_key(entity: EntityDocument) -> tuple:
    sort_bucket = 1 if entity.y_sort else 0
    sort_y = float(entity.y + 1 + entity.sort_y_offset) if entity.y_sort else 0.0
    return (
        entity.render_order,
        sort_bucket,
        sort_y,
        entity.stack_order,
        entity.x,
        entity.id,
    )


def entity_by_id(area: AreaDocument, entity_id: str) -> EntityDocument | None:
    """Return one entity instance by id, if present."""
    for entity in area.entities:
        if entity.id == entity_id:
            return entity
    return None


def entities_at_cell(area: AreaDocument, col: int, row: int) -> list[EntityDocument]:
    """Return world-space entities at one cell, ordered topmost-first."""
    matches = [
        entity
        for entity in area.entities
        if not entity.is_screen_space and entity.x == col and entity.y == row
    ]
    return sorted(matches, key=_entity_sort_key, reverse=True)


def topmost_entity_at(area: AreaDocument, col: int, row: int) -> EntityDocument | None:
    """Return the visually topmost world-space entity at one cell."""
    matches = entities_at_cell(area, col, row)
    return matches[0] if matches else None


def generate_entity_id(area: AreaDocument, template_id: str) -> str:
    """Generate a collision-safe entity id from the template basename."""
    base = (template_id.rsplit("/", 1)[-1] or "entity").replace(" ", "_")
    highest = 0
    for entity in area.entities:
        if entity.id == base:
            highest = max(highest, 1)
            continue
        prefix = f"{base}_"
        if not entity.id.startswith(prefix):
            continue
        suffix = entity.id[len(prefix):]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"{base}_{highest + 1}"


def place_entity(
    area: AreaDocument,
    template_id: str,
    col: int,
    row: int,
    *,
    entity_id: str | None = None,
    render_order: int = 10,
    y_sort: bool = True,
    sort_y_offset: float = 0.0,
    stack_order: int = 0,
) -> EntityDocument:
    """Append one new world-space entity to the area document."""
    created = EntityDocument(
        id=entity_id or generate_entity_id(area, template_id),
        grid_x=col,
        grid_y=row,
        template=template_id,
        render_order=render_order,
        y_sort=y_sort,
        sort_y_offset=sort_y_offset,
        stack_order=stack_order,
    )
    area.entities.append(created)
    return created


def place_screen_entity(
    area: AreaDocument,
    template_id: str,
    pixel_x: int,
    pixel_y: int,
    *,
    entity_id: str | None = None,
    render_order: int = 0,
    y_sort: bool = False,
    sort_y_offset: float = 0.0,
    stack_order: int = 0,
) -> EntityDocument:
    """Append one new screen-space entity to the area document."""
    created = EntityDocument(
        id=entity_id or generate_entity_id(area, template_id),
        pixel_x=pixel_x,
        pixel_y=pixel_y,
        space="screen",
        template=template_id,
        render_order=render_order,
        y_sort=y_sort,
        sort_y_offset=sort_y_offset,
        stack_order=stack_order,
    )
    area.entities.append(created)
    return created


def delete_entity_at(area: AreaDocument, col: int, row: int) -> str | None:
    """Delete the topmost world-space entity at one grid cell."""
    topmost = topmost_entity_at(area, col, row)
    if topmost is None:
        return None
    return delete_entity_by_id(area, topmost.id)


def delete_entity_by_id(area: AreaDocument, entity_id: str) -> str | None:
    """Delete one entity by id and return the removed id."""
    for index, entity in enumerate(area.entities):
        if entity.id != entity_id:
            continue
        del area.entities[index]
        return entity.id
    return None


def move_entity_by_id(
    area: AreaDocument,
    entity_id: str,
    dx: int,
    dy: int,
) -> bool:
    """Move one selected world-space entity by a tile delta inside area bounds."""
    entity = entity_by_id(area, entity_id)
    if entity is None or entity.is_screen_space:
        return False
    new_x = entity.x + dx
    new_y = entity.y + dy
    if not (0 <= new_x < area.width and 0 <= new_y < area.height):
        return False
    if new_x == entity.x and new_y == entity.y:
        return False
    entity.x = new_x
    entity.y = new_y
    return True


def move_entity_pixels(
    area: AreaDocument,
    entity_id: str,
    dx: int,
    dy: int,
) -> bool:
    """Move one entity's pixel_x/pixel_y by a delta.

    The caller is responsible for deciding whether pixel movement is the
    right operation for the selected entity.
    """
    entity = entity_by_id(area, entity_id)
    if entity is None:
        return False
    new_px = (entity.pixel_x or 0) + dx
    new_py = (entity.pixel_y or 0) + dy
    if new_px == (entity.pixel_x or 0) and new_py == (entity.pixel_y or 0):
        return False
    entity.pixel_x = new_px
    entity.pixel_y = new_py
    return True
