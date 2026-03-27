"""Standalone editor document model and editing operations.

Works with the GID-based tilemap system. The editor discovers available tileset
PNGs, lets the user pick frames visually, and paints GIDs onto the grid.

Depends on: config, area, entity, world, loader
Used by: editor_app
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dungeon_engine.project import ProjectContext
from dungeon_engine.world.area import Area, TileLayer, Tileset
from dungeon_engine.world.entity import Entity
from dungeon_engine.world.loader import (
    extract_template_parameter_names,
    instantiate_entity,
    list_entity_template_ids,
    load_area,
)
from dungeon_engine.world.serializer import serialize_area
from dungeon_engine.world.world import World


def list_tileset_paths(project: ProjectContext) -> list[str]:
    """Scan the active project's asset roots recursively for PNG files."""
    return project.list_tileset_paths()


@dataclass(slots=True)
class LevelEditor:
    """Edit the authoritative room document used by the standalone editor."""

    area_path: Path
    area: Area
    world: World
    project: ProjectContext
    asset_manager: Any = None
    mode: str = "paint"
    paint_submode: str = "tile"
    selected_layer_index: int = 0

    # GID-based tile selection (replaces old tile_ids / selected_tile_index)
    selected_gid: int = 1
    available_tileset_paths: list[str] = field(default_factory=list)
    selected_tileset_index: int = 0

    # Entity selection
    selected_template_index: int = 0
    template_ids: list[str] = field(default_factory=list)

    hovered_cell: tuple[int, int] | None = None
    selected_cell: tuple[int, int] | None = None
    selected_entity_id: str | None = None
    status_message: str = "Editor ready"
    dirty: bool = False
    last_drag_cell: tuple[int, int] | None = None
    walk_brush_walkable: bool = True
    move_pending_entity_id: str | None = None
    show_walk_overlay: bool = False

    def __post_init__(self) -> None:
        self._normalize_all_stack_orders()
        self.refresh_catalogs()
        self.selected_cell = (0, 0) if self.area.width > 0 and self.area.height > 0 else None
        self.selected_entity_id = None
        self._sync_selected_entity_to_cell()
        self._apply_mode_defaults()

    def refresh_catalogs(self) -> None:
        """Refresh tileset and template lists when content definitions change."""
        current_tileset_path = self.current_tileset_path if self.available_tileset_paths else None
        self.available_tileset_paths = list_tileset_paths(self.project)
        self.template_ids = list_entity_template_ids(self.project)
        self.selected_template_index %= max(1, len(self.template_ids))
        self.selected_layer_index %= max(1, len(self.area.tile_layers))

        preferred_tileset_path = current_tileset_path or self._preferred_tileset_path()
        if self.available_tileset_paths:
            if preferred_tileset_path in self.available_tileset_paths:
                self.selected_tileset_index = self.available_tileset_paths.index(preferred_tileset_path)
            else:
                self.selected_tileset_index = self._fallback_tileset_index()
        else:
            self.selected_tileset_index = 0

        # Ensure selected_gid is valid (at least 1 if we have tilesets)
        if self.selected_gid <= 0 and self.area.tilesets:
            self.selected_gid = self.area.tilesets[0].firstgid

    @property
    def current_layer(self):
        """Return the currently selected tile layer."""
        return self.area.tile_layers[self.selected_layer_index]

    @property
    def current_layer_name(self) -> str:
        """Return the active visual layer name."""
        return self.current_layer.name

    @property
    def current_tileset_path(self) -> str:
        """Return the path of the currently browsed tileset."""
        if not self.available_tileset_paths:
            return ""
        return self.available_tileset_paths[self.selected_tileset_index]

    @property
    def current_gid_label(self) -> str:
        """Return a readable label for the selected GID (for HUD display)."""
        if self.selected_gid <= 0:
            return "none"
        resolved = self.area.resolve_gid(self.selected_gid)
        if resolved is None:
            return f"gid:{self.selected_gid}"
        path, _, _, frame = resolved
        stem = Path(path).stem
        return f"{stem}:{frame}"

    @property
    def current_template_id(self) -> str:
        """Return the currently selected entity template id."""
        return self.template_ids[self.selected_template_index] if self.template_ids else ""

    @property
    def hover_label(self) -> str:
        """Return the hovered tile coordinate in a compact HUD-friendly format."""
        if self.hovered_cell is None:
            return "-"
        return f"{self.hovered_cell[0]},{self.hovered_cell[1]}"

    @property
    def selected_cell_label(self) -> str:
        """Return the selected tile coordinate in a compact HUD-friendly format."""
        if self.selected_cell is None:
            return "-"
        return f"{self.selected_cell[0]},{self.selected_cell[1]}"

    @property
    def dirty_label(self) -> str:
        """Return a short dirty-state label for the HUD."""
        return "yes" if self.dirty else "no"

    @property
    def mode_label(self) -> str:
        """Return a short mode label for HUD text."""
        if self.paint_submode == "walk":
            return "walk"
        return "tile"

    @property
    def palette_title(self) -> str:
        """Return the active palette title for the right-side panel."""
        if self.paint_submode == "walk":
            return "Flags"
        return "Tiles"

    @property
    def current_walk_brush_label(self) -> str:
        """Return the active walkability brush label."""
        return "walk" if self.walk_brush_walkable else "block"

    @property
    def cell_walk_label(self) -> str:
        """Return the walkability state for the selected cell."""
        if self.selected_cell is None:
            return "-"
        grid_x, grid_y = self.selected_cell
        return "yes" if self.area.is_walkable(grid_x, grid_y) else "no"

    def set_mode(self, mode: str) -> None:
        """Switch editor mode and choose a useful default selection."""
        self.mode = mode
        self._apply_mode_defaults()
        if self.paint_submode == "tile":
            self.status_message = f"Tile {self.current_gid_label} on {self.current_layer.name}"
        else:
            self.status_message = f"Walk brush {self.current_walk_brush_label}"

    def toggle_paint_submode(self) -> None:
        """Toggle between tile and walkability painting sub-modes."""
        if self.paint_submode == "tile":
            self.paint_submode = "walk"
            self.show_walk_overlay = True
            self.status_message = f"Walk brush {self.current_walk_brush_label}"
        else:
            self.paint_submode = "tile"
            self.status_message = f"Tile {self.current_gid_label} on {self.current_layer.name}"

    def move_entity_to(self, entity_id: str, grid_x: int, grid_y: int) -> None:
        """Move an entity to a new cell position."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            self.status_message = f"Entity {entity_id} not found"
            return
        # Compute stack order at destination BEFORE moving the entity there
        new_order = self._next_stack_order(grid_x, grid_y)
        entity.grid_x = grid_x
        entity.grid_y = grid_y
        entity.sync_pixel_position(self.area.tile_size)
        entity.stack_order = new_order
        self._mark_dirty(f"Moved {entity_id} to ({grid_x},{grid_y})")

    def select_tileset_frame(self, tileset_index: int, local_frame: int) -> None:
        """Select a tile from a tileset for painting.

        If the tileset is not yet in the area, adds it automatically. Sets the
        computed GID as the current brush.
        """
        # Find or add the tileset in the area
        tileset_path = self.available_tileset_paths[tileset_index]
        area_ts_index = self._find_or_add_tileset(tileset_path)

        # Compute the GID
        gid = self.area.gid_for_tileset_frame(area_ts_index, local_frame)
        self.selected_gid = gid
        self.status_message = f"Tile {self.current_gid_label}"

    def _find_or_add_tileset(self, tileset_path: str) -> int:
        """Return the area tileset index for the given path, adding it if needed."""
        for idx, ts in enumerate(self.area.tilesets):
            if ts.path == tileset_path:
                return idx

        # Auto-add the tileset
        firstgid = self.area.next_available_firstgid()
        tile_width = self.area.tile_size
        tile_height = self.area.tile_size

        ts = Tileset(
            firstgid=firstgid,
            path=tileset_path,
            tile_width=tile_width,
            tile_height=tile_height,
        )

        # Compute columns and tile_count from the image if we have an asset_manager
        if self.asset_manager is not None:
            ts.columns = self.asset_manager.get_columns(tileset_path, tile_width)
            ts.tile_count = self.asset_manager.get_frame_count(tileset_path, tile_width, tile_height)

        self.area.tilesets.append(ts)
        self.area.build_gid_lookup()
        self._mark_dirty(f"Added tileset {Path(tileset_path).stem}")
        return len(self.area.tilesets) - 1

    def selection_lines(self) -> list[str]:
        """Return compact mode-specific HUD lines for the editor."""
        lines = [f"Mode {self.mode_label}  Sel {self.selected_cell_label}  Dirty {self.dirty_label}"]
        if self.paint_submode == "tile":
            lines.append(f"Layer {self.current_layer.name}  Brush {self.current_gid_label}")
        else:
            lines.append(f"Walk {self.cell_walk_label}")
        lines.append(self.status_message)
        return lines

    def workflow_hint(self) -> str:
        """Return a short plain-language hint for the current workflow."""
        if self.move_pending_entity_id:
            return f"Click to move {self.move_pending_entity_id}"
        if self.paint_submode == "walk":
            return "L brush  R inverse  MMB pan"
        return "L paint  R erase  MMB pan"

    def selected_layer_summary(self) -> str:
        """Return a short summary of all layer contents on the selected cell."""
        return "  ".join(self.selected_layer_lines())

    def selected_layer_lines(self) -> list[str]:
        """Return one compact line per visual layer for the selected cell."""
        if self.selected_cell is None:
            return [f"{layer.name}: -" for layer in self.area.tile_layers]

        grid_x, grid_y = self.selected_cell
        parts: list[str] = []
        for layer in self.area.tile_layers:
            gid = layer.grid[grid_y][grid_x]
            if gid <= 0:
                parts.append(f"{layer.name}: -")
            else:
                resolved = self.area.resolve_gid(gid)
                if resolved:
                    _, _, _, frame = resolved
                    parts.append(f"{layer.name}: {frame}")
                else:
                    parts.append(f"{layer.name}: gid:{gid}")
        return parts

    def build_preview_entity(self) -> Entity | None:
        """Build a temporary entity preview for the hovered cell (move-pending ghost)."""
        if self.move_pending_entity_id is None or self.hovered_cell is None:
            return None
        source = self.world.get_entity(self.move_pending_entity_id)
        if source is None:
            return None

        grid_x, grid_y = self.hovered_cell
        template_id = source.template_id or source.kind
        return instantiate_entity(
            {
                "id": "__preview__",
                "template": template_id,
                "x": grid_x,
                "y": grid_y,
            },
            self.area.tile_size,
            project=self.project,
            source_name="<preview entity>",
        )

    def save(self) -> None:
        """Write the editable document to disk."""
        data = serialize_area(self.area, self.world, project=self.project)
        self.area_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.dirty = False
        self.status_message = f"Saved {self.area_path.name}"

    def reload_from_disk(self) -> None:
        """Discard unsaved changes and reload the document from its JSON file."""
        self.area, self.world = load_area(
            self.area_path,
            asset_manager=self.asset_manager,
            project=self.project,
        )
        self._normalize_all_stack_orders()
        self.refresh_catalogs()
        self.selected_cell = (0, 0) if self.area.width > 0 and self.area.height > 0 else None
        self.selected_entity_id = None
        self.hovered_cell = None
        self.last_drag_cell = None
        self.dirty = False
        self._sync_selected_entity_to_cell()
        self.status_message = f"Reloaded {self.area_path.name}"

    def add_layer(self, name: str | None = None) -> None:
        """Append a new visual layer with an empty grid."""
        layer_name = (name or "").strip() or self._generate_layer_name()
        width = self.area.width
        height = self.area.height
        grid = [[0 for _ in range(width)] for _ in range(height)]
        self.area.tile_layers.append(
            TileLayer(
                name=layer_name,
                grid=grid,
                draw_above_entities=False,
            )
        )
        self.selected_layer_index = len(self.area.tile_layers) - 1
        self._mark_dirty(f"Added {layer_name}")

    def remove_selected_layer(self) -> None:
        """Remove the active visual layer while keeping at least one layer alive."""
        if len(self.area.tile_layers) <= 1:
            self.status_message = "Keep at least one layer"
            return

        removed_name = self.current_layer.name
        del self.area.tile_layers[self.selected_layer_index]
        self.selected_layer_index = min(self.selected_layer_index, len(self.area.tile_layers) - 1)
        self._mark_dirty(f"Removed {removed_name}")

    def rename_selected_layer(self, new_name: str) -> None:
        """Rename the active visual layer."""
        normalized = new_name.strip()
        if not normalized:
            self.status_message = "Layer name required"
            return
        if normalized == self.current_layer.name:
            self.status_message = "Layer unchanged"
            return
        self.current_layer.name = normalized
        self._mark_dirty(f"Renamed to {normalized}")

    # --- Entity property inspector ---

    def selected_entity_properties(self) -> list[tuple[str, str, str]]:
        """Return editable properties for the selected entity.

        Returns a list of (field_name, display_label, current_value_as_string).
        """
        if self.selected_entity_id is None:
            return []
        entity = self.world.get_entity(self.selected_entity_id)
        if entity is None:
            return []

        props: list[tuple[str, str, str]] = []
        props.append(("template_id", "Template", entity.template_id or "(inline)"))
        props.append(("kind", "Kind", entity.kind))
        props.append(("facing", "Facing", entity.facing))
        props.append(("solid", "Solid", str(entity.solid).lower()))
        props.append(("pushable", "Pushable", str(entity.pushable).lower()))
        props.append(("present", "Present", str(entity.present).lower()))
        props.append(("visible", "Visible", str(entity.visible).lower()))
        props.append(("events_enabled", "Events Enabled", str(entity.events_enabled).lower()))

        # Template parameters (the most useful for game design)
        for key, value in entity.template_parameters.items():
            props.append((f"param:{key}", key, str(value)))

        return props

    def set_entity_property(self, entity_id: str, field_name: str, value_str: str) -> None:
        """Apply a property change to an entity from the inspector."""
        entity = self.world.get_entity(entity_id)
        if entity is None:
            self.status_message = f"Entity {entity_id} not found"
            return

        if field_name.startswith("param:"):
            param_key = field_name[6:]
            previous_parameters = copy.deepcopy(entity.template_parameters)
            entity.template_parameters[param_key] = value_str
            self._refresh_template_entity(entity, previous_parameters=previous_parameters)
            self._mark_dirty(f"Set {param_key}={value_str}")
            return

        bool_fields = {"solid", "pushable", "present", "visible", "events_enabled"}
        if field_name in bool_fields:
            bool_val = value_str.lower() in ("true", "1", "yes")
            if field_name == "present":
                entity.set_present(bool_val)
            else:
                setattr(entity, field_name, bool_val)
            self._mark_dirty(f"Set {field_name}={bool_val}")
            return

        if field_name == "facing":
            if value_str in ("up", "down", "left", "right"):
                entity.facing = value_str
                self._mark_dirty(f"Facing {value_str}")
            else:
                self.status_message = "Facing must be up/down/left/right"
            return

        self.status_message = f"Cannot edit {field_name}"

    def entities_for_selected_cell(self) -> list[Entity]:
        """Return a stable, visible entity stack for the selected cell."""
        if self.selected_cell is None:
            return []
        grid_x, grid_y = self.selected_cell
        return list(self.world.get_entities_at(grid_x, grid_y, include_hidden=True, include_absent=True))

    # --- Internal helpers ---

    def _cycle_selection(self, direction: int) -> None:
        """Cycle the active selection for the current editor mode.

        In tile mode, cycles through frames of the currently viewed tileset.
        """
        if self.paint_submode == "tile":
            self._cycle_tileset_frame(direction)

    def _cycle_tileset_frame(self, direction: int) -> None:
        """Cycle through frames in the current tileset."""
        if not self.available_tileset_paths:
            return

        tileset_path = self.current_tileset_path
        # Find this tileset in the area (or get its frame count)
        area_ts = None
        for ts in self.area.tilesets:
            if ts.path == tileset_path:
                area_ts = ts
                break

        if area_ts is not None and area_ts.tile_count > 0:
            current_frame = self.selected_gid - area_ts.firstgid
            new_frame = (current_frame + direction) % area_ts.tile_count
            self.selected_gid = area_ts.firstgid + new_frame
        elif self.asset_manager is not None:
            # Tileset not in area yet, compute frame count
            frame_count = self.asset_manager.get_frame_count(
                tileset_path, self.area.tile_size, self.area.tile_size
            )
            if frame_count > 0:
                # Use a temporary frame index
                current_frame = max(0, self.selected_gid - 1) if self.area.tilesets else 0
                new_frame = (current_frame + direction) % frame_count
                self.select_tileset_frame(self.selected_tileset_index, new_frame)
                return

        self.status_message = f"Tile {self.current_gid_label}"

    def _step_layer(self, direction: int) -> None:
        """Cycle the active tile layer selection."""
        self.selected_layer_index = (self.selected_layer_index + direction) % len(self.area.tile_layers)
        self.status_message = f"Layer {self.current_layer.name}"

    def _select_cell(self, grid_x: int, grid_y: int) -> None:
        """Select a tile and synchronize the selected entity stack entry."""
        self.selected_cell = (grid_x, grid_y)
        self._sync_selected_entity_to_cell()

    def _sync_selected_entity_to_cell(self) -> None:
        """Choose a sensible entity selection for the currently selected cell."""
        entities = self.entities_for_selected_cell()
        if not entities:
            self.selected_entity_id = None
            return

        if any(entity.entity_id == self.selected_entity_id for entity in entities):
            return

        self.selected_entity_id = entities[-1].entity_id

    def _set_cell_walkability(self, grid_x: int, grid_y: int, walkable: bool) -> None:
        """Write walkability to a specific cell independently from tile art."""
        current = bool(self.area.cell_flags[grid_y][grid_x].get("walkable", True))
        if current == walkable:
            self.status_message = "Walk unchanged" if walkable else "Block unchanged"
            return
        self.area.cell_flags[grid_y][grid_x]["walkable"] = walkable
        self._mark_dirty("Set walkable" if walkable else "Set blocked")

    def _apply_primary(self) -> None:
        """Apply the left-click editor action at the selected cell."""
        if self.selected_cell is None:
            return
        grid_x, grid_y = self.selected_cell
        if self.paint_submode == "tile":
            if self.current_layer.grid[grid_y][grid_x] == self.selected_gid:
                self.status_message = f"Already {self.current_gid_label}"
                return
            self.current_layer.grid[grid_y][grid_x] = self.selected_gid
            self._mark_dirty(f"Painted {self.current_gid_label}")
            return
        if self.paint_submode == "walk":
            self._set_cell_walkability(grid_x, grid_y, self.walk_brush_walkable)

    def _apply_secondary(self) -> None:
        """Apply the right-click editor action at the selected cell."""
        if self.selected_cell is None:
            return
        grid_x, grid_y = self.selected_cell
        if self.paint_submode == "tile":
            # Erase: set to first GID on layer 0, or 0 (empty) on other layers
            replacement = self.area.tilesets[0].firstgid if self.selected_layer_index == 0 and self.area.tilesets else 0
            if self.current_layer.grid[grid_y][grid_x] == replacement:
                self.status_message = "Nothing to erase"
                return
            self.current_layer.grid[grid_y][grid_x] = replacement
            self._mark_dirty(f"Erased {self.current_layer.name}")
            return
        if self.paint_submode == "walk":
            self._set_cell_walkability(grid_x, grid_y, not self.walk_brush_walkable)

    def _place_entity(self, grid_x: int, grid_y: int) -> None:
        """Place a template-based entity at the requested cell."""
        template_id = self.current_template_id
        if not template_id:
            return

        entity_id = self.world.generate_entity_id(template_id)

        # Seed parameters from the template so the editor exposes them
        param_names = extract_template_parameter_names(template_id, project=self.project)
        parameters = {name: "" for name in param_names}

        entity = instantiate_entity(
            {
                "id": entity_id,
                "template": template_id,
                "x": grid_x,
                "y": grid_y,
                "stack_order": self._next_stack_order(grid_x, grid_y),
                "parameters": parameters,
            },
            self.area.tile_size,
            project=self.project,
            source_name=f"placed entity '{entity_id}'",
        )
        self.world.add_entity(entity)
        self.selected_entity_id = entity_id
        self._mark_dirty(f"Placed {entity_id}")

    def _refresh_template_entity(
        self,
        entity: Entity,
        *,
        previous_parameters: dict[str, Any],
    ) -> None:
        """Rebuild template-derived fields after a parameter edit.

        Template parameters are authored inputs, so changing them should
        regenerate command chains, variables, and any other data resolved from
        the template. We preserve only per-instance overrides that the current
        editor meaningfully owns, such as placement and a few basic booleans.
        """
        if entity.template_id is None:
            return

        instance_base = {
            "id": entity.entity_id,
            "template": entity.template_id,
            "x": entity.grid_x,
            "y": entity.grid_y,
        }
        old_entity = instantiate_entity(
            {
                **instance_base,
                "parameters": copy.deepcopy(previous_parameters),
            },
            self.area.tile_size,
            project=self.project,
            source_name=f"template refresh '{entity.entity_id}' (previous)",
        )
        rebuilt_entity = instantiate_entity(
            {
                **instance_base,
                "parameters": copy.deepcopy(entity.template_parameters),
            },
            self.area.tile_size,
            project=self.project,
            source_name=f"template refresh '{entity.entity_id}'",
        )

        # Keep placement/editor-managed overrides when they intentionally differ
        # from the previously resolved template state.
        override_fields = (
            "facing",
            "solid",
            "pushable",
            "present",
            "visible",
            "layer",
            "stack_order",
        )
        for field_name in override_fields:
            current_value = getattr(entity, field_name)
            old_value = getattr(old_entity, field_name)
            if current_value != old_value:
                setattr(rebuilt_entity, field_name, copy.deepcopy(current_value))

        if entity.color != old_entity.color:
            rebuilt_entity.color = tuple(entity.color)

        if entity.visuals != old_entity.visuals:
            rebuilt_entity.visuals = [visual.clone() for visual in entity.visuals]

        rebuilt_entity.stack_order = entity.stack_order
        rebuilt_entity.sync_pixel_position(self.area.tile_size)
        self.world.add_entity(rebuilt_entity)

    def _next_stack_order(self, grid_x: int, grid_y: int) -> int:
        """Return the next stack slot for a new entity on the given cell."""
        stack = self.world.get_entities_at(grid_x, grid_y, include_hidden=True, include_absent=True)
        if not stack:
            return 0
        return max(entity.stack_order for entity in stack) + 1

    def _remove_entity(self, grid_x: int, grid_y: int) -> None:
        """Remove either the selected entity on the cell or the topmost removable one."""
        candidates = self.entities_for_selected_cell()
        if (grid_x, grid_y) != self.selected_cell:
            self._select_cell(grid_x, grid_y)
            candidates = self.entities_for_selected_cell()

        if not candidates:
            self.status_message = "No entity here"
            return

        entity_to_remove = None
        if self.selected_entity_id is not None:
            entity_to_remove = next(
                (
                    entity
                    for entity in candidates
                    if entity.entity_id == self.selected_entity_id
                ),
                None,
            )
        if entity_to_remove is None:
            entity_to_remove = candidates[-1]

        self.world.remove_entity(entity_to_remove.entity_id)
        self._sync_selected_entity_to_cell()
        self._mark_dirty(f"Removed {entity_to_remove.entity_id}")

    def _remove_selected_entity(self) -> None:
        """Remove the currently selected stacked entity from the inspector."""
        if self.selected_entity_id is None:
            self.status_message = "No entity selected"
            return

        entity = self.world.get_entity(self.selected_entity_id)
        if entity is None:
            self.selected_entity_id = None
            self.status_message = "Entity missing"
            return

        self.world.remove_entity(entity.entity_id)
        self._sync_selected_entity_to_cell()
        self._mark_dirty(f"Removed {entity.entity_id}")

    def _move_selected_entity(self, direction: int) -> None:
        """Move the selected entity up or down within the selected-cell stack."""
        if self.selected_entity_id is None:
            self.status_message = "No entity selected"
            return

        stack = self.entities_for_selected_cell()
        current_index = next(
            (index for index, entity in enumerate(stack) if entity.entity_id == self.selected_entity_id),
            None,
        )
        if current_index is None:
            self.status_message = "Entity missing"
            return

        target_index = current_index + direction
        if target_index < 0 or target_index >= len(stack):
            self.status_message = "Already at edge"
            return

        current = stack[current_index]
        target = stack[target_index]
        if current.layer != target.layer:
            self.status_message = "Change layer order later"
            return

        current.stack_order, target.stack_order = target.stack_order, current.stack_order
        self._mark_dirty(f"Reordered {current.entity_id}")

    def _mark_dirty(self, message: str) -> None:
        """Update editor state after a document-changing action."""
        self.dirty = True
        self.status_message = message

    def _normalize_all_stack_orders(self) -> None:
        """Normalize stack orders so every cell has a clear persistent sequence."""
        cells: dict[tuple[int, int], list[Entity]] = {}
        for entity in self.world.iter_entities(include_absent=True):
            cells.setdefault((entity.grid_x, entity.grid_y), []).append(entity)

        for stack in cells.values():
            for index, entity in enumerate(sorted(stack, key=self.world.entity_sort_key)):
                entity.stack_order = index

    def _apply_mode_defaults(self) -> None:
        """Pick immediately useful defaults for the active mode."""
        # Default to first GID if nothing selected
        if self.selected_gid <= 0 and self.area.tilesets:
            self.selected_gid = self.area.tilesets[0].firstgid
        # Pre-select a useful entity template
        self._select_preferred_template(["block", "lever", "gate", "player"])

    def _select_preferred_template(self, template_ids: list[str]) -> None:
        """Select the first available entity template from a preferred list."""
        for template_id in template_ids:
            if template_id in self.template_ids:
                self.selected_template_index = self.template_ids.index(template_id)
                return

    def _preferred_tileset_path(self) -> str | None:
        """Return the best tileset/image path to focus when the catalog refreshes."""
        if self.selected_gid > 0:
            resolved = self.area.resolve_gid(self.selected_gid)
            if resolved is not None:
                return resolved[0]

        if self.area.tilesets:
            return self.area.tilesets[0].path

        return None

    def _fallback_tileset_index(self) -> int:
        """Pick a sensible default catalog entry when there is no current match."""
        for index, path in enumerate(self.available_tileset_paths):
            normalized = path.replace("\\", "/")
            if "/tiles/" in normalized:
                return index
        return 0

    def _generate_layer_name(self) -> str:
        """Generate a stable generic layer name without semantic assumptions."""
        used = {layer.name for layer in self.area.tile_layers}
        counter = 1
        while True:
            candidate = f"layer_{counter}"
            if candidate not in used:
                return candidate
            counter += 1

