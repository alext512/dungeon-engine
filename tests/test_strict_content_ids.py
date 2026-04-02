from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import run_game
from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.library import (
    ProjectCommandValidationError,
    validate_project_commands,
)
from dungeon_engine.inventory import inventory_item_count
from dungeon_engine.items import (
    ItemDefinitionValidationError,
    load_item_definition,
    validate_project_items,
)
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import (
    AreaTransitionRequest,
    CommandRunner,
    CommandExecutionError,
    CommandContext,
    SequenceCommandHandle,
    _resolve_runtime_values,
    execute_command_spec,
    execute_registered_command,
)
from dungeon_engine.world.area import Area, TileLayer
from dungeon_engine.world.entity import (
    Entity,
    EntityCommandDefinition,
    EntityVisual,
    InventoryStack,
    InventoryState,
)
from dungeon_engine.world.world import World
from dungeon_engine.project import load_project
from dungeon_engine.world.loader import (
    AreaValidationError,
    EntityTemplateValidationError,
    instantiate_entity,
    load_area_from_data,
    validate_project_areas,
    validate_project_entity_templates,
)
from dungeon_engine.world.serializer import serialize_area
from dungeon_engine.world.persistence import (
    PersistenceRuntime,
    apply_area_travelers,
    apply_current_global_state,
    apply_persistent_global_state,
    apply_persistent_area_state,
    capture_current_global_state,
    capture_current_area_state,
    save_data_from_dict,
    save_data_to_dict,
)
from dungeon_engine.engine.asset_manager import AssetManager
from dungeon_engine.engine.audio import AudioPlayer
from dungeon_engine.engine.dialogue_runtime import DialogueRuntime
from dungeon_engine.engine.inventory_runtime import InventoryRuntime
from dungeon_engine.engine.input_handler import InputHandler
from dungeon_engine.engine.renderer import Renderer
from dungeon_engine.engine.screen import ScreenElementManager
from dungeon_engine.engine.text import TextRenderer
from dungeon_engine.systems.collision import CollisionSystem
from dungeon_engine.systems.interaction import InteractionSystem
from dungeon_engine.systems.movement import MovementSystem


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _minimal_area(*, name: str = "Test Room") -> dict[str, object]:
    return {
        "name": name,
        "tile_size": 16,
        "input_targets": {
            "move_up": "player",
            "move_down": "player",
            "move_left": "player",
            "move_right": "player",
            "interact": "player",
        },
        "variables": {},
        "tilesets": [
            {
                "firstgid": 1,
                "path": "assets/project/tiles/test.png",
                "tile_width": 16,
                "tile_height": 16,
            }
        ],
        "tile_layers": [
            {
                "name": "ground",
                "render_order": 0,
                "grid": [[1]],
            }
        ],
        "cell_flags": [[True]],
        "entities": [],
    }


def _minimal_item(
    *,
    name: str = "Apple",
    description: str | None = None,
    icon: dict[str, object] | None = None,
    portrait: dict[str, object] | None = None,
    max_stack: int = 9,
    consume_quantity_on_use: int = 0,
    use_commands: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": name,
        "max_stack": max_stack,
        "consume_quantity_on_use": consume_quantity_on_use,
    }
    if description is not None:
        payload["description"] = description
    if icon is not None:
        payload["icon"] = copy.deepcopy(icon)
    if portrait is not None:
        payload["portrait"] = copy.deepcopy(portrait)
    if use_commands is not None:
        payload["use_commands"] = use_commands
    return payload


def _dialogue_shared_variables() -> dict[str, object]:
    return {
        "dialogue_ui": {
            "default_preset": "standard",
            "presets": {
                "standard": {
                    "panel": {
                        "path": "assets/project/ui/dialogue_panel.png",
                        "x": 0,
                        "y": 148,
                    },
                    "portrait_slot": {
                        "x": 3,
                        "y": 151,
                        "width": 38,
                        "height": 38,
                    },
                    "text": {
                        "plain": {
                            "x": 8,
                            "y": 154,
                            "width": 240,
                            "max_lines": 3,
                        },
                        "with_portrait": {
                            "x": 56,
                            "y": 154,
                            "width": 192,
                            "max_lines": 3,
                        },
                    },
                    "choices": {
                        "mode": "inline",
                        "visible_rows": 3,
                        "base_y": 154,
                        "row_height": 10,
                        "overflow": "marquee",
                        "plain": {
                            "x": 8,
                            "width": 240,
                        },
                        "with_portrait": {
                            "x": 56,
                            "width": 188,
                        },
                    },
                    "font_id": "pixelbet",
                    "text_color": [245, 232, 190],
                    "choice_text_color": [238, 242, 248],
                    "ui_layer": 100,
                    "text_layer": 101,
                },
                "separate_choices": {
                    "panel": {
                        "path": "assets/project/ui/dialogue_panel.png",
                        "x": 0,
                        "y": 148,
                    },
                    "portrait_slot": {
                        "x": 3,
                        "y": 151,
                        "width": 38,
                        "height": 38,
                    },
                    "text": {
                        "plain": {
                            "x": 8,
                            "y": 154,
                            "width": 240,
                            "max_lines": 3,
                        },
                        "with_portrait": {
                            "x": 56,
                            "y": 154,
                            "width": 192,
                            "max_lines": 3,
                        },
                    },
                    "choices": {
                        "mode": "separate_panel",
                        "visible_rows": 3,
                        "x": 24,
                        "y": 96,
                        "width": 120,
                        "row_height": 10,
                        "overflow": "marquee",
                        "panel": {
                            "path": "assets/project/ui/dialogue_panel.png",
                            "x": 16,
                            "y": 88,
                        },
                    },
                    "font_id": "pixelbet",
                    "text_color": [245, 232, 190],
                    "choice_text_color": [238, 242, 248],
                    "ui_layer": 100,
                    "text_layer": 101,
                }
            },
        }
    }


def _inventory_shared_variables() -> dict[str, object]:
    shared_variables = _dialogue_shared_variables()
    shared_variables["inventory_ui"] = {
        "default_preset": "standard",
        "presets": {
            "standard": {
                "deny_sfx_path": "assets/project/sfx/bump.wav",
            }
        },
    }
    return shared_variables


def _minimal_runtime_area() -> Area:
    return Area(
        area_id="areas/test_room",
        name="Test Room",
        tile_size=16,
        tilesets=[],
        tile_layers=[],
        cell_flags=[],
    )


def _make_runtime_entity(
    entity_id: str,
    *,
    kind: str = "system",
    space: str = "world",
    scope: str = "area",
    with_visual: bool = False,
    entity_commands: dict[str, EntityCommandDefinition] | None = None,
) -> Entity:
    visuals = (
        [
            EntityVisual(
                visual_id="main",
                path="assets/project/sprites/test.png",
                frame_width=16,
                frame_height=16,
                frames=[0],
            )
        ]
        if with_visual
        else []
    )
    return Entity(
        entity_id=entity_id,
        kind=kind,
        grid_x=0,
        grid_y=0,
        space=space,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        visuals=visuals,
        entity_commands=entity_commands or {},
    )


class _RecordingAnimationSystem:
    def __init__(self) -> None:
        self.started: list[tuple[str, list[int], str | None, int, bool]] = []
        self.queries: list[tuple[str, str | None]] = []

    def start_frame_animation(
        self,
        entity_id: str,
        frame_sequence: list[int],
        *,
        visual_id: str | None = None,
        frames_per_sprite_change: int = 1,
        hold_last_frame: bool = True,
    ) -> None:
        self.started.append(
            (
                entity_id,
                list(frame_sequence),
                visual_id,
                frames_per_sprite_change,
                hold_last_frame,
            )
        )

    def is_entity_animating(self, entity_id: str, *, visual_id: str | None = None) -> bool:
        self.queries.append((entity_id, visual_id))
        return False


class _RecordingMovementSystem:
    def __init__(self) -> None:
        self.grid_steps: list[tuple[str, str, float | None, int | None, float | None, str]] = []
        self.move_to_positions: list[
            tuple[str, float, float, float | None, int | None, float | None, str, int | None, int | None]
        ] = []
        self.move_by_offsets: list[
            tuple[str, float, float, float | None, int | None, float | None, str, int | None, int | None]
        ] = []
        self.move_to_grid_positions: list[tuple[str, int, int, float | None, int | None, float | None, str]] = []
        self.move_by_grid_offsets: list[tuple[str, int, int, float | None, int | None, float | None, str]] = []
        self.teleport_grid_positions: list[tuple[str, int, int]] = []
        self.teleport_positions: list[tuple[str, float, float, int | None, int | None]] = []
        self.moving_entities: set[str] = set()

    def request_grid_step(
        self,
        entity_id: str,
        direction: str,
        *,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str = "immediate",
    ) -> list[str]:
        self.grid_steps.append(
            (entity_id, direction, duration, frames_needed, speed_px_per_second, grid_sync)
        )
        return [entity_id]

    def request_move_to_position(
        self,
        entity_id: str,
        x: float,
        y: float,
        *,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str = "none",
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
    ) -> list[str]:
        self.move_to_positions.append(
            (entity_id, x, y, duration, frames_needed, speed_px_per_second, grid_sync, target_grid_x, target_grid_y)
        )
        return [entity_id]

    def request_move_by_offset(
        self,
        entity_id: str,
        x: float,
        y: float,
        *,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str = "none",
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
    ) -> list[str]:
        self.move_by_offsets.append(
            (entity_id, x, y, duration, frames_needed, speed_px_per_second, grid_sync, target_grid_x, target_grid_y)
        )
        return [entity_id]

    def request_move_to_grid_position(
        self,
        entity_id: str,
        x: int,
        y: int,
        *,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str = "on_complete",
    ) -> list[str]:
        self.move_to_grid_positions.append(
            (entity_id, x, y, duration, frames_needed, speed_px_per_second, grid_sync)
        )
        return [entity_id]

    def request_move_by_grid_offset(
        self,
        entity_id: str,
        x: int,
        y: int,
        *,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str = "on_complete",
    ) -> list[str]:
        self.move_by_grid_offsets.append(
            (entity_id, x, y, duration, frames_needed, speed_px_per_second, grid_sync)
        )
        return [entity_id]

    def teleport_to_grid_position(self, entity_id: str, x: int, y: int) -> None:
        self.teleport_grid_positions.append((entity_id, x, y))

    def teleport_to_position(
        self,
        entity_id: str,
        x: float,
        y: float,
        *,
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
    ) -> None:
        self.teleport_positions.append((entity_id, x, y, target_grid_x, target_grid_y))

    def is_entity_moving(self, entity_id: str) -> bool:
        return entity_id in self.moving_entities


class _RecordingCamera:
    def __init__(self) -> None:
        self.follow_mode: str | None = None
        self.followed_entity_id: str | None = None
        self.follow_input_action: str | None = None
        self.follow_offset_x = 0.0
        self.follow_offset_y = 0.0
        self.bounds: dict[str, float] | None = None
        self.deadzone: dict[str, float] | None = None
        self.x = 0.0
        self.y = 0.0
        self.update_calls: list[tuple[World, bool]] = []
        self.state_stack: list[dict[str, object]] = []

    def follow_entity(
        self,
        entity_id: str,
        *,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
    ) -> None:
        self.follow_mode = "entity"
        self.followed_entity_id = entity_id
        self.follow_input_action = None
        self.follow_offset_x = float(offset_x)
        self.follow_offset_y = float(offset_y)

    def follow_input_target(
        self,
        action: str,
        *,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
    ) -> None:
        self.follow_mode = "input_target"
        self.followed_entity_id = None
        self.follow_input_action = action
        self.follow_offset_x = float(offset_x)
        self.follow_offset_y = float(offset_y)

    def update(self, world: World, *, advance_tick: bool = True) -> None:
        self.update_calls.append((world, advance_tick))

    def clear_follow(self) -> None:
        self.follow_mode = "none"
        self.followed_entity_id = None
        self.follow_input_action = None
        self.follow_offset_x = 0.0
        self.follow_offset_y = 0.0

    def set_bounds_rect(self, x: float, y: float, width: float, height: float) -> None:
        self.bounds = {
            "x": float(x),
            "y": float(y),
            "width": float(width),
            "height": float(height),
        }

    def clear_bounds(self) -> None:
        self.bounds = None

    def set_deadzone_rect(self, x: float, y: float, width: float, height: float) -> None:
        self.deadzone = {
            "x": float(x),
            "y": float(y),
            "width": float(width),
            "height": float(height),
        }

    def clear_deadzone(self) -> None:
        self.deadzone = None

    def push_state(self) -> None:
        self.state_stack.append(self.to_state_dict())

    def pop_state(self, world: World | None) -> None:
        if not self.state_stack:
            raise ValueError("Camera state stack is empty.")
        self.apply_state_dict(self.state_stack.pop(), world)

    def to_state_dict(self) -> dict[str, object]:
        follow: dict[str, object] = {
            "mode": self.follow_mode or "none",
            "offset_x": self.follow_offset_x,
            "offset_y": self.follow_offset_y,
        }
        if self.followed_entity_id is not None:
            follow["entity_id"] = self.followed_entity_id
        if self.follow_input_action is not None:
            follow["action"] = self.follow_input_action
        data: dict[str, object] = {
            "x": self.x,
            "y": self.y,
            "follow": follow,
        }
        if self.bounds is not None:
            data["bounds"] = dict(self.bounds)
        if self.deadzone is not None:
            data["deadzone"] = dict(self.deadzone)
        return data

    def apply_state_dict(self, state: dict[str, object], world: World | None) -> None:
        _ = world
        self.bounds = None
        self.deadzone = None
        if "bounds" in state and state["bounds"] is not None:
            self.bounds = dict(state["bounds"])  # type: ignore[arg-type]
        if "deadzone" in state and state["deadzone"] is not None:
            self.deadzone = dict(state["deadzone"])  # type: ignore[arg-type]
        self.x = float(state.get("x", self.x))
        self.y = float(state.get("y", self.y))
        raw_follow = state.get("follow")
        follow = raw_follow if isinstance(raw_follow, dict) else {"mode": "none"}
        mode = str(follow.get("mode", "none"))
        self.follow_mode = mode
        self.followed_entity_id = None
        self.follow_input_action = None
        self.follow_offset_x = float(follow.get("offset_x", 0.0))
        self.follow_offset_y = float(follow.get("offset_y", 0.0))
        if mode == "entity":
            entity_id = str(follow.get("entity_id", "")).strip()
            if entity_id:
                self.followed_entity_id = entity_id
            else:
                self.follow_mode = "none"
        elif mode == "input_target":
            action = str(follow.get("action", "")).strip()
            if action:
                self.follow_input_action = action
            else:
                self.follow_mode = "none"


class _StubTextRenderer:
    def measure_text(self, text: str, *, font_id: str = "") -> tuple[int, int]:
        _ = font_id
        lines = str(text).split("\n")
        longest = max((len(line) for line in lines), default=0)
        return (longest * 6, max(1, len(lines)) * 8)

    def wrap_lines(self, text: str, max_width: int, *, font_id: str = "") -> list[str]:
        _ = max_width
        _ = font_id
        return [part for part in str(text).split(" ") if part]

    def paginate_text(
        self,
        text: str,
        max_width: int,
        max_lines: int,
        *,
        font_id: str = "",
    ) -> list[str]:
        lines = self.wrap_lines(text, max_width, font_id=font_id)
        if not lines:
            return [""]
        chunk_size = max(1, int(max_lines))
        pages: list[str] = []
        for index in range(0, len(lines), chunk_size):
            pages.append("\n".join(lines[index:index + chunk_size]))
        return pages or [""]


class _FacingStateCollisionSystem:
    def __init__(self, *, blocking_entity=None, can_move: bool = True) -> None:
        self.blocking_entity = blocking_entity
        self.can_move = can_move

    def get_blocking_entity(
        self,
        target_x: int,
        target_y: int,
        *,
        ignore_entity_id: str | None = None,
    ):
        _ = target_x, target_y, ignore_entity_id
        return self.blocking_entity

    def can_move_to(
        self,
        target_x: int,
        target_y: int,
        *,
        ignore_entity_id: str | None = None,
    ) -> bool:
        _ = target_x, target_y, ignore_entity_id
        return self.can_move


class _RecordingInputDispatchRunner:
    def __init__(self) -> None:
        self.dispatched: list[tuple[str, str]] = []

    def has_pending_work(self) -> bool:
        return False

    def dispatch_input_entity_command(
        self,
        *,
        entity_id: str,
        command_id: str,
    ) -> bool:
        self.dispatched.append((entity_id, command_id))
        return True


class _FixedRandom:
    def __init__(self, *, randint_result: int, choice_result: Any) -> None:
        self.randint_result = randint_result
        self.choice_result = choice_result
        self.randint_calls: list[tuple[int, int]] = []
        self.choice_calls: list[list[Any]] = []

    def randint(self, minimum: int, maximum: int) -> int:
        self.randint_calls.append((minimum, maximum))
        return self.randint_result

    def choice(self, values: list[Any]) -> Any:
        self.choice_calls.append(list(values))
        return self.choice_result


class _RecordingAudioPlayer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def play_audio(self, path: str, *, volume: float | None = None) -> bool:
        self.calls.append(("play_audio", (path,), {"volume": volume}))
        return True

    def set_sound_volume(self, volume: float) -> None:
        self.calls.append(("set_sound_volume", (float(volume),), {}))

    def play_music(
        self,
        path: str,
        *,
        loop: bool = True,
        volume: float | None = None,
        restart_if_same: bool = False,
    ) -> bool:
        self.calls.append(
            (
                "play_music",
                (path,),
                {
                    "loop": bool(loop),
                    "volume": volume,
                    "restart_if_same": bool(restart_if_same),
                },
            )
        )
        return True

    def stop_music(self, *, fade_seconds: float = 0.0) -> bool:
        self.calls.append(("stop_music", (), {"fade_seconds": float(fade_seconds)}))
        return True

    def pause_music(self) -> bool:
        self.calls.append(("pause_music", (), {}))
        return True

    def resume_music(self) -> bool:
        self.calls.append(("resume_music", (), {}))
        return True

    def set_music_volume(self, volume: float) -> None:
        self.calls.append(("set_music_volume", (float(volume),), {}))


class _FakeAudioChannel:
    def __init__(self) -> None:
        self.volume: float | None = None

    def set_volume(self, volume: float) -> None:
        self.volume = float(volume)


class _FakeSound:
    def __init__(self, channel: _FakeAudioChannel | None) -> None:
        self.channel = channel
        self.play_calls = 0

    def play(self) -> _FakeAudioChannel | None:
        self.play_calls += 1
        return self.channel


class _FakeMusicController:
    def __init__(self) -> None:
        self.loaded_paths: list[str] = []
        self.play_calls: list[int] = []
        self.volume_calls: list[float] = []
        self.pause_calls = 0
        self.unpause_calls = 0
        self.stop_calls = 0
        self.fadeout_calls: list[int] = []
        self.busy = False

    def load(self, path: str) -> None:
        self.loaded_paths.append(str(path))

    def play(self, loops: int = 0) -> None:
        self.play_calls.append(int(loops))
        self.busy = True

    def set_volume(self, volume: float) -> None:
        self.volume_calls.append(float(volume))

    def get_busy(self) -> bool:
        return self.busy

    def pause(self) -> None:
        self.pause_calls += 1

    def unpause(self) -> None:
        self.unpause_calls += 1
        self.busy = True

    def stop(self) -> None:
        self.stop_calls += 1
        self.busy = False

    def fadeout(self, milliseconds: int) -> None:
        self.fadeout_calls.append(int(milliseconds))
        self.busy = False


class _FakeAudioAssetManager:
    def __init__(self, sound: _FakeSound | None = None, *, music_path: str = "C:/tmp/theme.ogg") -> None:
        self.sound = sound or _FakeSound(_FakeAudioChannel())
        self.music_path = Path(music_path)
        self.requested_sound_paths: list[str] = []
        self.requested_asset_paths: list[str] = []

    def get_sound(self, relative_path: str) -> _FakeSound:
        self.requested_sound_paths.append(str(relative_path))
        return self.sound

    def resolve_asset_path(self, relative_path: str) -> Path:
        self.requested_asset_paths.append(str(relative_path))
        return self.music_path


