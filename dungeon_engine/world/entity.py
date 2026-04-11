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
    persistent: bool | None = None
    persist_grid: bool = False
    persist_pixel: bool = False


@dataclass(slots=True)
class AnimationPlaybackState:
    """Command-driven visual playback state."""

    active: bool = False
    frame_sequence: list[int] = field(default_factory=list)
    duration_ticks: int = 0
    elapsed_ticks: int = 0
    current_sequence_index: int = 0
    started_this_tick: bool = False


@dataclass(slots=True)
class VisualAnimationClip:
    """One named animation clip authored under an entity visual."""

    frames: list[int] = field(default_factory=list)
    flip_x: bool | None = None
    preserve_phase: bool = False
    phase_index: int = 0

    def clone(self) -> "VisualAnimationClip":
        """Return a detached copy of this animation clip."""
        return VisualAnimationClip(
            frames=list(self.frames),
            flip_x=self.flip_x,
            preserve_phase=self.preserve_phase,
            phase_index=self.phase_index,
        )


@dataclass(slots=True)
class EntityCommandDefinition:
    """A named command chain owned by one entity."""

    enabled: bool = True
    commands: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class InventoryStack:
    """One ordered item stack in an entity-owned inventory."""

    item_id: str
    quantity: int = 1


@dataclass(slots=True)
class InventoryState:
    """Simple stack-based inventory data owned by one entity."""

    max_stacks: int = 0
    stacks: list[InventoryStack] = field(default_factory=list)


@dataclass(slots=True)
class EntityPersistencePolicy:
    """Authored persistence defaults for one entity."""

    entity_state: bool = False
    variables: dict[str, bool] = field(default_factory=dict)

    def resolve_field(self, *, explicit: bool | None = None) -> bool:
        """Return whether one entity-state mutation should persist."""
        if explicit is not None:
            return bool(explicit)
        return bool(self.entity_state)

    def resolve_variable(self, name: str, *, explicit: bool | None = None) -> bool:
        """Return whether one variable mutation should persist."""
        if explicit is not None:
            return bool(explicit)
        if name in self.variables:
            return bool(self.variables[name])
        return bool(self.entity_state)

    def is_default(self) -> bool:
        """Return True when the policy is equivalent to the engine default."""
        return not self.entity_state and not self.variables


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
    default_animation: str | None = None
    animations: dict[str, VisualAnimationClip] = field(default_factory=dict)
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
            default_animation=self.default_animation,
            animations={
                animation_id: clip.clone()
                for animation_id, clip in self.animations.items()
            },
            animation_playback=AnimationPlaybackState(
                active=self.animation_playback.active,
                frame_sequence=list(self.animation_playback.frame_sequence),
                duration_ticks=self.animation_playback.duration_ticks,
                elapsed_ticks=self.animation_playback.elapsed_ticks,
                current_sequence_index=self.animation_playback.current_sequence_index,
                started_this_tick=self.animation_playback.started_this_tick,
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
    facing: Direction = "down"
    solid: bool = False
    pushable: bool = False
    weight: int = 1
    push_strength: int = 0
    collision_push_strength: int = 0
    interactable: bool = False
    interaction_priority: int = 0
    entity_commands_enabled: bool = True
    render_order: int = 10
    y_sort: bool = True
    sort_y_offset: float = 0.0
    stack_order: int = 0
    color: tuple[int, int, int] = (255, 255, 255)
    template_id: str | None = None
    template_parameters: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    inventory: InventoryState | None = None
    visuals: list[EntityVisual] = field(default_factory=list)
    entity_commands: dict[str, EntityCommandDefinition] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    input_map: dict[str, str] = field(default_factory=dict)
    persistence: EntityPersistencePolicy = field(default_factory=EntityPersistencePolicy)
    movement_state: MovementState = field(default_factory=MovementState)
    animation_playback: AnimationPlaybackState = field(default_factory=AnimationPlaybackState)
    origin_area_id: str | None = None

    def sync_pixel_position(self, tile_size: int) -> None:
        """Align pixel coordinates to the current grid coordinate."""
        self.pixel_x = self.grid_x * tile_size
        self.pixel_y = self.grid_y * tile_size

    def get_entity_command(self, command_id: str) -> EntityCommandDefinition | None:
        """Return one named entity command definition when it exists."""
        return self.entity_commands.get(command_id)

    def has_enabled_entity_command(self, command_id: str) -> bool:
        """Return True when the named entity command exists and is enabled."""
        if not self.entity_commands_enabled:
            return False
        entity_command = self.get_entity_command(command_id)
        return entity_command is not None and entity_command.enabled

    def set_entity_command_enabled(self, command_id: str, enabled: bool) -> None:
        """Update the enabled state for one named entity command."""
        entity_command = self.get_entity_command(command_id)
        if entity_command is None:
            raise KeyError(f"Entity '{self.entity_id}' has no entity command '{command_id}'.")
        entity_command.enabled = enabled

    def set_entity_commands_enabled(self, enabled: bool) -> None:
        """Update the global enabled state for all named entity commands on this entity."""
        self.entity_commands_enabled = enabled

    def set_present(self, present: bool) -> None:
        """Update whether the entity participates in the current scene."""
        self.present = bool(present)
        if not self.present:
            self.movement_state.active = False
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

    def get_effective_facing(self) -> Direction:
        """Return the normalized engine-owned facing value."""
        resolved_facing = str(self.facing).strip().lower()
        if resolved_facing in DIRECTION_VECTORS:
            return resolved_facing  # type: ignore[return-value]
        return "down"

    def set_facing_value(self, facing: Direction) -> None:
        """Set the engine-owned facing field."""
        resolved_facing = str(facing).strip().lower()
        if resolved_facing not in DIRECTION_VECTORS:
            raise ValueError("Facing must be 'up', 'down', 'left', or 'right'.")
        self.facing = resolved_facing  # type: ignore[assignment]

    def is_effectively_solid(self) -> bool:
        """Return whether the entity currently blocks standard movement."""
        return bool(self.solid)

    def set_solid_value(self, solid: bool) -> None:
        """Set the engine-owned solid field."""
        self.solid = bool(solid)

    def is_effectively_pushable(self) -> bool:
        """Return whether the entity currently participates in push resolution."""
        return bool(self.pushable)

    def set_pushable_value(self, pushable: bool) -> None:
        """Set the engine-owned pushable field."""
        self.pushable = bool(pushable)

    def is_effectively_interactable(self) -> bool:
        """Return whether the entity should be considered by standard interaction lookup."""
        return bool(self.interactable) and self.has_enabled_entity_command("interact")
