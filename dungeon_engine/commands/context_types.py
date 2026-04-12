"""Typed protocols for command-facing runtime services."""

from __future__ import annotations

from typing import Any, Protocol


class TextRendererLike(Protocol):
    """Minimal text-renderer surface used by command value sources."""

    def wrap_lines(
        self,
        text: str,
        max_width: int,
        *,
        font_id: str,
    ) -> list[str]:
        """Return wrapped text lines for the requested font."""


class AudioPlayerLike(Protocol):
    """Minimal audio surface used by presentation commands."""

    def play_audio(self, relative_path: str, *, volume: float | None = None) -> bool:
        """Play one-shot audio and return whether playback started."""

    def set_sound_volume(self, volume: float) -> None:
        """Set the default sound-effect volume."""

    def play_music(
        self,
        relative_path: str,
        *,
        loop: bool = True,
        volume: float | None = None,
        restart_if_same: bool = False,
    ) -> bool:
        """Start or resume background music."""

    def stop_music(self, *, fade_seconds: float = 0.0) -> bool:
        """Stop the current background music track."""

    def pause_music(self) -> bool:
        """Pause the current music track."""

    def resume_music(self) -> bool:
        """Resume the paused music track."""

    def set_music_volume(self, volume: float) -> None:
        """Set the dedicated music-channel volume."""


class ScreenElementManagerLike(Protocol):
    """Minimal screen-space UI surface used by presentation commands."""

    def show_image(
        self,
        *,
        element_id: str,
        asset_path: str,
        x: float,
        y: float,
        frame_width: int | None = None,
        frame_height: int | None = None,
        frame: int = 0,
        layer: int = 0,
        anchor: str = "topleft",
        flip_x: bool = False,
        tint: tuple[int, int, int] = (255, 255, 255),
        visible: bool = True,
    ) -> Any:
        """Create or replace a screen-space image element."""

    def show_text(
        self,
        *,
        element_id: str,
        text: str,
        x: float,
        y: float,
        layer: int = 0,
        anchor: str = "topleft",
        color: tuple[int, int, int],
        font_id: str,
        max_width: int | None = None,
        visible: bool = True,
    ) -> Any:
        """Create or replace a screen-space text element."""

    def set_text(self, element_id: str, text: str) -> None:
        """Replace the text content of an existing text element."""

    def remove(self, element_id: str) -> None:
        """Remove one screen element."""

    def clear(self, *, layer: int | None = None) -> None:
        """Clear all screen elements or only one layer."""

    def start_animation(
        self,
        *,
        element_id: str,
        frame_sequence: list[int],
        ticks_per_frame: int = 1,
        hold_last_frame: bool = True,
    ) -> None:
        """Start a screen-space image animation."""

    def is_animating(self, element_id: str) -> bool:
        """Return whether an element animation is still playing."""


class CameraLike(Protocol):
    """Minimal camera surface used by camera commands and $camera tokens."""

    x: float
    y: float

    def follow_entity(
        self,
        entity_id: str,
        *,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
    ) -> None:
        """Bind the camera to a specific entity id."""

    def follow_input_target(
        self,
        action: str,
        *,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
    ) -> None:
        """Bind the camera to the entity receiving one input action."""

    def clear_follow(self) -> None:
        """Stop automatically following a target."""

    def update(self, world: Any, *, advance_tick: bool = False) -> None:
        """Advance the camera update step."""

    def to_state_dict(self) -> dict[str, Any]:
        """Serialize the current camera policy."""

    def apply_state_dict(self, state: dict[str, Any], world: Any | None) -> None:
        """Apply one serialized camera policy."""

    def push_state(self) -> None:
        """Push the current camera state onto the stack."""

    def pop_state(self, world: Any | None) -> None:
        """Pop and apply one stored camera state."""

    def set_bounds_rect(self, x: float, y: float, width: float, height: float) -> None:
        """Clamp camera movement to one world-space rectangle."""

    def set_deadzone_rect(self, x: float, y: float, width: float, height: float) -> None:
        """Set a camera deadzone rectangle."""

    def start_move_to(
        self,
        target_x: float,
        target_y: float,
        *,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
    ) -> None:
        """Start an interpolated camera move."""

    def is_moving(self) -> bool:
        """Return whether the camera is in a manual move."""

    def teleport_to(self, target_x: float, target_y: float) -> None:
        """Teleport the camera instantly."""


class DialogueRuntimeLike(Protocol):
    """Minimal dialogue session surface used by dialogue commands."""

    def open_session(
        self,
        *,
        dialogue_path: str,
        dialogue_on_start: Any = None,
        dialogue_on_end: Any = None,
        segment_hooks: Any = None,
        allow_cancel: bool = False,
        actor_id: str | None = None,
        caller_id: str | None = None,
        ui_preset_name: str | None = None,
    ) -> Any:
        """Open a dialogue session and return the session handle."""

    def close_current_session(self) -> None:
        """Close the currently active dialogue session."""

    def is_session_live(self, session: Any) -> bool:
        """Return whether a session is still live in the runtime."""


class InventoryRuntimeLike(Protocol):
    """Minimal inventory session surface used by inventory commands."""

    def open_session(
        self,
        *,
        entity_id: str,
        ui_preset_name: str | None = None,
    ) -> Any:
        """Open an inventory session and return the session handle."""

    def close_current_session(self) -> None:
        """Close the active inventory session."""

    def is_session_live(self, session: Any) -> bool:
        """Return whether a session is still live in the runtime."""


class PersistenceRuntimeLike(Protocol):
    """Minimal persistence surface used by commands."""

    save_data: Any

    def set_current_area_variable(self, name: str, value: Any) -> None:
        """Persist one variable on the current area."""

    def set_area_variable(self, area_id: str, name: str, value: Any) -> None:
        """Persist one variable on a specific area."""

    def set_entity_field(
        self,
        entity_id: str,
        field_name: str,
        value: Any,
        *,
        entity: Any | None = None,
        tile_size: int | None = None,
    ) -> None:
        """Persist one entity field override."""

    def set_area_entity_field(
        self,
        area_id: str,
        entity_id: str,
        field_name: str,
        value: Any,
    ) -> None:
        """Persist one area-owned entity field override."""

    def set_entity_variable(
        self,
        entity_id: str,
        name: str,
        value: Any,
        *,
        entity: Any | None = None,
        tile_size: int | None = None,
    ) -> None:
        """Persist one entity variable override."""

    def set_area_entity_variable(
        self,
        area_id: str,
        entity_id: str,
        name: str,
        value: Any,
    ) -> None:
        """Persist one area-owned entity variable override."""

    def set_entity_command_enabled(
        self,
        entity_id: str,
        command_id: str,
        enabled: bool,
        *,
        entity: Any | None = None,
        tile_size: int | None = None,
    ) -> None:
        """Persist one entity-command enabled-state override."""

    def remove_entity(self, entity_id: str, *, entity: Any | None = None) -> None:
        """Persistently remove an entity."""

    def record_spawned_entity(self, entity: Any, *, tile_size: int) -> None:
        """Persist a spawned entity."""

    def request_reset(
        self,
        *,
        kind: str,
        apply: str = "immediate",
        entity_ids: list[str] | tuple[str, ...] | None = None,
        include_tags: list[str] | tuple[str, ...] | None = None,
        exclude_tags: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        """Queue a transient or persistent reset request."""
