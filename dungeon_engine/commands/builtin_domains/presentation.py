"""Presentation-oriented builtin commands.

This module groups commands that operate on audio playback, screen-space UI,
simple time-based waiting, and entity-facing visual playback so future builtin
splits can follow one clear domain pattern without changing the public
``register_builtin_commands`` entry.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dungeon_engine import config
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import CommandHandle, ImmediateHandle, WaitFramesHandle


class ScreenAnimationCommandHandle(CommandHandle):
    """Wait until a screen-space animation finishes playback."""

    def __init__(self, screen_manager: Any, element_id: str) -> None:
        super().__init__()
        self.screen_manager = screen_manager
        self.element_id = element_id
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when the screen element stops animating."""
        self.complete = self.screen_manager is None or not self.screen_manager.is_animating(
            self.element_id
        )


class WaitSecondsHandle(CommandHandle):
    """Complete after a fixed amount of real dt has elapsed."""

    def __init__(self, seconds: float) -> None:
        super().__init__()
        self.seconds_remaining = max(0.0, float(seconds))
        if self.seconds_remaining <= 0.0:
            self.complete = True

    def update(self, dt: float) -> None:
        """Advance the timer using real elapsed seconds."""
        if self.complete or dt <= 0:
            return
        self.seconds_remaining -= float(dt)
        if self.seconds_remaining <= 0.0:
            self.complete = True


