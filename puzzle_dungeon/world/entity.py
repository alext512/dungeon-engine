"""Entity and movement data for the starter grid-based prototype."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from typing import Literal


Direction = Literal["up", "down", "left", "right"]

DIRECTION_VECTORS: dict[Direction, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


@dataclass(slots=True)
class MovementState:
    """Interpolation state for a tile-to-tile move."""

    active: bool = False
    start_grid_x: int = 0
    start_grid_y: int = 0
    target_grid_x: int = 0
    target_grid_y: int = 0
    elapsed: float = 0.0
    duration: float = 0.0


@dataclass(slots=True)
class Entity:
    """Runtime entity data kept separate from command execution logic."""

    entity_id: str
    kind: str
    grid_x: int
    grid_y: int
    pixel_x: float = 0.0
    pixel_y: float = 0.0
    facing: Direction = "down"
    solid: bool = True
    pushable: bool = False
    enabled: bool = True
    visible: bool = True
    layer: int = 1
    stack_order: int = 0
    color: tuple[int, int, int] = (255, 255, 255)
    template_id: str | None = None
    template_parameters: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    sprite_path: str = ""
    sprite_frame_width: int = 16
    sprite_frame_height: int = 16
    animation_frames: list[int] = field(default_factory=lambda: [0])
    animation_fps: float = 0.0
    animate_when_moving: bool = False
    current_frame: int = 0
    animation_elapsed: float = 0.0
    interact_commands: list[dict[str, Any]] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    movement: MovementState = field(default_factory=MovementState)

    def sync_pixel_position(self, tile_size: int) -> None:
        """Align pixel coordinates to the current grid coordinate."""
        self.pixel_x = self.grid_x * tile_size
        self.pixel_y = self.grid_y * tile_size
