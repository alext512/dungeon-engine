"""Runtime entity data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


Direction = Literal["up", "down", "left", "right"]
GridSyncPolicy = Literal["immediate", "on_complete", "none"]
EntitySpace = Literal["world", "screen"]
EntityScope = Literal["area", "global"]

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
    elapsed_ticks: int = 0
    total_ticks: int = 0
    grid_sync: GridSyncPolicy = "immediate"


@dataclass(slots=True)
class AnimationPlaybackState:
    """Command-driven visual playback state."""

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
class EntityVisual:
    """One persistent visual attached to an entity."""

    visual_id: str
    path: str = ""
    frame_width: int = 16
    frame_height: int = 16
    frames: list[int] = field(default_factory=lambda: [0])
    animation_fps: float = 0.0
    animate_when_moving: bool = False
    current_frame: int = 0
    animation_elapsed: float = 0.0
    flip_x: bool = False
    visible: bool = True
    tint: tuple[int, int, int] = (255, 255, 255)
    offset_x: float = 0.0
    offset_y: float = 0.0
    draw_order: int = 0
    animation_playback: AnimationPlaybackState = field(default_factory=AnimationPlaybackState)

    def clone(self) -> "EntityVisual":
        """Return a detached copy suitable for entity/template rebuilds."""
        return EntityVisual(
            visual_id=self.visual_id,
            path=self.path,
            frame_width=self.frame_width,
            frame_height=self.frame_height,
            frames=list(self.frames),
            animation_fps=self.animation_fps,
            animate_when_moving=self.animate_when_moving,
            current_frame=self.current_frame,
            animation_elapsed=self.animation_elapsed,
            flip_x=self.flip_x,
            visible=self.visible,
            tint=tuple(self.tint),
            offset_x=self.offset_x,
            offset_y=self.offset_y,
            draw_order=self.draw_order,
            animation_playback=AnimationPlaybackState(
                active=self.animation_playback.active,
                frame_sequence=list(self.animation_playback.frame_sequence),
                frames_per_sprite_change=self.animation_playback.frames_per_sprite_change,
                current_sequence_index=self.animation_playback.current_sequence_index,
                ticks_on_current_frame=self.animation_playback.ticks_on_current_frame,
                time_accumulator=self.animation_playback.time_accumulator,
                hold_last_frame=self.animation_playback.hold_last_frame,
            ),
        )


@dataclass(slots=True)
class Entity:
    """Runtime entity data kept separate from command execution logic."""

    entity_id: str
    kind: str
    grid_x: int
    grid_y: int
    pixel_x: float = 0.0
    pixel_y: float = 0.0
    space: EntitySpace = "world"
    scope: EntityScope = "area"
    present: bool = True
    visible: bool = True
    events_enabled: bool = True
    layer: int = 1
    stack_order: int = 0
    color: tuple[int, int, int] = (255, 255, 255)
    template_id: str | None = None
    template_parameters: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    visuals: list[EntityVisual] = field(default_factory=list)
    events: dict[str, EntityEvent] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    input_map: dict[str, str] = field(default_factory=dict)
    movement: MovementState = field(default_factory=MovementState)
    animation_playback: AnimationPlaybackState = field(default_factory=AnimationPlaybackState)
    session_entity_id: str | None = None
    origin_area_id: str | None = None
    origin_entity_id: str | None = None

    def sync_pixel_position(self, tile_size: int) -> None:
        """Align pixel coordinates to the current grid coordinate."""
        self.pixel_x = self.grid_x * tile_size
        self.pixel_y = self.grid_y * tile_size

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
            for visual in self.visuals:
                visual.animation_playback.active = False

    def is_world_space(self) -> bool:
        """Return True when the entity uses map/world coordinates."""
        return self.space == "world"

    def is_screen_space(self) -> bool:
        """Return True when the entity uses screen-space coordinates."""
        return self.space == "screen"

    def get_visual(self, visual_id: str) -> EntityVisual | None:
        """Return one visual by id when it exists."""
        for visual in self.visuals:
            if visual.visual_id == visual_id:
                return visual
        return None

    def require_visual(self, visual_id: str) -> EntityVisual:
        """Return one visual by id or fail clearly."""
        visual = self.get_visual(visual_id)
        if visual is None:
            raise KeyError(f"Entity '{self.entity_id}' has no visual '{visual_id}'.")
        return visual

    def get_primary_visual(self) -> EntityVisual | None:
        """Return the first visual when any exist."""
        if not self.visuals:
            return None
        return self.visuals[0]
