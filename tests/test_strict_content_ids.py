from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

import run_editor
import run_game
from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.library import (
    NamedCommandValidationError,
    validate_project_named_commands,
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
from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity, EntityEvent, EntityVisual
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
from dungeon_engine.engine.input_handler import InputHandler
from dungeon_engine.engine.screen import ScreenElementManager
from dungeon_engine.engine.text import TextRenderer


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
                "draw_above_entities": False,
                "grid": [[1]],
            }
        ],
        "cell_flags": [[True]],
        "entities": [],
    }


def _minimal_runtime_area() -> Area:
    return Area(
        area_id="test_room",
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
    events: dict[str, EntityEvent] | None = None,
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
        events=events or {},
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
        self.grid_steps: list[tuple[str, str, float | None, int | None, float | None, str, bool]] = []
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
        allow_push: bool = True,
    ) -> list[str]:
        self.grid_steps.append(
            (entity_id, direction, duration, frames_needed, speed_px_per_second, grid_sync, allow_push)
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

    def to_state_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "x": self.x,
            "y": self.y,
            "follow_mode": self.follow_mode,
            "follow_offset_x": self.follow_offset_x,
            "follow_offset_y": self.follow_offset_y,
        }
        if self.followed_entity_id is not None:
            data["follow_entity_id"] = self.followed_entity_id
        if self.follow_input_action is not None:
            data["follow_input_action"] = self.follow_input_action
        if self.bounds is not None:
            data["bounds"] = dict(self.bounds)
        if self.deadzone is not None:
            data["deadzone"] = dict(self.deadzone)
        return data


