"""Grouped command-facing runtime services."""

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
