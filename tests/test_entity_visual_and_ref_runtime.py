from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import (
    CommandContext,
    CommandExecutionError,
    execute_registered_command,
)
from dungeon_engine.project_context import load_project
from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity, EntityVisual
from dungeon_engine.world.world import World


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _minimal_runtime_area() -> Area:
    return Area(
        area_id="areas/test_room",
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
        self.move_by_offsets: list[
            tuple[str, float, float, float | None, int | None, float | None, str, int | None, int | None]
        ] = []

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
        persistent: bool | None = None,
    ) -> list[str]:
        _ = persistent
        self.move_by_offsets.append(
            (entity_id, x, y, duration, frames_needed, speed_px_per_second, grid_sync, target_grid_x, target_grid_y)
        )
        return [entity_id]


class _RecordingCamera:
    def follow_entity(
        self,
        entity_id: str,
        *,
        offset_x: float = 0.0,
        offset_y: float = 0.0,
    ) -> None:
        _ = (entity_id, offset_x, offset_y)


class EntityVisualAndRefRuntimeTests(unittest.TestCase):
    def _make_project(self) -> tuple[Path, object]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        project_root = Path(temp_dir.name)

        _write_json(
            project_root / "project.json",
            {
                "area_paths": ["areas/"],
                "entity_template_paths": ["entity_templates/"],
                "command_paths": ["commands/"],
                "item_paths": ["items/"],
                "shared_variables_path": "shared_variables.json",
            },
        )
        _write_json(project_root / "shared_variables.json", {})

        return project_root, load_project(project_root / "project.json")

    def _make_command_context(
        self,
        *,
        project: object | None = None,
        world: World | None = None,
    ) -> tuple[CommandRegistry, CommandContext]:
        registry = CommandRegistry()
        register_builtin_commands(registry)
        context = CommandContext(
            area=_minimal_runtime_area(),
            world=world or World(),
            collision_system=None,  # type: ignore[arg-type]
            movement_system=None,  # type: ignore[arg-type]
            interaction_system=None,  # type: ignore[arg-type]
            animation_system=None,  # type: ignore[arg-type]
            project=project,
        )
        return registry, context

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