class StrictContentIdTests(unittest.TestCase):
    def _make_project(
        self,
        *,
        startup_area: str | None = None,
        input_targets: dict[str, str] | None = None,
        global_entities: list[dict[str, object]] | None = None,
        entity_templates: dict[str, dict[str, object]] | None = None,
        areas: dict[str, dict[str, object]] | None = None,
        commands: dict[str, dict[str, object]] | None = None,
        items: dict[str, dict[str, object]] | None = None,
        dialogues: dict[str, dict[str, object]] | None = None,
        shared_variables: dict[str, object] | None = None,
    ) -> tuple[Path, object]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        project_root = Path(temp_dir.name)

        project_payload: dict[str, object] = {
            "area_paths": ["areas/"],
            "entity_template_paths": ["entity_templates/"],
            "command_paths": ["commands/"],
            "item_paths": ["items/"],
            "shared_variables_path": "shared_variables.json",
        }
        if startup_area is not None:
            project_payload["startup_area"] = startup_area
        if input_targets is not None:
            project_payload["input_targets"] = input_targets
        if global_entities is not None:
            project_payload["global_entities"] = global_entities

        _write_json(project_root / "project.json", project_payload)
        if shared_variables is not None:
            _write_json(project_root / "shared_variables.json", shared_variables)

        for relative_path, template_payload in (entity_templates or {}).items():
            _write_json(project_root / "entity_templates" / relative_path, template_payload)
        for relative_path, area_payload in (areas or {}).items():
            _write_json(project_root / "areas" / relative_path, area_payload)
        for relative_path, command_payload in (commands or {}).items():
            _write_json(project_root / "commands" / relative_path, command_payload)
        for relative_path, item_payload in (items or {}).items():
            _write_json(project_root / "items" / relative_path, item_payload)
        for relative_path, dialogue_payload in (dialogues or {}).items():
            _write_json(project_root / "dialogues" / relative_path, dialogue_payload)

        return project_root, load_project(project_root / "project.json")

    def _make_command_context(
        self,
        *,
        project: object | None = None,
        world: World | None = None,
        area: Area | None = None,
        persistence_runtime: PersistenceRuntime | None = None,
    ) -> tuple[CommandRegistry, CommandContext]:
        registry = CommandRegistry()
        register_builtin_commands(registry)
        context = CommandContext(
            area=area or _minimal_runtime_area(),
            world=world or World(),
            collision_system=None,  # type: ignore[arg-type]
            movement_system=None,  # type: ignore[arg-type]
            interaction_system=None,  # type: ignore[arg-type]
            animation_system=None,  # type: ignore[arg-type]
            project=project,
            persistence_runtime=persistence_runtime,
        )
        return registry, context

    def _complete_handle(self, handle: object, *, max_steps: int = 32) -> None:
        for _ in range(max_steps):
            if getattr(handle, "complete", False):
                return
            handle.update(0.0)
        self.fail("Command handle did not complete within the expected number of steps.")

    def _install_dialogue_runtime(
        self,
        *,
        registry: CommandRegistry,
        context: CommandContext,
        project: object,
    ) -> DialogueRuntime:
        dialogue_runtime = DialogueRuntime(
            project=project,
            screen_manager=ScreenElementManager(),
            text_renderer=_StubTextRenderer(),
            registry=registry,
            command_context=context,
        )
        context.screen_manager = dialogue_runtime.screen_manager
        context.text_renderer = dialogue_runtime.text_renderer
        context.dialogue_runtime = dialogue_runtime
        return dialogue_runtime

    def _install_inventory_runtime(
        self,
        *,
        registry: CommandRegistry,
        context: CommandContext,
        project: object,
    ) -> InventoryRuntime:
        inventory_runtime = InventoryRuntime(
            project=project,
            screen_manager=ScreenElementManager(),
            text_renderer=_StubTextRenderer(),
            command_context=context,
        )
        context.screen_manager = inventory_runtime.screen_manager
        context.text_renderer = inventory_runtime.text_renderer
        context.inventory_runtime = inventory_runtime
        if context.command_runner is None:
            CommandRunner(registry, context)
        return inventory_runtime

    def _run_command_runner_until_idle(
        self,
        runner: CommandRunner,
        *,
        max_steps: int = 32,
    ) -> None:
        for _ in range(max_steps):
            runner.update(0.0)
            if not runner.has_pending_work():
                return
        self.fail("Command runner did not become idle within the expected number of steps.")

    def _make_occupancy_runtime(
        self,
        *,
        area: Area,
        world: World,
    ) -> tuple[CommandRegistry, CommandContext, MovementSystem]:
        registry, context = self._make_command_context(area=area, world=world)
        collision = CollisionSystem(area, world)
        movement = MovementSystem(area, world, collision)
        context.collision_system = collision
        context.interaction_system = InteractionSystem(world)
        context.movement_system = movement

        def _dispatch_occupancy_hooks(
            instigator: Entity,
            previous_cell: tuple[int, int] | None,
            next_cell: tuple[int, int] | None,
        ) -> None:
            runtime_params: dict[str, int] = {}
            if previous_cell is not None:
                runtime_params["from_x"] = int(previous_cell[0])
                runtime_params["from_y"] = int(previous_cell[1])
            if next_cell is not None:
                runtime_params["to_x"] = int(next_cell[0])
                runtime_params["to_y"] = int(next_cell[1])

            def _run_hook(receiver: Entity, command_id: str) -> None:
                handle = execute_registered_command(
                    registry,
                    context,
                    "run_entity_command",
                    {
                        "entity_id": receiver.entity_id,
                        "command_id": command_id,
                        "entity_refs": {"instigator": instigator.entity_id},
                        "refs_mode": "merge",
                        **runtime_params,
                    },
                )
                handle.update(0.0)

            if previous_cell is not None:
                for receiver in world.get_entities_at(
                    previous_cell[0],
                    previous_cell[1],
                    exclude_entity_id=instigator.entity_id,
                    include_hidden=True,
                ):
                    _run_hook(receiver, "on_occupant_leave")

            if next_cell is not None:
                for receiver in world.get_entities_at(
                    next_cell[0],
                    next_cell[1],
                    exclude_entity_id=instigator.entity_id,
                    include_hidden=True,
                ):
                    _run_hook(receiver, "on_occupant_enter")

        movement.occupancy_transition_callback = _dispatch_occupancy_hooks
        return registry, context, movement

    def test_area_validation_rejects_authored_area_id(self) -> None:
        _, project = self._make_project(
            startup_area="areas/test_room",
            areas={
                "test_room.json": {
                    "area_id": "areas/test_room",
                    **_minimal_area(),
                }
            },
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("must not declare 'area_id'" in issue for issue in raised.exception.issues)
        )

    def test_area_validation_rejects_missing_startup_area_id(self) -> None:
        _, project = self._make_project(
            startup_area="areas/missing_room",
            areas={"test_room.json": _minimal_area()},
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("startup_area 'areas/missing_room'" in issue for issue in raised.exception.issues)
        )

    def test_area_loader_preserves_enter_commands(self) -> None:
        _, project = self._make_project()
        raw_area = _minimal_area()
        raw_area["enter_commands"] = [
            {
                "type": "run_entity_command",
                "entity_id": "dialogue_controller",
                "command_id": "open_dialogue",
                "dialogue_path": "dialogues/system/title_menu.json",
                "segment_hooks": [
                    {
                        "option_commands_by_id": {
                            "new_game": [],
                        }
                    }
                ],
            }
        ]

        area, _ = load_area_from_data(raw_area, source_name="<memory>", project=project)

        self.assertEqual(len(area.enter_commands), 1)
        self.assertEqual(area.enter_commands[0]["type"], "run_entity_command")
        self.assertEqual(area.enter_commands[0]["entity_id"], "dialogue_controller")
        self.assertEqual(area.enter_commands[0]["dialogue_path"], "dialogues/system/title_menu.json")

    def test_area_loader_and_serializer_round_trip_entry_points(self) -> None:
        _, project = self._make_project()
        raw_area = _minimal_area()
        raw_area["entry_points"] = {
            "front_door": {
                "x": 3,
                "y": 4,
                "facing": "up",
                "pixel_x": 52,
                "pixel_y": 68,
            }
        }
        raw_area["camera"] = {
            "follow": {
                "mode": "entity",
                "entity_id": "player",
                "offset_x": 10,
                "offset_y": 0,
            },
            "bounds": {
                "x": 16,
                "y": 32,
                "width": 128,
                "height": 96,
            },
        }

        area, world = load_area_from_data(raw_area, source_name="<memory>", project=project)
        entry_point = area.entry_points["front_door"]
        self.assertEqual(entry_point.grid_x, 3)
        self.assertEqual(entry_point.grid_y, 4)
        self.assertEqual(entry_point.facing, "up")
        self.assertEqual(entry_point.pixel_x, 52.0)
        self.assertEqual(entry_point.pixel_y, 68.0)
        self.assertEqual(area.camera_defaults["follow"]["entity_id"], "player")
        self.assertEqual(area.camera_defaults["follow"]["offset_x"], 10)

        serialized = serialize_area(area, world, project=project)
        self.assertEqual(
            serialized["entry_points"],
            {
                "front_door": {
                    "x": 3,
                    "y": 4,
                    "facing": "up",
                    "pixel_x": 52,
                    "pixel_y": 68,
                }
            },
        )
        self.assertEqual(serialized["camera"], raw_area["camera"])

    def test_serialize_area_writes_unified_layering_fields(self) -> None:
        _, project = self._make_project()
        raw_area = _minimal_area()
        raw_area["tile_layers"] = [
            {
                "name": "front_wall",
                "render_order": 10,
                "y_sort": True,
                "sort_y_offset": -2,
                "stack_order": 4,
                "grid": [[1]],
            }
        ]
        raw_area["entities"] = [
            {
                "id": "player",
                "kind": "player",
                "x": 0,
                "y": 0,
                "render_order": 12,
                "y_sort": False,
                "sort_y_offset": 5,
                "stack_order": 9,
            }
        ]

        area, world = load_area_from_data(raw_area, source_name="<memory>", project=project)
        serialized = serialize_area(area, world, project=project)

        tile_layer = serialized["tile_layers"][0]
        self.assertEqual(tile_layer["render_order"], 10)
        self.assertTrue(tile_layer["y_sort"])
        self.assertEqual(tile_layer["sort_y_offset"], -2)
        self.assertEqual(tile_layer["stack_order"], 4)
        self.assertNotIn("draw_above_entities", tile_layer)

        entity_data = serialized["entities"][0]
        self.assertEqual(entity_data["render_order"], 12)
        self.assertFalse(entity_data["y_sort"])
        self.assertEqual(entity_data["sort_y_offset"], 5)
        self.assertEqual(entity_data["stack_order"], 9)
        self.assertNotIn("layer", entity_data)

    def test_area_loader_normalizes_blocked_and_walkable_cell_flags(self) -> None:
        _, project = self._make_project()
        raw_area = _minimal_area()
        raw_area["cell_flags"] = [
            [False, {"blocked": True, "tags": ["wall"]}],
        ]
        raw_area["tile_layers"] = [
            {
                "name": "ground",
                "render_order": 0,
                "grid": [[1, 1]],
            }
        ]

        area, world = load_area_from_data(raw_area, source_name="<memory>", project=project)

        self.assertTrue(area.is_blocked(1, 0))
        self.assertFalse(area.is_walkable(1, 0))
        self.assertEqual(area.cell_flags_at(0, 0), {"blocked": True, "walkable": False})
        self.assertEqual(
            area.cell_flags_at(1, 0),
            {"blocked": True, "tags": ["wall"], "walkable": False},
        )

        serialized = serialize_area(area, world, project=project)
        self.assertEqual(
            serialized["cell_flags"],
            [[{"blocked": True}, {"blocked": True, "tags": ["wall"]}]],
        )

    def test_loader_supports_new_top_level_physics_and_interaction_fields(self) -> None:
        _, project = self._make_project()
        raw_area = _minimal_area()
        raw_area["entities"] = [
            {
                "id": "crate",
                "kind": "block",
                "x": 0,
                "y": 0,
                "facing": "left",
                "solid": True,
                "pushable": True,
                "weight": 3,
                "push_strength": 2,
                "collision_push_strength": 4,
                "interactable": True,
                "interaction_priority": 7,
                "entity_commands": {
                    "interact": {
                        "enabled": True,
                        "commands": [],
                    }
                },
            }
        ]

        area, world = load_area_from_data(raw_area, source_name="<memory>", project=project)
        crate = world.get_entity("crate")
        self.assertIsNotNone(crate)
        assert crate is not None
        self.assertEqual(crate.get_effective_facing(), "left")
        self.assertTrue(crate.is_effectively_solid())
        self.assertTrue(crate.is_effectively_pushable())
        self.assertEqual(crate.weight, 3)
        self.assertEqual(crate.push_strength, 2)
        self.assertEqual(crate.collision_push_strength, 4)
        self.assertTrue(crate.is_effectively_interactable())
        self.assertEqual(crate.interaction_priority, 7)

        serialized = serialize_area(area, world, project=project)
        serialized_entity = serialized["entities"][0]
        self.assertEqual(serialized_entity["facing"], "left")
        self.assertTrue(serialized_entity["solid"])
        self.assertTrue(serialized_entity["pushable"])
        self.assertEqual(serialized_entity["weight"], 3)
        self.assertEqual(serialized_entity["push_strength"], 2)
        self.assertEqual(serialized_entity["collision_push_strength"], 4)
        self.assertTrue(serialized_entity["interactable"])
        self.assertEqual(serialized_entity["interaction_priority"], 7)

    def test_engine_physics_fields_ignore_same_named_variables_and_interact_commands(self) -> None:
        _, project = self._make_project()
        raw_area = _minimal_area()
        raw_area["entities"] = [
            {
                "id": "explicit_block",
                "kind": "block",
                "x": 0,
                "y": 0,
                "facing": "left",
                "solid": False,
                "pushable": False,
                "interactable": False,
                "variables": {
                    "direction": "right",
                    "blocks_movement": True,
                    "pushable": True,
                },
                "entity_commands": {
                    "interact": {
                        "enabled": True,
                        "commands": [],
                    }
                },
            }
        ]

        _, world = load_area_from_data(raw_area, source_name="<memory>", project=project)
        explicit_block = world.get_entity("explicit_block")
        self.assertIsNotNone(explicit_block)
        assert explicit_block is not None
        self.assertEqual(explicit_block.get_effective_facing(), "left")
        self.assertFalse(explicit_block.is_effectively_solid())
        self.assertFalse(explicit_block.is_effectively_pushable())
        self.assertFalse(explicit_block.is_effectively_interactable())

        explicit_block.variables["direction"] = "up"
        explicit_block.variables["blocks_movement"] = False
        explicit_block.variables["pushable"] = False

        self.assertEqual(explicit_block.get_effective_facing(), "left")
        self.assertFalse(explicit_block.is_effectively_solid())
        self.assertFalse(explicit_block.is_effectively_pushable())
        self.assertFalse(explicit_block.is_effectively_interactable())

    def test_collision_system_uses_blocked_cells_and_solid_entities(self) -> None:
        area = Area(
            area_id="areas/test_room",
            name="Test Room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": True}]],
        )
        world = World()
        blocker = _make_runtime_entity("blocker", kind="block")
        blocker.grid_x = 0
        blocker.grid_y = 0
        blocker.solid = True
        world.add_entity(blocker)

        collision = CollisionSystem(area, world)

        self.assertFalse(collision.can_move_to(1, 0))
        self.assertFalse(collision.can_move_to(0, 0))
        self.assertEqual(collision.get_blocking_entity(0, 0), blocker)

    def test_interaction_system_prefers_explicit_priority_and_facing(self) -> None:
        world = World()
        actor = _make_runtime_entity("actor", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        actor.facing = "right"
        world.add_entity(actor)

        low = _make_runtime_entity(
            "low",
            kind="npc",
            entity_commands={"interact": EntityCommandDefinition(enabled=True, commands=[])},
        )
        low.grid_x = 1
        low.grid_y = 0
        low.interactable = True
        low.interaction_priority = 1
        world.add_entity(low)

        high = _make_runtime_entity(
            "high",
            kind="npc",
            entity_commands={"interact": EntityCommandDefinition(enabled=True, commands=[])},
        )
        high.grid_x = 1
        high.grid_y = 0
        high.interactable = True
        high.interaction_priority = 10
        world.add_entity(high)

        interaction = InteractionSystem(world)
        self.assertEqual(interaction.get_facing_target("actor"), high)

    def test_move_in_direction_steps_actor_and_updates_facing(self) -> None:
        area = Area(
            area_id="areas/test_room",
            name="Test Room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        world.add_entity(actor)
        registry, context = self._make_command_context(area=area, world=world)
        movement_system = _RecordingMovementSystem()
        context.movement_system = movement_system
        context.collision_system = CollisionSystem(area, world)

        handle = execute_registered_command(
            registry,
            context,
            "move_in_direction",
            {
                "entity_id": "player",
                "direction": "right",
                "frames_needed": 6,
                "wait": False,
            },
        )
        handle.update(0.0)

        self.assertEqual(actor.get_effective_facing(), "right")
        self.assertEqual(
            movement_system.grid_steps,
            [("player", "right", None, 6, None, "immediate")],
        )

    def test_move_in_direction_runs_on_blocked_hook_with_context(self) -> None:
        area = Area(
            area_id="areas/test_room",
            name="Test Room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity(
            "player",
            kind="player",
            entity_commands={
                "on_blocked": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "blocked",
                            "value": True,
                        },
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "blocked_direction",
                            "value": "$direction",
                        },
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "blocked_entity",
                            "value": "$blocking_entity_id",
                        },
                    ]
                )
            },
        )
        actor.grid_x = 0
        actor.grid_y = 0
        world.add_entity(actor)
        blocker = _make_runtime_entity("crate", kind="block")
        blocker.grid_x = 1
        blocker.grid_y = 0
        blocker.solid = True
        world.add_entity(blocker)
        registry, context = self._make_command_context(area=area, world=world)
        movement_system = _RecordingMovementSystem()
        context.movement_system = movement_system
        context.collision_system = CollisionSystem(area, world)

        handle = execute_registered_command(
            registry,
            context,
            "move_in_direction",
            {
                "entity_id": "player",
                "direction": "right",
                "wait": False,
            },
        )
        handle.update(0.0)

        self.assertTrue(actor.variables["blocked"])  # type: ignore[index]
        self.assertEqual(actor.variables["blocked_direction"], "right")
        self.assertEqual(actor.variables["blocked_entity"], "crate")
        self.assertEqual(movement_system.grid_steps, [])

    def test_move_in_direction_pushes_one_blocker_using_entity_push_strength(self) -> None:
        area = Area(
            area_id="areas/test_room",
            name="Test Room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": False}, {"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        actor.push_strength = 1
        world.add_entity(actor)
        blocker = _make_runtime_entity("crate", kind="block")
        blocker.grid_x = 1
        blocker.grid_y = 0
        blocker.solid = True
        blocker.pushable = True
        blocker.weight = 1
        world.add_entity(blocker)
        registry, context = self._make_command_context(area=area, world=world)
        movement_system = _RecordingMovementSystem()
        context.movement_system = movement_system
        context.collision_system = CollisionSystem(area, world)

        handle = execute_registered_command(
            registry,
            context,
            "move_in_direction",
            {
                "entity_id": "player",
                "direction": "right",
                "frames_needed": 8,
                "wait": False,
            },
        )
        handle.update(0.0)

        self.assertEqual(actor.get_effective_facing(), "right")
        self.assertEqual(
            movement_system.grid_steps,
            [
                ("crate", "right", None, 8, None, "immediate"),
                ("player", "right", None, 8, None, "immediate"),
            ],
        )

    def test_push_facing_moves_only_the_blocker(self) -> None:
        area = Area(
            area_id="areas/test_room",
            name="Test Room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": False}, {"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        actor.facing = "right"
        actor.push_strength = 1
        world.add_entity(actor)
        blocker = _make_runtime_entity("crate", kind="block")
        blocker.grid_x = 1
        blocker.grid_y = 0
        blocker.solid = True
        blocker.pushable = True
        blocker.weight = 1
        world.add_entity(blocker)
        registry, context = self._make_command_context(area=area, world=world)
        movement_system = _RecordingMovementSystem()
        context.movement_system = movement_system
        context.collision_system = CollisionSystem(area, world)

        handle = execute_registered_command(
            registry,
            context,
            "push_facing",
            {
                "entity_id": "player",
                "frames_needed": 5,
                "wait": False,
            },
        )
        handle.update(0.0)

        self.assertEqual((actor.grid_x, actor.grid_y), (0, 0))
        self.assertEqual(
            movement_system.grid_steps,
            [("crate", "right", None, 5, None, "immediate")],
        )

    def test_interact_facing_dispatches_target_interact_with_instigator(self) -> None:
        area = Area(
            area_id="areas/test_room",
            name="Test Room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        actor.facing = "right"
        world.add_entity(actor)
        target = _make_runtime_entity(
            "sign",
            kind="sign",
            entity_commands={
                "interact": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$ref_ids.instigator",
                            "name": "interacted",
                            "value": True,
                        }
                    ]
                )
            },
        )
        target.grid_x = 1
        target.grid_y = 0
        target.interactable = True
        world.add_entity(target)
        registry, context = self._make_command_context(area=area, world=world)
        context.interaction_system = InteractionSystem(world)

        handle = execute_registered_command(
            registry,
            context,
            "interact_facing",
            {
                "entity_id": "player",
            },
        )
        handle.update(0.0)

        self.assertTrue(actor.variables["interacted"])  # type: ignore[index]

    def test_move_in_direction_runs_occupant_enter_and_leave_hooks(self) -> None:
        area = Area(
            area_id="areas/test_room",
            name="Test Room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": False}, {"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        actor.sync_pixel_position(area.tile_size)
        world.add_entity(actor)
        button = _make_runtime_entity(
            "button",
            kind="button",
            entity_commands={
                "on_occupant_enter": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "entered_by",
                            "value": "$ref_ids.instigator",
                        }
                    ]
                ),
                "on_occupant_leave": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "left_by",
                            "value": "$ref_ids.instigator",
                        }
                    ]
                ),
            },
        )
        button.grid_x = 1
        button.grid_y = 0
        button.sync_pixel_position(area.tile_size)
        world.add_entity(button)
        registry, context, movement_system = self._make_occupancy_runtime(area=area, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "move_in_direction",
            {
                "entity_id": "player",
                "direction": "right",
                "frames_needed": 0,
                "wait": False,
            },
        )
        handle.update(0.0)
        movement_system.update_tick()

        self.assertEqual(button.variables["entered_by"], "player")

        handle = execute_registered_command(
            registry,
            context,
            "move_in_direction",
            {
                "entity_id": "player",
                "direction": "right",
                "frames_needed": 0,
                "wait": False,
            },
        )
        handle.update(0.0)
        movement_system.update_tick()

        self.assertEqual(button.variables["left_by"], "player")

    def test_set_present_false_runs_occupant_leave_hook(self) -> None:
        area = Area(
            area_id="areas/test_room",
            name="Test Room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1]], render_order=0)],
            cell_flags=[[{"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        world.add_entity(actor)
        button = _make_runtime_entity(
            "button",
            kind="button",
            entity_commands={
                "on_occupant_leave": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "released_by",
                            "value": "$ref_ids.instigator",
                        }
                    ]
                )
            },
        )
        button.grid_x = 0
        button.grid_y = 0
        world.add_entity(button)
        registry, context = self._make_command_context(area=area, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "set_present",
            {
                "entity_id": "player",
                "present": False,
            },
        )
        handle.update(0.0)

        self.assertFalse(actor.present)
        self.assertEqual(button.variables["released_by"], "player")

    def test_set_present_true_runs_occupant_enter_hook(self) -> None:
        area = Area(
            area_id="areas/test_room",
            name="Test Room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1]], render_order=0)],
            cell_flags=[[{"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        actor.set_present(False)
        world.add_entity(actor)
        button = _make_runtime_entity(
            "button",
            kind="button",
            entity_commands={
                "on_occupant_enter": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "entered_by",
                            "value": "$ref_ids.instigator",
                        }
                    ]
                )
            },
        )
        button.grid_x = 0
        button.grid_y = 0
        world.add_entity(button)
        registry, context = self._make_command_context(area=area, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "set_present",
            {
                "entity_id": "player",
                "present": True,
            },
        )
        handle.update(0.0)

        self.assertTrue(actor.present)
        self.assertEqual(button.variables["entered_by"], "player")

    def test_destroy_entity_runs_occupant_leave_hook_before_removal(self) -> None:
        area = Area(
            area_id="areas/test_room",
            name="Test Room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1]], render_order=0)],
            cell_flags=[[{"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        world.add_entity(actor)
        button = _make_runtime_entity(
            "button",
            kind="button",
            entity_commands={
                "on_occupant_leave": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "released_by",
                            "value": "$ref_ids.instigator",
                        }
                    ]
                )
            },
        )
        button.grid_x = 0
        button.grid_y = 0
        world.add_entity(button)
        registry, context = self._make_command_context(area=area, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "destroy_entity",
            {
                "entity_id": "player",
            },
        )
        handle.update(0.0)

        self.assertIsNone(world.get_entity("player"))
        self.assertEqual(button.variables["released_by"], "player")

    def test_renderer_collect_world_render_items_interleaves_tiles_and_entities(self) -> None:
        import pygame

        area = Area(
            area_id="areas/test_room",
            name="Test Room",
            tile_size=16,
            tilesets=[],
            tile_layers=[
                TileLayer(name="ground", grid=[[1]], render_order=0, y_sort=False, stack_order=0),
                TileLayer(name="front_wall", grid=[[1]], render_order=10, y_sort=True, stack_order=0),
                TileLayer(name="roof", grid=[[1]], render_order=20, y_sort=False, stack_order=0),
            ],
            cell_flags=[[{"walkable": True}]],
        )
        world = World()
        player = _make_runtime_entity("player", kind="player")
        player.grid_x = 0
        player.grid_y = 0
        player.sync_pixel_position(area.tile_size)
        player.render_order = 10
        player.y_sort = True
        player.stack_order = 0
        world.add_entity(player)

        renderer = Renderer(pygame.Surface((16, 16)), object())
        items = sorted(renderer._collect_world_render_items(area, world), key=lambda item: item.sort_key)

        self.assertEqual(
            [item.draw_kind for item in items],
            ["tile_layer", "tile_cell", "entity", "tile_layer"],
        )
        self.assertEqual(items[0].payload[0].name, "ground")
        self.assertEqual(items[1].payload[0].name, "front_wall")
        self.assertEqual(items[2].payload[0].entity_id, "player")
        self.assertEqual(items[3].payload[0].name, "roof")

    def test_load_project_requires_manifest(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        with self.assertRaises(FileNotFoundError):
            load_project(Path(temp_dir.name) / "project.json")

    def test_area_loader_leaves_unassigned_project_input_targets_unrouted(self) -> None:
        _, project = self._make_project(
            input_targets={"menu": "pause_controller"},
        )
        raw_area = _minimal_area()
        raw_area.pop("input_targets", None)
        raw_area["entities"] = [
            {
                "id": "hero",
                "kind": "player",
                "x": 0,
                "y": 0,
            }
        ]

        _, world = load_area_from_data(raw_area, source_name="<memory>", project=project)
        world.add_entity(
            _make_runtime_entity(
                "pause_controller",
                kind="system",
                space="screen",
                scope="global",
            )
        )

        self.assertIsNone(world.get_input_target_id("move_up"))
        self.assertIsNone(world.get_input_target_id("interact"))
        self.assertEqual(world.get_input_target_id("menu"), "pause_controller")

    def test_input_handler_only_dispatches_actions_with_explicit_input_map_entries(self) -> None:
        import pygame

        world = World(default_input_targets={"interact": "player"})
        player = _make_runtime_entity("player", kind="player")
        world.add_entity(player)
        runner = _RecordingInputDispatchRunner()
        input_handler = InputHandler(runner, world)

        input_handler.handle_events(
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_SPACE})]
        )
        self.assertEqual(runner.dispatched, [])

        player.input_map["interact"] = "confirm"
        input_handler.handle_events(
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_SPACE})]
        )

        self.assertEqual(runner.dispatched, [("player", "confirm")])

    def test_input_handler_routes_inventory_key_only_when_explicitly_mapped(self) -> None:
        import pygame

        world = World(default_input_targets={"inventory": "player"})
        player = _make_runtime_entity("player", kind="player")
        world.add_entity(player)
        runner = _RecordingInputDispatchRunner()
        input_handler = InputHandler(runner, world)

        input_handler.handle_events(
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_i})]
        )
        self.assertEqual(runner.dispatched, [])

        player.input_map["inventory"] = "open_inventory"
        input_handler.handle_events(
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_i})]
        )

        self.assertEqual(runner.dispatched, [("player", "open_inventory")])

    def test_input_handler_blocks_world_routing_when_inventory_modal_is_active(self) -> None:
        import pygame

        class _BlockingModalRuntime:
            def __init__(self) -> None:
                self.actions: list[str] = []

            def is_active(self) -> bool:
                return True

            def handle_action(self, action_name: str) -> bool:
                self.actions.append(str(action_name))
                return False

        world = World(default_input_targets={"inventory": "player"})
        player = _make_runtime_entity("player", kind="player")
        player.input_map["inventory"] = "open_inventory"
        world.add_entity(player)
        runner = _RecordingInputDispatchRunner()
        modal_runtime = _BlockingModalRuntime()
        input_handler = InputHandler(runner, world, inventory_runtime=modal_runtime)

        input_handler.handle_events(
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_i})]
        )

        self.assertEqual(modal_runtime.actions, ["inventory"])
        self.assertEqual(runner.dispatched, [])

    def test_input_handler_escape_without_menu_target_does_not_quit(self) -> None:
        import pygame

        world = World()
        runner = _RecordingInputDispatchRunner()
        input_handler = InputHandler(runner, world)

        result = input_handler.handle_events(
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})]
        )

        self.assertFalse(result.should_quit)
        self.assertEqual(runner.dispatched, [])

    def test_input_handler_routes_debug_keys_only_when_explicit_targets_exist(self) -> None:
        import pygame

        world = World(
            default_input_targets={
                "debug_toggle_pause": "debug_controller",
                "debug_step_tick": "debug_controller",
                "debug_zoom_out": "debug_controller",
                "debug_zoom_in": "debug_controller",
            }
        )
        debug_controller = _make_runtime_entity("debug_controller", kind="system")
        world.add_entity(debug_controller)
        runner = _RecordingInputDispatchRunner()
        input_handler = InputHandler(runner, world)

        input_handler.handle_events(
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_F6})]
        )
        self.assertEqual(runner.dispatched, [])

        debug_controller.input_map["debug_toggle_pause"] = "toggle_pause"
        debug_controller.input_map["debug_step_tick"] = "step_tick"
        debug_controller.input_map["debug_zoom_out"] = "zoom_out"
        debug_controller.input_map["debug_zoom_in"] = "zoom_in"

        input_handler.handle_events(
            [
                pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_F6}),
                pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_F7}),
                pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_LEFTBRACKET}),
                pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RIGHTBRACKET}),
            ]
        )

        self.assertEqual(
            runner.dispatched,
            [
                ("debug_controller", "toggle_pause"),
                ("debug_controller", "step_tick"),
                ("debug_controller", "zoom_out"),
                ("debug_controller", "zoom_in"),
            ],
        )

    def test_entity_template_validation_rejects_removed_sprite_field(self) -> None:
        _, project = self._make_project(
            entity_templates={
                "legacy_sign.json": {
                    "kind": "sign",
                    "sprite": {
                        "path": "assets/project/sprites/sign.png",
                    },
                }
            }
        )

        with self.assertRaises(EntityTemplateValidationError) as raised:
            validate_project_entity_templates(project)

        self.assertTrue(
            any("must not use 'sprite'" in issue for issue in raised.exception.issues)
        )

    def test_project_command_validation_rejects_authored_id(self) -> None:
        _, project = self._make_project(
            commands={
                "walk_one_tile.json": {
                    "id": "walk_one_tile",
                    "params": [],
                    "commands": [],
                }
            }
        )

        with self.assertRaises(ProjectCommandValidationError) as raised:
            validate_project_commands(project)

        self.assertTrue(
            any("must not declare 'id'" in issue for issue in raised.exception.issues)
        )

    def test_project_command_validation_rejects_symbolic_entity_refs_for_strict_primitives(self) -> None:
        _, project = self._make_project(
            commands={
                "bad_primitive.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "set_entity_field",
                            "entity_id": "self",
                            "field_name": "visible",
                            "value": False,
                        }
                    ],
                }
            }
        )

        with self.assertRaises(ProjectCommandValidationError) as raised:
            validate_project_commands(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'self' with strict primitive 'set_entity_field'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_project_command_validation_rejects_symbolic_entity_refs_for_strict_visual_primitives(self) -> None:
        _, project = self._make_project(
            commands={
                "bad_visual_primitive.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "play_animation",
                            "entity_id": "self",
                            "frame_sequence": [1, 2],
                        }
                    ],
                }
            }
        )

        with self.assertRaises(ProjectCommandValidationError) as raised:
            validate_project_commands(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'self' with strict primitive 'play_animation'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_project_command_validation_rejects_symbolic_entity_refs_for_strict_movement_primitives(self) -> None:
        _, project = self._make_project(
            commands={
                "bad_move_primitive.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "move_entity_world_position",
                            "entity_id": "self",
                            "x": 16,
                            "y": 0,
                            "mode": "relative",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(ProjectCommandValidationError) as raised:
            validate_project_commands(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'self' with strict primitive 'move_entity_world_position'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_json_file_value_source_loads_project_relative_dialogue_data(self) -> None:
        _, project = self._make_project(
            dialogues={
                "menus/test.json": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "Gate is closed.",
                        }
                    ],
                    "font_id": "pixelbet",
                }
            }
        )
        world = World()
        world.add_entity(
            _make_runtime_entity(
                "dialogue_controller",
                kind="system",
                space="screen",
            )
        )
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_command_spec(
            registry,
            context,
            {
                "entity_id": "dialogue_controller",
                "name": "dialogue_definition",
                "type": "set_entity_var",
                "value": {"$json_file": "dialogues/menus/test.json"},
            },
        )
        handle.update(0.0)

        controller = world.get_entity("dialogue_controller")
        assert controller is not None
        self.assertEqual(
            controller.variables["dialogue_definition"]["segments"][0]["text"],
            "Gate is closed.",
        )
        self.assertEqual(controller.variables["dialogue_definition"]["font_id"], "pixelbet")

    def test_removed_text_session_commands_raise_clear_runtime_errors(self) -> None:
        registry, context = self._make_command_context()
        for command_name in (
            "prepare_text_session",
            "read_text_session",
            "advance_text_session",
            "reset_text_session",
            "wait_for_action_press",
            "wait_for_direction_release",
            "set_var_from_json_file",
            "set_var_from_wrapped_lines",
            "set_var_from_text_window",
            "query_facing_state",
            "run_facing_event",
        ):
            with self.assertRaises(CommandExecutionError) as raised:
                params = {}
                if command_name == "wait_for_direction_release":
                    params = {"direction": "down"}
                elif command_name == "query_facing_state":
                    params = {"entity_id": "self", "store_state_var": "move_attempt_state"}
                elif command_name == "run_facing_event":
                    params = {"entity_id": "self", "command_id": "interact"}
                execute_registered_command(registry, context, command_name, params)
            self.assertIsNotNone(raised.exception.__cause__)
            self.assertIn(f"Unknown command '{command_name}'", str(raised.exception.__cause__))

    def test_removed_dialogue_runtime_commands_raise_clear_errors(self) -> None:
        registry, context = self._make_command_context()
        for command_name in (
            "start_dialogue_session",
            "dialogue_advance",
            "dialogue_move_selection",
            "dialogue_confirm_choice",
            "dialogue_cancel",
            "close_dialogue",
        ):
            with self.assertRaises(CommandExecutionError) as raised:
                execute_registered_command(registry, context, command_name, {})
            self.assertIsNotNone(raised.exception.__cause__)
            self.assertIn(f"Unknown command '{command_name}'", str(raised.exception.__cause__))

    def test_open_dialogue_session_runs_hooks_and_renders_text(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_note.json": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "Engine owned dialogue runtime",
                        }
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        caller = _make_runtime_entity("terminal", kind="terminal")
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        handle = execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_note.json",
                "dialogue_on_start": [
                    {
                        "type": "set_entity_var",
                        "entity_id": "$self_id",
                        "name": "phase",
                        "value": "opened",
                    }
                ],
                "dialogue_on_end": [
                    {
                        "type": "set_entity_var",
                        "entity_id": "$self_id",
                        "name": "phase",
                        "value": "closed",
                    }
                ],
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )
        self.assertFalse(handle.complete)
        self.assertTrue(dialogue_runtime.is_active())
        self.assertEqual(caller.variables["phase"], "opened")

        text_element = context.screen_manager.get_element(DialogueRuntime.TEXT_ELEMENT_ID)
        assert text_element is not None
        self.assertIn("Engine", text_element.text)

        close_handle = execute_registered_command(
            registry,
            context,
            "close_dialogue_session",
            {},
        )
        self.assertTrue(close_handle.complete)
        self.assertFalse(dialogue_runtime.is_active())
        self.assertEqual(caller.variables["phase"], "closed")
        handle.update(0.0)
        self.assertTrue(handle.complete)

    def test_dialogue_runtime_choice_window_scrolls_after_three_visible_rows(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_choices.json": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Pick one",
                            "options": [
                                {"text": "One", "option_id": "one"},
                                {"text": "Two", "option_id": "two"},
                                {"text": "Three", "option_id": "three"},
                                {"text": "Four", "option_id": "four"},
                                {"text": "Five", "option_id": "five"},
                            ],
                        }
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(_make_runtime_entity("terminal", kind="terminal"))
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_choices.json",
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )
        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.choice_index, 0)
        self.assertEqual(session.choice_scroll_offset, 0)

        option_0 = context.screen_manager.get_element("engine_dialogue_option_0")
        option_1 = context.screen_manager.get_element("engine_dialogue_option_1")
        option_2 = context.screen_manager.get_element("engine_dialogue_option_2")
        assert option_0 is not None
        assert option_1 is not None
        assert option_2 is not None
        self.assertEqual(option_0.text, ">One")
        self.assertEqual(option_1.text, " Two")
        self.assertEqual(option_2.text, " Three")

        dialogue_runtime.handle_action("move_down")
        dialogue_runtime.handle_action("move_down")
        dialogue_runtime.handle_action("move_down")

        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.choice_index, 3)
        self.assertEqual(session.choice_scroll_offset, 1)

        option_0 = context.screen_manager.get_element("engine_dialogue_option_0")
        option_1 = context.screen_manager.get_element("engine_dialogue_option_1")
        option_2 = context.screen_manager.get_element("engine_dialogue_option_2")
        assert option_0 is not None
        assert option_1 is not None
        assert option_2 is not None
        self.assertEqual(option_0.text, " Two")
        self.assertEqual(option_1.text, " Three")
        self.assertEqual(option_2.text, ">Four")

    def test_dialogue_runtime_can_render_choices_in_a_separate_panel(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_separate_panel.json": {
                    "ui_preset": "separate_choices",
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Pick one",
                            "options": [
                                {"text": "One", "option_id": "one"},
                                {"text": "Two", "option_id": "two"},
                            ],
                        }
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(_make_runtime_entity("terminal", kind="terminal"))
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_separate_panel.json",
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        self.assertTrue(dialogue_runtime.is_active())
        choices_panel = context.screen_manager.get_element(DialogueRuntime.CHOICES_PANEL_ELEMENT_ID)
        option_0 = context.screen_manager.get_element("engine_dialogue_option_0")
        assert choices_panel is not None
        assert option_0 is not None
        self.assertEqual(choices_panel.kind, "image")
        self.assertEqual((choices_panel.x, choices_panel.y), (16.0, 88.0))
        self.assertEqual((option_0.x, option_0.y), (24.0, 96.0))
        self.assertEqual(option_0.text, ">One")

    def test_dialogue_runtime_marquees_the_selected_long_option(self) -> None:
        shared_variables = copy.deepcopy(_dialogue_shared_variables())
        choices = shared_variables["dialogue_ui"]["presets"]["standard"]["choices"]["plain"]
        choices["width"] = 36
        _, project = self._make_project(
            shared_variables=shared_variables,
            dialogues={
                "system/runtime_marquee.json": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Pick one",
                            "options": [
                                {"text": "Long option text", "option_id": "long"},
                            ],
                        }
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(_make_runtime_entity("terminal", kind="terminal"))
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_marquee.json",
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        option_before = context.screen_manager.get_element("engine_dialogue_option_0")
        assert option_before is not None
        before_text = option_before.text
        self.assertTrue(before_text.startswith(">"))

        dialogue_runtime.update(0.7)

        option_after = context.screen_manager.get_element("engine_dialogue_option_0")
        assert option_after is not None
        self.assertTrue(option_after.text.startswith(">"))
        self.assertNotEqual(option_after.text, before_text)

    def test_dialogue_runtime_segment_hooks_override_inline_option_commands(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_override.json": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Resolve the choice",
                            "options": [
                                {
                                    "text": "Apply behavior",
                                    "option_id": "apply",
                                    "commands": [
                                        {
                                            "type": "set_entity_var",
                                            "entity_id": "$self_id",
                                            "name": "mode",
                                            "value": "inline",
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        caller = _make_runtime_entity("terminal", kind="terminal")
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_override.json",
                "segment_hooks": [
                    {
                        "option_commands_by_id": {
                            "apply": [
                                {
                                    "type": "set_entity_var",
                                    "entity_id": "$self_id",
                                    "name": "mode",
                                    "value": "hook",
                                }
                            ]
                        }
                    }
                ],
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        self.assertTrue(dialogue_runtime.is_active())
        dialogue_runtime.handle_action("interact")
        self.assertFalse(dialogue_runtime.is_active())
        self.assertEqual(caller.variables["mode"], "hook")

    def test_dialogue_runtime_timer_segments_advance_without_input(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_timer.json": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "Soon",
                            "advance": {
                                "mode": "timer",
                                "seconds": 0.25,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Later",
                        },
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(_make_runtime_entity("terminal", kind="terminal"))
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_timer.json",
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.segment_index, 0)

        dialogue_runtime.update(0.25)

        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.segment_index, 1)
        text_element = context.screen_manager.get_element(DialogueRuntime.TEXT_ELEMENT_ID)
        assert text_element is not None
        self.assertIn("Later", text_element.text)

    def test_nested_dialogue_sessions_suspend_parent_flow_until_child_closes(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_parent.json": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Open the child dialogue",
                            "options": [
                                {
                                    "text": "Open child",
                                    "option_id": "open_child",
                                    "commands": [
                                        {
                                            "type": "open_dialogue_session",
                                            "dialogue_path": "dialogues/system/runtime_child.json",
                                            "allow_cancel": True,
                                        },
                                        {
                                            "type": "set_entity_var",
                                            "entity_id": "$self_id",
                                            "name": "result",
                                            "value": "resumed",
                                        },
                                    ],
                                }
                            ],
                        }
                    ]
                },
                "system/runtime_child.json": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "Nested child session",
                        }
                    ]
                },
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        caller = _make_runtime_entity("terminal", kind="terminal")
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        parent_handle = execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_parent.json",
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )
        self.assertFalse(parent_handle.complete)
        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.dialogue_path, "dialogues/system/runtime_parent.json")

        dialogue_runtime.handle_action("interact")

        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.dialogue_path, "dialogues/system/runtime_child.json")
        self.assertNotIn("result", caller.variables)

        dialogue_runtime.handle_action("menu")

        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.dialogue_path, "dialogues/system/runtime_parent.json")
        self.assertNotIn("result", caller.variables)

        dialogue_runtime.update(0.0)

        self.assertFalse(dialogue_runtime.is_active())
        self.assertEqual(caller.variables["result"], "resumed")
        parent_handle.update(0.0)
        self.assertTrue(parent_handle.complete)

    def test_wrapped_lines_and_text_window_value_sources_store_visible_text(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("dialogue_controller", kind="system", space="screen"))
        registry, context = self._make_command_context(world=world)
        context.text_renderer = _StubTextRenderer()

        wrapped_handle = execute_command_spec(
            registry,
            context,
            {
                "entity_id": "dialogue_controller",
                "name": "wrapped_lines",
                "type": "set_entity_var",
                "value": {
                    "$wrapped_lines": {
                        "text": "one two three four",
                        "max_width": 64,
                    }
                },
            },
        )
        wrapped_handle.update(0.0)
        controller = world.get_entity("dialogue_controller")
        assert controller is not None

        window_handle = execute_command_spec(
            registry,
            context,
            {
                "entity_id": "dialogue_controller",
                "name": "text_window",
                "type": "set_entity_var",
                "value": {
                    "$text_window": {
                        "lines": controller.variables["wrapped_lines"],
                        "start": 1,
                        "max_lines": 2,
                    }
                },
            },
        )
        window_handle.update(0.0)

        self.assertEqual(controller.variables["wrapped_lines"], ["one", "two", "three", "four"])
        self.assertEqual(controller.variables["text_window"]["visible_text"], "two\nthree")
        self.assertEqual(
            controller.variables["text_window"]["visible_lines"],
            ["two", "three"],
        )
        self.assertTrue(controller.variables["text_window"]["has_more"])
        self.assertEqual(controller.variables["text_window"]["total_lines"], 4)

    def test_slice_collection_wrap_index_and_join_text_value_sources_store_windowed_values(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("dialogue_controller", kind="system", space="screen"))
        registry, context = self._make_command_context(world=world)

        slice_handle = execute_command_spec(
            registry,
            context,
            {
                "entity_id": "dialogue_controller",
                "name": "visible_options",
                "type": "set_entity_var",
                "value": {
                    "$slice_collection": {
                        "value": ["zero", "one", "two", "three", "four"],
                        "start": 1,
                        "count": 3,
                    }
                },
            },
        )
        slice_handle.update(0.0)

        wrap_handle = execute_command_spec(
            registry,
            context,
            {
                "entity_id": "dialogue_controller",
                "name": "wrapped_index",
                "type": "set_entity_var",
                "value": {
                    "$wrap_index": {
                        "value": -1,
                        "count": 5,
                        "default": 0,
                    }
                },
            },
        )
        wrap_handle.update(0.0)

        join_handle = execute_command_spec(
            registry,
            context,
            {
                "entity_id": "dialogue_controller",
                "name": "joined_text",
                "type": "set_entity_var",
                "value": {
                    "$join_text": [">", "one"]
                },
            },
        )
        join_handle.update(0.0)

        controller = world.get_entity("dialogue_controller")
        assert controller is not None
        self.assertEqual(controller.variables["visible_options"], ["one", "two", "three"])
        self.assertEqual(controller.variables["wrapped_index"], 4)
        self.assertEqual(controller.variables["joined_text"], ">one")

    def test_boolean_and_random_value_sources_store_resolved_values(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("dialogue_controller", kind="system", space="screen"))
        registry, context = self._make_command_context(world=world)
        fixed_random = _FixedRandom(randint_result=4, choice_result="blue")
        context.random_generator = fixed_random

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "all_true",
                "value": {"$and": [True, 1, "yes"]},
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "any_true",
                "value": {"$or": [0, "", "picked"]},
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "negated",
                "value": {"$not": []},
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "random_roll",
                "value": {"$random_int": {"min": 2, "max": 6}},
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "picked_color",
                "value": {
                    "$random_choice": {
                        "value": ["red", "blue", "green"],
                        "default": "none",
                    }
                },
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "empty_pick",
                "value": {
                    "$random_choice": {
                        "value": [],
                        "default": "fallback",
                    }
                },
            },
        ).update(0.0)

        controller = world.get_entity("dialogue_controller")
        assert controller is not None
        self.assertTrue(controller.variables["all_true"])
        self.assertTrue(controller.variables["any_true"])
        self.assertTrue(controller.variables["negated"])
        self.assertEqual(controller.variables["random_roll"], 4)
        self.assertEqual(controller.variables["picked_color"], "blue")
        self.assertEqual(controller.variables["empty_pick"], "fallback")
        self.assertEqual(fixed_random.randint_calls, [(2, 6)])
        self.assertEqual(fixed_random.choice_calls, [["red", "blue", "green"]])

    def test_explicit_movement_query_value_sources_resolve_cell_flags_and_blockers(self) -> None:
        area = Area(
            area_id="areas/test_room",
            name="Test Room",
            tile_size=16,
            tilesets=[],
            tile_layers=[],
            cell_flags=[
                [{"blocked": False}, {"blocked": False}, {"blocked": False}],
                [{"blocked": False}, {"blocked": False}, {"blocked": True}],
                [{"blocked": False}, {"blocked": False}, {"blocked": False}],
            ],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 1
        actor.grid_y = 1
        blocking_entity = _make_runtime_entity("crate", kind="crate")
        blocking_entity.grid_x = 2
        blocking_entity.grid_y = 1
        blocking_entity.solid = True
        blocking_entity.pushable = True
        world.add_entity(actor)
        world.add_entity(blocking_entity)
        registry, context = self._make_command_context(area=area, world=world)

        handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "player",
                "name": "target_cell",
                "value": {
                    "$cell_flags_at": {
                        "x": 2,
                        "y": 1,
                    }
                },
            },
        )
        handle.update(0.0)

        handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "player",
                "name": "target_entities",
                "value": {
                    "$entities_at": {
                        "x": 2,
                        "y": 1,
                        "select": {
                            "fields": ["entity_id", "solid", "pushable"],
                        },
                    }
                },
            },
        )
        handle.update(0.0)

        handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "player",
                "name": "blocking_entity",
                "value": {
                    "$find_in_collection": {
                        "value": "$self.target_entities",
                        "field": "solid",
                        "op": "eq",
                        "match": True,
                        "default": None,
                    }
                },
            },
            base_params={"source_entity_id": "player"},
        )
        handle.update(0.0)

        handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "player",
                "name": "has_pushable_blocker",
                "value": {
                    "$any_in_collection": {
                        "value": "$self.target_entities",
                        "field": "pushable",
                        "op": "eq",
                        "match": True,
                    }
                },
            },
            base_params={"source_entity_id": "player"},
        )
        handle.update(0.0)

        player = world.get_entity("player")
        assert player is not None
        self.assertEqual(player.variables["target_cell"]["blocked"], True)
        self.assertEqual(player.variables["blocking_entity"]["entity_id"], "crate")
        self.assertTrue(player.variables["has_pushable_blocker"])

    def test_entities_at_and_entity_at_value_sources_return_stable_plain_refs(self) -> None:
        world = World()
        low = _make_runtime_entity("low", kind="sign")
        low.grid_x = 2
        low.grid_y = 3
        low.render_order = 1
        low.stack_order = 0
        high = _make_runtime_entity("high", kind="lever")
        high.grid_x = 2
        high.grid_y = 3
        high.render_order = 2
        high.stack_order = 5
        high.solid = True
        high.pushable = True
        high.variables["custom_marker"] = "blocking"
        high.visuals.append(
            EntityVisual(
                visual_id="main",
                visible=False,
                flip_x=True,
                current_frame=3,
            )
        )
        world.add_entity(low)
        world.add_entity(high)
        world.add_entity(_make_runtime_entity("dialogue_controller", kind="system", space="screen"))
        registry, context = self._make_command_context(world=world)

        handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "targets_here",
                "value": {
                    "$entities_at": {
                        "x": 2,
                        "y": 3,
                        "select": {
                            "fields": ["entity_id", "kind"],
                        },
                    }
                },
            },
        )
        handle.update(0.0)

        controller = world.get_entity("dialogue_controller")
        assert controller is not None
        targets_here = controller.variables["targets_here"]
        self.assertEqual([item["entity_id"] for item in targets_here], ["low", "high"])
        self.assertEqual(targets_here[0]["kind"], "sign")
        self.assertEqual(targets_here[1]["kind"], "lever")

        first_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "first_target",
                "value": {
                    "$entity_at": {
                        "x": 2,
                        "y": 3,
                        "index": 0,
                        "select": {
                            "fields": ["entity_id"],
                        },
                        "default": None,
                    }
                },
            },
        )
        first_handle.update(0.0)
        self.assertEqual(controller.variables["first_target"]["entity_id"], "low")

        last_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "last_target",
                "value": {
                    "$entity_at": {
                        "x": 2,
                        "y": 3,
                        "index": -1,
                        "select": {
                            "fields": ["entity_id"],
                        },
                        "default": None,
                    }
                },
            },
        )
        last_handle.update(0.0)
        self.assertEqual(controller.variables["last_target"]["entity_id"], "high")

        ref_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "self_ref",
                "value": {
                    "$entity_ref": {
                        "entity_id": "high",
                        "select": {
                            "fields": ["entity_id", "grid_x", "solid", "pushable"],
                            "variables": ["custom_marker"],
                        },
                    }
                },
            },
        )
        ref_handle.update(0.0)
        self.assertEqual(controller.variables["self_ref"]["entity_id"], "high")
        self.assertEqual(controller.variables["self_ref"]["grid_x"], 2)
        self.assertTrue(controller.variables["self_ref"]["solid"])
        self.assertTrue(controller.variables["self_ref"]["pushable"])
        self.assertEqual(
            controller.variables["self_ref"]["variables"],
            {"custom_marker": "blocking"},
        )

        selected_ref_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "selected_ref",
                "value": {
                    "$entity_ref": {
                        "entity_id": "high",
                        "select": {
                            "fields": ["grid_x", "pixel_y", "present", "pushable"],
                            "variables": ["custom_marker"],
                            "visuals": [
                                {
                                    "id": "main",
                                    "fields": ["visible", "flip_x", "current_frame"],
                                }
                            ],
                        },
                    }
                },
            },
        )
        selected_ref_handle.update(0.0)
        self.assertEqual(
            controller.variables["selected_ref"],
            {
                "grid_x": 2,
                "pixel_y": 0.0,
                "present": True,
                "pushable": True,
                "variables": {"custom_marker": "blocking"},
                "visuals": {
                    "main": {
                        "visible": False,
                        "flip_x": True,
                        "current_frame": 3,
                    }
                },
            },
        )

        selected_target_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "selected_target",
                "value": {
                    "$entity_at": {
                        "x": 2,
                        "y": 3,
                        "index": -1,
                        "select": {
                            "fields": ["entity_id", "pushable"],
                            "variables": ["custom_marker"],
                        },
                        "default": None,
                    }
                },
            },
        )
        selected_target_handle.update(0.0)
        self.assertEqual(
            controller.variables["selected_target"],
            {
                "entity_id": "high",
                "pushable": True,
                "variables": {"custom_marker": "blocking"},
            },
        )

        selected_targets_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "selected_targets",
                "value": {
                    "$entities_at": {
                        "x": 2,
                        "y": 3,
                        "select": {
                            "fields": ["entity_id", "solid", "pushable"],
                            "variables": ["custom_marker"],
                        },
                    }
                },
            },
        )
        selected_targets_handle.update(0.0)
        self.assertEqual(
            controller.variables["selected_targets"],
            [
                {
                    "entity_id": "low",
                    "solid": False,
                    "pushable": False,
                    "variables": {},
                },
                {
                    "entity_id": "high",
                    "solid": True,
                    "pushable": True,
                    "variables": {"custom_marker": "blocking"},
                },
            ],
        )

        missing_selected_ref_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "missing_selected_ref",
                "value": {
                    "$entity_ref": {
                        "entity_id": "missing",
                        "select": {
                            "fields": ["grid_x", "grid_y"],
                        },
                        "default": None,
                    }
                },
            },
        )
        missing_selected_ref_handle.update(0.0)
        self.assertIsNone(controller.variables["missing_selected_ref"])

        with self.assertRaisesRegex(ValueError, r"\$entity_ref select\.fields does not support"):
            execute_command_spec(
                registry,
                context,
                {
                    "type": "set_entity_var",
                    "entity_id": "dialogue_controller",
                    "name": "invalid_select",
                    "value": {
                        "$entity_ref": {
                            "entity_id": "high",
                            "select": {
                                "fields": ["grid_x", "variables"],
                            },
                        }
                    },
                },
            )

        sum_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "target_x",
                "value": {
                    "$sum": [
                        "$self.self_ref.grid_x",
                        -1,
                    ]
                },
            },
            base_params={"source_entity_id": "dialogue_controller"},
        )
        sum_handle.update(0.0)
        self.assertEqual(controller.variables["target_x"], 1)

    def test_entity_query_value_sources_support_where_filters(self) -> None:
        world = World()
        sign = _make_runtime_entity("alpha_sign", kind="sign")
        sign.grid_x = 2
        sign.grid_y = 3
        sign.render_order = 1
        sign.stack_order = 0
        sign.tags = ["readable"]

        lever_visible = _make_runtime_entity("beta_lever", kind="lever")
        lever_visible.grid_x = 2
        lever_visible.grid_y = 3
        lever_visible.render_order = 2
        lever_visible.stack_order = 0
        lever_visible.tags = ["switch", "red"]
        lever_visible.variables["toggled"] = False

        lever_hidden = _make_runtime_entity("aardvark_hidden", kind="lever")
        lever_hidden.grid_x = 2
        lever_hidden.grid_y = 3
        lever_hidden.render_order = 2
        lever_hidden.stack_order = 0
        lever_hidden.visible = False
        lever_hidden.tags = ["switch", "red"]
        lever_hidden.variables["toggled"] = True

        lever_absent = _make_runtime_entity("absent_lever", kind="lever")
        lever_absent.grid_x = 5
        lever_absent.grid_y = 6
        lever_absent.render_order = 0
        lever_absent.stack_order = 0
        lever_absent.present = False
        lever_absent.tags = ["switch", "blue"]
        lever_absent.variables["toggled"] = True

        save_point = _make_runtime_entity(
            "global_save",
            kind="save_point",
            scope="global",
        )
        save_point.grid_x = 9
        save_point.grid_y = 9
        save_point.render_order = 0
        save_point.stack_order = 2
        save_point.tags = ["save_point"]

        controller = _make_runtime_entity("dialogue_controller", kind="system", space="screen")
        world.add_entity(sign)
        world.add_entity(lever_visible)
        world.add_entity(lever_hidden)
        world.add_entity(lever_absent)
        world.add_entity(save_point)
        world.add_entity(controller)
        registry, context = self._make_command_context(world=world)

        all_switches_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "all_switches",
                "value": {
                    "$entities_query": {
                        "where": {
                            "tags_any": ["switch"],
                        },
                        "select": {
                            "fields": ["entity_id", "visible"],
                            "variables": ["toggled"],
                        },
                    }
                },
            },
        )
        all_switches_handle.update(0.0)

        hidden_switches_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "hidden_switches",
                "value": {
                    "$entities_query": {
                        "where": {
                            "tags_all": ["switch", "red"],
                            "visible": False,
                        },
                        "select": {
                            "fields": ["entity_id", "visible"],
                            "variables": ["toggled"],
                        },
                    }
                },
            },
        )
        hidden_switches_handle.update(0.0)

        absent_switches_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "absent_switches",
                "value": {
                    "$entities_query": {
                        "where": {
                            "kind": "lever",
                            "present": False,
                        },
                        "select": {
                            "fields": ["entity_id", "present"],
                            "variables": ["toggled"],
                        },
                    }
                },
            },
        )
        absent_switches_handle.update(0.0)

        first_query_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "first_query_result",
                "value": {
                    "$entity_query": {
                        "where": {
                            "kinds": ["sign", "lever"],
                        },
                        "index": 0,
                        "default": None,
                        "select": {
                            "fields": ["entity_id", "kind"],
                        },
                    }
                },
            },
        )
        first_query_handle.update(0.0)

        last_query_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "last_query_result",
                "value": {
                    "$entity_query": {
                        "where": {
                            "kinds": ["sign", "lever"],
                        },
                        "index": -1,
                        "default": None,
                        "select": {
                            "fields": ["entity_id", "kind"],
                        },
                    }
                },
            },
        )
        last_query_handle.update(0.0)

        hidden_tile_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "hidden_tile_target",
                "value": {
                    "$entity_at": {
                        "x": 2,
                        "y": 3,
                        "index": 0,
                        "where": {
                            "kind": "lever",
                            "visible": False,
                        },
                        "select": {
                            "fields": ["entity_id", "visible"],
                        },
                        "default": None,
                    }
                },
            },
        )
        hidden_tile_handle.update(0.0)

        controller_entity = world.get_entity("dialogue_controller")
        assert controller_entity is not None
        self.assertEqual(
            controller_entity.variables["all_switches"],
            [
                {
                    "entity_id": "beta_lever",
                    "visible": True,
                    "variables": {"toggled": False},
                }
            ],
        )
        self.assertEqual(
            controller_entity.variables["hidden_switches"],
            [
                {
                    "entity_id": "aardvark_hidden",
                    "visible": False,
                    "variables": {"toggled": True},
                }
            ],
        )
        self.assertEqual(
            controller_entity.variables["absent_switches"],
            [
                {
                    "entity_id": "absent_lever",
                    "present": False,
                    "variables": {"toggled": True},
                }
            ],
        )
        self.assertEqual(
            controller_entity.variables["first_query_result"],
            {"entity_id": "alpha_sign", "kind": "sign"},
        )
        self.assertEqual(
            controller_entity.variables["last_query_result"],
            {"entity_id": "beta_lever", "kind": "lever"},
        )
        self.assertEqual(
            controller_entity.variables["hidden_tile_target"],
            {"entity_id": "aardvark_hidden", "visible": False},
        )

        with self.assertRaisesRegex(
            ValueError,
            r"\$entities_query where does not allow both 'kind' and 'kinds'",
        ):
            execute_command_spec(
                registry,
                context,
                {
                    "type": "set_entity_var",
                    "entity_id": "dialogue_controller",
                    "name": "invalid_where",
                    "value": {
                        "$entities_query": {
                            "where": {
                                "kind": "lever",
                                "kinds": ["lever", "sign"],
                            },
                            "select": {
                                "fields": ["entity_id"],
                            },
                        }
                    },
                },
            )

        with self.assertRaisesRegex(
            ValueError,
            r"\$entities_query where\.tags_any requires a non-empty list",
        ):
            execute_command_spec(
                registry,
                context,
                {
                    "type": "set_entity_var",
                    "entity_id": "dialogue_controller",
                    "name": "invalid_where_tags",
                    "value": {
                        "$entities_query": {
                            "where": {
                                "tags_any": [],
                            },
                            "select": {
                                "fields": ["entity_id"],
                            },
                        }
                    },
                },
            )

    def test_debug_runtime_commands_are_gated_by_project_debug_flag(self) -> None:
        registry, context = self._make_command_context()
        paused_states: list[bool] = []
        zoom_deltas: list[int] = []
        step_requests: list[str] = []
        pause_state = {"paused": False}

        def _record_pause(paused: bool) -> None:
            paused_states.append(bool(paused))
            pause_state["paused"] = bool(paused)

        context.set_simulation_paused = _record_pause
        context.get_simulation_paused = lambda: pause_state["paused"]
        context.request_step_simulation_tick = lambda: step_requests.append("step")
        context.adjust_output_scale = lambda delta: zoom_deltas.append(int(delta))

        context.debug_inspection_enabled = False
        execute_registered_command(registry, context, "toggle_simulation_paused", {}).update(0.0)
        execute_registered_command(registry, context, "step_simulation_tick", {}).update(0.0)
        execute_registered_command(
            registry,
            context,
            "adjust_output_scale",
            {"delta": 1},
        ).update(0.0)
        self.assertEqual(paused_states, [])
        self.assertEqual(step_requests, [])
        self.assertEqual(zoom_deltas, [])

        context.debug_inspection_enabled = True
        execute_registered_command(registry, context, "toggle_simulation_paused", {}).update(0.0)
        execute_registered_command(registry, context, "step_simulation_tick", {}).update(0.0)
        execute_registered_command(
            registry,
            context,
            "adjust_output_scale",
            {"delta": -1},
        ).update(0.0)
        self.assertEqual(paused_states, [True])
        self.assertEqual(step_requests, ["step"])
        self.assertEqual(zoom_deltas, [-1])

    def test_named_interact_one_tile_can_target_adjacent_entity_with_explicit_tile_query(self) -> None:
        _, project = self._make_project(
            commands={
                "interact_one_tile.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "interact_self_position",
                            "value": {
                                "$entity_ref": {
                                    "entity_id": "$self_id",
                                    "select": {
                                        "fields": ["grid_x", "grid_y"],
                                    },
                                }
                            },
                        },
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "interact_offset",
                            "value": {
                                "$collection_item": {
                                    "value": {
                                        "up": {"x": 0, "y": -1},
                                        "down": {"x": 0, "y": 1},
                                        "left": {"x": -1, "y": 0},
                                        "right": {"x": 1, "y": 0},
                                    },
                                    "key": "$self.direction",
                                    "default": {"x": 0, "y": 0},
                                }
                            },
                        },
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "interact_target_x",
                            "value": {
                                "$sum": [
                                    "$self.interact_self_position.grid_x",
                                    "$self.interact_offset.x",
                                ]
                            },
                        },
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "interact_target_y",
                            "value": {
                                "$sum": [
                                    "$self.interact_self_position.grid_y",
                                    "$self.interact_offset.y",
                                ]
                            },
                        },
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "interact_target",
                            "value": {
                                "$entity_at": {
                                    "x": "$self.interact_target_x",
                                    "y": "$self.interact_target_y",
                                    "index": 0,
                                    "select": {
                                        "fields": ["entity_id"],
                                    },
                                    "default": None,
                                }
                            },
                        },
                        {
                            "type": "if",
                            "left": "$self.interact_target",
                            "op": "neq",
                            "right": None,
                            "then": [
                                {
                                    "type": "run_entity_command",
                                    "entity_id": "$self.interact_target.entity_id",
                                    "command_id": "interact",
                                    "entity_refs": {
                                        "instigator": "$self_id",
                                    },
                                }
                            ],
                        },
                    ],
                }
            }
        )
        world = World()
        player = _make_runtime_entity("player", kind="player")
        player.grid_x = 4
        player.grid_y = 6
        player.variables["direction"] = "right"
        lever = _make_runtime_entity(
            "lever",
            kind="lever",
            entity_commands={
                "interact": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_current_area_var",
                            "name": "adjacent_interaction_triggered",
                            "value": True,
                        }
                    ]
                )
            },
        )
        lever.grid_x = 5
        lever.grid_y = 6
        world.add_entity(player)
        world.add_entity(lever)
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_command_spec(
            registry,
            context,
            {
                "type": "run_project_command",
                "command_id": "commands/interact_one_tile",
            },
            base_params={
                "source_entity_id": "player",
                "entity_refs": {
                    "instigator": "player",
                },
            },
        )
        while not handle.complete:
            handle.update(0.0)
        self.assertTrue(world.variables["adjacent_interaction_triggered"])

    def test_explicit_entity_var_primitives_manage_values_and_branching(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("dialogue_controller", kind="system", space="screen"))
        registry, context = self._make_command_context(world=world)

        execute_registered_command(
            registry,
            context,
            "set_entity_var",
            {
                "entity_id": "dialogue_controller",
                "name": "mode",
                "value": "menu",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "add_entity_var",
            {
                "entity_id": "dialogue_controller",
                "name": "choice_index",
                "amount": 2,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "append_entity_var",
            {
                "entity_id": "dialogue_controller",
                "name": "dialogue_state_stack",
                "value": {"dialogue_path": "dialogues/system/title_menu.json"},
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "append_entity_var",
            {
                "entity_id": "dialogue_controller",
                "name": "dialogue_state_stack",
                "value": {"dialogue_path": "dialogues/system/save_prompt.json"},
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_entity_var_length",
            {
                "entity_id": "dialogue_controller",
                "name": "stack_count",
                "value": [{"a": 1}, {"b": 2}],
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "selected_option",
                "value": {
                    "$collection_item": {
                        "value": [
                            {"option_id": "new_game"},
                            {"option_id": "load_game"},
                        ],
                        "index": 1,
                        "default": {},
                    }
                },
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "pop_entity_var",
            {
                "entity_id": "dialogue_controller",
                "name": "dialogue_state_stack",
                "store_var": "restored_snapshot",
                "default": {},
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "if",
                "left": {
                    "$entity_var": {
                        "entity_id": "dialogue_controller",
                        "name": "mode",
                    }
                },
                "op": "eq",
                "right": "menu",
                "then": [
                    {
                        "type": "set_entity_var",
                        "entity_id": "dialogue_controller",
                        "name": "branch_hit",
                        "value": True,
                    }
                ],
            },
        ).update(0.0)

        controller = world.get_entity("dialogue_controller")
        assert controller is not None
        self.assertEqual(controller.variables["mode"], "menu")
        self.assertEqual(controller.variables["choice_index"], 2)
        self.assertEqual(controller.variables["stack_count"], 2)
        self.assertEqual(controller.variables["selected_option"], {"option_id": "load_game"})
        self.assertEqual(
            controller.variables["dialogue_state_stack"],
            [{"dialogue_path": "dialogues/system/title_menu.json"}],
        )
        self.assertEqual(
            controller.variables["restored_snapshot"],
            {"dialogue_path": "dialogues/system/save_prompt.json"},
        )
        self.assertTrue(controller.variables["branch_hit"])

    def test_explicit_current_area_var_primitives_manage_values_and_branching(self) -> None:
        registry, context = self._make_command_context()

        execute_registered_command(
            registry,
            context,
            "set_current_area_var",
            {
                "name": "mode",
                "value": "play",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "add_current_area_var",
            {
                "name": "turn_count",
                "amount": 3,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "append_current_area_var",
            {
                "name": "visited_rooms",
                "value": "areas/village_square",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "append_current_area_var",
            {
                "name": "visited_rooms",
                "value": "areas/village_house",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_current_area_var_length",
            {
                "name": "visited_room_count",
                "value": context.world.variables["visited_rooms"],
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_current_area_var",
                "name": "latest_room",
                "value": {
                    "$collection_item": {
                        "value": context.world.variables["visited_rooms"],
                        "index": 1,
                        "default": "",
                    }
                },
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "pop_current_area_var",
            {
                "name": "visited_rooms",
                "store_var": "popped_room",
                "default": "",
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "if",
                "left": "$current_area.mode",
                "op": "eq",
                "right": "play",
                "then": [
                    {
                        "type": "set_current_area_var",
                        "name": "world_branch_hit",
                        "value": True,
                    }
                ],
            },
        ).update(0.0)

        self.assertEqual(context.world.variables["mode"], "play")
        self.assertEqual(context.world.variables["turn_count"], 3)
        self.assertEqual(context.world.variables["visited_room_count"], 2)
        self.assertEqual(context.world.variables["latest_room"], "areas/village_house")
        self.assertEqual(context.world.variables["visited_rooms"], ["areas/village_square"])
        self.assertEqual(context.world.variables["popped_room"], "areas/village_house")
        self.assertTrue(context.world.variables["world_branch_hit"])

    def test_toggle_var_primitives_flip_boolean_values(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("switch", kind="switch"))
        registry, context = self._make_command_context(world=world)

        execute_registered_command(
            registry,
            context,
            "toggle_entity_var",
            {
                "entity_id": "switch",
                "name": "enabled",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "toggle_entity_var",
            {
                "entity_id": "switch",
                "name": "enabled",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "toggle_current_area_var",
            {
                "name": "paused",
            },
        ).update(0.0)

        switch = world.get_entity("switch")
        assert switch is not None
        self.assertFalse(switch.variables["enabled"])
        self.assertTrue(context.world.variables["paused"])

        switch.variables["enabled"] = "yes"
        with self.assertRaises(CommandExecutionError):
            execute_registered_command(
                registry,
                context,
                "toggle_entity_var",
                {
                    "entity_id": "switch",
                    "name": "enabled",
                },
            ).update(0.0)

    def test_set_entity_fields_updates_multiple_sections(self) -> None:
        world = World()
        lever = _make_runtime_entity("lever", kind="lever", with_visual=True)
        lever.variables["active"] = False
        lever.visuals.append(
            EntityVisual(
                visual_id="shadow",
                path="assets/project/sprites/shadow.png",
                frame_width=16,
                frame_height=16,
                frames=[0],
            )
        )
        world.add_entity(lever)
        registry, context = self._make_command_context(world=world)

        execute_registered_command(
            registry,
            context,
            "set_entity_fields",
            {
                "entity_id": "lever",
                "set": {
                    "fields": {
                        "visible": False,
                    },
                    "variables": {
                        "active": True,
                    },
                    "visuals": {
                        "main": {
                            "offset_x": 2,
                            "offset_y": -1,
                            "animation_fps": 6,
                            "tint": [1, 2, 3],
                        },
                        "shadow": {
                            "visible": False,
                        },
                    },
                },
            },
        ).update(0.0)

        updated = world.get_entity("lever")
        assert updated is not None
        self.assertFalse(updated.visible)
        self.assertTrue(updated.variables["active"])
        main_visual = updated.require_visual("main")
        self.assertEqual(main_visual.tint, (1, 2, 3))
        self.assertEqual(main_visual.offset_x, 2.0)
        self.assertEqual(main_visual.offset_y, -1.0)
        self.assertEqual(main_visual.animation_fps, 6.0)
        self.assertFalse(updated.require_visual("shadow").visible)

    def test_set_entity_fields_is_all_or_nothing(self) -> None:
        world = World()
        lever = _make_runtime_entity("lever", kind="lever", with_visual=True)
        lever.variables["active"] = False
        world.add_entity(lever)
        registry, context = self._make_command_context(world=world)

        with self.assertRaises(CommandExecutionError):
            execute_registered_command(
                registry,
                context,
                "set_entity_fields",
                {
                    "entity_id": "lever",
                    "set": {
                        "fields": {
                            "visible": False,
                        },
                        "variables": {
                            "active": True,
                        },
                        "visuals": {
                            "main": {
                                "path": "assets/project/other.png",
                            }
                        },
                    },
                },
            ).update(0.0)

        unchanged = world.get_entity("lever")
        assert unchanged is not None
        self.assertTrue(unchanged.visible)
        self.assertFalse(unchanged.variables["active"])
        self.assertEqual(unchanged.require_visual("main").path, "assets/project/sprites/test.png")

    def test_explicit_var_primitives_persist_when_requested(self) -> None:
        _, project = self._make_project()
        authored_world = World()
        authored_world.add_entity(_make_runtime_entity("dialogue_controller", kind="system", space="screen"))
        runtime = PersistenceRuntime(project=project)
        runtime.bind_area("areas/test_room", authored_world=authored_world)

        live_world = World()
        live_world.add_entity(_make_runtime_entity("dialogue_controller", kind="system", space="screen"))
        registry, context = self._make_command_context(
            project=project,
            world=live_world,
            persistence_runtime=runtime,
        )

        execute_registered_command(
            registry,
            context,
            "set_current_area_var",
            {
                "name": "door_open",
                "value": True,
                "persistent": True,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_entity_var",
            {
                "entity_id": "dialogue_controller",
                "name": "mode",
                "value": "choice",
                "persistent": True,
            },
        ).update(0.0)

        area_state = runtime.current_area_state()
        assert area_state is not None
        self.assertTrue(area_state.variables["door_open"])
        self.assertEqual(
            area_state.entities["dialogue_controller"].overrides["variables"]["mode"],
            "choice",
        )

    def test_current_area_runtime_token_replaces_world_token(self) -> None:
        world = World()
        world.variables["phase"] = "opening"
        world.add_entity(_make_runtime_entity("controller", kind="system", space="screen"))
        registry, context = self._make_command_context(world=world)

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "controller",
                "name": "copied_phase",
                "value": "$current_area.phase",
            },
        ).update(0.0)

        controller = world.get_entity("controller")
        assert controller is not None
        self.assertEqual(controller.variables["copied_phase"], "opening")

        with self.assertRaises(KeyError):
            execute_command_spec(
                registry,
                context,
                {
                    "type": "set_entity_var",
                    "entity_id": "controller",
                    "name": "legacy_phase",
                    "value": "$world.phase",
                },
            ).update(0.0)

    def test_cross_area_state_commands_persist_target_area_state_and_update_loaded_area(self) -> None:
        _, project = self._make_project(
            areas={
                "current_room.json": {
                    **_minimal_area(name="Current Room"),
                    "entities": [
                        {
                            "id": "switch_1",
                            "kind": "switch",
                            "x": 0,
                            "y": 0,
                            "variables": {"enabled": False},
                        }
                    ],
                },
                "other_room.json": {
                    **_minimal_area(name="Other Room"),
                    "entities": [
                        {
                            "id": "gate_1",
                            "kind": "gate",
                            "x": 0,
                            "y": 0,
                            "variables": {"open": False},
                        }
                    ],
                },
            }
        )
        runtime = PersistenceRuntime(project=project)
        world = World()
        switch = _make_runtime_entity("switch_1", kind="switch")
        switch.variables["enabled"] = False
        world.add_entity(switch)
        current_area = Area(
            area_id="areas/current_room",
            name="Current Room",
            tile_size=16,
            tilesets=[],
            tile_layers=[],
            cell_flags=[],
        )
        registry, context = self._make_command_context(
            project=project,
            world=world,
            area=current_area,
            persistence_runtime=runtime,
        )

        execute_registered_command(
            registry,
            context,
            "set_area_var",
            {
                "area_id": "areas/other_room",
                "name": "bridge_lowered",
                "value": True,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_area_var",
            {
                "area_id": "areas/current_room",
                "name": "alarm_on",
                "value": True,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_area_entity_var",
            {
                "area_id": "areas/other_room",
                "entity_id": "gate_1",
                "name": "open",
                "value": True,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_area_entity_var",
            {
                "area_id": "areas/current_room",
                "entity_id": "switch_1",
                "name": "enabled",
                "value": True,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_area_entity_field",
            {
                "area_id": "areas/other_room",
                "entity_id": "gate_1",
                "field_name": "visible",
                "value": False,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_area_entity_field",
            {
                "area_id": "areas/current_room",
                "entity_id": "switch_1",
                "field_name": "visible",
                "value": False,
            },
        ).update(0.0)

        self.assertTrue(world.variables["alarm_on"])
        updated_switch = world.get_entity("switch_1")
        assert updated_switch is not None
        self.assertTrue(updated_switch.variables["enabled"])
        self.assertFalse(updated_switch.visible)

        self.assertTrue(runtime.save_data.areas["areas/other_room"].variables["bridge_lowered"])
        self.assertTrue(runtime.save_data.areas["areas/current_room"].variables["alarm_on"])
        self.assertTrue(
            runtime.save_data.areas["areas/other_room"].entities["gate_1"].overrides["variables"]["open"]
        )
        self.assertTrue(
            runtime.save_data.areas["areas/current_room"].entities["switch_1"].overrides["variables"][
                "enabled"
            ]
        )
        self.assertFalse(runtime.save_data.areas["areas/other_room"].entities["gate_1"].overrides["visible"])
        self.assertFalse(
            runtime.save_data.areas["areas/current_room"].entities["switch_1"].overrides["visible"]
        )

    def test_area_entity_ref_reads_area_owned_state_plus_persistent_overrides(self) -> None:
        _, project = self._make_project(
            areas={
                "other_room.json": {
                    **_minimal_area(name="Other Room"),
                    "entities": [
                        {
                            "id": "gate_1",
                            "kind": "gate",
                            "x": 0,
                            "y": 0,
                            "variables": {"open": False},
                        }
                    ],
                }
            }
        )
        runtime = PersistenceRuntime(project=project)
        runtime.set_area_entity_variable("areas/other_room", "gate_1", "open", True)
        runtime.set_area_entity_field("areas/other_room", "gate_1", "visible", False)

        world = World()
        world.add_entity(_make_runtime_entity("controller", kind="system", space="screen"))
        registry, context = self._make_command_context(
            project=project,
            world=world,
            persistence_runtime=runtime,
        )

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "controller",
                "name": "snapshot",
                "value": {
                    "$area_entity_ref": {
                        "area_id": "areas/other_room",
                        "entity_id": "gate_1",
                        "select": {
                            "fields": ["entity_id", "visible"],
                            "variables": ["open"],
                        },
                        "default": None,
                    }
                },
            },
        ).update(0.0)

        controller = world.get_entity("controller")
        assert controller is not None
        self.assertEqual(
            controller.variables["snapshot"],
            {
                "entity_id": "gate_1",
                "visible": False,
                "variables": {"open": True},
            },
        )

    def test_registry_filters_inherited_runtime_params_for_explicit_primitives(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("dialogue_controller", kind="system", space="screen"))
        registry, context = self._make_command_context(world=world)

        execute_registered_command(
            registry,
            context,
            "set_entity_var",
            {
                "entity_id": "dialogue_controller",
                "name": "mode",
                "value": "nested_dialogue",
                "source_entity_id": "dialogue_controller",
                "entity_refs": {
                    "instigator": "player",
                    "caller": "lever",
                },
                "scope": "entity",
                "unused_named_param": 42,
            },
        ).update(0.0)

        controller = world.get_entity("dialogue_controller")
        assert controller is not None
        self.assertEqual(controller.variables["mode"], "nested_dialogue")

    def test_registry_declares_deferred_params_for_orchestration_commands(self) -> None:
        registry = CommandRegistry()
        register_builtin_commands(registry)

        self.assertEqual(registry.get_deferred_params("run_commands"), {"commands"})
        self.assertEqual(registry.get_deferred_params("spawn_flow"), {"commands"})
        self.assertEqual(registry.get_deferred_params("run_parallel"), {"commands"})
        self.assertEqual(registry.get_deferred_params("run_commands_for_collection"), {"commands"})
        self.assertEqual(
            registry.get_deferred_params("run_entity_command"),
            {"dialogue_on_start", "dialogue_on_end", "segment_hooks"},
        )
        self.assertEqual(registry.get_deferred_params("if"), {"then", "else"})

    def test_append_and_pop_entity_var_support_nested_dialogue_snapshots(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("dialogue_controller", kind="system", space="screen"))
        registry, context = self._make_command_context(world=world)

        append_parent = execute_registered_command(
            registry,
            context,
            "append_entity_var",
            {
                "entity_id": "dialogue_controller",
                "name": "dialogue_state_stack",
                "value": {"dialogue_path": "dialogues/system/title_menu.json", "choice_index": 1},
            },
        )
        append_parent.update(0.0)

        append_child = execute_registered_command(
            registry,
            context,
            "append_entity_var",
            {
                "entity_id": "dialogue_controller",
                "name": "dialogue_state_stack",
                "value": {"dialogue_path": "dialogues/system/save_prompt.json", "choice_index": 0},
            },
        )
        append_child.update(0.0)

        pop_handle = execute_registered_command(
            registry,
            context,
            "pop_entity_var",
            {
                "entity_id": "dialogue_controller",
                "name": "dialogue_state_stack",
                "store_var": "restored_snapshot",
                "default": {},
            },
        )
        pop_handle.update(0.0)

        controller = world.get_entity("dialogue_controller")
        assert controller is not None
        self.assertEqual(
            controller.variables["dialogue_state_stack"],
            [{"dialogue_path": "dialogues/system/title_menu.json", "choice_index": 1}],
        )
        self.assertEqual(
            controller.variables["restored_snapshot"],
            {"dialogue_path": "dialogues/system/save_prompt.json", "choice_index": 0},
        )

    def test_area_validation_rejects_legacy_interact_commands(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "sign_1",
                            "kind": "sign",
                            "x": 1,
                            "y": 1,
                            "interact_commands": [{"type": "run_dialogue", "text": "Old schema"}],
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("interact_commands" in issue and "entity_commands.interact" in issue for issue in raised.exception.issues)
        )

    def test_area_validation_rejects_symbolic_entity_refs_for_strict_primitives(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "route_inputs_to_entity",
                            "entity_id": "self",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'self' with strict primitive 'route_inputs_to_entity'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_area_validation_rejects_symbolic_entity_refs_for_strict_visual_primitives(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "set_visual_frame",
                            "entity_id": "self",
                            "frame": 2,
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'self' with strict primitive 'set_visual_frame'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_area_validation_rejects_symbolic_entity_refs_for_strict_movement_primitives(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "wait_for_move",
                            "entity_id": "self",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'self' with strict primitive 'wait_for_move'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_area_validation_rejects_reserved_entity_id_self(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "self",
                            "kind": "sign",
                            "x": 1,
                            "y": 1,
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("reserved runtime entity reference 'self'" in issue for issue in raised.exception.issues)
        )

    def test_area_validation_allows_entity_id_actor(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "actor",
                            "kind": "sign",
                            "x": 1,
                            "y": 1,
                        }
                    ],
                }
            }
        )

        validate_project_areas(project)

    def test_area_validation_rejects_duplicate_project_global_entity_ids(self) -> None:
        _, project = self._make_project(
            global_entities=[
                {
                    "id": "dialogue_controller",
                    "kind": "system",
                    "space": "screen",
                },
                {
                    "id": "dialogue_controller",
                    "kind": "system",
                    "space": "screen",
                },
            ],
            areas={"test_room.json": _minimal_area()},
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "global_entities[1] uses duplicate entity id 'dialogue_controller'" in issue
                for issue in raised.exception.issues
            )
        )

    def test_area_validation_rejects_area_entity_id_collision_with_project_global(self) -> None:
        _, project = self._make_project(
            global_entities=[
                {
                    "id": "dialogue_controller",
                    "kind": "system",
                    "space": "screen",
                }
            ],
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "dialogue_controller",
                            "kind": "sign",
                            "x": 1,
                            "y": 1,
                        }
                    ],
                }
            },
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "conflicts with project.json global entity id 'dialogue_controller'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_world_rejects_cross_scope_entity_id_collisions(self) -> None:
        world = World()
        world.add_entity(
            _make_runtime_entity(
                "dialogue_controller",
                kind="system",
                space="screen",
                scope="global",
            )
        )

        with self.assertRaises(ValueError):
            world.add_entity(
                _make_runtime_entity(
                    "dialogue_controller",
                    kind="sign",
                    scope="area",
                )
            )

        restored_entity = world.get_entity("dialogue_controller")
        assert restored_entity is not None
        self.assertEqual(restored_entity.scope, "global")

    def test_world_route_inputs_to_entity_clear_restores_defaults(self) -> None:
        world = World(
            default_input_targets={
                "interact": "player",
                "menu": "dialogue_controller",
            },
        )
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(
            _make_runtime_entity(
                "dialogue_controller",
                kind="system",
                space="screen",
                scope="global",
            )
        )

        world.route_inputs_to_entity("dialogue_controller", actions=["interact"])
        self.assertEqual(world.get_input_target_id("interact"), "dialogue_controller")
        self.assertEqual(world.get_input_target_id("menu"), "dialogue_controller")

        world.route_inputs_to_entity(None, actions=["interact"])

        self.assertEqual(world.get_input_target_id("interact"), "player")
        self.assertEqual(world.get_input_target_id("menu"), "dialogue_controller")

    def test_game_launcher_resolves_startup_area_and_cli_ids(self) -> None:
        _, project = self._make_project(
            startup_area="areas/intro/title_screen",
            areas={"intro/title_screen.json": _minimal_area(name="Title Screen")},
        )

        self.assertEqual(run_game._resolve_project_startup_area(project), "areas/intro/title_screen")
        self.assertEqual(
            run_game._resolve_area_argument(project, "areas/intro/title_screen"),
            "areas/intro/title_screen",
        )

    def test_game_launcher_rejects_area_paths_as_cli_arguments(self) -> None:
        _, project = self._make_project(
            startup_area="areas/intro/title_screen",
            areas={"intro/title_screen.json": _minimal_area(name="Title Screen")},
        )

        with self.assertRaises(FileNotFoundError):
            run_game._resolve_area_argument(project, "areas/intro/title_screen.json")

    def test_new_game_command_queues_requested_transition(self) -> None:
        recorded_requests: list[AreaTransitionRequest] = []
        registry = CommandRegistry()
        register_builtin_commands(registry)
        context = CommandContext(
            area=_minimal_runtime_area(),
            world=World(),
            collision_system=None,  # type: ignore[arg-type]
            movement_system=None,  # type: ignore[arg-type]
            interaction_system=None,  # type: ignore[arg-type]
            animation_system=None,  # type: ignore[arg-type]
            request_new_game=recorded_requests.append,
        )

        handle = execute_registered_command(
            registry,
            context,
            "new_game",
            {
                "area_id": "areas/village_square",
                "entry_id": "startup",
            },
        )
        handle.update(0.0)

        self.assertEqual(len(recorded_requests), 1)
        self.assertEqual(recorded_requests[0].area_id, "areas/village_square")
        self.assertEqual(recorded_requests[0].entry_id, "startup")

    def test_change_area_command_queues_transfer_and_camera_request(self) -> None:
        recorded_requests: list[AreaTransitionRequest] = []
        registry = CommandRegistry()
        register_builtin_commands(registry)
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        context = CommandContext(
            area=_minimal_runtime_area(),
            world=world,
            collision_system=None,  # type: ignore[arg-type]
            movement_system=None,  # type: ignore[arg-type]
            interaction_system=None,  # type: ignore[arg-type]
            animation_system=None,  # type: ignore[arg-type]
            request_area_change=recorded_requests.append,
        )

        handle = execute_command_spec(
            registry,
            context,
            {
                "type": "change_area",
                "area_id": "areas/village_house",
                "entry_id": "from_square",
                "transfer_entity_ids": ["$ref_ids.instigator"],
                "camera_follow": {
                    "mode": "entity",
                    "entity_id": "$ref_ids.instigator",
                    "offset_x": 12,
                    "offset_y": -8,
                },
            },
            base_params={"entity_refs": {"instigator": "player"}},
        )
        handle.update(0.0)

        self.assertEqual(len(recorded_requests), 1)
        request = recorded_requests[0]
        self.assertEqual(request.area_id, "areas/village_house")
        self.assertEqual(request.entry_id, "from_square")
        self.assertEqual(request.transfer_entity_ids, ["player"])
        self.assertIsNotNone(request.camera_follow)
        assert request.camera_follow is not None
        self.assertEqual(request.camera_follow.mode, "entity")
        self.assertEqual(request.camera_follow.entity_id, "player")
        self.assertEqual(request.camera_follow.offset_x, 12.0)
        self.assertEqual(request.camera_follow.offset_y, -8.0)

    def test_asset_manager_requires_project_asset_resolution(self) -> None:
        _, project = self._make_project()
        asset_manager = AssetManager(project)

        with self.assertRaises(FileNotFoundError):
            asset_manager.get_image("assets/project/missing.png")

    def test_sample_pixelbet_font_includes_choice_cursor_glyphs(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame

        pygame.init()
        pygame.display.set_mode((1, 1))
        self.addCleanup(pygame.quit)

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        asset_manager = AssetManager(project)
        text_renderer = TextRenderer(asset_manager)

        font = text_renderer.get_font("pixelbet")

        self.assertIn(">", font.glyphs)
        self.assertIn("<", font.glyphs)
        self.assertGreater(text_renderer.measure_text("><", font_id="pixelbet")[0], 0)

    def test_sample_debug_controller_routes_pause_step_and_zoom_actions(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        pygame.init()
        pygame.display.set_mode((1, 1))
        self.addCleanup(pygame.quit)

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        title_area_path = project.resolve_area_reference("areas/title_screen")
        assert title_area_path is not None
        game = Game(area_path=title_area_path, project=project)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        self.assertFalse(game.simulation_paused)
        base_scale = game.output_scale
        base_tick_count = game.simulation_tick_count

        self.assertTrue(
            game._run_play_frame(
                1 / 60,
                [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_F6})],
            )
        )
        self.assertTrue(game.simulation_paused)

        paused_tick_count = game.simulation_tick_count
        self.assertTrue(
            game._run_play_frame(
                1 / 60,
                [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_F7})],
            )
        )
        self.assertTrue(game.simulation_paused)
        self.assertEqual(game.simulation_tick_count, paused_tick_count + 1)

        self.assertTrue(
            game._run_play_frame(
                1 / 60,
                [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RIGHTBRACKET})],
            )
        )
        self.assertGreaterEqual(game.output_scale, base_scale)

        self.assertTrue(
            game._run_play_frame(
                1 / 60,
                [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_F6})],
            )
        )
        self.assertFalse(game.simulation_paused)
        self.assertGreater(game.simulation_tick_count, base_tick_count)

    def test_sample_escape_without_menu_target_no_longer_quits(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        pygame.init()
        pygame.display.set_mode((1, 1))
        self.addCleanup(pygame.quit)

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        title_area_path = project.resolve_area_reference("areas/title_screen")
        assert title_area_path is not None
        game = Game(area_path=title_area_path, project=project)

        game.world.route_inputs_to_entity(None, actions=["menu"])

        still_running = game._run_play_frame(
            1 / 60,
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})],
        )

        self.assertTrue(still_running)

    def test_save_data_ignores_removed_legacy_session_fields(self) -> None:
        save_data = save_data_from_dict(
            {
                "active_entity": "legacy_player",
                "session": {
                    "current_area_path": "legacy/room",
                    "active_entity_id": "legacy_player",
                }
            }
        )

        self.assertEqual(save_data.current_area, "")
        self.assertIsNone(save_data.current_input_targets)

    def test_game_new_game_resets_session_state(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        _, project = self._make_project(
            startup_area="areas/title_screen",
            areas={
                "title_screen.json": {
                    "name": "Title",
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [
                        {
                            "name": "ground",
                            "render_order": 0,
                            "grid": [[0]],
                        }
                    ],
                    "cell_flags": [[True]],
                    "entities": [
                        {
                            "id": "player",
                            "kind": "player",
                            "x": 0,
                            "y": 0,
                        }
                    ],
                },
                "village_square.json": {
                    "name": "Village Square",
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [
                        {
                            "name": "ground",
                            "render_order": 0,
                            "grid": [[0]],
                        }
                    ],
                    "cell_flags": [[True]],
                    "entities": [
                        {
                            "id": "player",
                            "kind": "player",
                            "x": 0,
                            "y": 0,
                        }
                    ],
                },
            },
        )

        title_area_path = project.resolve_area_reference("areas/title_screen")
        assert title_area_path is not None
        game = Game(area_path=title_area_path, project=project)
        self.addCleanup(pygame.quit)

        save_path = project.project_root / "saves" / "slot_1.json"
        game.persistence_runtime.save_data.globals["seen_intro"] = True
        game.persistence_runtime.set_save_path(save_path)
        game.request_new_game(AreaTransitionRequest(area_id="areas/village_square"))
        game._apply_pending_new_game_if_idle()

        self.assertEqual(game.area.area_id, "areas/village_square")
        self.assertEqual(game.persistence_runtime.save_data.globals, {})
        self.assertIsNone(game.persistence_runtime.save_path)
        self.assertIsNone(game.persistence_runtime.save_data.current_input_targets)

    def test_title_screen_dialogue_accepts_direction_and_confirm_input(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        title_area_path = project.resolve_area_reference("areas/title_screen")
        assert title_area_path is not None

        game = Game(area_path=title_area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        controller = game.world.get_entity("dialogue_controller")
        assert controller is not None
        self.assertTrue(controller.variables["dialogue_open"])
        self.assertEqual(controller.variables["dialogue_choice_index"], 0)

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN)])
        game._advance_simulation_tick(1 / 60)

        self.assertEqual(controller.variables["dialogue_choice_index"], 1)

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP)])
        game._advance_simulation_tick(1 / 60)

        self.assertEqual(controller.variables["dialogue_choice_index"], 0)

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)])
        for _ in range(6):
            game._advance_simulation_tick(1 / 60)

        self.assertEqual(game.area.area_id, "areas/village_square")
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_title_screen_dialogue_held_direction_repeats_after_delay(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        title_area_path = project.resolve_area_reference("areas/title_screen")
        assert title_area_path is not None

        game = Game(area_path=title_area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        controller = game.world.get_entity("dialogue_controller")
        assert controller is not None
        self.assertEqual(controller.variables["dialogue_choice_index"], 0)

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN)])
        game._advance_simulation_tick(1 / 60)
        self.assertEqual(controller.variables["dialogue_choice_index"], 1)

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN)])
        game._advance_simulation_tick(1 / 60)
        self.assertEqual(controller.variables["dialogue_choice_index"], 1)

        for _ in range(5):
            game._advance_simulation_tick(1 / 60)
        self.assertEqual(controller.variables["dialogue_choice_index"], 1)

        for _ in range(7):
            game._advance_simulation_tick(1 / 60)
        self.assertEqual(controller.variables["dialogue_choice_index"], 2)

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYUP, key=pygame.K_DOWN)])
        for _ in range(10):
            game._advance_simulation_tick(1 / 60)
        self.assertEqual(controller.variables["dialogue_choice_index"], 2)

    def test_sample_player_held_direction_chains_movement_without_extra_pause(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = (
            Path(__file__).resolve().parents[1]
            / "projects"
            / "physics_contract_demo"
            / "project.json"
        )
        project = load_project(project_path)
        area_path = project.resolve_area_reference("areas/physics_contract_demo")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        player = game.world.get_entity("player")
        assert player is not None
        start_grid_x = player.grid_x

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT)])
        max_root_handles = 0
        for _ in range(32):
            game._advance_simulation_tick(1 / 60)
            max_root_handles = max(max_root_handles, len(game.command_runner.root_handles))

        self.assertGreaterEqual(player.grid_x, start_grid_x + 3)
        self.assertLessEqual(max_root_handles, 1)
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_sample_player_held_direction_keeps_walk_animation_active_across_steps(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = (
            Path(__file__).resolve().parents[1]
            / "projects"
            / "physics_contract_demo"
            / "project.json"
        )
        project = load_project(project_path)
        area_path = project.resolve_area_reference("areas/physics_contract_demo")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        player = game.world.get_entity("player")
        assert player is not None
        visual = player.require_visual("body")

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT)])
        for _ in range(20):
            game._advance_simulation_tick(1 / 60)

        self.assertTrue(player.movement_state.active)
        self.assertTrue(visual.animation_playback.active)
        self.assertIn(visual.current_frame, {6, 7, 8})
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_sample_player_position_snapshots_stay_lightweight(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = (
            Path(__file__).resolve().parents[1]
            / "projects"
            / "physics_contract_demo"
            / "project.json"
        )
        project = load_project(project_path)
        area_path = project.resolve_area_reference("areas/physics_contract_demo")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        player = game.world.get_entity("player")
        assert player is not None

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT)])
        game._advance_simulation_tick(1 / 60)

        move_self_position = player.variables["move_self_position"]
        self.assertEqual(
            set(move_self_position.keys()),
            {"grid_x", "grid_y", "pixel_x", "pixel_y"},
        )

        while player.movement_state.active:
            game._advance_simulation_tick(1 / 60)

        walk_cleanup_position = player.variables["walk_cleanup_position"]
        self.assertEqual(
            set(walk_cleanup_position.keys()),
            {"grid_x", "grid_y", "pixel_x", "pixel_y"},
        )
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_sample_player_repeated_direction_input_during_walk_does_not_raise_cycle_error(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = (
            Path(__file__).resolve().parents[1]
            / "projects"
            / "physics_contract_demo"
            / "project.json"
        )
        project = load_project(project_path)
        area_path = project.resolve_area_reference("areas/physics_contract_demo")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        player = game.world.get_entity("player")
        assert player is not None

        selected_event_id: str | None = None
        for event_id, delta_x, delta_y in (
            ("move_right", 1, 0),
            ("move_left", -1, 0),
            ("move_down", 0, 1),
            ("move_up", 0, -1),
        ):
            target_x = player.grid_x + delta_x
            target_y = player.grid_y + delta_y
            if not game.area.in_bounds(target_x, target_y):
                continue
            cell_flags = game.area.cell_flags_at(target_x, target_y)
            if game.area.is_blocked(target_x, target_y):
                continue
            blocking_entities = [
                entity
                for entity in game.world.get_entities_at(
                    target_x,
                    target_y,
                    exclude_entity_id="player",
                    include_hidden=True,
                )
                if entity.is_effectively_solid()
            ]
            if blocking_entities:
                continue
            selected_event_id = event_id
            break

        self.assertIsNotNone(selected_event_id)

        game.command_runner.enqueue(
            "run_entity_command",
            entity_id="player",
            command_id=selected_event_id,
        )
        game._advance_simulation_tick(1 / 60)
        self.assertTrue(player.movement_state.active)

        for _ in range(4):
            game.command_runner.enqueue(
                "run_entity_command",
                entity_id="player",
                command_id=selected_event_id,
            )
            game._advance_simulation_tick(1 / 60)

        for _ in range(24):
            game._advance_simulation_tick(1 / 60)

        self.assertIsNone(game.command_runner.last_error_notice)

    def test_sample_player_opposite_direction_during_walk_does_not_flip_mid_step(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = (
            Path(__file__).resolve().parents[1]
            / "projects"
            / "physics_contract_demo"
            / "project.json"
        )
        project = load_project(project_path)
        area_path = project.resolve_area_reference("areas/physics_contract_demo")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        player = game.world.get_entity("player")
        assert player is not None

        game.command_runner.enqueue(
            "run_entity_command",
            entity_id="player",
            command_id="move_right",
        )
        game._advance_simulation_tick(1 / 60)

        visual = player.require_visual("body")
        self.assertTrue(player.movement_state.active)
        self.assertTrue(visual.flip_x)

        game.command_runner.enqueue(
            "run_entity_command",
            entity_id="player",
            command_id="move_left",
        )
        game._advance_simulation_tick(1 / 60)

        self.assertTrue(player.movement_state.active)
        self.assertTrue(visual.flip_x)
        self.assertEqual(player.get_effective_facing(), "right")
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_sample_push_block_does_not_move_into_blocked_cells(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = (
            Path(__file__).resolve().parents[1]
            / "projects"
            / "physics_contract_demo"
            / "project.json"
        )
        project = load_project(project_path)
        area_path = project.resolve_area_reference("areas/physics_contract_demo")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        block = game.world.get_entity("house_block")
        assert block is not None

        game.movement_system.set_grid_position("house_block", 5, 2)
        game.movement_system.set_pixel_position(
            "house_block",
            5 * game.area.tile_size,
            2 * game.area.tile_size,
        )

        game.command_runner.enqueue(
            "run_entity_command",
            entity_id="house_block",
            command_id="push_from_left",
        )
        game._advance_simulation_tick(1 / 60)

        self.assertEqual((block.grid_x, block.grid_y), (5, 2))
        self.assertEqual(
            (block.pixel_x, block.pixel_y),
            (5 * game.area.tile_size, 2 * game.area.tile_size),
        )
        self.assertFalse(block.movement_state.active)
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_demo_dialogue_runtime_intercepts_input_and_runs_inline_choice_commands(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = (
            Path(__file__).resolve().parents[1]
            / "projects"
            / "physics_contract_demo"
            / "project.json"
        )
        project = load_project(project_path)
        area_path = project.resolve_area_reference("areas/physics_contract_demo")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        player = game.world.get_entity("player")
        indicator = game.world.get_entity("occupancy_indicator")
        assert player is not None
        assert indicator is not None

        game.movement_system.set_grid_position("player", 4, 4)
        game.movement_system.set_pixel_position(
            "player",
            4 * game.area.tile_size,
            4 * game.area.tile_size,
        )
        player.set_facing_value("right")

        self.assertFalse(indicator.visible)

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)])
        game._advance_simulation_tick(1 / 60)

        self.assertIsNotNone(game.dialogue_runtime)
        assert game.dialogue_runtime is not None
        self.assertTrue(game.dialogue_runtime.is_active())
        self.assertEqual((player.grid_x, player.grid_y), (4, 4))

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT)])
        game._advance_simulation_tick(1 / 60)
        self.assertEqual((player.grid_x, player.grid_y), (4, 4))
        game.input_handler.handle_events([pygame.event.Event(pygame.KEYUP, key=pygame.K_LEFT)])

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)])
        game._advance_simulation_tick(1 / 60)

        session = game.dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.segment_index, 1)
        self.assertEqual(session.choice_index, 0)

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN)])
        game._advance_simulation_tick(1 / 60)
        session = game.dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.choice_index, 1)
        self.assertEqual((player.grid_x, player.grid_y), (4, 4))
        game.input_handler.handle_events([pygame.event.Event(pygame.KEYUP, key=pygame.K_DOWN)])

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP)])
        game._advance_simulation_tick(1 / 60)
        session = game.dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.choice_index, 0)
        game.input_handler.handle_events([pygame.event.Event(pygame.KEYUP, key=pygame.K_UP)])

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)])
        game._advance_simulation_tick(1 / 60)

        self.assertFalse(game.dialogue_runtime.is_active())
        self.assertTrue(indicator.visible)
        self.assertEqual((player.grid_x, player.grid_y), (4, 4))
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_dialogue_choice_window_scrolls_after_three_visible_rows(self) -> None:
        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        controller = instantiate_entity(
            {
                "id": "dialogue_controller",
                "template": "entity_templates/dialogue_panel",
                "space": "screen",
                "scope": "global",
            },
            16,
            project=project,
            source_name="test dialogue controller",
        )
        controller.variables["dialogue_phase"] = "choice"
        controller.variables["dialogue_font_id"] = "pixelbet"
        controller.variables["choice_width"] = controller.variables["layout"]["choice"]["plain"]["width"]
        controller.variables["choice_cursor_x"] = controller.variables["layout"]["choice"]["plain"]["x"]
        controller.variables["dialogue_current_segment_options"] = [
            {"text": "One"},
            {"text": "Two"},
            {"text": "Three"},
            {"text": "Four"},
            {"text": "Five"},
        ]
        controller.variables["dialogue_current_option_count"] = 5
        controller.variables["dialogue_choice_index"] = 0
        controller.variables["dialogue_choice_scroll_offset"] = 0

        world = World()
        world.add_entity(controller)
        registry, context = self._make_command_context(project=project, world=world)
        context.screen_manager = ScreenElementManager()

        def _run_named(command_id: str, **params: object) -> None:
            handle = execute_registered_command(
                registry,
                context,
                "run_project_command",
                {
                    "command_id": command_id,
                    "source_entity_id": "dialogue_controller",
                    **params,
                },
            )
            while not handle.complete:
                handle.update(0.0)

        _run_named("commands/dialogue/render_choice")

        option_0 = context.screen_manager.get_element("dialogue_option_0")
        option_1 = context.screen_manager.get_element("dialogue_option_1")
        option_2 = context.screen_manager.get_element("dialogue_option_2")
        assert option_0 is not None
        assert option_1 is not None
        assert option_2 is not None
        self.assertEqual(option_0.text, ">One")
        self.assertEqual(option_1.text, " Two")
        self.assertEqual(option_2.text, " Three")

        _run_named("commands/dialogue/move_selection", delta=1)
        _run_named("commands/dialogue/move_selection", delta=1)
        _run_named("commands/dialogue/move_selection", delta=1)

        self.assertEqual(controller.variables["dialogue_choice_index"], 3)
        self.assertEqual(controller.variables["dialogue_choice_scroll_offset"], 1)

        option_0 = context.screen_manager.get_element("dialogue_option_0")
        option_1 = context.screen_manager.get_element("dialogue_option_1")
        option_2 = context.screen_manager.get_element("dialogue_option_2")
        assert option_0 is not None
        assert option_1 is not None
        assert option_2 is not None
        self.assertEqual(option_0.text, " Two")
        self.assertEqual(option_1.text, " Three")
        self.assertEqual(option_2.text, ">Four")
        self.assertIsNone(context.screen_manager.get_element("dialogue_cursor"))

    def test_sample_timer_dialogue_segment_advances_without_input(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        area_path = project.resolve_area_reference("areas/village_square")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        controller = game.world.get_entity("dialogue_controller")
        assert controller is not None

        game.command_runner.enqueue(
            "run_entity_command",
            entity_id="dialogue_controller",
            command_id="open_dialogue",
            dialogue_path="dialogues/showcase/village_square_note.json",
            dialogue_on_start=[],
            dialogue_on_end=[],
            segment_hooks=[],
            allow_cancel=False,
            entity_refs={"instigator": "player", "caller": "player"},
        )
        for _ in range(4):
            game._advance_simulation_tick(1 / 60)

        self.assertEqual(controller.variables["dialogue_segment_index"], 0)

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)])
        game._advance_simulation_tick(1 / 60)

        self.assertEqual(controller.variables["dialogue_segment_index"], 1)
        self.assertIn("cool breeze", controller.variables["dialogue_current_visible_text"])

        for _ in range(80):
            game._advance_simulation_tick(1 / 60)

        self.assertEqual(controller.variables["dialogue_segment_index"], 2)
        self.assertIn("Use the save point", controller.variables["dialogue_current_visible_text"])
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_sample_lever_dialogue_segment_hook_uses_stored_caller_context(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        area_path = project.resolve_area_reference("areas/village_house")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        lever = game.world.get_entity("house_lever")
        gate = game.world.get_entity("house_gate")
        controller = game.world.get_entity("dialogue_controller")
        assert lever is not None
        assert gate is not None
        assert controller is not None

        game.command_runner.enqueue(
            "run_entity_command",
            entity_id="house_lever",
            command_id="interact",
            entity_refs={"instigator": "player"},
        )
        for _ in range(4):
            game._advance_simulation_tick(1 / 60)

        self.assertTrue(controller.variables["dialogue_open"])
        self.assertEqual(controller.variables["dialogue_caller_id"], "house_lever")

        for _ in range(2):
            game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)])
            game._advance_simulation_tick(1 / 60)

        for _ in range(4):
            game._advance_simulation_tick(1 / 60)

        self.assertFalse(controller.variables["dialogue_open"])
        self.assertTrue(lever.variables["toggled"])
        self.assertFalse(gate.visible)
        self.assertFalse(gate.is_effectively_solid())
        self.assertEqual(lever.require_visual("main").tint, (150, 150, 150))
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_controller_owned_dialogue_restores_nested_snapshot_and_input_routes(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        area_path = project.resolve_area_reference("areas/village_square")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        controller = game.world.get_entity("dialogue_controller")
        assert controller is not None
        self.assertFalse(controller.variables["dialogue_open"])
        self.assertEqual(game.world.get_input_target_id("interact"), "player")
        self.assertEqual(game.world.get_input_target_id("move_up"), "player")
        self.assertEqual(game.world.get_input_target_id("menu"), "pause_controller")

        game.command_runner.enqueue(
            "run_commands",
            commands=[
                {
                    "type": "run_entity_command",
                    "entity_id": "dialogue_controller",
                    "command_id": "open_dialogue",
                    "dialogue_path": "dialogues/system/title_menu.json",
                    "dialogue_on_start": [],
                    "dialogue_on_end": [],
                    "segment_hooks": [],
                    "allow_cancel": False,
                },
                {
                    "type": "run_entity_command",
                    "entity_id": "dialogue_controller",
                    "command_id": "open_dialogue",
                    "dialogue_path": "dialogues/system/save_prompt.json",
                    "dialogue_on_start": [],
                    "dialogue_on_end": [],
                    "segment_hooks": [],
                    "allow_cancel": True,
                },
            ],
            entity_refs={"instigator": "player", "caller": "lever"},
        )
        for _ in range(6):
            game._advance_simulation_tick(1 / 60)

        self.assertTrue(controller.variables["dialogue_open"])
        self.assertEqual(controller.variables["dialogue_path"], "dialogues/system/save_prompt.json")
        self.assertEqual(controller.variables["dialogue_actor_id"], "player")
        self.assertEqual(controller.variables["dialogue_caller_id"], "lever")
        self.assertEqual(len(controller.variables["dialogue_state_stack"]), 1)
        parent_snapshot = controller.variables["dialogue_state_stack"][0]
        self.assertEqual(parent_snapshot["dialogue_path"], "dialogues/system/title_menu.json")
        self.assertEqual(parent_snapshot["dialogue_on_end"], [])
        self.assertEqual(parent_snapshot["dialogue_segment_hooks"], [])
        self.assertFalse(parent_snapshot["dialogue_allow_cancel"])
        self.assertEqual(parent_snapshot["dialogue_actor_id"], "player")
        self.assertEqual(parent_snapshot["dialogue_caller_id"], "lever")
        self.assertEqual(parent_snapshot["dialogue_segment_index"], 0)
        self.assertEqual(parent_snapshot["dialogue_source_page_index"], 0)
        self.assertEqual(parent_snapshot["dialogue_text_line_offset"], 0)
        self.assertEqual(parent_snapshot["dialogue_choice_index"], 0)
        self.assertIsNone(parent_snapshot["dialogue_current_speaker_id"])
        self.assertIn("segments", parent_snapshot["dialogue_definition"])
        for action in ("interact", "menu", "move_up", "move_down", "move_left", "move_right"):
            self.assertEqual(game.world.get_input_target_id(action), "dialogue_controller")

        game.command_runner.enqueue(
            "run_project_command",
            command_id="commands/dialogue/close_current_dialogue",
            source_entity_id="dialogue_controller",
            entity_refs={"instigator": "player", "caller": "lever"},
        )
        for _ in range(4):
            game._advance_simulation_tick(1 / 60)

        self.assertTrue(controller.variables["dialogue_open"])
        self.assertEqual(controller.variables["dialogue_path"], "dialogues/system/title_menu.json")
        self.assertEqual(controller.variables["dialogue_actor_id"], "player")
        self.assertEqual(controller.variables["dialogue_caller_id"], "lever")
        self.assertEqual(controller.variables["dialogue_state_stack"], [])
        self.assertEqual(game.world.get_input_target_id("interact"), "dialogue_controller")
        self.assertEqual(game.world.get_input_target_id("menu"), "dialogue_controller")

        game.command_runner.enqueue(
            "run_project_command",
            command_id="commands/dialogue/close_current_dialogue",
            source_entity_id="dialogue_controller",
            entity_refs={"instigator": "player", "caller": "lever"},
        )
        for _ in range(4):
            game._advance_simulation_tick(1 / 60)

        self.assertFalse(controller.variables["dialogue_open"])
        self.assertEqual(game.world.get_input_target_id("interact"), "player")
        self.assertEqual(game.world.get_input_target_id("move_up"), "player")
        self.assertEqual(game.world.get_input_target_id("menu"), "pause_controller")
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_save_game_after_returning_inputs_persists_player_input_targets(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        _, project = self._make_project(
            startup_area="areas/room_a",
            global_entities=[
                {
                    "id": "dialogue_controller",
                    "kind": "system",
                    "space": "screen",
                    "visible": False,
                }
            ],
            areas={
                "room_a.json": {
                    "name": "Room A",
                    "tile_size": 16,
                    "input_targets": {
                        "move_up": "player",
                        "move_down": "player",
                        "move_left": "player",
                        "move_right": "player",
                        "interact": "player",
                        "menu": "player",
                    },
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [
                        {
                            "name": "ground",
                            "render_order": 0,
                            "grid": [[0]],
                        }
                    ],
                    "cell_flags": [[True]],
                    "entities": [
                        {
                            "id": "player",
                            "kind": "player",
                            "x": 0,
                            "y": 0,
                        }
                    ],
                }
            },
        )

        area_path = project.resolve_area_reference("areas/room_a")
        assert area_path is not None
        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        save_path = project.project_root / "saves" / "slot_1.json"
        registry = CommandRegistry()
        register_builtin_commands(registry)
        context = CommandContext(
            area=game.area,
            world=game.world,
            collision_system=None,  # type: ignore[arg-type]
            movement_system=None,  # type: ignore[arg-type]
            interaction_system=None,  # type: ignore[arg-type]
            animation_system=None,  # type: ignore[arg-type]
            project=project,
            persistence_runtime=game.persistence_runtime,
            save_game=game.save_game,
        )

        handle = SequenceCommandHandle(
            registry,
            context,
            [
                {"type": "push_input_routes"},
                {"type": "route_inputs_to_entity", "entity_id": "dialogue_controller"},
                {"type": "pop_input_routes"},
                {"type": "save_game", "save_path": str(save_path)},
            ],
            base_params={"entity_refs": {"instigator": "player"}},
        )

        self.assertTrue(handle.complete)
        for action in ("interact", "menu", "move_up", "move_down", "move_left", "move_right"):
            self.assertEqual(game.world.get_input_target_id(action), "player")

        save_payload = json.loads(save_path.read_text(encoding="utf-8"))
        restored_save_data = save_data_from_dict(save_payload)

        self.assertNotIn("active_entity", save_payload)
        self.assertNotIn("input_route_stack", save_payload)
        self.assertIsNotNone(restored_save_data.current_input_targets)
        assert restored_save_data.current_input_targets is not None
        self.assertTrue(
            all(
                restored_save_data.current_input_targets.get(action) == "player"
                for action in ("interact", "menu", "move_up", "move_down", "move_left", "move_right")
            )
        )

    def test_load_game_restores_saved_input_targets(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        _, project = self._make_project(
            startup_area="areas/room_a",
            global_entities=[
                {
                    "id": "dialogue_controller",
                    "kind": "system",
                    "space": "screen",
                    "visible": False,
                }
            ],
            areas={
                "room_a.json": {
                    "name": "Room A",
                    "tile_size": 16,
                    "input_targets": {
                        "move_up": "player",
                        "move_down": "player",
                        "move_left": "player",
                        "move_right": "player",
                        "interact": "player",
                        "menu": "player",
                    },
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [
                        {
                            "name": "ground",
                            "render_order": 0,
                            "grid": [[0]],
                        }
                    ],
                    "cell_flags": [[True]],
                    "entities": [
                        {
                            "id": "player",
                            "kind": "player",
                            "x": 0,
                            "y": 0,
                        }
                    ],
                }
            },
        )

        area_path = project.resolve_area_reference("areas/room_a")
        assert area_path is not None
        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        save_path = project.project_root / "saves" / "slot_1.json"
        game.world.push_input_routes()
        game.world.route_inputs_to_entity("dialogue_controller")
        game._write_save_slot(save_path)
        game.world.pop_input_routes()

        self.assertEqual(game.world.get_input_target_id("interact"), "player")

        game._load_save_slot(save_path)

        for action in game.world.list_input_actions():
            self.assertEqual(game.world.get_input_target_id(action), "dialogue_controller")
        self.assertEqual(game.world.input_route_stack, [])
        with self.assertRaises(ValueError):
            game.world.pop_input_routes()

    def test_current_area_state_preserves_current_frame(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "player",
                            "kind": "player",
                            "x": 0,
                            "y": 0,
                            "visuals": [
                                {
                                    "id": "body",
                                    "path": "assets/project/sprites/player.png",
                                    "frame_width": 16,
                                    "frame_height": 16,
                                    "frames": [0, 1, 2],
                                }
                            ],
                        }
                    ],
                }
            }
        )

        authored_area_data = {
            **_minimal_area(),
            "entities": [
                {
                    "id": "player",
                    "kind": "player",
                    "x": 0,
                    "y": 0,
                    "visuals": [
                        {
                            "id": "body",
                            "path": "assets/project/sprites/player.png",
                            "frame_width": 16,
                            "frame_height": 16,
                            "frames": [0, 1, 2],
                        }
                    ],
                }
            ],
        }

        area, authored_world = load_area_from_data(
            authored_area_data,
            source_name="<memory>",
            project=project,
        )
        _, current_world = load_area_from_data(
            authored_area_data,
            source_name="<memory>",
            project=project,
        )
        current_player = current_world.get_entity("player")
        assert current_player is not None
        current_visual = current_player.get_primary_visual()
        assert current_visual is not None
        current_player.set_facing_value("right")
        current_visual.current_frame = 2

        current_area_state = capture_current_area_state(
            area,
            authored_world,
            current_world,
            project=project,
        )
        self.assertIsNotNone(current_area_state)

        _, restored_world = load_area_from_data(
            authored_area_data,
            source_name="<memory>",
            project=project,
        )
        apply_persistent_area_state(area, restored_world, current_area_state, project=project)  # type: ignore[arg-type]

        restored_player = restored_world.get_entity("player")
        assert restored_player is not None
        restored_visual = restored_player.get_primary_visual()
        assert restored_visual is not None
        self.assertEqual(restored_player.get_effective_facing(), "right")
        self.assertEqual(restored_visual.current_frame, 2)

    def test_runtime_token_lookup_rejects_removed_source_alias(self) -> None:
        context = CommandContext(
            area=Area(
                area_id="areas/test_room",
                name="Test Room",
                tile_size=16,
                tilesets=[],
                tile_layers=[],
                cell_flags=[],
            ),
            world=World(),
            collision_system=None,  # type: ignore[arg-type]
            movement_system=None,  # type: ignore[arg-type]
            interaction_system=None,  # type: ignore[arg-type]
            animation_system=None,  # type: ignore[arg-type]
        )

        with self.assertRaises(KeyError):
            _resolve_runtime_values(
                "$source.some_flag",
                context,
                {"source_entity_id": "player"},
            )


    def test_run_entity_command_propagates_named_entity_refs(self) -> None:
        _, project = self._make_project()
        caller = _make_runtime_entity("lever", kind="lever")
        controller = _make_runtime_entity(
            "dialogue_controller",
            kind="system",
            space="screen",
            scope="global",
            entity_commands={
                "open_dialogue": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$ref_ids.caller",
                            "name": "toggled",
                            "value": True,
                        }
                    ]
                )
            },
        )
        world = World()
        world.add_entity(caller)
        world.add_entity(controller)
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "run_entity_command",
            {
                "entity_id": "dialogue_controller",
                "command_id": "open_dialogue",
                "entity_refs": {
                    "instigator": "lever",
                    "caller": "lever",
                },
            },
        )
        handle.update(0.0)

        self.assertTrue(world.get_entity("lever").variables["toggled"])  # type: ignore[index]

    def test_run_project_command_propagates_named_entity_refs(self) -> None:
        _, project = self._make_project(
            commands={
                "toggle_caller.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "set_entity_var",
                            "entity_id": "$ref_ids.caller",
                            "name": "toggled",
                            "value": True,
                        }
                    ],
                }
            }
        )
        caller = _make_runtime_entity("lever", kind="lever")
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "run_project_command",
            {
                "command_id": "commands/toggle_caller",
                "entity_refs": {
                    "instigator": "lever",
                    "caller": "lever",
                },
            },
        )
        handle.update(0.0)

        self.assertTrue(world.get_entity("lever").variables["toggled"])  # type: ignore[index]

    def test_run_commands_propagates_named_entity_refs(self) -> None:
        _, project = self._make_project()
        caller = _make_runtime_entity("lever", kind="lever")
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "run_commands",
            {
                "commands": [
                    {
                        "type": "set_entity_var",
                        "entity_id": "$ref_ids.caller",
                        "name": "toggled",
                        "value": True,
                    }
                ],
                "entity_refs": {
                    "caller": "lever",
                },
            },
        )
        handle.update(0.0)

        self.assertTrue(world.get_entity("lever").variables["toggled"])  # type: ignore[index]

    def test_root_flows_run_independently_by_default(self) -> None:
        world = World()
        registry, context = self._make_command_context(world=world)
        runner = CommandRunner(registry, context)

        runner.enqueue(
            "run_commands",
            commands=[
                {"type": "wait_frames", "frames": 1},
                {"type": "set_current_area_var", "name": "first_done", "value": True},
            ],
        )
        runner.enqueue(
            "run_commands",
            commands=[
                {"type": "wait_frames", "frames": 1},
                {"type": "set_current_area_var", "name": "second_done", "value": True},
            ],
        )

        runner.update(1 / 60)

        self.assertTrue(world.variables["first_done"])
        self.assertTrue(world.variables["second_done"])
        self.assertFalse(runner.has_pending_work())

    def test_spawn_flow_returns_immediately_inside_run_commands(self) -> None:
        world = World()
        registry, context = self._make_command_context(world=world)
        runner = CommandRunner(registry, context)

        runner.enqueue(
            "run_commands",
            commands=[
                {
                    "type": "spawn_flow",
                    "commands": [
                        {"type": "wait_frames", "frames": 1},
                        {"type": "set_current_area_var", "name": "later", "value": True},
                    ],
                },
                {"type": "set_current_area_var", "name": "now", "value": True},
            ],
        )

        runner.update(0.0)
        self.assertTrue(world.variables["now"])
        self.assertNotIn("later", world.variables)
        self.assertTrue(runner.has_pending_work())

        runner.update(1 / 60)
        self.assertTrue(world.variables["later"])
        self.assertFalse(runner.has_pending_work())

    def test_run_parallel_can_wait_for_one_child_and_let_others_continue(self) -> None:
        world = World()
        registry, context = self._make_command_context(world=world)
        runner = CommandRunner(registry, context)

        runner.enqueue(
            "run_commands",
            commands=[
                {
                    "type": "run_parallel",
                    "completion": {
                        "mode": "child",
                        "child_id": "fast",
                        "remaining": "keep_running",
                    },
                    "commands": [
                        {
                            "id": "fast",
                            "type": "wait_frames",
                            "frames": 1,
                        },
                        {
                            "id": "slow",
                            "type": "run_commands",
                            "commands": [
                                {"type": "wait_frames", "frames": 2},
                                {"type": "set_current_area_var", "name": "slow_done", "value": True},
                            ],
                        },
                    ],
                },
                {"type": "set_current_area_var", "name": "after_fast", "value": True},
            ],
        )

        runner.update(1 / 60)
        self.assertTrue(world.variables["after_fast"])
        self.assertNotIn("slow_done", world.variables)
        self.assertTrue(runner.has_pending_work())

        runner.update(1 / 60)
        self.assertTrue(world.variables["slow_done"])
        self.assertFalse(runner.has_pending_work())

    def test_set_entity_field_supports_named_ref_via_run_commands(self) -> None:
        _, project = self._make_project()
        caller = _make_runtime_entity("lever", kind="lever", with_visual=True)
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "run_commands",
            {
                "entity_refs": {
                    "caller": "lever",
                },
                "commands": [
                    {
                        "type": "set_entity_field",
                        "entity_id": "$ref_ids.caller",
                        "field_name": "visuals.main.tint",
                        "value": [5, 6, 7],
                    }
                ],
            },
        )
        handle.update(0.0)

        caller_visual = world.get_entity("lever").require_visual("main")  # type: ignore[union-attr]
        self.assertEqual(caller_visual.tint, (5, 6, 7))

    def test_route_inputs_to_entity_command_supports_instigator_ref_via_run_commands(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(
            _make_runtime_entity(
                "dialogue_controller",
                kind="system",
                space="screen",
                scope="global",
            )
        )
        world.route_inputs_to_entity("dialogue_controller")
        registry, context = self._make_command_context(world=world)

        handle = execute_registered_command(
            registry,
            context,
            "run_commands",
            {
                "entity_refs": {
                    "instigator": "player",
                },
                "commands": [
                    {
                        "type": "route_inputs_to_entity",
                        "entity_id": "$ref_ids.instigator",
                    }
                ],
            },
        )
        handle.update(0.0)

        for action in world.list_input_actions():
            self.assertEqual(world.get_input_target_id(action), "player")

    def test_set_input_target_routes_one_action_without_affecting_others(self) -> None:
        world = World(
            default_input_targets={"interact": "player"},
        )
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(
            _make_runtime_entity(
                "dialogue_controller",
                kind="system",
                space="screen",
                scope="global",
            )
        )
        registry, context = self._make_command_context(world=world)

        handle = execute_registered_command(
            registry,
            context,
            "set_input_target",
            {
                "action": "menu",
                "entity_id": "dialogue_controller",
            },
        )
        handle.update(0.0)

        self.assertEqual(world.get_input_target_id("menu"), "dialogue_controller")
        self.assertEqual(world.get_input_target_id("interact"), "player")

    def test_audio_commands_forward_parameters_to_audio_player(self) -> None:
        registry, context = self._make_command_context()
        audio_player = _RecordingAudioPlayer()
        context.audio_player = audio_player

        execute_registered_command(
            registry,
            context,
            "play_audio",
            {"path": "assets/project/sfx/click.wav", "volume": 0.25},
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_sound_volume",
            {"volume": 0.5},
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "play_music",
            {
                "path": "assets/project/music/field.ogg",
                "loop": False,
                "volume": 0.8,
                "restart_if_same": True,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "pause_music",
            {},
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "resume_music",
            {},
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_music_volume",
            {"volume": 0.6},
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "stop_music",
            {"fade_seconds": 1.25},
        ).update(0.0)

        self.assertEqual(
            audio_player.calls,
            [
                ("play_audio", ("assets/project/sfx/click.wav",), {"volume": 0.25}),
                ("set_sound_volume", (0.5,), {}),
                (
                    "play_music",
                    ("assets/project/music/field.ogg",),
                    {"loop": False, "volume": 0.8, "restart_if_same": True},
                ),
                ("pause_music", (), {}),
                ("resume_music", (), {}),
                ("set_music_volume", (0.6,), {}),
                ("stop_music", (), {"fade_seconds": 1.25}),
            ],
        )

    def test_audio_player_supports_sound_volume_and_music_track_control(self) -> None:
        fake_channel = _FakeAudioChannel()
        fake_sound = _FakeSound(fake_channel)
        fake_music = _FakeMusicController()
        asset_manager = _FakeAudioAssetManager(sound=fake_sound, music_path="C:/tmp/field.ogg")
        expected_music_path = str(Path("C:/tmp/field.ogg"))

        with patch("pygame.mixer.get_init", return_value=(44100, -16, 2)):
            with patch("pygame.mixer.music", fake_music):
                player = AudioPlayer(asset_manager, enabled=True)
                player.set_sound_volume(0.5)

                self.assertTrue(player.play_audio("assets/project/sfx/click.wav", volume=0.6))
                self.assertEqual(asset_manager.requested_sound_paths, ["assets/project/sfx/click.wav"])
                self.assertEqual(fake_sound.play_calls, 1)
                self.assertAlmostEqual(fake_channel.volume or 0.0, 0.3)

                self.assertTrue(player.play_music("assets/project/music/field.ogg", volume=0.7))
                self.assertEqual(asset_manager.requested_asset_paths, ["assets/project/music/field.ogg"])
                self.assertEqual(fake_music.loaded_paths, [expected_music_path])
                self.assertEqual(fake_music.play_calls, [-1])
                self.assertAlmostEqual(player.music_volume, 0.7)
                self.assertEqual(player.current_music_path, expected_music_path)

                self.assertTrue(player.play_music("assets/project/music/field.ogg"))
                self.assertEqual(fake_music.loaded_paths, [expected_music_path])

                self.assertTrue(player.pause_music())
                self.assertTrue(player.music_paused)
                self.assertEqual(fake_music.pause_calls, 1)

                self.assertTrue(player.resume_music())
                self.assertFalse(player.music_paused)
                self.assertEqual(fake_music.unpause_calls, 1)

                player.set_music_volume(0.4)
                self.assertAlmostEqual(player.music_volume, 0.4)
                self.assertAlmostEqual(fake_music.volume_calls[-1], 0.4)

                self.assertTrue(player.stop_music(fade_seconds=0.5))
                self.assertEqual(fake_music.fadeout_calls, [500])
                self.assertIsNone(player.current_music_path)

    def test_strict_entity_primitives_reject_raw_symbolic_entity_refs(self) -> None:
        world = World(default_input_targets={"interact": "player"})
        world.add_entity(_make_runtime_entity("player", kind="player", with_visual=True))
        registry, context = self._make_command_context(world=world)
        context.camera = _RecordingCamera()

        for command_name, params in (
            (
                "set_entity_field",
                {
                    "entity_id": "self",
                    "field_name": "visible",
                    "value": False,
                },
            ),
            (
                "set_entity_fields",
                {
                    "entity_id": "self",
                    "set": {
                        "fields": {
                            "visible": False,
                        }
                    },
                },
            ),
            (
                "set_input_target",
                {
                    "action": "interact",
                    "entity_id": "self",
                },
            ),
            (
                "set_entity_command_enabled",
                {
                    "entity_id": "self",
                    "command_id": "interact",
                    "enabled": False,
                },
            ),
            (
                "set_camera_follow",
                {
                    "follow": {
                        "mode": "entity",
                        "entity_id": "self",
                    },
                },
            ),
            (
                "set_visual_frame",
                {
                    "entity_id": "self",
                    "frame": 2,
                },
            ),
            (
                "move_entity_world_position",
                {
                    "entity_id": "self",
                    "x": 16,
                    "y": 0,
                    "mode": "relative",
                },
            ),
        ):
            with self.subTest(command_name=command_name):
                with self.assertRaises(CommandExecutionError) as raised:
                    execute_registered_command(registry, context, command_name, params)
                self.assertIsNotNone(raised.exception.__cause__)
                self.assertIn("use '$self_id' or '$ref_ids.<name>'", str(raised.exception.__cause__))

    def test_push_and_pop_input_routes_restore_nested_snapshots(self) -> None:
        world = World(
            default_input_targets={
                "move_up": "player",
                "move_down": "player",
                "move_left": "player",
                "move_right": "player",
                "interact": "player",
                "menu": "pause_controller",
            },
        )
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(
            _make_runtime_entity(
                "pause_controller",
                kind="system",
                space="screen",
                scope="global",
            )
        )
        world.add_entity(
            _make_runtime_entity(
                "dialogue_controller",
                kind="system",
                space="screen",
                scope="global",
            )
        )
        world.add_entity(
            _make_runtime_entity(
                "save_controller",
                kind="system",
                space="screen",
                scope="global",
            )
        )

        self.assertEqual(world.get_input_target_id("move_up"), "player")
        self.assertEqual(world.get_input_target_id("menu"), "pause_controller")

        world.push_input_routes()
        world.route_inputs_to_entity("dialogue_controller")
        for action in world.list_input_actions():
            self.assertEqual(world.get_input_target_id(action), "dialogue_controller")

        world.push_input_routes(actions=["interact", "menu"])
        world.route_inputs_to_entity("save_controller", actions=["interact", "menu"])

        self.assertEqual(world.get_input_target_id("interact"), "save_controller")
        self.assertEqual(world.get_input_target_id("menu"), "save_controller")
        self.assertEqual(world.get_input_target_id("move_up"), "dialogue_controller")

        world.pop_input_routes()

        for action in world.list_input_actions():
            self.assertEqual(world.get_input_target_id(action), "dialogue_controller")

        world.pop_input_routes()

        self.assertEqual(world.get_input_target_id("move_up"), "player")
        self.assertEqual(world.get_input_target_id("interact"), "player")
        self.assertEqual(world.get_input_target_id("menu"), "pause_controller")

    def test_pop_input_routes_command_rejects_empty_stack(self) -> None:
        registry, context = self._make_command_context()

        with self.assertRaises(CommandExecutionError):
            execute_registered_command(
                registry,
                context,
                "pop_input_routes",
                {},
            )

    def test_animation_commands_accept_visual_id_and_named_ref_via_run_commands(self) -> None:
        _, project = self._make_project()
        caller = _make_runtime_entity("lever", kind="lever", with_visual=True)
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)
        animation_system = _RecordingAnimationSystem()
        context.animation_system = animation_system

        play_handle = execute_registered_command(
            registry,
            context,
            "run_commands",
            {
                "entity_refs": {
                    "caller": "lever",
                },
                "commands": [
                    {
                        "type": "play_animation",
                        "entity_id": "$ref_ids.caller",
                        "visual_id": "main",
                        "frame_sequence": [1, 2, 3],
                        "frames_per_sprite_change": 2,
                        "hold_last_frame": False,
                        "wait": False,
                    }
                ],
            },
        )
        play_handle.update(0.0)

        wait_handle = execute_registered_command(
            registry,
            context,
            "run_commands",
            {
                "entity_refs": {
                    "caller": "lever",
                },
                "commands": [
                    {
                        "type": "wait_for_animation",
                        "entity_id": "$ref_ids.caller",
                        "visual_id": "main",
                    }
                ],
            },
        )
        wait_handle.update(0.0)

        self.assertEqual(
            animation_system.started,
            [("lever", [1, 2, 3], "main", 2, False)],
        )
        self.assertEqual(animation_system.queries, [("lever", "main")])

    def test_move_entity_world_position_supports_named_ref_via_run_commands(self) -> None:
        caller = _make_runtime_entity("lever", kind="lever")
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(world=world)
        movement_system = _RecordingMovementSystem()
        context.movement_system = movement_system

        handle = execute_registered_command(
            registry,
            context,
            "run_commands",
            {
                "entity_refs": {
                    "caller": "lever",
                },
                "commands": [
                    {
                        "type": "move_entity_world_position",
                        "entity_id": "$ref_ids.caller",
                        "x": 16,
                        "y": 0,
                        "mode": "relative",
                        "frames_needed": 8,
                        "wait": False,
                    }
                ],
            },
        )
        handle.update(0.0)

        self.assertEqual(
            movement_system.move_by_offsets,
            [("lever", 16.0, 0.0, None, 8, None, "none", None, None)],
        )

    def test_set_camera_follow_supports_named_ref_via_run_commands(self) -> None:
        caller = _make_runtime_entity("lever", kind="lever")
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(world=world)
        camera = _RecordingCamera()
        context.camera = camera

        handle = execute_registered_command(
            registry,
            context,
            "run_commands",
            {
                "entity_refs": {
                    "caller": "lever",
                },
                "commands": [
                    {
                        "type": "set_camera_follow",
                        "follow": {
                            "mode": "entity",
                            "entity_id": "$ref_ids.caller",
                            "offset_x": 4,
                            "offset_y": -2,
                        },
                    }
                ],
            },
        )
        handle.update(0.0)

        self.assertEqual(camera.followed_entity_id, "lever")
        self.assertEqual(camera.follow_offset_x, 4.0)
        self.assertEqual(camera.follow_offset_y, -2.0)
        self.assertEqual(len(camera.update_calls), 1)
        self.assertIs(camera.update_calls[0][0], world)
        self.assertFalse(camera.update_calls[0][1])

    def test_set_camera_follow_tracks_routed_action(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(
            _make_runtime_entity(
                "dialogue_controller",
                kind="system",
                space="screen",
                scope="global",
            )
        )
        world.route_inputs_to_entity("dialogue_controller", actions=["menu"])
        registry, context = self._make_command_context(world=world)
        camera = _RecordingCamera()
        context.camera = camera

        handle = execute_registered_command(
            registry,
            context,
            "set_camera_follow",
            {
                "follow": {
                    "mode": "input_target",
                    "action": "menu",
                }
            },
        )
        handle.update(0.0)

        self.assertEqual(camera.follow_mode, "input_target")
        self.assertEqual(camera.follow_input_action, "menu")
        self.assertEqual(len(camera.update_calls), 1)
        self.assertIs(camera.update_calls[0][0], world)
        self.assertFalse(camera.update_calls[0][1])

    def test_set_camera_state_push_and_pop_restore_previous_camera_policy(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        registry, context = self._make_command_context(world=world)
        camera = _RecordingCamera()
        context.camera = camera

        execute_registered_command(
            registry,
            context,
            "set_camera_state",
            {
                "follow": {
                    "mode": "entity",
                    "entity_id": "player",
                    "offset_x": 3,
                    "offset_y": -1,
                },
                "bounds": {
                    "x": 1,
                    "y": 2,
                    "width": 3,
                    "height": 4,
                    "space": "world_grid",
                },
                "deadzone": {
                    "x": 2,
                    "y": 1,
                    "width": 5,
                    "height": 4,
                    "space": "viewport_grid",
                },
            },
        ).update(0.0)
        execute_registered_command(registry, context, "push_camera_state", {}).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_camera_state",
            {
                "follow": None,
                "bounds": None,
                "deadzone": None,
            },
        ).update(0.0)

        self.assertEqual(camera.follow_mode, "none")
        self.assertIsNone(camera.bounds)
        self.assertIsNone(camera.deadzone)

        execute_registered_command(registry, context, "pop_camera_state", {}).update(0.0)

        self.assertEqual(camera.follow_mode, "entity")
        self.assertEqual(camera.followed_entity_id, "player")
        self.assertEqual(camera.follow_offset_x, 3.0)
        self.assertEqual(camera.follow_offset_y, -1.0)
        self.assertEqual(
            camera.bounds,
            {"x": 16.0, "y": 32.0, "width": 48.0, "height": 64.0},
        )
        self.assertEqual(
            camera.deadzone,
            {"x": 32.0, "y": 16.0, "width": 80.0, "height": 64.0},
        )

    def test_set_camera_follow_player_is_removed(self) -> None:
        world = World()
        registry, context = self._make_command_context(world=world)
        camera = _RecordingCamera()
        context.camera = camera

        with self.assertRaises(CommandExecutionError) as raised:
            execute_registered_command(
                registry,
                context,
                "set_camera_follow_player",
                {},
            )

        self.assertIsNotNone(raised.exception.__cause__)
        self.assertIn("Unknown command 'set_camera_follow_player'", str(raised.exception.__cause__))

    def test_legacy_camera_commands_are_removed(self) -> None:
        world = World()
        registry, context = self._make_command_context(world=world)
        context.camera = _RecordingCamera()

        for command_name in (
            "set_camera_follow_entity",
            "set_camera_follow_input_target",
            "clear_camera_follow",
            "set_camera_bounds_rect",
            "clear_camera_bounds",
            "clear_camera_deadzone",
        ):
            with self.subTest(command_name=command_name):
                with self.assertRaises(CommandExecutionError) as raised:
                    execute_registered_command(registry, context, command_name, {})
                self.assertIsNotNone(raised.exception.__cause__)
                self.assertIn(f"Unknown command '{command_name}'", str(raised.exception.__cause__))

    def test_set_var_from_camera_is_removed(self) -> None:
        world = World()
        registry, context = self._make_command_context(world=world)
        camera = _RecordingCamera()
        context.camera = camera

        with self.assertRaises(CommandExecutionError) as raised:
            execute_registered_command(
                registry,
                context,
                "set_var_from_camera",
                {
                    "scope": "world",
                    "name": "camera_x",
                    "field": "x",
                },
            )

        self.assertIsNotNone(raised.exception.__cause__)
        self.assertIn("Unknown command 'set_var_from_camera'", str(raised.exception.__cause__))

    def test_set_input_event_name_is_removed(self) -> None:
        world = World()
        registry, context = self._make_command_context(world=world)

        with self.assertRaises(CommandExecutionError) as raised:
            execute_registered_command(
                registry,
                context,
                "set_input_event_name",
                {
                    "action": "interact",
                    "command_id": "confirm",
                },
            )

        self.assertIsNotNone(raised.exception.__cause__)
        self.assertIn("Unknown command 'set_input_event_name'", str(raised.exception.__cause__))

    def test_explicit_camera_query_helpers_are_removed(self) -> None:
        world = World()
        registry, context = self._make_command_context(world=world)
        camera = _RecordingCamera()
        context.camera = camera

        for command_name, params, expected_message in (
            (
                "set_world_var_from_camera",
                {"name": "camera_x", "field": "x"},
                "Unknown command 'set_world_var_from_camera'",
            ),
            (
                "set_entity_var_from_camera",
                {"entity_id": "player", "name": "camera_x", "field": "x"},
                "Unknown command 'set_entity_var_from_camera'",
            ),
        ):
            with self.assertRaises(CommandExecutionError) as raised:
                execute_registered_command(
                    registry,
                    context,
                    command_name,
                    params,
                )

            self.assertIsNotNone(raised.exception.__cause__)
            self.assertIn(expected_message, str(raised.exception.__cause__))

    def test_camera_tokens_support_bounds_deadzone_and_follow_state(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        registry, context = self._make_command_context(world=world)
        camera = _RecordingCamera()
        context.camera = camera

        bounds_handle = execute_registered_command(
            registry,
            context,
            "set_camera_bounds",
            {
                "x": 1,
                "y": 2,
                "width": 3,
                "height": 4,
                "space": "world_grid",
            },
        )
        bounds_handle.update(0.0)
        self.assertEqual(
            camera.bounds,
            {"x": 16.0, "y": 32.0, "width": 48.0, "height": 64.0},
        )

        deadzone_handle = execute_registered_command(
            registry,
            context,
            "set_camera_deadzone",
            {
                "x": 8,
                "y": 12,
                "width": 24,
                "height": 30,
                "space": "viewport_pixel",
            },
        )
        deadzone_handle.update(0.0)
        self.assertEqual(
            camera.deadzone,
            {"x": 8.0, "y": 12.0, "width": 24.0, "height": 30.0},
        )

        follow_set_handle = execute_registered_command(
            registry,
            context,
            "set_camera_follow",
            {
                "follow": {
                    "mode": "entity",
                    "entity_id": "player",
                    "offset_x": 6,
                    "offset_y": -2,
                }
            },
        )
        follow_set_handle.update(0.0)

        query_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_current_area_var",
                "name": "camera_bounds",
                "value": "$camera.bounds",
            },
        )
        query_handle.update(0.0)
        self.assertEqual(
            world.variables["camera_bounds"],
            {"x": 16.0, "y": 32.0, "width": 48.0, "height": 64.0},
        )

        entity_query_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "player",
                "name": "camera_has_bounds",
                "value": "$camera.has_bounds",
            },
        )
        entity_query_handle.update(0.0)

        player = world.get_entity("player")
        assert player is not None
        self.assertTrue(player.variables["camera_has_bounds"])
        self.assertEqual(world.variables["camera_bounds"]["x"], 16.0)

        follow_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_current_area_var",
                "name": "follow_target",
                "value": "$camera.follow.entity_id",
            },
        )
        follow_handle.update(0.0)
        self.assertEqual(world.variables["follow_target"], "player")

        follow_mode_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_current_area_var",
                "name": "follow_mode",
                "value": "$camera.follow.mode",
            },
        )
        follow_mode_handle.update(0.0)
        self.assertEqual(world.variables["follow_mode"], "entity")

    def test_save_game_restores_explicit_camera_state(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game
        from pathlib import Path

        project = load_project(
            Path(
                r"C:\Syncthing\Vault\projects\puzzle_dungeon_v3\python_puzzle_engine\projects\test_project\project.json"
            )
        )
        area_path = project.resolve_area_reference("areas/village_square")
        assert area_path is not None
        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        game.camera.follow_entity("player", offset_x=14, offset_y=-6)
        game.camera.set_bounds_rect(16, 16, 160, 112)
        game.camera.set_deadzone_rect(80, 56, 32, 24)
        save_path = project.project_root / "saves" / "camera_slot.json"
        game.save_game(str(save_path))

        game.camera.clear_follow()
        game.camera.clear_bounds()
        game.camera.clear_deadzone()
        game.request_load_game(str(save_path))
        game._apply_pending_load_if_idle()

        assert game.camera is not None
        camera_state = game.camera.to_state_dict()
        self.assertEqual(camera_state["follow"]["mode"], "entity")
        self.assertEqual(camera_state["follow"]["entity_id"], "player")
        self.assertEqual(camera_state["follow"]["offset_x"], 14.0)
        self.assertEqual(camera_state["follow"]["offset_y"], -6.0)
        self.assertEqual(
            camera_state["bounds"],
            {"x": 16.0, "y": 16.0, "width": 160.0, "height": 112.0},
        )
        self.assertEqual(
            camera_state["deadzone"],
            {"x": 80.0, "y": 56.0, "width": 32.0, "height": 24.0},
        )

    def test_set_visual_frame_updates_primary_visual(self) -> None:
        _, project = self._make_project()
        caller = _make_runtime_entity("lever", kind="lever", with_visual=True)
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "set_visual_frame",
            {
                "entity_id": "lever",
                "frame": 2,
            },
        )
        handle.update(0.0)

        self.assertEqual(world.get_entity("lever").require_visual("main").current_frame, 2)  # type: ignore[union-attr]

    def test_set_visual_flip_x_updates_primary_visual(self) -> None:
        _, project = self._make_project()
        caller = _make_runtime_entity("lever", kind="lever", with_visual=True)
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "set_visual_flip_x",
            {
                "entity_id": "lever",
                "flip_x": True,
            },
        )
        handle.update(0.0)

        self.assertTrue(world.get_entity("lever").require_visual("main").flip_x)  # type: ignore[union-attr]

    def test_global_entity_persistence_round_trips(self) -> None:
        _, project = self._make_project()
        area = _minimal_runtime_area()
        authored_global = _make_runtime_entity(
            "dialogue_controller",
            kind="system",
            space="screen",
            scope="global",
            with_visual=True,
        )
        authored_world = World()
        authored_world.add_entity(authored_global)

        runtime = PersistenceRuntime(project=project)
        runtime.bind_area(area.area_id, authored_world=authored_world)

        mutated_global = _make_runtime_entity(
            "dialogue_controller",
            kind="system",
            space="screen",
            scope="global",
            with_visual=True,
        )
        mutated_global.visible = False
        runtime.set_entity_field(
            "dialogue_controller",
            "visible",
            False,
            entity=mutated_global,
            tile_size=area.tile_size,
        )
        runtime.set_entity_variable(
            "dialogue_controller",
            "mode",
            "menu",
            entity=mutated_global,
            tile_size=area.tile_size,
        )

        restored_save_data = save_data_from_dict(save_data_to_dict(runtime.save_data))
        fresh_world = World()
        fresh_world.add_entity(
            _make_runtime_entity(
                "dialogue_controller",
                kind="system",
                space="screen",
                scope="global",
                with_visual=True,
            )
        )

        apply_persistent_global_state(area, fresh_world, restored_save_data, project=project)

        restored_entity = fresh_world.get_entity("dialogue_controller")
        assert restored_entity is not None
        self.assertFalse(restored_entity.visible)
        self.assertEqual(restored_entity.variables["mode"], "menu")

    def test_current_global_state_round_trips(self) -> None:
        _, project = self._make_project()
        area = _minimal_runtime_area()
        reference_world = World()
        reference_world.add_entity(
            _make_runtime_entity(
                "dialogue_controller",
                kind="system",
                space="screen",
                scope="global",
                with_visual=True,
            )
        )

        current_world = World()
        current_global = _make_runtime_entity(
            "dialogue_controller",
            kind="system",
            space="screen",
            scope="global",
            with_visual=True,
        )
        current_global.variables["mode"] = "menu"
        current_global.visible = False
        current_global.require_visual("main").current_frame = 2
        current_world.add_entity(current_global)

        current_global_entities = capture_current_global_state(
            area,
            reference_world,
            current_world,
            project=project,
        )
        self.assertIsNotNone(current_global_entities)

        save_data = save_data_from_dict(
            save_data_to_dict(
                PersistenceRuntime(project=project).save_data
            )
        )
        save_data.current_global_entities = current_global_entities
        restored_save_data = save_data_from_dict(save_data_to_dict(save_data))

        restored_world = World()
        restored_world.add_entity(
            _make_runtime_entity(
                "dialogue_controller",
                kind="system",
                space="screen",
                scope="global",
                with_visual=True,
            )
        )
        apply_current_global_state(
            area,
            restored_world,
            restored_save_data.current_global_entities,
            project=project,
        )

        restored_entity = restored_world.get_entity("dialogue_controller")
        assert restored_entity is not None
        self.assertEqual(restored_entity.variables["mode"], "menu")
        self.assertFalse(restored_entity.visible)
        self.assertEqual(restored_entity.require_visual("main").current_frame, 2)

    def test_traveler_state_round_trips_and_installs_in_destination_area(self) -> None:
        _, project = self._make_project()
        area_a = Area(
            area_id="areas/room_a",
            name="Room A",
            tile_size=16,
            tilesets=[],
            tile_layers=[],
            cell_flags=[],
        )
        area_b = Area(
            area_id="areas/room_b",
            name="Room B",
            tile_size=16,
            tilesets=[],
            tile_layers=[],
            cell_flags=[],
        )
        authored_world_a = World()
        authored_world_a.add_entity(_make_runtime_entity("crate", kind="crate"))
        authored_world_b = World()

        runtime = PersistenceRuntime(project=project)
        runtime.bind_area(area_a.area_id, authored_world=authored_world_a)

        traveling_crate = _make_runtime_entity("crate", kind="crate")
        traveling_crate.grid_x = 5
        traveling_crate.grid_y = 6
        traveling_crate.sync_pixel_position(area_a.tile_size)
        traveling_crate.variables["moved"] = True
        runtime.prepare_traveler_for_area(
            traveling_crate,
            destination_area_id=area_b.area_id,
            tile_size=area_a.tile_size,
        )

        restored_save_data = save_data_from_dict(save_data_to_dict(runtime.save_data))

        world_a = World()
        world_a.add_entity(_make_runtime_entity("crate", kind="crate"))
        apply_area_travelers(area_a, world_a, restored_save_data, project=project)
        self.assertIsNone(world_a.get_entity("crate"))

        world_b = World()
        apply_area_travelers(area_b, world_b, restored_save_data, project=project)
        restored_crate = world_b.get_entity("crate")
        assert restored_crate is not None
        self.assertEqual(restored_crate.grid_x, 5)
        self.assertEqual(restored_crate.grid_y, 6)
        self.assertTrue(restored_crate.variables["moved"])  # type: ignore[index]
        self.assertIsNotNone(restored_crate.session_entity_id)
        self.assertEqual(restored_crate.origin_area_id, "areas/room_a")
        self.assertEqual(restored_crate.origin_entity_id, "crate")

    def test_game_area_change_without_returning_traveler_suppresses_origin_placeholder(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        _, project = self._make_project(
            startup_area="areas/room_a",
            areas={
                "room_a.json": {
                    "name": "Room A",
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [
                        {
                            "name": "ground",
                            "render_order": 0,
                            "grid": [[0, 0, 0]],
                        }
                    ],
                    "cell_flags": [[True, True, True]],
                    "entities": [
                        {
                            "id": "player",
                            "kind": "player",
                            "x": 0,
                            "y": 0,
                        },
                        {
                            "id": "crate",
                            "kind": "crate",
                            "x": 1,
                            "y": 0,
                        },
                    ],
                },
                "room_b.json": {
                    "name": "Room B",
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [
                        {
                            "name": "ground",
                            "render_order": 0,
                            "grid": [[0, 0, 0]],
                        }
                    ],
                    "cell_flags": [[True, True, True]],
                    "entry_points": {
                        "landing": {
                            "x": 2,
                            "y": 0,
                        }
                    },
                    "entities": [],
                },
            },
        )

        area_a_path = project.resolve_area_reference("areas/room_a")
        assert area_a_path is not None
        game = Game(area_path=area_a_path, project=project)
        self.addCleanup(pygame.quit)

        crate = game.world.get_entity("crate")
        assert crate is not None
        crate.variables["moved"] = True

        game.request_area_change(
            AreaTransitionRequest(
                area_id="areas/room_b",
                entry_id="landing",
                transfer_entity_ids=["crate"],
            )
        )
        game._apply_pending_area_change_if_idle()

        self.assertEqual(game.area.area_id, "areas/room_b")
        moved_crate = game.world.get_entity("crate")
        assert moved_crate is not None
        self.assertEqual(moved_crate.grid_x, 2)
        self.assertEqual(moved_crate.grid_y, 0)
        self.assertTrue(moved_crate.variables["moved"])  # type: ignore[index]

        game.request_area_change(AreaTransitionRequest(area_id="areas/room_a"))
        game._apply_pending_area_change_if_idle()

        self.assertEqual(game.area.area_id, "areas/room_a")
        self.assertIsNone(game.world.get_entity("crate"))

    def test_item_definitions_use_path_derived_ids(self) -> None:
        _, project = self._make_project(
            items={
                "consumables/apple.json": _minimal_item(name="Apple", max_stack=9),
                "keys/copper_key.json": _minimal_item(name="Copper Key", max_stack=1),
            }
        )

        validate_project_items(project)

        self.assertEqual(
            sorted(project.list_item_ids()),
            ["items/consumables/apple", "items/keys/copper_key"],
        )
        apple = load_item_definition(project, "items/consumables/apple")
        self.assertEqual(apple.item_id, "items/consumables/apple")
        self.assertEqual(apple.name, "Apple")
        self.assertEqual(apple.max_stack, 9)

    def test_item_definitions_support_optional_portrait_payloads(self) -> None:
        _, project = self._make_project(
            items={
                "apple.json": _minimal_item(
                    name="Apple",
                    description="Crunchy.",
                    icon={
                        "path": "assets/project/sprites/object_sheet.png",
                        "frame_width": 16,
                        "frame_height": 16,
                        "frame": 0,
                    },
                    portrait={
                        "path": "assets/project/sprites/object_sheet.png",
                        "frame_width": 16,
                        "frame_height": 16,
                        "frame": 1,
                    },
                    max_stack=9,
                )
            }
        )

        validate_project_items(project)
        apple = load_item_definition(project, "items/apple")

        self.assertEqual(apple.description, "Crunchy.")
        self.assertEqual(
            apple.icon,
            {
                "path": "assets/project/sprites/object_sheet.png",
                "frame_width": 16,
                "frame_height": 16,
                "frame": 0,
            },
        )
        self.assertEqual(
            apple.portrait,
            {
                "path": "assets/project/sprites/object_sheet.png",
                "frame_width": 16,
                "frame_height": 16,
                "frame": 1,
            },
        )

    def test_item_validation_rejects_authored_id_fields(self) -> None:
        _, project = self._make_project(
            items={
                "apple.json": {
                    "id": "items/apple",
                    **_minimal_item(name="Apple", max_stack=9),
                }
            }
        )

        with self.assertRaises(ItemDefinitionValidationError) as exc_info:
            validate_project_items(project)

        self.assertTrue(
            any("must not declare 'id'" in issue for issue in exc_info.exception.issues)
        )

    def test_entity_inventory_round_trips_through_loader_and_serializer(self) -> None:
        _, project = self._make_project(
            items={
                "apple.json": _minimal_item(name="Apple", max_stack=9),
                "keys/copper_key.json": _minimal_item(name="Copper Key", max_stack=1),
            }
        )
        entity = instantiate_entity(
            {
                "id": "player",
                "kind": "player",
                "x": 0,
                "y": 0,
                "inventory": {
                    "max_stacks": 3,
                    "stacks": [
                        {"item_id": "items/apple", "quantity": 2},
                        {"item_id": "items/keys/copper_key", "quantity": 1},
                    ],
                },
            },
            16,
            project=project,
            source_name="test entity",
        )
        assert entity.inventory is not None
        self.assertEqual(entity.inventory.max_stacks, 3)
        self.assertEqual(
            [(stack.item_id, stack.quantity) for stack in entity.inventory.stacks],
            [("items/apple", 2), ("items/keys/copper_key", 1)],
        )

        area = _minimal_runtime_area()
        world = World()
        world.add_entity(entity)
        serialized = serialize_area(area, world, project=project)
        self.assertEqual(
            serialized["entities"][0]["inventory"],
            {
                "max_stacks": 3,
                "stacks": [
                    {"item_id": "items/apple", "quantity": 2},
                    {"item_id": "items/keys/copper_key", "quantity": 1},
                ],
            },
        )

    def test_loader_inventory_rejects_missing_items_unless_explicitly_allowed(self) -> None:
        _, project = self._make_project()
        entity_payload = {
            "id": "player",
            "kind": "player",
            "x": 0,
            "y": 0,
            "inventory": {
                "max_stacks": 2,
                "stacks": [
                    {"item_id": "items/missing_key", "quantity": 1},
                ],
            },
        }

        with self.assertRaises(ValueError):
            instantiate_entity(
                entity_payload,
                16,
                project=project,
                source_name="test entity",
            )

        entity = instantiate_entity(
            entity_payload,
            16,
            project=project,
            source_name="saved entity",
            allow_missing_inventory_items=True,
        )
        assert entity.inventory is not None
        self.assertEqual(entity.inventory.max_stacks, 2)
        self.assertEqual(
            [(stack.item_id, stack.quantity) for stack in entity.inventory.stacks],
            [("items/missing_key", 1)],
        )

    def test_add_inventory_item_supports_partial_adds_and_writes_result_on_command_owner(self) -> None:
        _, project = self._make_project(
            items={
                "apple.json": _minimal_item(name="Apple", max_stack=9),
            }
        )
        world = World()
        player = _make_runtime_entity("player", kind="player")
        player.inventory = InventoryState(
            max_stacks=1,
            stacks=[InventoryStack(item_id="items/apple", quantity=8)],
        )
        pickup = _make_runtime_entity(
            "apple_pickup",
            kind="pickup",
            entity_commands={
                "interact": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "add_inventory_item",
                            "entity_id": "$ref_ids.instigator",
                            "item_id": "items/apple",
                            "quantity": 3,
                            "quantity_mode": "partial",
                            "result_var_name": "last_inventory_result",
                        }
                    ]
                )
            },
        )
        world.add_entity(player)
        world.add_entity(pickup)
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "run_entity_command",
            {
                "entity_id": "apple_pickup",
                "command_id": "interact",
                "entity_refs": {"instigator": "player"},
            },
        )
        self._complete_handle(handle)

        self.assertEqual(inventory_item_count(player.inventory, "items/apple"), 9)
        self.assertEqual(
            pickup.variables["last_inventory_result"],
            {
                "success": True,
                "item_id": "items/apple",
                "requested_quantity": 3,
                "changed_quantity": 1,
                "remaining_quantity": 2,
            },
        )

    def test_remove_inventory_item_respects_atomic_and_partial_modes(self) -> None:
        world = World()
        player = _make_runtime_entity("player", kind="player")
        player.inventory = InventoryState(
            max_stacks=3,
            stacks=[InventoryStack(item_id="items/apple", quantity=3)],
        )
        controller = _make_runtime_entity("controller", kind="system", space="screen")
        world.add_entity(player)
        world.add_entity(controller)
        registry, context = self._make_command_context(world=world)

        execute_registered_command(
            registry,
            context,
            "remove_inventory_item",
            {
                "entity_id": "player",
                "item_id": "items/apple",
                "quantity": 5,
                "quantity_mode": "atomic",
                "source_entity_id": "controller",
                "result_var_name": "last_inventory_result",
            },
        ).update(0.0)
        self.assertEqual(inventory_item_count(player.inventory, "items/apple"), 3)
        self.assertEqual(
            controller.variables["last_inventory_result"],
            {
                "success": True,
                "item_id": "items/apple",
                "requested_quantity": 5,
                "changed_quantity": 0,
                "remaining_quantity": 5,
            },
        )

        execute_registered_command(
            registry,
            context,
            "remove_inventory_item",
            {
                "entity_id": "player",
                "item_id": "items/apple",
                "quantity": 5,
                "quantity_mode": "partial",
                "source_entity_id": "controller",
                "result_var_name": "last_inventory_result",
            },
        ).update(0.0)
        self.assertEqual(inventory_item_count(player.inventory, "items/apple"), 0)
        self.assertEqual(
            controller.variables["last_inventory_result"],
            {
                "success": True,
                "item_id": "items/apple",
                "requested_quantity": 5,
                "changed_quantity": 3,
                "remaining_quantity": 2,
            },
        )

    def test_inventory_value_sources_return_counts_and_requirements(self) -> None:
        world = World()
        player = _make_runtime_entity("player", kind="player")
        player.inventory = InventoryState(
            max_stacks=3,
            stacks=[InventoryStack(item_id="items/apple", quantity=3)],
        )
        controller = _make_runtime_entity("controller", kind="system", space="screen")
        world.add_entity(player)
        world.add_entity(controller)
        registry, context = self._make_command_context(world=world)

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "controller",
                "name": "apple_count",
                "value": {
                    "$inventory_item_count": {
                        "entity_id": "player",
                        "item_id": "items/apple",
                    }
                },
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "controller",
                "name": "has_two_apples",
                "value": {
                    "$inventory_has_item": {
                        "entity_id": "player",
                        "item_id": "items/apple",
                        "quantity": 2,
                    }
                },
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "controller",
                "name": "has_four_apples",
                "value": {
                    "$inventory_has_item": {
                        "entity_id": "player",
                        "item_id": "items/apple",
                        "quantity": 4,
                    }
                },
            },
        ).update(0.0)

        self.assertEqual(controller.variables["apple_count"], 3)
        self.assertTrue(controller.variables["has_two_apples"])
        self.assertFalse(controller.variables["has_four_apples"])

    def test_set_inventory_max_stacks_creates_inventory_and_refuses_unsafe_shrink(self) -> None:
        world = World()
        player = _make_runtime_entity("player", kind="player")
        world.add_entity(player)
        registry, context = self._make_command_context(world=world)

        execute_registered_command(
            registry,
            context,
            "set_inventory_max_stacks",
            {
                "entity_id": "player",
                "max_stacks": 2,
            },
        ).update(0.0)

        assert player.inventory is not None
        self.assertEqual(player.inventory.max_stacks, 2)
        self.assertEqual(player.inventory.stacks, [])

        player.inventory.stacks = [
            InventoryStack(item_id="items/apple", quantity=1),
            InventoryStack(item_id="items/key", quantity=1),
        ]
        execute_registered_command(
            registry,
            context,
            "set_inventory_max_stacks",
            {
                "entity_id": "player",
                "max_stacks": 1,
            },
        ).update(0.0)

        self.assertEqual(player.inventory.max_stacks, 2)

    def test_use_inventory_item_runs_commands_with_instigator_and_consumes_after_success(self) -> None:
        _, project = self._make_project(
            items={
                "orb.json": _minimal_item(
                    name="Orb of Light",
                    max_stack=3,
                    consume_quantity_on_use=1,
                    use_commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$ref_ids.instigator",
                            "name": "orb_used",
                            "value": True,
                        }
                    ],
                )
            }
        )
        world = World()
        player = _make_runtime_entity("player", kind="player")
        player.inventory = InventoryState(
            max_stacks=3,
            stacks=[InventoryStack(item_id="items/orb", quantity=2)],
        )
        controller = _make_runtime_entity("controller", kind="system", space="screen")
        world.add_entity(player)
        world.add_entity(controller)
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "use_inventory_item",
            {
                "entity_id": "player",
                "item_id": "items/orb",
                "quantity": 1,
                "source_entity_id": "controller",
                "result_var_name": "last_inventory_result",
            },
        )
        self._complete_handle(handle)

        self.assertTrue(player.variables["orb_used"])  # type: ignore[index]
        self.assertEqual(inventory_item_count(player.inventory, "items/orb"), 1)
        self.assertEqual(
            controller.variables["last_inventory_result"],
            {
                "success": True,
                "item_id": "items/orb",
                "requested_quantity": 1,
                "changed_quantity": 1,
                "remaining_quantity": 0,
            },
        )

    def test_use_inventory_item_can_succeed_without_consuming_inventory(self) -> None:
        _, project = self._make_project(
            items={
                "key.json": _minimal_item(
                    name="Reusable Key",
                    max_stack=1,
                    consume_quantity_on_use=0,
                    use_commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$ref_ids.instigator",
                            "name": "key_used",
                            "value": True,
                        }
                    ],
                )
            }
        )
        world = World()
        player = _make_runtime_entity("player", kind="player")
        player.inventory = InventoryState(
            max_stacks=3,
            stacks=[InventoryStack(item_id="items/key", quantity=1)],
        )
        controller = _make_runtime_entity("controller", kind="system", space="screen")
        world.add_entity(player)
        world.add_entity(controller)
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "use_inventory_item",
            {
                "entity_id": "player",
                "item_id": "items/key",
                "quantity": 1,
                "source_entity_id": "controller",
                "result_var_name": "last_inventory_result",
            },
        )
        self._complete_handle(handle)

        self.assertTrue(player.variables["key_used"])  # type: ignore[index]
        self.assertEqual(inventory_item_count(player.inventory, "items/key"), 1)
        self.assertEqual(
            controller.variables["last_inventory_result"],
            {
                "success": True,
                "item_id": "items/key",
                "requested_quantity": 1,
                "changed_quantity": 0,
                "remaining_quantity": 0,
            },
        )

    def test_use_inventory_item_does_not_consume_inventory_when_use_commands_fail(self) -> None:
        _, project = self._make_project(
            items={
                "orb.json": _minimal_item(
                    name="Broken Orb",
                    max_stack=3,
                    consume_quantity_on_use=1,
                    use_commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "missing_target",
                            "name": "orb_used",
                            "value": True,
                        }
                    ],
                )
            }
        )
        world = World()
        player = _make_runtime_entity("player", kind="player")
        player.inventory = InventoryState(
            max_stacks=3,
            stacks=[InventoryStack(item_id="items/orb", quantity=1)],
        )
        controller = _make_runtime_entity("controller", kind="system", space="screen")
        world.add_entity(player)
        world.add_entity(controller)
        registry, context = self._make_command_context(project=project, world=world)

        with self.assertRaises(CommandExecutionError):
            execute_registered_command(
                registry,
                context,
                "use_inventory_item",
                {
                    "entity_id": "player",
                    "item_id": "items/orb",
                    "quantity": 1,
                    "source_entity_id": "controller",
                    "result_var_name": "last_inventory_result",
                },
            )

        self.assertEqual(inventory_item_count(player.inventory, "items/orb"), 1)

    def test_open_inventory_session_renders_empty_state_and_waits_for_close(self) -> None:
        _, project = self._make_project(shared_variables=_inventory_shared_variables())
        world = World()
        player = _make_runtime_entity("player", kind="player")
        player.inventory = InventoryState(max_stacks=4, stacks=[])
        world.add_entity(player)
        registry, context = self._make_command_context(project=project, world=world)
        inventory_runtime = self._install_inventory_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        handle = execute_registered_command(
            registry,
            context,
            "open_inventory_session",
            {
                "entity_id": "player",
            },
        )

        self.assertTrue(inventory_runtime.is_active())
        self.assertFalse(handle.complete)
        empty_row = inventory_runtime.screen_manager.get_element("engine_inventory_row_text_0")
        detail_text = inventory_runtime.screen_manager.get_element("engine_inventory_detail_text")
        self.assertIsNotNone(empty_row)
        self.assertEqual(empty_row.text, " No items")
        self.assertIsNotNone(detail_text)
        self.assertEqual(detail_text.text, "Inventory empty.")

        execute_registered_command(
            registry,
            context,
            "close_inventory_session",
            {},
        ).update(0.0)
        handle.update(0.0)

        self.assertTrue(handle.complete)
        self.assertFalse(inventory_runtime.is_active())

    def test_inventory_runtime_uses_selected_item_and_closes_session(self) -> None:
        _, project = self._make_project(
            items={
                "apple.json": _minimal_item(
                    name="Apple",
                    max_stack=9,
                    consume_quantity_on_use=1,
                    use_commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$ref_ids.instigator",
                            "name": "ate_apple",
                            "value": True,
                        }
                    ],
                )
            },
            shared_variables=_inventory_shared_variables(),
        )
        world = World()
        player = _make_runtime_entity("player", kind="player")
        player.inventory = InventoryState(
            max_stacks=4,
            stacks=[InventoryStack(item_id="items/apple", quantity=2)],
        )
        world.add_entity(player)
        registry, context = self._make_command_context(project=project, world=world)
        inventory_runtime = self._install_inventory_runtime(
            registry=registry,
            context=context,
            project=project,
        )
        assert context.command_runner is not None

        inventory_runtime.open_session(entity_id="player")
        inventory_runtime.handle_action("interact")
        self.assertIsNotNone(
            inventory_runtime.screen_manager.get_element("engine_inventory_action_panel")
        )

        inventory_runtime.handle_action("interact")
        self._run_command_runner_until_idle(context.command_runner)

        self.assertFalse(inventory_runtime.is_active())
        self.assertTrue(player.variables["ate_apple"])  # type: ignore[index]
        self.assertEqual(inventory_item_count(player.inventory, "items/apple"), 1)

    def test_inventory_runtime_interact_on_non_usable_item_only_plays_deny_feedback(self) -> None:
        class _RecordingAudioPlayer:
            def __init__(self) -> None:
                self.paths: list[str] = []

            def play_audio(self, relative_path: str, *, volume: float | None = None) -> bool:
                _ = volume
                self.paths.append(str(relative_path))
                return True

        _, project = self._make_project(
            items={
                "copper_key.json": _minimal_item(
                    name="Copper Key",
                    max_stack=1,
                )
            },
            shared_variables=_inventory_shared_variables(),
        )
        world = World()
        player = _make_runtime_entity("player", kind="player")
        player.inventory = InventoryState(
            max_stacks=4,
            stacks=[InventoryStack(item_id="items/copper_key", quantity=1)],
        )
        world.add_entity(player)
        registry, context = self._make_command_context(project=project, world=world)
        context.audio_player = _RecordingAudioPlayer()
        inventory_runtime = self._install_inventory_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        inventory_runtime.open_session(entity_id="player")
        inventory_runtime.handle_action("interact")

        self.assertIsNone(
            inventory_runtime.screen_manager.get_element("engine_inventory_action_panel")
        )
        self.assertEqual(context.audio_player.paths, ["assets/project/sfx/bump.wav"])  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()

