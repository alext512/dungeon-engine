"""Grouped command-facing runtime services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, cast

from dungeon_engine.commands.context_types import (
    AudioPlayerLike,
    CameraLike,
    DialogueRuntimeLike,
    InventoryRuntimeLike,
    PersistenceRuntimeLike,
    ScreenElementManagerLike,
    TextRendererLike,
)
from dungeon_engine.systems.animation import AnimationSystem
from dungeon_engine.systems.collision import CollisionSystem
from dungeon_engine.systems.interaction import InteractionSystem
from dungeon_engine.systems.movement import MovementSystem
from dungeon_engine.world.area import Area
from dungeon_engine.world.world import World


@dataclass(slots=True)
class CommandWorldServices:
    """Core world and system services used by command execution."""

    area: Area
    world: World
    collision_system: CollisionSystem
    movement_system: MovementSystem
    interaction_system: InteractionSystem
    animation_system: AnimationSystem


@dataclass(slots=True)
class CommandUiServices:
    """Screen, camera, and modal UI services used by commands."""

    text_renderer: TextRendererLike | None
    screen_manager: ScreenElementManagerLike | None
    camera: CameraLike | None
    dialogue_runtime: DialogueRuntimeLike | None
    inventory_runtime: InventoryRuntimeLike | None


@dataclass(slots=True)
class CommandAudioServices:
    """Audio playback helpers used by presentation commands."""

    audio_player: AudioPlayerLike | None


@dataclass(slots=True)
class CommandPersistenceServices:
    """Persistence helpers used by state-mutation commands."""

    persistence_runtime: PersistenceRuntimeLike | None


@dataclass(slots=True)
class CommandRuntimeServices:
    """Runtime hooks that let commands request higher-level actions."""

    request_area_change: Callable[[Any], None] | None
    request_new_game: Callable[[Any], None] | None
    request_load_game: Callable[[str | None], None] | None
    save_game: Callable[[str | None], bool] | None
    request_quit: Callable[[], None] | None
    set_simulation_paused: Callable[[bool], None] | None
    get_simulation_paused: Callable[[], bool] | None
    request_step_simulation_tick: Callable[[], None] | None
    adjust_output_scale: Callable[[int], None] | None
    debug_inspection_enabled: bool


@dataclass(slots=True)
class CommandServices:
    """Grouped services exposed to command implementations."""

    world: CommandWorldServices | None = None
    ui: CommandUiServices | None = None
    audio: CommandAudioServices | None = None
    persistence: CommandPersistenceServices | None = None
    runtime: CommandRuntimeServices | None = None


def build_command_services(
    *,
    area: Area | None = None,
    world: World | None = None,
    collision_system: CollisionSystem | None = None,
    movement_system: MovementSystem | None = None,
    interaction_system: InteractionSystem | None = None,
    animation_system: AnimationSystem | None = None,
    text_renderer: TextRendererLike | None = None,
    screen_manager: ScreenElementManagerLike | None = None,
    camera: CameraLike | None = None,
    dialogue_runtime: DialogueRuntimeLike | None = None,
    inventory_runtime: InventoryRuntimeLike | None = None,
    audio_player: AudioPlayerLike | None = None,
    persistence_runtime: PersistenceRuntimeLike | None = None,
    request_area_change: Callable[[Any], None] | None = None,
    request_new_game: Callable[[Any], None] | None = None,
    request_load_game: Callable[[str | None], None] | None = None,
    save_game: Callable[[str | None], bool] | None = None,
    request_quit: Callable[[], None] | None = None,
    set_simulation_paused: Callable[[bool], None] | None = None,
    get_simulation_paused: Callable[[], bool] | None = None,
    request_step_simulation_tick: Callable[[], None] | None = None,
    adjust_output_scale: Callable[[int], None] | None = None,
    debug_inspection_enabled: bool = False,
) -> CommandServices:
    """Build one command-service bundle from the provided runtime slices."""
    services = CommandServices()
    if any(
        value is not None
        for value in (
            area,
            world,
            collision_system,
            movement_system,
            interaction_system,
            animation_system,
        )
    ):
        services.world = CommandWorldServices(
            area=cast(Area, area),
            world=cast(World, world),
            collision_system=cast(CollisionSystem, collision_system),
            movement_system=cast(MovementSystem, movement_system),
            interaction_system=cast(InteractionSystem, interaction_system),
            animation_system=cast(AnimationSystem, animation_system),
        )
    if any(
        value is not None
        for value in (
            text_renderer,
            screen_manager,
            camera,
            dialogue_runtime,
            inventory_runtime,
        )
    ):
        services.ui = CommandUiServices(
            text_renderer=text_renderer,
            screen_manager=screen_manager,
            camera=camera,
            dialogue_runtime=dialogue_runtime,
            inventory_runtime=inventory_runtime,
        )
    if audio_player is not None:
        services.audio = CommandAudioServices(audio_player=audio_player)
    if persistence_runtime is not None:
        services.persistence = CommandPersistenceServices(
            persistence_runtime=persistence_runtime,
        )
    if any(
        value is not None
        for value in (
            request_area_change,
            request_new_game,
            request_load_game,
            save_game,
            request_quit,
            set_simulation_paused,
            get_simulation_paused,
            request_step_simulation_tick,
            adjust_output_scale,
        )
    ) or debug_inspection_enabled:
        services.runtime = CommandRuntimeServices(
            request_area_change=request_area_change,
            request_new_game=request_new_game,
            request_load_game=request_load_game,
            save_game=save_game,
            request_quit=request_quit,
            set_simulation_paused=set_simulation_paused,
            get_simulation_paused=get_simulation_paused,
            request_step_simulation_tick=request_step_simulation_tick,
            adjust_output_scale=adjust_output_scale,
            debug_inspection_enabled=bool(debug_inspection_enabled),
        )
    return services
