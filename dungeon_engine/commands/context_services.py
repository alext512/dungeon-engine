"""Grouped command-facing runtime services and injectable service lookups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

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

    area: Area | None = None
    world: World | None = None
    collision_system: CollisionSystem | None = None
    movement_system: MovementSystem | None = None
    interaction_system: InteractionSystem | None = None
    animation_system: AnimationSystem | None = None


@dataclass(slots=True)
class CommandUiServices:
    """Screen, camera, and modal UI services used by commands."""

    text_renderer: TextRendererLike | None = None
    screen_manager: ScreenElementManagerLike | None = None
    camera: CameraLike | None = None
    dialogue_runtime: DialogueRuntimeLike | None = None
    inventory_runtime: InventoryRuntimeLike | None = None


@dataclass(slots=True)
class CommandAudioServices:
    """Audio playback helpers used by presentation commands."""

    audio_player: AudioPlayerLike | None = None


@dataclass(slots=True)
class CommandPersistenceServices:
    """Persistence helpers used by state-mutation commands."""

    persistence_runtime: PersistenceRuntimeLike | None = None


@dataclass(slots=True)
class CommandRuntimeServices:
    """Runtime hooks that let commands request higher-level actions."""

    request_area_change: Callable[[Any], None] | None = None
    request_new_game: Callable[[Any], None] | None = None
    request_load_game: Callable[[str | None], None] | None = None
    save_game: Callable[[str | None], bool] | None = None
    request_quit: Callable[[], None] | None = None
    set_simulation_paused: Callable[[bool], None] | None = None
    get_simulation_paused: Callable[[], bool] | None = None
    request_step_simulation_tick: Callable[[], None] | None = None
    adjust_output_scale: Callable[[int], None] | None = None
    debug_inspection_enabled: bool = False


@dataclass(slots=True)
class CommandServices:
    """Grouped services exposed to command implementations."""

    world: CommandWorldServices | None = None
    ui: CommandUiServices | None = None
    audio: CommandAudioServices | None = None
    persistence: CommandPersistenceServices | None = None
    runtime: CommandRuntimeServices | None = None


COMMAND_SERVICE_INJECTION_NAMES = frozenset(
    {
        "area",
        "world",
        "collision_system",
        "movement_system",
        "interaction_system",
        "animation_system",
        "text_renderer",
        "camera",
        "audio_player",
        "screen_manager",
        "dialogue_runtime",
        "inventory_runtime",
        "persistence_runtime",
        "request_area_change",
        "request_new_game",
        "request_load_game",
        "save_game",
        "request_quit",
        "debug_inspection_enabled",
        "set_simulation_paused",
        "get_simulation_paused",
        "request_step_simulation_tick",
        "adjust_output_scale",
    }
)


def resolve_service_injection(services: CommandServices, name: str) -> Any:
    """Return one injectable dependency from the grouped command services."""

    if name in {
        "area",
        "world",
        "collision_system",
        "movement_system",
        "interaction_system",
        "animation_system",
    }:
        world_services = services.world
        if world_services is None:
            return None
        return getattr(world_services, name)

    if name in {
        "text_renderer",
        "camera",
        "screen_manager",
        "dialogue_runtime",
        "inventory_runtime",
    }:
        ui_services = services.ui
        if ui_services is None:
            return None
        return getattr(ui_services, name)

    if name == "audio_player":
        audio_services = services.audio
        return None if audio_services is None else audio_services.audio_player

    if name == "persistence_runtime":
        persistence_services = services.persistence
        return (
            None
            if persistence_services is None
            else persistence_services.persistence_runtime
        )

    if name in {
        "request_area_change",
        "request_new_game",
        "request_load_game",
        "save_game",
        "request_quit",
        "debug_inspection_enabled",
        "set_simulation_paused",
        "get_simulation_paused",
        "request_step_simulation_tick",
        "adjust_output_scale",
    }:
        runtime_services = services.runtime
        if runtime_services is None:
            if name == "debug_inspection_enabled":
                return False
            return None
        return getattr(runtime_services, name)

    raise KeyError(f"Unknown service injection name '{name}'.")


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
            area=area,
            world=world,
            collision_system=collision_system,
            movement_system=movement_system,
            interaction_system=interaction_system,
            animation_system=animation_system,
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


def build_play_command_services(
    *,
    area: Area,
    world: World,
    collision_system: CollisionSystem,
    movement_system: MovementSystem,
    interaction_system: InteractionSystem,
    animation_system: AnimationSystem,
    text_renderer: TextRendererLike,
    screen_manager: ScreenElementManagerLike,
    camera: CameraLike,
    audio_player: AudioPlayerLike,
    persistence_runtime: PersistenceRuntimeLike,
    request_area_change: Callable[[Any], None],
    request_new_game: Callable[[Any], None],
    request_load_game: Callable[[str | None], None],
    save_game: Callable[[str | None], bool],
    request_quit: Callable[[], None],
    set_simulation_paused: Callable[[bool], None],
    get_simulation_paused: Callable[[], bool],
    request_step_simulation_tick: Callable[[], None],
    adjust_output_scale: Callable[[int], None],
    debug_inspection_enabled: bool = False,
) -> CommandServices:
    """Build the strict service bundle used by the play-mode runtime."""

    return CommandServices(
        world=CommandWorldServices(
            area=area,
            world=world,
            collision_system=collision_system,
            movement_system=movement_system,
            interaction_system=interaction_system,
            animation_system=animation_system,
        ),
        ui=CommandUiServices(
            text_renderer=text_renderer,
            screen_manager=screen_manager,
            camera=camera,
        ),
        audio=CommandAudioServices(audio_player=audio_player),
        persistence=CommandPersistenceServices(
            persistence_runtime=persistence_runtime,
        ),
        runtime=CommandRuntimeServices(
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
        ),
    )


def attach_modal_command_services(
    services: CommandServices,
    *,
    dialogue_runtime: DialogueRuntimeLike,
    inventory_runtime: InventoryRuntimeLike,
) -> None:
    """Attach modal runtimes after they receive the command context they need."""

    if services.ui is None:
        raise RuntimeError("Cannot attach modal runtimes without a UI service bundle.")
    services.ui.dialogue_runtime = dialogue_runtime
    services.ui.inventory_runtime = inventory_runtime


__all__ = [
    "COMMAND_SERVICE_INJECTION_NAMES",
    "CommandAudioServices",
    "CommandPersistenceServices",
    "CommandRuntimeServices",
    "CommandServices",
    "CommandUiServices",
    "CommandWorldServices",
    "attach_modal_command_services",
    "build_command_services",
    "build_play_command_services",
    "resolve_service_injection",
]
