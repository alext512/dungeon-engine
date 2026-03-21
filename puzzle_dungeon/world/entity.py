"""Entity and movement data for the starter grid-based prototype."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from typing import Literal


Direction = Literal["up", "down", "left", "right"]
GridSyncPolicy = Literal["immediate", "on_complete", "none"]

DIRECTION_VECTORS: dict[Direction, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


@dataclass(slots=True)
class MovementState:
    """Interpolation state for an in-progress runtime move."""

    active: bool = False
    start_grid_x: int = 0
    start_grid_y: int = 0
    target_grid_x: int | None = None
    target_grid_y: int | None = None
    start_pixel_x: float = 0.0
    start_pixel_y: float = 0.0
    target_pixel_x: float = 0.0
    target_pixel_y: float = 0.0
    elapsed: float = 0.0
    duration: float = 0.0
    grid_sync: GridSyncPolicy = "immediate"


@dataclass(slots=True)
class AnimationPlaybackState:
    """Command-driven sprite playback state."""

    active: bool = False
    frame_sequence: list[int] = field(default_factory=list)
    frames_per_sprite_change: int = 1
    current_sequence_index: int = 0
    ticks_on_current_frame: int = 0
    time_accumulator: float = 0.0
    hold_last_frame: bool = True


@dataclass(slots=True)
class EntityEvent:
    """A named command group owned by an entity."""

    enabled: bool = True
    commands: list[dict[str, Any]] = field(default_factory=list)


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
    present: bool = True
    visible: bool = True
    events_enabled: bool = True
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
    events: dict[str, EntityEvent] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    movement: MovementState = field(default_factory=MovementState)
    animation_playback: AnimationPlaybackState = field(default_factory=AnimationPlaybackState)

    def sync_pixel_position(self, tile_size: int) -> None:
        """Align pixel coordinates to the current grid coordinate."""
        self.pixel_x = self.grid_x * tile_size
        self.pixel_y = self.grid_y * tile_size

    @property
    def interact_commands(self) -> list[dict[str, Any]]:
        """Backward-compatible access to the interact event command list."""
        event = self.events.get("interact")
        if event is None:
            return []
        return event.commands

    @interact_commands.setter
    def interact_commands(self, commands: list[dict[str, Any]]) -> None:
        """Backward-compatible setter for the interact event command list."""
        if commands:
            self.events["interact"] = EntityEvent(
                enabled=self.events.get("interact", EntityEvent()).enabled,
                commands=commands,
            )
            return
        self.events.pop("interact", None)

    def get_event(self, event_id: str) -> EntityEvent | None:
        """Return a named event definition when it exists."""
        return self.events.get(event_id)

    def has_enabled_event(self, event_id: str) -> bool:
        """Return True when the named event exists and is enabled."""
        if not self.events_enabled:
            return False
        event = self.get_event(event_id)
        return event is not None and event.enabled

    def set_event_enabled(self, event_id: str, enabled: bool) -> None:
        """Update the enabled state for one named event."""
        event = self.get_event(event_id)
        if event is None:
            raise KeyError(f"Entity '{self.entity_id}' has no event '{event_id}'.")
        event.enabled = enabled

    def set_events_enabled(self, enabled: bool) -> None:
        """Update the global enabled state for all events on this entity."""
        self.events_enabled = enabled

    def set_present(self, present: bool) -> None:
        """Update whether the entity participates in the current scene."""
        self.present = bool(present)
        if not self.present:
            self.movement.active = False
            self.animation_playback.active = False