class _StubTextRenderer:
    def wrap_lines(self, text: str, max_width: int, *, font_id: str = "") -> list[str]:
        _ = max_width
        _ = font_id
        return [part for part in str(text).split(" ") if part]


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
        self.dispatched: list[tuple[str, str, str | None]] = []

    def has_pending_work(self) -> bool:
        return False

    def dispatch_input_event(
        self,
        *,
        entity_id: str,
        event_id: str,
        actor_entity_id: str | None = None,
    ) -> bool:
        self.dispatched.append((entity_id, event_id, actor_entity_id))
        return True


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
        dialogues: dict[str, dict[str, object]] | None = None,
    ) -> tuple[Path, object]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        project_root = Path(temp_dir.name)

        project_payload: dict[str, object] = {
            "area_paths": ["areas/"],
            "entity_template_paths": ["entity_templates/"],
            "named_command_paths": ["named_commands/"],
            "shared_variables_path": "shared_variables.json",
        }
        if startup_area is not None:
            project_payload["startup_area"] = startup_area
        if input_targets is not None:
            project_payload["input_targets"] = input_targets
        if global_entities is not None:
            project_payload["global_entities"] = global_entities

        _write_json(project_root / "project.json", project_payload)

        for relative_path, template_payload in (entity_templates or {}).items():
            _write_json(project_root / "entity_templates" / relative_path, template_payload)
        for relative_path, area_payload in (areas or {}).items():
            _write_json(project_root / "areas" / relative_path, area_payload)
        for relative_path, command_payload in (commands or {}).items():
            _write_json(project_root / "named_commands" / relative_path, command_payload)
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

    def test_area_validation_rejects_authored_area_id(self) -> None:
        _, project = self._make_project(
            startup_area="test_room",
            areas={
                "test_room.json": {
                    "area_id": "test_room",
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
            startup_area="missing_room",
            areas={"test_room.json": _minimal_area()},
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("startup_area 'missing_room'" in issue for issue in raised.exception.issues)
        )

    def test_area_loader_preserves_enter_commands(self) -> None:
        _, project = self._make_project()
        raw_area = _minimal_area()
        raw_area["enter_commands"] = [
            {
                "type": "run_event",
                "entity_id": "dialogue_controller",
                "event_id": "open_dialogue",
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
        self.assertEqual(area.enter_commands[0]["type"], "run_event")
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
            "follow_entity_id": "player",
            "follow_offset_x": 10,
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
        self.assertEqual(area.camera_defaults["follow_entity_id"], "player")
        self.assertEqual(area.camera_defaults["follow_offset_x"], 10)

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

        self.assertEqual(runner.dispatched, [("player", "confirm", "player")])

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
                ("debug_controller", "toggle_pause", "debug_controller"),
                ("debug_controller", "step_tick", "debug_controller"),
                ("debug_controller", "zoom_out", "debug_controller"),
                ("debug_controller", "zoom_in", "debug_controller"),
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

    def test_named_command_validation_rejects_authored_id(self) -> None:
        _, project = self._make_project(
            commands={
                "walk_one_tile.json": {
                    "id": "walk_one_tile",
                    "params": [],
                    "commands": [],
                }
            }
        )

        with self.assertRaises(NamedCommandValidationError) as raised:
            validate_project_named_commands(project)

        self.assertTrue(
            any("must not declare 'id'" in issue for issue in raised.exception.issues)
        )

    def test_named_command_validation_rejects_symbolic_entity_refs_for_strict_primitives(self) -> None:
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

        with self.assertRaises(NamedCommandValidationError) as raised:
            validate_project_named_commands(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'self' with strict primitive 'set_entity_field'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_named_command_validation_rejects_symbolic_entity_refs_for_strict_visual_primitives(self) -> None:
        _, project = self._make_project(
            commands={
                "bad_visual_primitive.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "play_animation",
                            "entity_id": "caller",
                            "frame_sequence": [1, 2],
                        }
                    ],
                }
            }
        )

        with self.assertRaises(NamedCommandValidationError) as raised:
            validate_project_named_commands(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'caller' with strict primitive 'play_animation'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_named_command_validation_rejects_symbolic_entity_refs_for_strict_movement_primitives(self) -> None:
        _, project = self._make_project(
            commands={
                "bad_move_primitive.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "move_entity_world_position",
                            "entity_id": "actor",
                            "x": 16,
                            "y": 0,
                            "mode": "relative",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(NamedCommandValidationError) as raised:
            validate_project_named_commands(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'actor' with strict primitive 'move_entity_world_position'"
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
            "interact_facing",
        ):
            with self.assertRaises(CommandExecutionError) as raised:
                params = {}
                if command_name == "wait_for_direction_release":
                    params = {"direction": "down"}
                elif command_name == "query_facing_state":
                    params = {"entity_id": "self", "store_state_var": "move_attempt_state"}
                elif command_name == "run_facing_event":
                    params = {"entity_id": "self", "event_id": "interact"}
                elif command_name == "interact_facing":
                    params = {"entity_id": "self"}
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

    def test_explicit_movement_query_value_sources_resolve_cell_flags_and_blockers(self) -> None:
        area = Area(
            area_id="test_room",
            name="Test Room",
            tile_size=16,
            tilesets=[],
            tile_layers=[],
            cell_flags=[
                [{"walkable": True}, {"walkable": True}, {"walkable": True}],
                [{"walkable": True}, {"walkable": True}, {"walkable": False}],
                [{"walkable": True}, {"walkable": True}, {"walkable": True}],
            ],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 1
        actor.grid_y = 1
        blocking_entity = _make_runtime_entity("crate", kind="crate")
        blocking_entity.grid_x = 2
        blocking_entity.grid_y = 1
        blocking_entity.variables["blocks_movement"] = True
        blocking_entity.variables["pushable"] = True
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
                            "fields": ["entity_id"],
                            "variables": ["blocks_movement", "pushable"],
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
                        "value": "$entity.player.target_entities",
                        "field": "variables.blocks_movement",
                        "op": "eq",
                        "match": True,
                        "default": None,
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
                "name": "has_pushable_blocker",
                "value": {
                    "$any_in_collection": {
                        "value": "$entity.player.target_entities",
                        "field": "variables.pushable",
                        "op": "eq",
                        "match": True,
                    }
                },
            },
        )
        handle.update(0.0)

        player = world.get_entity("player")
        assert player is not None
        self.assertEqual(player.variables["target_cell"]["walkable"], False)
        self.assertEqual(player.variables["blocking_entity"]["entity_id"], "crate")
        self.assertTrue(player.variables["has_pushable_blocker"])

    def test_entities_at_and_entity_at_value_sources_return_stable_plain_refs(self) -> None:
        world = World()
        low = _make_runtime_entity("low", kind="sign")
        low.grid_x = 2
        low.grid_y = 3
        low.layer = 1
        low.stack_order = 0
        high = _make_runtime_entity("high", kind="lever")
        high.grid_x = 2
        high.grid_y = 3
        high.layer = 2
        high.stack_order = 5
        high.variables["blocks_movement"] = True
        high.variables["pushable"] = True
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
                            "fields": ["entity_id", "grid_x"],
                            "variables": ["blocks_movement", "pushable"],
                        },
                    }
                },
            },
        )
        ref_handle.update(0.0)
        self.assertEqual(controller.variables["self_ref"]["entity_id"], "high")
        self.assertEqual(controller.variables["self_ref"]["grid_x"], 2)
        self.assertEqual(
            controller.variables["self_ref"]["variables"],
            {"blocks_movement": True, "pushable": True},
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
                            "fields": ["grid_x", "pixel_y", "present"],
                            "variables": ["pushable"],
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
                "variables": {"pushable": True},
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
                            "fields": ["entity_id"],
                            "variables": ["pushable"],
                        },
                        "default": None,
                    }
                },
            },
        )
        selected_target_handle.update(0.0)
        self.assertEqual(
            controller.variables["selected_target"],
            {"entity_id": "high", "variables": {"pushable": True}},
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
                            "fields": ["entity_id"],
                            "variables": ["blocks_movement", "pushable"],
                        },
                    }
                },
            },
        )
        selected_targets_handle.update(0.0)
        self.assertEqual(
            controller.variables["selected_targets"],
            [
                {"entity_id": "low", "variables": {}},
                {
                    "entity_id": "high",
                    "variables": {"blocks_movement": True, "pushable": True},
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
                            "type": "check_entity_var",
                            "entity_id": "$self_id",
                            "name": "interact_target",
                            "op": "neq",
                            "value": None,
                            "then": [
                                {
                                    "type": "run_event",
                                    "entity_id": "$self.interact_target.entity_id",
                                    "event_id": "interact",
                                    "actor_entity_id": "$self_id",
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
            events={
                "interact": EntityEvent(
                    commands=[
                        {
                            "type": "set_world_var",
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
                "type": "run_named_command",
                "command_id": "interact_one_tile",
            },
            base_params={
                "source_entity_id": "player",
                "actor_entity_id": "player",
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
            "increment_entity_var",
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
        execute_registered_command(
            registry,
            context,
            "check_entity_var",
            {
                "entity_id": "dialogue_controller",
                "name": "mode",
                "op": "eq",
                "value": "menu",
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

    def test_explicit_world_var_primitives_manage_values_and_branching(self) -> None:
        registry, context = self._make_command_context()

        execute_registered_command(
            registry,
            context,
            "set_world_var",
            {
                "name": "mode",
                "value": "play",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "increment_world_var",
            {
                "name": "turn_count",
                "amount": 3,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "append_world_var",
            {
                "name": "visited_rooms",
                "value": "village_square",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "append_world_var",
            {
                "name": "visited_rooms",
                "value": "village_house",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_world_var_length",
            {
                "name": "visited_room_count",
                "value": context.world.variables["visited_rooms"],
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_world_var",
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
            "pop_world_var",
            {
                "name": "visited_rooms",
                "store_var": "popped_room",
                "default": "",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "check_world_var",
            {
                "name": "mode",
                "op": "eq",
                "value": "play",
                "then": [
                    {
                        "type": "set_world_var",
                        "name": "world_branch_hit",
                        "value": True,
                    }
                ],
            },
        ).update(0.0)

        self.assertEqual(context.world.variables["mode"], "play")
        self.assertEqual(context.world.variables["turn_count"], 3)
        self.assertEqual(context.world.variables["visited_room_count"], 2)
        self.assertEqual(context.world.variables["latest_room"], "village_house")
        self.assertEqual(context.world.variables["visited_rooms"], ["village_square"])
        self.assertEqual(context.world.variables["popped_room"], "village_house")
        self.assertTrue(context.world.variables["world_branch_hit"])

    def test_explicit_var_primitives_persist_when_requested(self) -> None:
        _, project = self._make_project()
        authored_world = World()
        authored_world.add_entity(_make_runtime_entity("dialogue_controller", kind="system", space="screen"))
        runtime = PersistenceRuntime(project=project)
        runtime.bind_area("test_room", authored_world=authored_world)

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
            "set_world_var",
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
                "actor_entity_id": "player",
                "caller_entity_id": "lever",
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

        self.assertEqual(registry.get_deferred_params("run_sequence"), {"commands"})
        self.assertEqual(registry.get_deferred_params("spawn_flow"), {"commands"})
        self.assertEqual(registry.get_deferred_params("run_parallel"), {"commands"})
        self.assertEqual(registry.get_deferred_params("run_commands_for_collection"), {"commands"})
        self.assertEqual(
            registry.get_deferred_params("run_event"),
            {"dialogue_on_start", "dialogue_on_end", "segment_hooks"},
        )
        self.assertEqual(registry.get_deferred_params("check_world_var"), {"then", "else"})
        self.assertEqual(registry.get_deferred_params("check_entity_var"), {"then", "else"})

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
            any("interact_commands" in issue and "events.interact" in issue for issue in raised.exception.issues)
        )

    def test_area_validation_rejects_symbolic_entity_refs_for_strict_primitives(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "route_inputs_to_entity",
                            "entity_id": "actor",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'actor' with strict primitive 'route_inputs_to_entity'"
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
                            "entity_id": "caller",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'caller' with strict primitive 'wait_for_move'"
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

    def test_area_validation_rejects_reserved_entity_id_actor(self) -> None:
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

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("reserved runtime entity reference 'actor'" in issue for issue in raised.exception.issues)
        )

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

    def test_launchers_resolve_startup_area_and_cli_ids(self) -> None:
        _, project = self._make_project(
            startup_area="intro/title_screen",
            areas={"intro/title_screen.json": _minimal_area(name="Title Screen")},
        )

        self.assertEqual(run_game._resolve_project_startup_area(project), "intro/title_screen")
        self.assertEqual(run_editor._resolve_project_startup_area(project), "intro/title_screen")
        self.assertEqual(run_game._resolve_area_argument(project, "intro/title_screen"), "intro/title_screen")
        self.assertEqual(run_editor._resolve_area_argument(project, "intro/title_screen"), "intro/title_screen")

    def test_launchers_reject_area_paths_as_cli_arguments(self) -> None:
        _, project = self._make_project(
            startup_area="intro/title_screen",
            areas={"intro/title_screen.json": _minimal_area(name="Title Screen")},
        )

        with self.assertRaises(FileNotFoundError):
            run_game._resolve_area_argument(project, "areas/intro/title_screen.json")

        with self.assertRaises(FileNotFoundError):
            run_editor._resolve_area_argument(project, "areas/intro/title_screen.json")

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
                "area_id": "village_square",
                "entry_id": "startup",
            },
        )
        handle.update(0.0)

        self.assertEqual(len(recorded_requests), 1)
        self.assertEqual(recorded_requests[0].area_id, "village_square")
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

        handle = execute_registered_command(
            registry,
            context,
            "change_area",
            {
                "area_id": "village_house",
                "entry_id": "from_square",
                "transfer_entity_ids": ["actor"],
                "camera_follow_entity_id": "actor",
                "camera_offset_x": 12,
                "camera_offset_y": -8,
                "actor_entity_id": "player",
            },
        )
        handle.update(0.0)

        self.assertEqual(len(recorded_requests), 1)
        request = recorded_requests[0]
        self.assertEqual(request.area_id, "village_house")
        self.assertEqual(request.entry_id, "from_square")
        self.assertEqual(request.transfer_entity_ids, ["player"])
        self.assertIsNotNone(request.camera_follow)
        assert request.camera_follow is not None
        self.assertEqual(request.camera_follow.mode, "entity")
        self.assertEqual(request.camera_follow.entity_id, "player")
        self.assertEqual(request.camera_follow.offset_x, 12.0)
        self.assertEqual(request.camera_follow.offset_y, -8.0)

    def test_editor_launcher_headless_without_picker_returns_none(self) -> None:
        _, project = self._make_project(
            areas={"test_room.json": _minimal_area()},
        )

        self.assertIsNone(run_editor._choose_area_id(None, project, None, allow_picker=False))

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
        title_area_path = project.resolve_area_reference("title_screen")
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
        title_area_path = project.resolve_area_reference("title_screen")
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
            startup_area="title_screen",
            areas={
                "title_screen.json": {
                    "name": "Title",
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [
                        {
                            "name": "ground",
                            "draw_above_entities": False,
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
                            "draw_above_entities": False,
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

        title_area_path = project.resolve_area_reference("title_screen")
        assert title_area_path is not None
        game = Game(area_path=title_area_path, project=project)
        self.addCleanup(pygame.quit)

        save_path = project.project_root / "saves" / "slot_1.json"
        game.persistence_runtime.save_data.globals["seen_intro"] = True
        game.persistence_runtime.set_save_path(save_path)
        game.request_new_game(AreaTransitionRequest(area_id="village_square"))
        game._apply_pending_new_game_if_idle()

        self.assertEqual(game.area.area_id, "village_square")
        self.assertEqual(game.persistence_runtime.save_data.globals, {})
        self.assertIsNone(game.persistence_runtime.save_path)
        self.assertIsNone(game.persistence_runtime.save_data.current_input_targets)

    def test_title_screen_dialogue_accepts_direction_and_confirm_input(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        title_area_path = project.resolve_area_reference("title_screen")
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

        self.assertEqual(game.area.area_id, "village_square")
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_title_screen_dialogue_held_direction_repeats_after_delay(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        title_area_path = project.resolve_area_reference("title_screen")
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

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        area_path = project.resolve_area_reference("village_square")
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

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        area_path = project.resolve_area_reference("village_square")
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

        self.assertTrue(player.movement.active)
        self.assertTrue(visual.animation_playback.active)
        self.assertIn(visual.current_frame, {1, 4, 7})
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_sample_player_position_snapshots_stay_lightweight(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        area_path = project.resolve_area_reference("village_square")
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

        while player.movement.active:
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

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        area_path = project.resolve_area_reference("village_square")
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
            walkable = (
                bool(cell_flags.get("walkable"))
                if isinstance(cell_flags, dict)
                else bool(cell_flags)
            )
            if not walkable:
                continue
            blocking_entities = [
                entity
                for entity in game.world.get_entities_at(
                    target_x,
                    target_y,
                    exclude_entity_id="player",
                    include_hidden=True,
                )
                if bool(entity.variables.get("blocks_movement"))
            ]
            if blocking_entities:
                continue
            selected_event_id = event_id
            break

        self.assertIsNotNone(selected_event_id)

        game.command_runner.enqueue(
            "run_event",
            entity_id="player",
            event_id=selected_event_id,
        )
        game._advance_simulation_tick(1 / 60)
        self.assertTrue(player.movement.active)

        for _ in range(4):
            game.command_runner.enqueue(
                "run_event",
                entity_id="player",
                event_id=selected_event_id,
            )
            game._advance_simulation_tick(1 / 60)

        for _ in range(24):
            game._advance_simulation_tick(1 / 60)

        self.assertIsNone(game.command_runner.last_error_notice)

    def test_sample_player_opposite_direction_during_walk_does_not_flip_mid_step(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        area_path = project.resolve_area_reference("village_square")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        player = game.world.get_entity("player")
        assert player is not None

        game.command_runner.enqueue(
            "run_event",
            entity_id="player",
            event_id="move_right",
        )
        game._advance_simulation_tick(1 / 60)

        visual = player.require_visual("body")
        self.assertTrue(player.movement.active)
        self.assertTrue(visual.flip_x)

        game.command_runner.enqueue(
            "run_event",
            entity_id="player",
            event_id="move_left",
        )
        game._advance_simulation_tick(1 / 60)

        self.assertTrue(player.movement.active)
        self.assertTrue(visual.flip_x)
        self.assertEqual(player.variables["direction"], "right")
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_dialogue_choice_window_scrolls_after_three_visible_rows(self) -> None:
        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        controller = instantiate_entity(
            {
                "id": "dialogue_controller",
                "template": "dialogue_panel",
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
                "run_named_command",
                {
                    "command_id": command_id,
                    "source_entity_id": "dialogue_controller",
                    **params,
                },
            )
            while not handle.complete:
                handle.update(0.0)

        _run_named("dialogue/render_choice")

        option_0 = context.screen_manager.get_element("dialogue_option_0")
        option_1 = context.screen_manager.get_element("dialogue_option_1")
        option_2 = context.screen_manager.get_element("dialogue_option_2")
        assert option_0 is not None
        assert option_1 is not None
        assert option_2 is not None
        self.assertEqual(option_0.text, ">One")
        self.assertEqual(option_1.text, " Two")
        self.assertEqual(option_2.text, " Three")

        _run_named("dialogue/move_selection", delta=1)
        _run_named("dialogue/move_selection", delta=1)
        _run_named("dialogue/move_selection", delta=1)

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
        area_path = project.resolve_area_reference("village_square")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        controller = game.world.get_entity("dialogue_controller")
        assert controller is not None

        game.command_runner.enqueue(
            "run_event",
            entity_id="dialogue_controller",
            event_id="open_dialogue",
            dialogue_path="dialogues/showcase/village_square_note.json",
            dialogue_on_start=[],
            dialogue_on_end=[],
            segment_hooks=[],
            allow_cancel=False,
            actor_entity_id="player",
            caller_entity_id="player",
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
        area_path = project.resolve_area_reference("village_house")
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
            "run_event",
            entity_id="house_lever",
            event_id="interact",
            actor_entity_id="player",
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
        self.assertFalse(gate.variables["blocks_movement"])
        self.assertEqual(lever.require_visual("main").tint, (150, 150, 150))
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_controller_owned_dialogue_restores_nested_snapshot_and_input_routes(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project_path = Path(__file__).resolve().parents[1] / "projects" / "test_project" / "project.json"
        project = load_project(project_path)
        area_path = project.resolve_area_reference("village_square")
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
            "run_sequence",
            commands=[
                {
                    "type": "run_event",
                    "entity_id": "dialogue_controller",
                    "event_id": "open_dialogue",
                    "dialogue_path": "dialogues/system/title_menu.json",
                    "dialogue_on_start": [],
                    "dialogue_on_end": [],
                    "segment_hooks": [],
                    "allow_cancel": False,
                },
                {
                    "type": "run_event",
                    "entity_id": "dialogue_controller",
                    "event_id": "open_dialogue",
                    "dialogue_path": "dialogues/system/save_prompt.json",
                    "dialogue_on_start": [],
                    "dialogue_on_end": [],
                    "segment_hooks": [],
                    "allow_cancel": True,
                },
            ],
            actor_entity_id="player",
            caller_entity_id="lever",
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
            "run_named_command",
            command_id="dialogue/close_current_dialogue",
            source_entity_id="dialogue_controller",
            actor_entity_id="player",
            caller_entity_id="lever",
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
            "run_named_command",
            command_id="dialogue/close_current_dialogue",
            source_entity_id="dialogue_controller",
            actor_entity_id="player",
            caller_entity_id="lever",
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
            startup_area="room_a",
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
                            "draw_above_entities": False,
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

        area_path = project.resolve_area_reference("room_a")
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
            base_params={"actor_entity_id": "player"},
        )

        self.assertTrue(handle.complete)
        for action in game.world.list_input_actions():
            self.assertEqual(game.world.get_input_target_id(action), "player")

        save_payload = json.loads(save_path.read_text(encoding="utf-8"))
        restored_save_data = save_data_from_dict(save_payload)

        self.assertNotIn("active_entity", save_payload)
        self.assertNotIn("input_route_stack", save_payload)
        self.assertIsNotNone(restored_save_data.current_input_targets)
        assert restored_save_data.current_input_targets is not None
        self.assertTrue(
            all(
                target_id == "player"
                for target_id in restored_save_data.current_input_targets.values()
            )
        )

    def test_load_game_restores_saved_input_targets(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        _, project = self._make_project(
            startup_area="room_a",
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
                            "draw_above_entities": False,
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

        area_path = project.resolve_area_reference("room_a")
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
        current_player.variables["direction"] = "right"
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
        self.assertEqual(restored_player.variables["direction"], "right")
        self.assertEqual(restored_visual.current_frame, 2)

    def test_runtime_token_lookup_rejects_removed_source_alias(self) -> None:
        context = CommandContext(
            area=Area(
                area_id="test_room",
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


    def test_run_event_propagates_caller_entity_id(self) -> None:
        _, project = self._make_project()
        caller = _make_runtime_entity("lever", kind="lever")
        controller = _make_runtime_entity(
            "dialogue_controller",
            kind="system",
            space="screen",
            scope="global",
            events={
                "open_dialogue": EntityEvent(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$caller_id",
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
            "run_event",
            {
                "entity_id": "dialogue_controller",
                "event_id": "open_dialogue",
                "actor_entity_id": "lever",
                "caller_entity_id": "lever",
            },
        )
        handle.update(0.0)

        self.assertTrue(world.get_entity("lever").variables["toggled"])  # type: ignore[index]

    def test_run_named_command_propagates_caller_entity_id(self) -> None:
        _, project = self._make_project(
            commands={
                "toggle_caller.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "set_entity_var",
                            "entity_id": "$caller_id",
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
            "run_named_command",
            {
                "command_id": "toggle_caller",
                "actor_entity_id": "lever",
                "caller_entity_id": "lever",
            },
        )
        handle.update(0.0)

        self.assertTrue(world.get_entity("lever").variables["toggled"])  # type: ignore[index]

    def test_run_sequence_propagates_caller_entity_id(self) -> None:
        _, project = self._make_project()
        caller = _make_runtime_entity("lever", kind="lever")
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "run_sequence",
            {
                "commands": [
                    {
                        "type": "set_entity_var",
                        "entity_id": "$caller_id",
                        "name": "toggled",
                        "value": True,
                    }
                ],
                "caller_entity_id": "lever",
            },
        )
        handle.update(0.0)

        self.assertTrue(world.get_entity("lever").variables["toggled"])  # type: ignore[index]

    def test_root_flows_run_independently_by_default(self) -> None:
        world = World()
        registry, context = self._make_command_context(world=world)
        runner = CommandRunner(registry, context)

        runner.enqueue(
            "run_sequence",
            commands=[
                {"type": "wait_frames", "frames": 1},
                {"type": "set_world_var", "name": "first_done", "value": True},
            ],
        )
        runner.enqueue(
            "run_sequence",
            commands=[
                {"type": "wait_frames", "frames": 1},
                {"type": "set_world_var", "name": "second_done", "value": True},
            ],
        )

        runner.update(1 / 60)

        self.assertTrue(world.variables["first_done"])
        self.assertTrue(world.variables["second_done"])
        self.assertFalse(runner.has_pending_work())

    def test_spawn_flow_returns_immediately_inside_run_sequence(self) -> None:
        world = World()
        registry, context = self._make_command_context(world=world)
        runner = CommandRunner(registry, context)

        runner.enqueue(
            "run_sequence",
            commands=[
                {
                    "type": "spawn_flow",
                    "commands": [
                        {"type": "wait_frames", "frames": 1},
                        {"type": "set_world_var", "name": "later", "value": True},
                    ],
                },
                {"type": "set_world_var", "name": "now", "value": True},
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
            "run_sequence",
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
                            "type": "run_sequence",
                            "commands": [
                                {"type": "wait_frames", "frames": 2},
                                {"type": "set_world_var", "name": "slow_done", "value": True},
                            ],
                        },
                    ],
                },
                {"type": "set_world_var", "name": "after_fast", "value": True},
            ],
        )

        runner.update(1 / 60)
        self.assertTrue(world.variables["after_fast"])
        self.assertNotIn("slow_done", world.variables)
        self.assertTrue(runner.has_pending_work())

        runner.update(1 / 60)
        self.assertTrue(world.variables["slow_done"])
        self.assertFalse(runner.has_pending_work())

    def test_set_entity_field_supports_caller_token_via_run_sequence(self) -> None:
        _, project = self._make_project()
        caller = _make_runtime_entity("lever", kind="lever", with_visual=True)
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "run_sequence",
            {
                "caller_entity_id": "lever",
                "commands": [
                    {
                        "type": "set_entity_field",
                        "entity_id": "$caller_id",
                        "field_name": "visuals.main.tint",
                        "value": [5, 6, 7],
                    }
                ],
            },
        )
        handle.update(0.0)

        caller_visual = world.get_entity("lever").require_visual("main")  # type: ignore[union-attr]
        self.assertEqual(caller_visual.tint, (5, 6, 7))

    def test_route_inputs_to_entity_command_supports_actor_token_via_run_sequence(self) -> None:
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
            "run_sequence",
            {
                "actor_entity_id": "player",
                "commands": [
                    {
                        "type": "route_inputs_to_entity",
                        "entity_id": "$actor_id",
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
                "set_input_target",
                {
                    "action": "interact",
                    "entity_id": "actor",
                },
            ),
            (
                "set_event_enabled",
                {
                    "entity_id": "caller",
                    "event_id": "interact",
                    "enabled": False,
                },
            ),
            (
                "set_camera_follow_entity",
                {
                    "entity_id": "actor",
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
                    "entity_id": "caller",
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
                self.assertIn("use '$self_id', '$actor_id', or '$caller_id'", str(raised.exception.__cause__))

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

    def test_animation_commands_accept_visual_id_and_caller_token_via_run_sequence(self) -> None:
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
            "run_sequence",
            {
                "caller_entity_id": "lever",
                "commands": [
                    {
                        "type": "play_animation",
                        "entity_id": "$caller_id",
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
            "run_sequence",
            {
                "caller_entity_id": "lever",
                "commands": [
                    {
                        "type": "wait_for_animation",
                        "entity_id": "$caller_id",
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

    def test_move_entity_world_position_supports_caller_token_via_run_sequence(self) -> None:
        caller = _make_runtime_entity("lever", kind="lever")
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(world=world)
        movement_system = _RecordingMovementSystem()
        context.movement_system = movement_system

        handle = execute_registered_command(
            registry,
            context,
            "run_sequence",
            {
                "caller_entity_id": "lever",
                "commands": [
                    {
                        "type": "move_entity_world_position",
                        "entity_id": "$caller_id",
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

    def test_set_camera_follow_entity_supports_caller_token_via_run_sequence(self) -> None:
        caller = _make_runtime_entity("lever", kind="lever")
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(world=world)
        camera = _RecordingCamera()
        context.camera = camera

        handle = execute_registered_command(
            registry,
            context,
            "run_sequence",
            {
                "caller_entity_id": "lever",
                "commands": [
                    {
                        "type": "set_camera_follow_entity",
                        "entity_id": "$caller_id",
                    }
                ],
            },
        )
        handle.update(0.0)

        self.assertEqual(camera.followed_entity_id, "lever")
        self.assertEqual(len(camera.update_calls), 1)
        self.assertIs(camera.update_calls[0][0], world)
        self.assertFalse(camera.update_calls[0][1])

    def test_set_camera_follow_input_target_tracks_routed_action(self) -> None:
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
            "set_camera_follow_input_target",
            {"action": "menu"},
        )
        handle.update(0.0)

        self.assertEqual(camera.follow_mode, "input_target")
        self.assertEqual(camera.follow_input_action, "menu")
        self.assertEqual(len(camera.update_calls), 1)
        self.assertIs(camera.update_calls[0][0], world)
        self.assertFalse(camera.update_calls[0][1])

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
                    "event_id": "confirm",
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
            "set_camera_bounds_rect",
            {
                "x": 1,
                "y": 2,
                "width": 3,
                "height": 4,
                "space": "grid",
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
            },
        )
        deadzone_handle.update(0.0)
        self.assertEqual(
            camera.deadzone,
            {"x": 8.0, "y": 12.0, "width": 24.0, "height": 30.0},
        )

        query_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_world_var",
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
                "type": "set_world_var",
                "name": "follow_target",
                "value": "$camera.follow_entity_id",
            },
        )
        follow_handle.update(0.0)
        self.assertIsNone(world.variables["follow_target"])

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
        area_path = project.resolve_area_reference("village_square")
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
        self.assertEqual(camera_state["follow_mode"], "entity")
        self.assertEqual(camera_state["follow_entity_id"], "player")
        self.assertEqual(camera_state["follow_offset_x"], 14.0)
        self.assertEqual(camera_state["follow_offset_y"], -6.0)
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
            area_id="room_a",
            name="Room A",
            tile_size=16,
            tilesets=[],
            tile_layers=[],
            cell_flags=[],
        )
        area_b = Area(
            area_id="room_b",
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
        self.assertEqual(restored_crate.origin_area_id, "room_a")
        self.assertEqual(restored_crate.origin_entity_id, "crate")

    def test_game_area_change_without_returning_traveler_suppresses_origin_placeholder(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        _, project = self._make_project(
            startup_area="room_a",
            areas={
                "room_a.json": {
                    "name": "Room A",
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [
                        {
                            "name": "ground",
                            "draw_above_entities": False,
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
                            "draw_above_entities": False,
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

        area_a_path = project.resolve_area_reference("room_a")
        assert area_a_path is not None
        game = Game(area_path=area_a_path, project=project)
        self.addCleanup(pygame.quit)

        crate = game.world.get_entity("crate")
        assert crate is not None
        crate.variables["moved"] = True

        game.request_area_change(
            AreaTransitionRequest(
                area_id="room_b",
                entry_id="landing",
                transfer_entity_ids=["crate"],
            )
        )
        game._apply_pending_area_change_if_idle()

        self.assertEqual(game.area.area_id, "room_b")
        moved_crate = game.world.get_entity("crate")
        assert moved_crate is not None
        self.assertEqual(moved_crate.grid_x, 2)
        self.assertEqual(moved_crate.grid_y, 0)
        self.assertTrue(moved_crate.variables["moved"])  # type: ignore[index]

        game.request_area_change(AreaTransitionRequest(area_id="room_a"))
        game._apply_pending_area_change_if_idle()

        self.assertEqual(game.area.area_id, "room_a")
        self.assertIsNone(game.world.get_entity("crate"))


if __name__ == "__main__":
    unittest.main()

