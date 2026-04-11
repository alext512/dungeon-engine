"""Tool-owned document model for area JSON files.

Every dataclass pops the fields it understands from the raw dict and stores
the remainder in ``_extra``.  This guarantees unknown keys survive a
load -> save round-trip even when the runtime adds new fields the editor
does not yet know about.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from area_editor.json_io import compose_json_file_text, load_json_data
from area_editor.json_format import format_json_for_editor

# ---------------------------------------------------------------------------
# Leaf documents
# ---------------------------------------------------------------------------

CellFlag = bool | dict[str, Any] | None


def _normalize_entity_space(space: str) -> str:
    normalized = str(space).strip().lower()
    return normalized or "world"


def _default_entity_render_order(space: str) -> int:
    return 10 if _normalize_entity_space(space) == "world" else 0


def _default_entity_y_sort(space: str) -> bool:
    return _normalize_entity_space(space) == "world"


@dataclass
class TilesetRef:
    firstgid: int
    path: str
    tile_width: int
    tile_height: int
    _extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TilesetRef:
        d = dict(d)
        return cls(
            firstgid=d.pop("firstgid", 1),
            path=d.pop("path", ""),
            tile_width=d.pop("tile_width", 16),
            tile_height=d.pop("tile_height", 16),
            _extra=d,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "firstgid": self.firstgid,
            "path": self.path,
            "tile_width": self.tile_width,
            "tile_height": self.tile_height,
        }
        out.update(self._extra)
        return out


@dataclass
class TileLayerDocument:
    name: str
    render_order: int
    y_sort: bool
    sort_y_offset: float
    stack_order: int
    grid: list[list[int]]
    _extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TileLayerDocument:
        d = dict(d)
        return cls(
            name=d.pop("name", ""),
            render_order=int(d.pop("render_order", 0)),
            y_sort=bool(d.pop("y_sort", False)),
            sort_y_offset=float(d.pop("sort_y_offset", 0.0)),
            stack_order=int(d.pop("stack_order", 0)),
            grid=d.pop("grid", []),
            _extra=d,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "render_order": self.render_order,
            "y_sort": self.y_sort,
            "stack_order": self.stack_order,
            "grid": self.grid,
        }
        if self.sort_y_offset != 0:
            out["sort_y_offset"] = self.sort_y_offset
        out.update(self._extra)
        return out


@dataclass
class EntityDocument:
    """Thin wrapper around one authored entity instance.

    Only fields needed for placement and identification are promoted to
    typed attributes.  Everything else lives in ``_extra`` so the editor
    never silently drops unknown authored data.
    """

    id: str
    grid_x: int = 0
    grid_y: int = 0
    pixel_x: int | None = None
    pixel_y: int | None = None
    space: str = "world"
    render_order: int = 10
    y_sort: bool = True
    sort_y_offset: float = 0.0
    stack_order: int = 0
    template: str | None = None
    parameters: dict[str, Any] | None = None
    _extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EntityDocument:
        d = dict(d)
        space = d.pop("space", "world")
        return cls(
            id=d.pop("id", ""),
            grid_x=d.pop("grid_x", 0),
            grid_y=d.pop("grid_y", 0),
            pixel_x=d.pop("pixel_x", None),
            pixel_y=d.pop("pixel_y", None),
            space=space,
            render_order=int(d.pop("render_order", _default_entity_render_order(space))),
            y_sort=bool(d.pop("y_sort", _default_entity_y_sort(space))),
            sort_y_offset=float(d.pop("sort_y_offset", 0.0)),
            stack_order=int(d.pop("stack_order", 0)),
            template=d.pop("template", None),
            parameters=d.pop("parameters", None),
            _extra=d,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id}
        if self.space == "world":
            out["grid_x"] = self.grid_x
            out["grid_y"] = self.grid_y
        if self.pixel_x is not None:
            out["pixel_x"] = self.pixel_x
        if self.pixel_y is not None:
            out["pixel_y"] = self.pixel_y
        if self.space != "world":
            out["space"] = self.space
        if self.render_order != _default_entity_render_order(self.space):
            out["render_order"] = self.render_order
        if self.y_sort != _default_entity_y_sort(self.space):
            out["y_sort"] = self.y_sort
        if not math.isclose(float(self.sort_y_offset), 0.0, abs_tol=0.001):
            out["sort_y_offset"] = self.sort_y_offset
        if self.stack_order != 0:
            out["stack_order"] = self.stack_order
        if self.template is not None:
            out["template"] = self.template
        if self.parameters is not None:
            out["parameters"] = self.parameters
        out.update(self._extra)
        return out

    @property
    def is_screen_space(self) -> bool:
        return self.space == "screen"

    @property
    def x(self) -> int:
        return self.grid_x

    @x.setter
    def x(self, value: int) -> None:
        self.grid_x = int(value)

    @property
    def y(self) -> int:
        return self.grid_y

    @y.setter
    def y(self, value: int) -> None:
        self.grid_y = int(value)


# ---------------------------------------------------------------------------
# Root document
# ---------------------------------------------------------------------------


@dataclass
class AreaDocument:
    tile_size: int
    tilesets: list[TilesetRef]
    tile_layers: list[TileLayerDocument]
    cell_flags: list[list[CellFlag]]
    entry_points: dict[str, dict[str, Any]]
    entities: list[EntityDocument]
    camera: dict[str, Any]
    input_targets: dict[str, str]
    variables: dict[str, Any]
    enter_commands: list[Any]
    _extra: dict[str, Any] = field(default_factory=dict)

    # Derived geometry -------------------------------------------------------

    @property
    def width(self) -> int:
        """Map width in tiles (columns), derived from the first tile layer."""
        for layer in self.tile_layers:
            if layer.grid and layer.grid[0]:
                return len(layer.grid[0])
        return 0

    @property
    def height(self) -> int:
        """Map height in tiles (rows), derived from the first tile layer."""
        for layer in self.tile_layers:
            if layer.grid:
                return len(layer.grid)
        return 0

    # Serialisation ----------------------------------------------------------

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AreaDocument:
        d = dict(d)
        if "name" in d:
            raise ValueError("Area JSON must not declare 'name'; areas no longer support a display-name field.")
        tilesets = [TilesetRef.from_dict(t) for t in d.pop("tilesets", [])]
        tile_layers = [TileLayerDocument.from_dict(l) for l in d.pop("tile_layers", [])]
        entities = [EntityDocument.from_dict(e) for e in d.pop("entities", [])]
        return cls(
            tile_size=d.pop("tile_size", 16),
            tilesets=tilesets,
            tile_layers=tile_layers,
            cell_flags=d.pop("cell_flags", []),
            entry_points=d.pop("entry_points", {}),
            entities=entities,
            camera=d.pop("camera", {}),
            input_targets=d.pop("input_targets", {}),
            variables=d.pop("variables", {}),
            enter_commands=d.pop("enter_commands", []),
            _extra=d,
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "tile_size": self.tile_size,
            "tilesets": [t.to_dict() for t in self.tilesets],
            "tile_layers": [l.to_dict() for l in self.tile_layers],
        }
        if self.cell_flags:
            out["cell_flags"] = self.cell_flags
        if self.entry_points:
            out["entry_points"] = self.entry_points
        out["entities"] = [e.to_dict() for e in self.entities]
        if self.camera:
            out["camera"] = self.camera
        if self.input_targets:
            out["input_targets"] = self.input_targets
        if self.variables is not None:
            out["variables"] = self.variables
        if self.enter_commands:
            out["enter_commands"] = self.enter_commands
        out.update(self._extra)
        return out


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------


def load_area_document(file_path: Path) -> AreaDocument:
    """Read an area JSON file into a tool-owned document model."""
    raw = load_json_data(file_path)
    return AreaDocument.from_dict(raw)


def save_area_document(file_path: Path, document: AreaDocument) -> None:
    """Write an area document back to JSON with preserved unknown fields."""
    original_text = file_path.read_text(encoding="utf-8") if file_path.exists() else None
    text = format_json_for_editor(document.to_dict())
    file_path.write_text(
        compose_json_file_text(
            text,
            original_text=original_text,
            add_default_header=original_text is None and file_path.suffix.lower() == ".json5",
        ),
        encoding="utf-8",
    )
