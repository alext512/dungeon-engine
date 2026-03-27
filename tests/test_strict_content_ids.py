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
    CommandExecutionError,
    CommandContext,
    SequenceCommandHandle,
    _resolve_runtime_values,
    execute_registered_command,
)
from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity, EntityEvent, EntityVisual
from dungeon_engine.world.world import World
from dungeon_engine.project import load_project
from dungeon_engine.world.loader import (
    AreaValidationError,
    EntityTemplateValidationError,
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

    def test_area_validation_rejects_removed_player_id_field(self) -> None:
        _, project = self._make_project(
            startup_area="test_room",
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "player_id": "player",
                }
            },
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("must not declare 'player_id'" in issue for issue in raised.exception.issues)
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

    def test_entity_template_validation_rejects_removed_run_dialogue_command(self) -> None:
        _, project = self._make_project(
            entity_templates={
                "legacy_sign.json": {
                    "kind": "sign",
                    "events": {
                        "interact": [
                            {
                                "type": "run_dialogue",
                                "dialogue_path": "dialogues/system/title_menu.json",
                            }
                        ]
                    },
                }
            }
        )

        with self.assertRaises(EntityTemplateValidationError) as raised:
            validate_project_entity_templates(project)

        self.assertTrue(
            any("uses removed command 'run_dialogue'" in issue for issue in raised.exception.issues)
        )

    def test_entity_template_validation_rejects_removed_set_camera_follow_player_command(self) -> None:
        _, project = self._make_project(
            entity_templates={
                "legacy_camera.json": {
                    "kind": "system",
                    "events": {
                        "activate": [
                            {
                                "type": "set_camera_follow_player",
                            }
                        ]
                    },
                }
            }
        )

        with self.assertRaises(EntityTemplateValidationError) as raised:
            validate_project_entity_templates(project)

        self.assertTrue(
            any(
                "uses removed command 'set_camera_follow_player'" in issue
                for issue in raised.exception.issues
            )
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

    def test_named_command_validation_rejects_on_complete(self) -> None:
        _, project = self._make_project(
            commands={
                "walk_one_tile.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "wait_frames",
                            "frames": 1,
                            "on_complete": [],
                        }
                    ],
                }
            }
        )

        with self.assertRaises(NamedCommandValidationError) as raised:
            validate_project_named_commands(project)

        self.assertTrue(
            any("must not use 'on_complete'" in issue for issue in raised.exception.issues)
        )

    def test_named_command_validation_rejects_removed_sprite_command(self) -> None:
        _, project = self._make_project(
            commands={
                "walk_one_tile.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "set_sprite_frame",
                            "entity_id": "self",
                            "frame": 1,
                        }
                    ],
                }
            }
        )

        with self.assertRaises(NamedCommandValidationError) as raised:
            validate_project_named_commands(project)

        self.assertTrue(
            any("uses removed command 'set_sprite_frame'" in issue for issue in raised.exception.issues)
        )

    def test_named_command_validation_rejects_removed_set_camera_follow_player_command(self) -> None:
        _, project = self._make_project(
            commands={
                "follow_camera.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "set_camera_follow_player",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(NamedCommandValidationError) as raised:
            validate_project_named_commands(project)

        self.assertTrue(
            any(
                "uses removed command 'set_camera_follow_player'" in issue
                for issue in raised.exception.issues
            )
        )

    def test_named_command_validation_rejects_removed_set_var_from_camera_command(self) -> None:
        _, project = self._make_project(
            commands={
                "camera_query.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "set_var_from_camera",
                            "scope": "world",
                            "name": "camera_x",
                            "field": "x",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(NamedCommandValidationError) as raised:
            validate_project_named_commands(project)

        self.assertTrue(
            any(
                "uses removed command 'set_var_from_camera'" in issue
                for issue in raised.exception.issues
            )
        )

    def test_named_command_validation_rejects_removed_broad_variable_commands(self) -> None:
        for command_name in (
            "set_var",
            "increment_var",
            "set_var_length",
            "append_to_var",
            "pop_var",
            "set_var_from_collection_item",
            "check_var",
        ):
            with self.subTest(command_name=command_name):
                _, project = self._make_project(
                    commands={
                        "legacy_var.json": {
                            "params": [],
                            "commands": [{"type": command_name}],
                        }
                    }
                )

                with self.assertRaises(NamedCommandValidationError) as raised:
                    validate_project_named_commands(project)

                self.assertTrue(
                    any(
                        f"uses removed command '{command_name}'" in issue
                        for issue in raised.exception.issues
                    )
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

    def test_set_var_from_json_file_loads_project_relative_dialogue_data(self) -> None:
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

        handle = execute_registered_command(
            registry,
            context,
            "set_var_from_json_file",
            {
                "scope": "entity",
                "entity_id": "dialogue_controller",
                "name": "dialogue_definition",
                "path": "dialogues/menus/test.json",
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

    def test_entity_template_validation_rejects_removed_start_dialogue_session_command(self) -> None:
        _, project = self._make_project(
            entity_templates={
                "legacy_sign.json": {
                    "kind": "sign",
                    "events": {
                        "interact": [
                            {
                                "type": "start_dialogue_session",
                                "dialogue_path": "dialogues/system/title_menu.json",
                            }
                        ]
                    },
                }
            }
        )

        with self.assertRaises(EntityTemplateValidationError) as raised:
            validate_project_entity_templates(project)

        self.assertTrue(
            any("uses removed command 'start_dialogue_session'" in issue for issue in raised.exception.issues)
        )

    def test_removed_text_session_commands_raise_clear_runtime_errors(self) -> None:
        registry, context = self._make_command_context()
        for command_name in (
            "prepare_text_session",
            "read_text_session",
            "advance_text_session",
            "reset_text_session",
        ):
            with self.assertRaises(CommandExecutionError) as raised:
                execute_registered_command(registry, context, command_name, {})
            self.assertIsNotNone(raised.exception.__cause__)
            self.assertIn("was removed", str(raised.exception.__cause__))

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
            self.assertIn("was removed", str(raised.exception.__cause__))

    def test_set_var_from_wrapped_lines_and_text_window_store_visible_text(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("dialogue_controller", kind="system", space="screen"))
        registry, context = self._make_command_context(world=world)
        context.text_renderer = _StubTextRenderer()

        wrapped_handle = execute_registered_command(
            registry,
            context,
            "set_var_from_wrapped_lines",
            {
                "scope": "entity",
                "entity_id": "dialogue_controller",
                "name": "wrapped_lines",
                "text": "one two three four",
                "max_width": 64,
            },
        )
        wrapped_handle.update(0.0)
        controller = world.get_entity("dialogue_controller")
        assert controller is not None

        window_handle = execute_registered_command(
            registry,
            context,
            "set_var_from_text_window",
            {
                "scope": "entity",
                "entity_id": "dialogue_controller",
                "name": "visible_text",
                "lines": controller.variables["wrapped_lines"],
                "start": 1,
                "max_lines": 2,
                "store_has_more_var": "has_more",
                "store_total_var": "total_lines",
            },
        )
        window_handle.update(0.0)

        self.assertEqual(controller.variables["wrapped_lines"], ["one", "two", "three", "four"])
        self.assertEqual(controller.variables["visible_text"], "two\nthree")
        self.assertTrue(controller.variables["has_more"])
        self.assertEqual(controller.variables["total_lines"], 4)

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
        execute_registered_command(
            registry,
            context,
            "set_entity_var_from_collection_item",
            {
                "entity_id": "dialogue_controller",
                "name": "selected_option",
                "value": [
                    {"option_id": "new_game"},
                    {"option_id": "load_game"},
                ],
                "index": 1,
                "default": {},
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
        execute_registered_command(
            registry,
            context,
            "set_world_var_from_collection_item",
            {
                "name": "latest_room",
                "value": context.world.variables["visited_rooms"],
                "index": 1,
                "default": "",
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

    def test_area_validation_rejects_removed_run_dialogue_command(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "run_dialogue",
                            "dialogue_path": "dialogues/system/title_menu.json",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("uses removed command 'run_dialogue'" in issue for issue in raised.exception.issues)
        )

    def test_area_validation_rejects_removed_set_camera_follow_player_command(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "set_camera_follow_player",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "uses removed command 'set_camera_follow_player'" in issue
                for issue in raised.exception.issues
            )
        )

    def test_area_validation_rejects_removed_set_var_from_camera_command(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "set_var_from_camera",
                            "scope": "world",
                            "name": "camera_x",
                            "field": "x",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("uses removed command 'set_var_from_camera'" in issue for issue in raised.exception.issues)
        )

    def test_area_validation_rejects_removed_if_var_command(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "if_var",
                            "scope": "entity",
                            "entity_id": "self",
                            "name": "seen",
                            "then": [],
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("uses removed command 'if_var'" in issue for issue in raised.exception.issues)
        )

    def test_area_validation_rejects_removed_broad_variable_commands(self) -> None:
        for command_name in (
            "set_var",
            "increment_var",
            "set_var_length",
            "append_to_var",
            "pop_var",
            "set_var_from_collection_item",
            "check_var",
        ):
            with self.subTest(command_name=command_name):
                _, project = self._make_project(
                    areas={
                        "test_room.json": {
                            **_minimal_area(),
                            "enter_commands": [{"type": command_name}],
                        }
                    }
                )

                with self.assertRaises(AreaValidationError) as raised:
                    validate_project_areas(project)

                self.assertTrue(
                    any(
                        f"uses removed command '{command_name}'" in issue
                        for issue in raised.exception.issues
                    )
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

    def test_area_validation_rejects_on_complete_in_entity_event(self) -> None:
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
                            "events": {
                                "interact": {
                                    "commands": [
                                        {
                                            "type": "wait_frames",
                                            "frames": 1,
                                            "on_complete": [],
                                        }
                                    ]
                                }
                            },
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("must not use 'on_complete'" in issue for issue in raised.exception.issues)
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
        self.assertFalse(gate.solid)
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
            "run_commands",
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
        current_player.facing = "right"
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
        self.assertEqual(restored_player.facing, "right")
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

    def test_run_commands_propagates_caller_entity_id(self) -> None:
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

    def test_set_entity_field_supports_caller_token_via_run_commands(self) -> None:
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

    def test_route_inputs_to_entity_command_supports_actor_token_via_run_commands(self) -> None:
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

    def test_animation_commands_accept_visual_id_and_caller_reference(self) -> None:
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
            "play_animation",
            {
                "entity_id": "caller",
                "caller_entity_id": "lever",
                "visual_id": "main",
                "frame_sequence": [1, 2, 3],
                "frames_per_sprite_change": 2,
                "hold_last_frame": False,
                "wait": False,
            },
        )
        play_handle.update(0.0)

        wait_handle = execute_registered_command(
            registry,
            context,
            "wait_for_animation",
            {
                "entity_id": "caller",
                "caller_entity_id": "lever",
                "visual_id": "main",
            },
        )
        wait_handle.update(0.0)

        self.assertEqual(
            animation_system.started,
            [("lever", [1, 2, 3], "main", 2, False)],
        )
        self.assertEqual(animation_system.queries, [("lever", "main")])

    def test_set_camera_follow_entity_supports_caller_token_via_run_commands(self) -> None:
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
        self.assertIn("set_camera_follow_player is removed", str(raised.exception.__cause__))

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
        self.assertIn("set_var_from_camera was removed", str(raised.exception.__cause__))

    def test_camera_bounds_deadzone_and_query_commands(self) -> None:
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

        query_handle = execute_registered_command(
            registry,
            context,
            "set_world_var_from_camera",
            {
                "name": "camera_bounds",
                "field": "bounds",
            },
        )
        query_handle.update(0.0)
        self.assertEqual(
            world.variables["camera_bounds"],
            {"x": 16.0, "y": 32.0, "width": 48.0, "height": 64.0},
        )

        entity_query_handle = execute_registered_command(
            registry,
            context,
            "set_entity_var_from_camera",
            {
                "entity_id": "player",
                "name": "camera_has_bounds",
                "field": "has_bounds",
            },
        )
        entity_query_handle.update(0.0)

        player = world.get_entity("player")
        assert player is not None
        self.assertTrue(player.variables["camera_has_bounds"])

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
                "entity_id": "self",
                "source_entity_id": "lever",
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
                "entity_id": "self",
                "source_entity_id": "lever",
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
