"""Grouped command-facing runtime services and injectable service lookups."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar

from dungeon_engine.commands.context_types import (
    AreaTransitionCallback,
    AudioPlayerLike,
    CameraLike,
    DialogueRuntimeLike,
    InventoryRuntimeLike,
    LoadGameRequestCallback,
    OutputScaleAdjustCallback,
    PersistenceRuntimeLike,
    RuntimeQuitCallback,
    ScreenElementManagerLike,
    SaveGameCallback,
    SimulationPauseGetter,
    SimulationPauseSetter,
    SimulationStepRequestCallback,
    TextRendererLike,
)
from dungeon_engine.systems.animation import AnimationSystem
from dungeon_engine.systems.collision import CollisionSystem
from dungeon_engine.systems.interaction import InteractionSystem
from dungeon_engine.systems.movement import MovementSystem
from dungeon_engine.world.area import Area
from dungeon_engine.world.world import World


_T = TypeVar("_T")


def _require_play_service(value: _T | None, name: str) -> _T:
    if value is None:
        raise RuntimeError(f"Play command services require '{name}'.")
    return value


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

    request_area_change: AreaTransitionCallback | None = None
    request_new_game: AreaTransitionCallback | None = None
    request_load_game: LoadGameRequestCallback | None = None
    save_game: SaveGameCallback | None = None
    request_quit: RuntimeQuitCallback | None = None
    set_simulation_paused: SimulationPauseSetter | None = None
    get_simulation_paused: SimulationPauseGetter | None = None
    request_step_simulation_tick: SimulationStepRequestCallback | None = None
    adjust_output_scale: OutputScaleAdjustCallback | None = None
    debug_inspection_enabled: bool = False


@dataclass(slots=True)
class CommandServices:
    """Grouped services exposed to command implementations."""

    world: CommandWorldServices | None = None
    ui: CommandUiServices | None = None
    audio: CommandAudioServices | None = None
    persistence: CommandPersistenceServices | None = None
    runtime: CommandRuntimeServices | None = None


_SERVICE_BUNDLE_BY_INJECTION_NAME = {
    "area": "world",
    "world": "world",
    "collision_system": "world",
    "movement_system": "world",
    "interaction_system": "world",
    "animation_system": "world",
    "text_renderer": "ui",
    "screen_manager": "ui",
    "camera": "ui",
    "dialogue_runtime": "ui",
    "inventory_runtime": "ui",
    "audio_player": "audio",
    "persistence_runtime": "persistence",
    "request_area_change": "runtime",
    "request_new_game": "runtime",
    "request_load_game": "runtime",
    "save_game": "runtime",
    "request_quit": "runtime",
    "debug_inspection_enabled": "runtime",
    "set_simulation_paused": "runtime",
    "get_simulation_paused": "runtime",
    "request_step_simulation_tick": "runtime",
    "adjust_output_scale": "runtime",
}

COMMAND_SERVICE_INJECTION_NAMES = frozenset(_SERVICE_BUNDLE_BY_INJECTION_NAME)


def resolve_service_injection(services: CommandServices, name: str) -> Any:
    """Return one injectable dependency from the grouped command services."""

    bundle_name = _SERVICE_BUNDLE_BY_INJECTION_NAME.get(name)
    if bundle_name is None:
        raise KeyError(f"Unknown service injection name '{name}'.")

    service_bundle = getattr(services, bundle_name)
    if service_bundle is None:
        if name == "debug_inspection_enabled":
            return False
        return None
    return getattr(service_bundle, name)


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
    request_area_change: AreaTransitionCallback | None = None,
    request_new_game: AreaTransitionCallback | None = None,
    request_load_game: LoadGameRequestCallback | None = None,
    save_game: SaveGameCallback | None = None,
    request_quit: RuntimeQuitCallback | None = None,
    set_simulation_paused: SimulationPauseSetter | None = None,
    get_simulation_paused: SimulationPauseGetter | None = None,
    request_step_simulation_tick: SimulationStepRequestCallback | None = None,
    adjust_output_scale: OutputScaleAdjustCallback | None = None,
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
    request_area_change: AreaTransitionCallback,
    request_new_game: AreaTransitionCallback,
    request_load_game: LoadGameRequestCallback,
    save_game: SaveGameCallback,
    request_quit: RuntimeQuitCallback,
    set_simulation_paused: SimulationPauseSetter,
    get_simulation_paused: SimulationPauseGetter,
    request_step_simulation_tick: SimulationStepRequestCallback,
    adjust_output_scale: OutputScaleAdjustCallback,
    debug_inspection_enabled: bool = False,
) -> CommandServices:
    """Build the strict service bundle used by the play-mode runtime."""

    return CommandServices(
        world=CommandWorldServices(
            area=_require_play_service(area, "area"),
            world=_require_play_service(world, "world"),
            collision_system=_require_play_service(
                collision_system,
                "collision_system",
            ),
            movement_system=_require_play_service(
                movement_system,
                "movement_system",
            ),
            interaction_system=_require_play_service(
                interaction_system,
                "interaction_system",
            ),
            animation_system=_require_play_service(
                animation_system,
                "animation_system",
            ),
        ),
        ui=CommandUiServices(
            text_renderer=_require_play_service(text_renderer, "text_renderer"),
            screen_manager=_require_play_service(screen_manager, "screen_manager"),
            camera=_require_play_service(camera, "camera"),
        ),
        audio=CommandAudioServices(
            audio_player=_require_play_service(audio_player, "audio_player"),
        ),
        persistence=CommandPersistenceServices(
            persistence_runtime=_require_play_service(
                persistence_runtime,
                "persistence_runtime",
            ),
        ),
        runtime=CommandRuntimeServices(
            request_area_change=_require_play_service(
                request_area_change,
                "request_area_change",
            ),
            request_new_game=_require_play_service(
                request_new_game,
                "request_new_game",
            ),
            request_load_game=_require_play_service(
                request_load_game,
                "request_load_game",
            ),
            save_game=_require_play_service(save_game, "save_game"),
            request_quit=_require_play_service(request_quit, "request_quit"),
            set_simulation_paused=_require_play_service(
                set_simulation_paused,
                "set_simulation_paused",
            ),
            get_simulation_paused=_require_play_service(
                get_simulation_paused,
                "get_simulation_paused",
            ),
            request_step_simulation_tick=_require_play_service(
                request_step_simulation_tick,
                "request_step_simulation_tick",
            ),
            adjust_output_scale=_require_play_service(
                adjust_output_scale,
                "adjust_output_scale",
            ),
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
