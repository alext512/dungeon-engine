"""A more visual in-app editor for layered tiles, flags, and entity stacks."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pygame

from puzzle_dungeon import config
from puzzle_dungeon.engine.camera import Camera
from puzzle_dungeon.world.area import Area, TileLayer
from puzzle_dungeon.world.entity import Entity
from puzzle_dungeon.world.loader import instantiate_entity, list_entity_template_ids, load_area
from puzzle_dungeon.world.serializer import serialize_area
from puzzle_dungeon.world.world import World


@dataclass(slots=True)
class EditorAction:
    """A small event emitted by the editor for the game loop to react to."""

    kind: str
    message: str = ""


@dataclass(slots=True)
class EditorUiItem:
    """A simple clickable UI item used by the editor panels."""

    key: str
    label: str
    rect: pygame.Rect
    active: bool = False


@dataclass(slots=True)
class LevelEditor:
    """Edit the authoritative room document separately from playtest state."""

    area_path: Path
    area: Area
    world: World
    mode: str = "tile"
    selected_layer_index: int = 0
    selected_tile_index: int = 0
    selected_template_index: int = 0
    hovered_cell: tuple[int, int] | None = None
    selected_cell: tuple[int, int] | None = None
    selected_entity_id: str | None = None
    status_message: str = "Editor ready"
    dirty: bool = False
    tile_ids: list[str] = field(default_factory=list)
    template_ids: list[str] = field(default_factory=list)
    last_drag_cell: tuple[int, int] | None = None
    walk_brush_walkable: bool = True
    middle_pan_active: bool = False

    UI_GAP: int = 4
    RIGHT_PANEL_WIDTH: int = 0
    BOTTOM_PANEL_HEIGHT: int = 0

    def __post_init__(self) -> None:
        self._normalize_all_stack_orders()
        self.refresh_catalogs()
        player = self.world.get_player()
        self.selected_cell = (player.grid_x, player.grid_y)
        self._sync_selected_entity_to_cell()
        self.set_mode(self.mode)

    @property
    def map_viewport_rect(self) -> pygame.Rect:
        """Return the world-view rectangle reserved for the map canvas."""
        return pygame.Rect(0, 0, config.INTERNAL_WIDTH, config.INTERNAL_HEIGHT)

    @property
    def right_panel_rect(self) -> pygame.Rect:
        """Return the right-side toolbox panel rectangle."""
        return pygame.Rect(config.INTERNAL_WIDTH, 0, 0, 0)

    @property
    def bottom_panel_rect(self) -> pygame.Rect:
        """Return the bottom inspector panel rectangle."""
        return pygame.Rect(0, config.INTERNAL_HEIGHT, 0, 0)

    def refresh_catalogs(self) -> None:
        """Refresh tile and template lists when content definitions change."""
        self.tile_ids = list(self.area.tile_definitions.keys())
        self.template_ids = list_entity_template_ids()
        self.selected_tile_index %= max(1, len(self.tile_ids))
        self.selected_template_index %= max(1, len(self.template_ids))
        self.selected_layer_index %= max(1, len(self.area.tile_layers))

    @property
    def current_layer(self):
        """Return the currently selected tile layer."""
        return self.area.tile_layers[self.selected_layer_index]

    @property
    def current_layer_name(self) -> str:
        """Return the active visual layer name."""
        return self.current_layer.name

    @property
    def current_tile_id(self) -> str:
        """Return the currently selected tile id."""
        return self.tile_ids[self.selected_tile_index] if self.tile_ids else ""

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
        return {
            "tile": "tile",
            "walkability": "walk",
            "entity": "entity",
        }.get(self.mode, self.mode)

    @property
    def palette_title(self) -> str:
        """Return the active palette title for the right-side panel."""
        if self.mode == "tile":
            return "Tiles"
        if self.mode == "entity":
            return "Objects"
        return "Flags"

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
        if mode == "tile":
            self.status_message = f"Tile {self.current_tile_id} on {self.current_layer.name}"
        elif mode == "walkability":
            self.status_message = f"Walk brush {self.current_walk_brush_label}"
        else:
            self.status_message = f"Entity {self.current_template_id}"

    def selection_lines(self) -> list[str]:
        """Return compact mode-specific HUD lines for the editor."""
        lines = [f"Mode {self.mode_label}  Sel {self.selected_cell_label}  Dirty {self.dirty_label}"]
        if self.mode == "tile":
            lines.append(f"Layer {self.current_layer.name}  Brush {self.current_tile_id or '-'}")
        elif self.mode == "walkability":
            lines.append(f"Walk {self.cell_walk_label}")
        else:
            lines.append(f"Template {self.current_template_id or '-'}")
        lines.append(self.status_message)
        return lines

    def workflow_hint(self) -> str:
        """Return a short plain-language hint for the current workflow."""
        if self.mode == "tile":
            return "L paint  R erase  MMB pan"
        if self.mode == "walkability":
            return "L brush  R inverse  MMB pan"
        return "L place  R remove  MMB pan"

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
            tile_id = layer.grid[grid_y][grid_x] or "-"
            parts.append(f"{layer.name}: {tile_id}")
        return parts

    def build_preview_entity(self) -> Entity | None:
        """Build a temporary entity preview for the hovered cell."""
        if self.mode != "entity" or self.hovered_cell is None or not self.current_template_id:
            return None

        grid_x, grid_y = self.hovered_cell
        return instantiate_entity(
            {
                "id": "__preview__",
                "template": self.current_template_id,
                "x": grid_x,
                "y": grid_y,
            },
            self.area.tile_size,
        )

    def save(self) -> None:
        """Write the editable document to disk."""
        data = serialize_area(self.area, self.world)
        self.area_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self.dirty = False
        self.status_message = f"Saved {self.area_path.name}"

    def reload_from_disk(self) -> None:
        """Discard unsaved changes and reload the document from its JSON file."""
        self.area, self.world = load_area(self.area_path)
        self._normalize_all_stack_orders()
        self.refresh_catalogs()
        player = self.world.get_player()
        self.selected_cell = (player.grid_x, player.grid_y)
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
        grid = [[None for _ in range(width)] for _ in range(height)]
        self.area.tile_layers.append(
            TileLayer(
                name=layer_name,
                grid=grid,
                draw_above_entities=False,
            )
        )
        self.selected_layer_index = len(self.area.tile_layers) - 1
        self._choose_default_tile_for_layer()
        self._mark_dirty(f"Added {layer_name}")

    def remove_selected_layer(self) -> None:
        """Remove the active visual layer while keeping at least one layer alive."""
        if len(self.area.tile_layers) <= 1:
            self.status_message = "Keep at least one layer"
            return

        removed_name = self.current_layer.name
        del self.area.tile_layers[self.selected_layer_index]
        self.selected_layer_index = min(self.selected_layer_index, len(self.area.tile_layers) - 1)
        self._choose_default_tile_for_layer()
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

    def handle_events(self, events: list[pygame.event.Event], camera: Camera) -> list[EditorAction]:
        """Process editor input and return any game-level actions."""
        actions: list[EditorAction] = []
        for event in events:
            if event.type == pygame.QUIT:
                actions.append(EditorAction("quit"))
                continue

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    actions.append(EditorAction("quit"))
                    continue
                if event.key == pygame.K_F1:
                    actions.append(EditorAction("toggle_play"))
                    continue
                if event.key == pygame.K_F2:
                    self.set_mode("tile")
                    continue
                if event.key == pygame.K_F3:
                    self.set_mode("walkability")
                    continue
                if event.key == pygame.K_F4:
                    self.set_mode("entity")
                    continue
                if event.key == pygame.K_TAB:
                    self._step_layer(1)
                    continue
                if event.key == pygame.K_q:
                    self._cycle_selection(-1)
                    continue
                if event.key == pygame.K_e:
                    self._cycle_selection(1)
                    continue
                if event.key == pygame.K_r:
                    actions.append(EditorAction("reload_document"))
                    continue
                if event.key == pygame.K_DELETE:
                    self._remove_selected_entity()
                    continue
                if event.key == pygame.K_s and (event.mod & pygame.KMOD_CTRL):
                    self.save()
                    actions.append(EditorAction("saved", self.status_message))
                    continue

            if event.type == pygame.MOUSEMOTION:
                internal_pos = self._window_to_internal(event.pos)
                if self.middle_pan_active and event.buttons[1]:
                    camera.pan(-(event.rel[0] / config.SCALE), -(event.rel[1] / config.SCALE))
                self.hovered_cell = self._mouse_to_cell(internal_pos, camera)
                if (
                    not self.middle_pan_active
                    and self.mode in {"tile", "walkability"}
                    and self.hovered_cell is not None
                    and self.hovered_cell != self.last_drag_cell
                ):
                    if event.buttons[0]:
                        self._select_cell(*self.hovered_cell)
                        self._apply_primary()
                        self.last_drag_cell = self.hovered_cell
                    elif event.buttons[2]:
                        self._select_cell(*self.hovered_cell)
                        self._apply_secondary()
                        self.last_drag_cell = self.hovered_cell
                    else:
                        self.last_drag_cell = None
                elif not (event.buttons[0] or event.buttons[2]):
                    self.last_drag_cell = None
                continue

            if event.type == pygame.MOUSEBUTTONUP:
                if event.button in (1, 3):
                    self.last_drag_cell = None
                if event.button == 2:
                    self.middle_pan_active = False
                continue

            if event.type == pygame.MOUSEBUTTONDOWN:
                internal_pos = self._window_to_internal(event.pos)
                self.hovered_cell = self._mouse_to_cell(internal_pos, camera)

                if event.button == 2 and self.map_viewport_rect.collidepoint(internal_pos):
                    self.middle_pan_active = True
                    self.status_message = "Panning map"
                    continue

                if event.button in (4, 5):
                    self._handle_wheel(event.button)
                    continue

                if self._handle_ui_click(internal_pos, event.button, actions):
                    continue

                if self.hovered_cell is None:
                    continue

                if self.mode == "entity" and self.selected_cell != self.hovered_cell:
                    self._select_cell(*self.hovered_cell)
                    self.status_message = f"Cell {self.selected_cell_label} selected"
                    continue

                self._select_cell(*self.hovered_cell)
                if event.button == 1:
                    self._apply_primary()
                    self.last_drag_cell = self.hovered_cell
                elif event.button == 3:
                    self._apply_secondary()
                    self.last_drag_cell = self.hovered_cell
                continue

        return actions

    def update(self, dt: float, camera: Camera) -> None:
        """Handle continuous camera panning while editing."""
        _ = dt
        key_state = pygame.key.get_pressed()
        delta_x = 0.0
        delta_y = 0.0
        pan_step = config.EDITOR_CAMERA_PAN_SPEED / config.FPS
        if key_state[pygame.K_LEFT] or key_state[pygame.K_a]:
            delta_x -= pan_step
        if key_state[pygame.K_RIGHT] or key_state[pygame.K_d]:
            delta_x += pan_step
        if key_state[pygame.K_UP] or key_state[pygame.K_w]:
            delta_y -= pan_step
        if key_state[pygame.K_DOWN] or key_state[pygame.K_s]:
            delta_y += pan_step
        if delta_x or delta_y:
            camera.pan(delta_x, delta_y)

    def toolbar_items(self) -> list[EditorUiItem]:
        """Return action buttons and browser tabs for the asset panel."""
        panel = self.right_panel_rect
        padding = 4
        gap = 2
        button_height = 14
        usable_width = panel.width - (padding * 2)
        button_width = (usable_width - (gap * 2)) // 3
        x0 = panel.x + padding
        y0 = panel.y + 14

        items = [
            EditorUiItem("action:play", "Play", pygame.Rect(x0, y0, button_width, button_height)),
            EditorUiItem(
                "action:save",
                "Save",
                pygame.Rect(x0 + button_width + gap, y0, button_width, button_height),
            ),
            EditorUiItem(
                "action:load",
                "Load",
                pygame.Rect(x0 + ((button_width + gap) * 2), y0, button_width, button_height),
            ),
        ]
        y1 = y0 + button_height + gap
        items.extend(
            [
                EditorUiItem(
                    "mode:tile",
                    "Tiles",
                    pygame.Rect(x0, y1, button_width, button_height),
                    active=self.mode == "tile",
                ),
                EditorUiItem(
                    "mode:walkability",
                    "Flags",
                    pygame.Rect(x0 + button_width + gap, y1, button_width, button_height),
                    active=self.mode == "walkability",
                ),
                EditorUiItem(
                    "mode:entity",
                    "Objs",
                    pygame.Rect(x0 + ((button_width + gap) * 2), y1, button_width, button_height),
                    active=self.mode == "entity",
                ),
            ]
        )
        return items

    def layer_items(self) -> list[EditorUiItem]:
        """Return clickable layer chips for choosing the active visual layer."""
        panel = self.right_panel_rect
        padding = 4
        row_height = 12
        gap = 2
        start_y = panel.y + 60
        width = (panel.width - (padding * 2) - (gap * 2)) // 3
        items: list[EditorUiItem] = []
        for index, layer in enumerate(self.area.tile_layers):
            label = {"ground": "Gnd", "structure": "Str", "overlay": "Ovr"}.get(layer.name, layer.name[:3].title())
            items.append(
                EditorUiItem(
                    key=f"layer:{index}",
                    label=label,
                    rect=pygame.Rect(
                        panel.x + padding + (index * (width + gap)),
                        start_y,
                        width,
                        row_height,
                    ),
                    active=index == self.selected_layer_index,
                )
            )
        return items

    def palette_items(self) -> list[EditorUiItem]:
        """Return the active tile, walkability, or entity palette rows."""
        panel = self.right_panel_rect
        padding = 4
        row_height = 18
        gap = 2
        start_y = panel.y + 84
        width = panel.width - (padding * 2)
        items: list[EditorUiItem] = []

        if self.mode == "tile":
            for index, tile_id in enumerate(self.tile_ids):
                items.append(
                    EditorUiItem(
                        key=f"palette:tile:{tile_id}",
                        label=tile_id,
                        rect=pygame.Rect(panel.x + padding, start_y + (index * (row_height + gap)), width, row_height),
                        active=tile_id == self.current_tile_id,
                    )
                )
        elif self.mode == "walkability":
            items.extend(
                [
                    EditorUiItem(
                        key="palette:walk:walk",
                        label="Walkable",
                        rect=pygame.Rect(panel.x + padding, start_y, width, row_height),
                        active=self.walk_brush_walkable,
                    ),
                    EditorUiItem(
                        key="palette:walk:block",
                        label="Blocked",
                        rect=pygame.Rect(panel.x + padding, start_y + row_height + gap, width, row_height),
                        active=not self.walk_brush_walkable,
                    ),
                ]
            )
        elif self.mode == "entity":
            for index, template_id in enumerate(self.template_ids):
                items.append(
                    EditorUiItem(
                        key=f"palette:template:{template_id}",
                        label=template_id,
                        rect=pygame.Rect(panel.x + padding, start_y + (index * (row_height + gap)), width, row_height),
                        active=template_id == self.current_template_id,
                    )
                )
        return items

    def inspector_entity_items(self) -> list[EditorUiItem]:
        """Return one row per stacked entity in the selected cell."""
        panel = self.bottom_panel_rect
        row_height = 10
        gap = 2
        start_x = panel.x + 92
        start_y = panel.y + 24
        width = panel.width - 96
        items: list[EditorUiItem] = []
        for index, entity in enumerate(self.entities_for_selected_cell()[:3]):
            items.append(
                EditorUiItem(
                    key=f"cell-entity:{entity.entity_id}",
                    label=f"{index + 1} {entity.entity_id}",
                    rect=pygame.Rect(start_x, start_y + (index * (row_height + gap)), width, row_height),
                    active=entity.entity_id == self.selected_entity_id,
                )
            )
        return items

    def stack_action_items(self) -> list[EditorUiItem]:
        """Return buttons for managing the selected entity stack entry."""
        if self.selected_entity_id is None:
            return []
        panel = self.bottom_panel_rect
        gap = 2
        button_width = 26
        height = 12
        start_x = panel.right - ((button_width * 3) + (gap * 2)) - 4
        y = panel.bottom - height - 4
        items = [
            EditorUiItem(
                key="cell-entity-up",
                label="Up",
                rect=pygame.Rect(start_x, y, button_width, height),
            ),
            EditorUiItem(
                key="cell-entity-down",
                label="Dn",
                rect=pygame.Rect(start_x + button_width + gap, y, button_width, height),
            ),
        ]
        if self.selected_entity_id != self.world.player_id:
            items.append(
                EditorUiItem(
                    key="cell-entity-remove",
                    label="Del",
                    rect=pygame.Rect(start_x + ((button_width + gap) * 2), y, button_width, height),
                )
            )
        return items

    def entities_for_selected_cell(self) -> list[Entity]:
        """Return a stable, visible entity stack for the selected cell."""
        if self.selected_cell is None:
            return []
        grid_x, grid_y = self.selected_cell
        return list(self.world.get_entities_at(grid_x, grid_y, include_hidden=True))

    def _handle_wheel(self, button: int) -> None:
        """Handle scroll wheel selection changes."""
        direction = -1 if button == 4 else 1
        if self.mode == "tile" and (pygame.key.get_mods() & pygame.KMOD_SHIFT):
            self._step_layer(direction)
            return
        self._cycle_selection(direction)

    def _handle_ui_click(
        self,
        internal_pos: tuple[int, int],
        button: int,
        actions: list[EditorAction],
    ) -> bool:
        """Handle mouse clicks in the toolbar, palette, or inspector."""
        if button != 1:
            return False

        for item in self.toolbar_items():
            if item.rect.collidepoint(internal_pos):
                self._apply_ui_item(item, actions)
                return True

        for item in self.layer_items():
            if item.rect.collidepoint(internal_pos):
                self._apply_ui_item(item, actions)
                return True

        for item in self.palette_items():
            if item.rect.collidepoint(internal_pos):
                self._apply_ui_item(item, actions)
                return True

        for item in self.inspector_entity_items():
            if item.rect.collidepoint(internal_pos):
                self._apply_ui_item(item, actions)
                return True

        for item in self.stack_action_items():
            if item.rect.collidepoint(internal_pos):
                self._apply_ui_item(item, actions)
                return True

        return False

    def _apply_ui_item(self, item: EditorUiItem, actions: list[EditorAction]) -> None:
        """Apply a clicked UI item."""
        key = item.key
        if key == "action:play":
            actions.append(EditorAction("toggle_play"))
            return
        if key == "action:save":
            self.save()
            actions.append(EditorAction("saved", self.status_message))
            return
        if key == "action:load":
            actions.append(EditorAction("reload_document"))
            return
        if key.startswith("mode:"):
            self.set_mode(key.split(":", 1)[1])
            return
        if key.startswith("layer:"):
            self.selected_layer_index = int(key.split(":", 1)[1])
            if self.mode == "tile":
                self._choose_default_tile_for_layer()
            self.status_message = f"Layer {self.current_layer.name}"
            return
        if key.startswith("palette:tile:"):
            tile_id = key.split(":", 2)[2]
            if tile_id in self.tile_ids:
                self.selected_tile_index = self.tile_ids.index(tile_id)
                if self.mode != "tile":
                    self.set_mode("tile")
                else:
                    self.status_message = f"Brush {self.current_tile_id}"
            return
        if key.startswith("palette:template:"):
            template_id = key.split(":", 2)[2]
            if template_id in self.template_ids:
                self.selected_template_index = self.template_ids.index(template_id)
                if self.mode != "entity":
                    self.set_mode("entity")
                else:
                    self.status_message = f"Template {self.current_template_id}"
            return
        if key == "palette:walk:walk":
            self.walk_brush_walkable = True
            if self.mode != "walkability":
                self.set_mode("walkability")
            else:
                self.status_message = "Walk brush walk"
            return
        if key == "palette:walk:block":
            self.walk_brush_walkable = False
            if self.mode != "walkability":
                self.set_mode("walkability")
            else:
                self.status_message = "Walk brush block"
            return
        if key.startswith("cell-entity:"):
            self.selected_entity_id = key.split(":", 1)[1]
            self.status_message = f"Selected {self.selected_entity_id}"
            return
        if key == "cell-entity-up":
            self._move_selected_entity(-1)
            return
        if key == "cell-entity-down":
            self._move_selected_entity(1)
            return
        if key == "cell-entity-remove":
            self._remove_selected_entity()

    def _cycle_selection(self, direction: int) -> None:
        """Cycle the active selection for the current editor mode."""
        if self.mode == "tile" and self.tile_ids:
            self.selected_tile_index = (self.selected_tile_index + direction) % len(self.tile_ids)
            self.status_message = f"Brush {self.current_tile_id}"
        elif self.mode == "entity" and self.template_ids:
            self.selected_template_index = (self.selected_template_index + direction) % len(self.template_ids)
            self.status_message = f"Template {self.current_template_id}"

    def _step_layer(self, direction: int) -> None:
        """Cycle the active tile layer selection."""
        self.selected_layer_index = (self.selected_layer_index + direction) % len(self.area.tile_layers)
        if self.mode == "tile":
            self._choose_default_tile_for_layer()
        self.status_message = f"Layer {self.current_layer.name}"

    def _window_to_internal(self, mouse_pos: tuple[int, int]) -> tuple[int, int]:
        """Convert a scaled window mouse position to internal render coordinates."""
        return (int(mouse_pos[0] / config.SCALE), int(mouse_pos[1] / config.SCALE))

    def _mouse_to_cell(
        self,
        internal_pos: tuple[int, int],
        camera: Camera,
    ) -> tuple[int, int] | None:
        """Convert an internal mouse position to a tile coordinate inside the map viewport."""
        if not self.map_viewport_rect.collidepoint(internal_pos):
            return None

        world_x = internal_pos[0] + camera.render_x
        world_y = internal_pos[1] + camera.render_y
        grid_x = int(world_x // self.area.tile_size)
        grid_y = int(world_y // self.area.tile_size)
        if not self.area.in_bounds(grid_x, grid_y):
            return None
        return (grid_x, grid_y)

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

        removable = [entity for entity in entities if entity.entity_id != self.world.player_id]
        chosen = removable[-1] if removable else entities[-1]
        self.selected_entity_id = chosen.entity_id

    def _set_selected_walkability(self, walkable: bool) -> None:
        """Change the selected cell walkability from the inspector buttons."""
        if self.selected_cell is None:
            return
        grid_x, grid_y = self.selected_cell
        self._set_cell_walkability(grid_x, grid_y, walkable)

    def _set_cell_walkability(self, grid_x: int, grid_y: int, walkable: bool) -> None:
        """Write walkability to a specific cell independently from tile art."""
        current = bool(self.area.cell_flags[grid_y][grid_x].get("walkable", True))
        if current == walkable:
            self.status_message = "Walk unchanged" if walkable else "Block unchanged"
            return
        self.area.cell_flags[grid_y][grid_x]["walkable"] = walkable
        self._mark_dirty("Set walkable" if walkable else "Set blocked")

    def _pick_tile_from_selected_cell_layer(self) -> None:
        """Pick the tile currently present on the selected cell for the active layer."""
        if self.selected_cell is None:
            self._choose_default_tile_for_layer()
            return
        grid_x, grid_y = self.selected_cell
        tile_id = self.current_layer.grid[grid_y][grid_x]
        if tile_id and tile_id in self.tile_ids:
            self.selected_tile_index = self.tile_ids.index(tile_id)
            return
        self._choose_default_tile_for_layer()

    def _apply_primary(self) -> None:
        """Apply the left-click editor action at the selected cell."""
        if self.selected_cell is None:
            return
        grid_x, grid_y = self.selected_cell
        if self.mode == "tile":
            if self.current_layer.grid[grid_y][grid_x] == self.current_tile_id:
                self.status_message = f"Already {self.current_tile_id}"
                return
            self.current_layer.grid[grid_y][grid_x] = self.current_tile_id
            self._mark_dirty(f"Painted {self.current_tile_id}")
            return
        if self.mode == "walkability":
            self._set_cell_walkability(grid_x, grid_y, self.walk_brush_walkable)
            return
        if self.mode == "entity":
            self._place_entity(grid_x, grid_y)

    def _apply_secondary(self) -> None:
        """Apply the right-click editor action at the selected cell."""
        if self.selected_cell is None:
            return
        grid_x, grid_y = self.selected_cell
        if self.mode == "tile":
            replacement = self.tile_ids[0] if self.selected_layer_index == 0 and self.tile_ids else None
            if self.current_layer.grid[grid_y][grid_x] == replacement:
                self.status_message = "Nothing to erase"
                return
            self.current_layer.grid[grid_y][grid_x] = replacement
            self._mark_dirty(f"Erased {self.current_layer.name}")
            return
        if self.mode == "walkability":
            self._set_cell_walkability(grid_x, grid_y, not self.walk_brush_walkable)
            return
        if self.mode == "entity":
            self._remove_entity(grid_x, grid_y)

    def _place_entity(self, grid_x: int, grid_y: int) -> None:
        """Place a template-based entity at the requested cell."""
        template_id = self.current_template_id
        if not template_id:
            return

        if template_id == "player":
            player = self.world.get_player()
            player.grid_x = grid_x
            player.grid_y = grid_y
            player.sync_pixel_position(self.area.tile_size)
            self.selected_entity_id = player.entity_id
            self._mark_dirty("Moved player spawn")
            return

        entity_id = self.world.generate_entity_id(template_id)
        entity = instantiate_entity(
            {
                "id": entity_id,
                "template": template_id,
                "x": grid_x,
                "y": grid_y,
                "stack_order": self._next_stack_order(grid_x, grid_y),
            },
            self.area.tile_size,
        )
        self.world.add_entity(entity)
        self.selected_entity_id = entity_id
        self._mark_dirty(f"Placed {entity_id}")

    def _next_stack_order(self, grid_x: int, grid_y: int) -> int:
        """Return the next stack slot for a new entity on the given cell."""
        stack = self.world.get_entities_at(grid_x, grid_y, include_hidden=True)
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
                    if entity.entity_id == self.selected_entity_id and entity.entity_id != self.world.player_id
                ),
                None,
            )
        if entity_to_remove is None:
            removable = [entity for entity in candidates if entity.entity_id != self.world.player_id]
            if removable:
                entity_to_remove = removable[-1]

        if entity_to_remove is None:
            self.status_message = "Player can't be removed"
            return

        self.world.remove_entity(entity_to_remove.entity_id)
        self._sync_selected_entity_to_cell()
        self._mark_dirty(f"Removed {entity_to_remove.entity_id}")

    def _remove_selected_entity(self) -> None:
        """Remove the currently selected stacked entity from the inspector."""
        if self.selected_entity_id is None:
            self.status_message = "No entity selected"
            return
        if self.selected_entity_id == self.world.player_id:
            self.status_message = "Player can't be removed"
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
        for entity in self.world.iter_entities():
            cells.setdefault((entity.grid_x, entity.grid_y), []).append(entity)

        for stack in cells.values():
            for index, entity in enumerate(sorted(stack, key=self.world.entity_sort_key)):
                entity.stack_order = index

    def _apply_mode_defaults(self) -> None:
        """Pick immediately useful defaults for the active mode."""
        if self.mode == "tile":
            self._choose_default_tile_for_layer()
            return

        if self.mode == "entity":
            self._select_preferred_template(["block", "lever", "gate", "player"])

    def _choose_default_tile_for_layer(self) -> None:
        """Select a visible brush without assuming layer semantics."""
        if self.selected_cell is not None:
            grid_x, grid_y = self.selected_cell
            tile_id = self.current_layer.grid[grid_y][grid_x]
            if tile_id and tile_id in self.tile_ids:
                self.selected_tile_index = self.tile_ids.index(tile_id)
                return
        if self.tile_ids:
            self.selected_tile_index %= len(self.tile_ids)

    def _select_preferred_tile(self, tile_ids: list[str]) -> None:
        """Select the first available tile id from a preferred list."""
        for tile_id in tile_ids:
            if tile_id in self.tile_ids:
                self.selected_tile_index = self.tile_ids.index(tile_id)
                return

    def _select_preferred_template(self, template_ids: list[str]) -> None:
        """Select the first available entity template from a preferred list."""
        for template_id in template_ids:
            if template_id in self.template_ids:
                self.selected_template_index = self.template_ids.index(template_id)
                return

    def _generate_layer_name(self) -> str:
        """Generate a stable generic layer name without semantic assumptions."""
        used = {layer.name for layer in self.area.tile_layers}
        counter = 1
        while True:
            candidate = f"layer_{counter}"
            if candidate not in used:
                return candidate
            counter += 1