class AnimationCommandHandle(CommandHandle):
    """Wait until all entities started by an animation command finish playback."""

    def __init__(
        self,
        animation_system: Any,
        entity_ids: list[str],
        *,
        visual_id: str | None = None,
    ) -> None:
        super().__init__()
        self.animation_system = animation_system
        self.entity_ids = entity_ids
        self.visual_id = visual_id
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when every animated entity has finished."""
        self.complete = not any(
            self.animation_system.is_entity_animating(entity_id, visual_id=self.visual_id)
            for entity_id in self.entity_ids
        )


def _play_exact_animation(
    *,
    require_exact_entity: Callable[[Any, str], Any],
    world: Any,
    animation_system: Any,
    entity_id: str,
    visual_id: str | None = None,
    frame_sequence: list[int],
    frames_per_sprite_change: int = 1,
    hold_last_frame: bool = True,
    wait: bool = True,
    **_: Any,
) -> CommandHandle:
    """Start one exact entity animation and optionally wait for it to finish."""
    resolved_id = require_exact_entity(world, entity_id).entity_id
    animation_system.start_frame_animation(
        resolved_id,
        frame_sequence,
        visual_id=visual_id,
        frames_per_sprite_change=frames_per_sprite_change,
        hold_last_frame=hold_last_frame,
    )
    if not wait:
        return ImmediateHandle()
    return AnimationCommandHandle(animation_system, [resolved_id], visual_id=visual_id)


def register_presentation_commands(
    registry: CommandRegistry,
    *,
    require_exact_entity: Callable[[Any, str], Any],
) -> None:
    """Register audio, screen-space UI, timing, and entity-visual commands."""

    @registry.register("play_audio")
    def play_audio(
        audio_player: Any | None,
        *,
        path: str,
        volume: int | float | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Play a one-shot audio asset from the active project's assets."""
        if audio_player is None:
            return ImmediateHandle()
        audio_player.play_audio(str(path), volume=volume)
        return ImmediateHandle()

    @registry.register("set_sound_volume")
    def set_sound_volume(
        audio_player: Any | None,
        *,
        volume: int | float,
        **_: Any,
    ) -> CommandHandle:
        """Set the default sound-effect volume for future one-shot playback."""
        if audio_player is None:
            return ImmediateHandle()
        audio_player.set_sound_volume(float(volume))
        return ImmediateHandle()

    @registry.register("play_music")
    def play_music(
        audio_player: Any | None,
        *,
        path: str,
        loop: bool = True,
        volume: int | float | None = None,
        restart_if_same: bool = False,
        **_: Any,
    ) -> CommandHandle:
        """Start or resume one dedicated background music track."""
        if audio_player is None:
            return ImmediateHandle()
        audio_player.play_music(
            str(path),
            loop=bool(loop),
            volume=None if volume is None else float(volume),
            restart_if_same=bool(restart_if_same),
        )
        return ImmediateHandle()

    @registry.register("stop_music")
    def stop_music(
        audio_player: Any | None,
        *,
        fade_seconds: int | float = 0.0,
        **_: Any,
    ) -> CommandHandle:
        """Stop the current background music track."""
        if audio_player is None:
            return ImmediateHandle()
        audio_player.stop_music(fade_seconds=float(fade_seconds))
        return ImmediateHandle()

    @registry.register("pause_music")
    def pause_music(
        audio_player: Any | None,
        **_: Any,
    ) -> CommandHandle:
        """Pause the current background music track."""
        if audio_player is None:
            return ImmediateHandle()
        audio_player.pause_music()
        return ImmediateHandle()

    @registry.register("resume_music")
    def resume_music(
        audio_player: Any | None,
        **_: Any,
    ) -> CommandHandle:
        """Resume the paused background music track."""
        if audio_player is None:
            return ImmediateHandle()
        audio_player.resume_music()
        return ImmediateHandle()

    @registry.register("set_music_volume")
    def set_music_volume(
        audio_player: Any | None,
        *,
        volume: int | float,
        **_: Any,
    ) -> CommandHandle:
        """Set the dedicated music-channel volume."""
        if audio_player is None:
            return ImmediateHandle()
        audio_player.set_music_volume(float(volume))
        return ImmediateHandle()

    @registry.register("show_screen_image")
    def show_screen_image(
        screen_manager: Any | None,
        *,
        element_id: str,
        path: str,
        x: int | float,
        y: int | float,
        frame_width: int | None = None,
        frame_height: int | None = None,
        frame: int = 0,
        layer: int = 0,
        anchor: str = "topleft",
        flip_x: bool = False,
        tint: tuple[int, int, int] = (255, 255, 255),
        visible: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Create or replace a screen-space image element."""
        if screen_manager is None:
            raise ValueError("Cannot show a screen image without a screen manager.")
        screen_manager.show_image(
            element_id=str(element_id),
            asset_path=str(path),
            x=float(x),
            y=float(y),
            frame_width=int(frame_width) if frame_width is not None else None,
            frame_height=int(frame_height) if frame_height is not None else None,
            frame=int(frame),
            layer=int(layer),
            anchor=str(anchor),  # type: ignore[arg-type]
            flip_x=bool(flip_x),
            tint=tuple(int(channel) for channel in tint),
            visible=bool(visible),
        )
        return ImmediateHandle()

    @registry.register("show_screen_text")
    def show_screen_text(
        screen_manager: Any | None,
        *,
        element_id: str,
        text: str,
        x: int | float,
        y: int | float,
        layer: int = 0,
        anchor: str = "topleft",
        color: tuple[int, int, int] = config.COLOR_TEXT,
        font_id: str = config.DEFAULT_UI_FONT_ID,
        max_width: int | None = None,
        visible: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Create or replace a screen-space text element."""
        if screen_manager is None:
            raise ValueError("Cannot show screen text without a screen manager.")
        screen_manager.show_text(
            element_id=str(element_id),
            text=str(text),
            x=float(x),
            y=float(y),
            layer=int(layer),
            anchor=str(anchor),  # type: ignore[arg-type]
            color=tuple(int(channel) for channel in color),
            font_id=str(font_id),
            max_width=int(max_width) if max_width is not None else None,
            visible=bool(visible),
        )
        return ImmediateHandle()

    @registry.register("set_screen_text")
    def set_screen_text(
        screen_manager: Any | None,
        *,
        element_id: str,
        text: str,
        **_: Any,
    ) -> CommandHandle:
        """Replace the text content of an existing screen-space text element."""
        if screen_manager is None:
            raise ValueError("Cannot set screen text without a screen manager.")
        screen_manager.set_text(str(element_id), str(text))
        return ImmediateHandle()

    @registry.register("remove_screen_element")
    def remove_screen_element(
        screen_manager: Any | None,
        *,
        element_id: str,
        **_: Any,
    ) -> CommandHandle:
        """Remove one screen-space element."""
        if screen_manager is None:
            raise ValueError("Cannot remove a screen element without a screen manager.")
        screen_manager.remove(str(element_id))
        return ImmediateHandle()

    @registry.register("clear_screen_elements")
    def clear_screen_elements(
        screen_manager: Any | None,
        *,
        layer: int | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Clear all screen-space elements, optionally only one layer."""
        if screen_manager is None:
            raise ValueError("Cannot clear screen elements without a screen manager.")
        screen_manager.clear(layer=layer)
        return ImmediateHandle()

    @registry.register("play_screen_animation")
    def play_screen_animation(
        screen_manager: Any | None,
        *,
        element_id: str,
        frame_sequence: list[int],
        ticks_per_frame: int = 1,
        hold_last_frame: bool = True,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Start a one-shot frame animation on an existing screen image."""
        if screen_manager is None:
            raise ValueError("Cannot play a screen animation without a screen manager.")
        screen_manager.start_animation(
            element_id=str(element_id),
            frame_sequence=[int(frame) for frame in frame_sequence],
            ticks_per_frame=int(ticks_per_frame),
            hold_last_frame=bool(hold_last_frame),
        )
        if not wait:
            return ImmediateHandle()
        return ScreenAnimationCommandHandle(screen_manager, str(element_id))

    @registry.register("wait_for_screen_animation")
    def wait_for_screen_animation(
        screen_manager: Any | None,
        *,
        element_id: str,
        **_: Any,
    ) -> CommandHandle:
        """Block until the requested screen-space animation finishes."""
        if screen_manager is None:
            raise ValueError("Cannot wait for a screen animation without a screen manager.")
        if not screen_manager.is_animating(str(element_id)):
            return ImmediateHandle()
        return ScreenAnimationCommandHandle(screen_manager, str(element_id))

    @registry.register("wait_frames")
    def wait_frames(
        *,
        frames: int,
        **_: Any,
    ) -> CommandHandle:
        """Pause the current command lane for a fixed number of simulation ticks."""
        return WaitFramesHandle(int(frames))

    @registry.register("wait_seconds")
    def wait_seconds(
        *,
        seconds: int | float,
        **_: Any,
    ) -> CommandHandle:
        """Pause the current command lane for a fixed amount of elapsed time."""
        return WaitSecondsHandle(float(seconds))

    @registry.register("play_animation")
    def play_animation(
        world: Any,
        animation_system: Any,
        *,
        entity_id: str,
        visual_id: str | None = None,
        frame_sequence: list[int],
        frames_per_sprite_change: int = 1,
        hold_last_frame: bool = True,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Play a one-shot sprite frame sequence on an entity."""
        return _play_exact_animation(
            require_exact_entity=require_exact_entity,
            world=world,
            animation_system=animation_system,
            entity_id=entity_id,
            visual_id=visual_id,
            frame_sequence=frame_sequence,
            frames_per_sprite_change=frames_per_sprite_change,
            hold_last_frame=hold_last_frame,
            wait=wait,
        )

    @registry.register("wait_for_animation")
    def wait_for_animation(
        world: Any,
        animation_system: Any,
        *,
        entity_id: str,
        visual_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Block the command lane until the requested entity stops animating."""
        resolved_id = require_exact_entity(world, entity_id).entity_id
        if not animation_system.is_entity_animating(resolved_id, visual_id=visual_id):
            return ImmediateHandle()
        return AnimationCommandHandle(animation_system, [resolved_id], visual_id=visual_id)

    @registry.register("stop_animation")
    def stop_animation(
        world: Any,
        animation_system: Any,
        *,
        entity_id: str,
        visual_id: str | None = None,
        reset_to_default: bool = False,
        **_: Any,
    ) -> CommandHandle:
        """Stop command-driven animation playback on an entity."""
        resolved_id = require_exact_entity(world, entity_id).entity_id
        animation_system.stop_animation(
            resolved_id,
            visual_id=visual_id,
            reset_to_default=reset_to_default,
        )
        return ImmediateHandle()

    @registry.register("set_visual_frame")
    def set_visual_frame(
        world: Any,
        *,
        entity_id: str,
        visual_id: str | None = None,
        frame: int,
        **_: Any,
    ) -> CommandHandle:
        """Set the currently displayed visual frame directly."""
        entity = require_exact_entity(world, entity_id)
        visual = entity.require_visual(visual_id) if visual_id is not None else entity.get_primary_visual()
        if visual is None:
            raise KeyError(f"Entity '{entity.entity_id}' has no visual to set a frame on.")
        visual.current_frame = int(frame)
        return ImmediateHandle()

    @registry.register("set_visual_flip_x")
    def set_visual_flip_x(
        world: Any,
        *,
        entity_id: str,
        visual_id: str | None = None,
        flip_x: bool,
        **_: Any,
    ) -> CommandHandle:
        """Set whether an entity's visual should be mirrored horizontally."""
        entity = require_exact_entity(world, entity_id)
        visual = entity.require_visual(visual_id) if visual_id is not None else entity.get_primary_visual()
        if visual is None:
            raise KeyError(f"Entity '{entity.entity_id}' has no visual to set flip_x on.")
        visual.flip_x = bool(flip_x)
        return ImmediateHandle()


__all__ = ["register_presentation_commands"]
