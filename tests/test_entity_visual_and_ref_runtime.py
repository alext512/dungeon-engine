from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.context_services import CommandUiServices, build_command_services
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import (
    CommandContext,
    CommandExecutionError,
    execute_registered_command,
)
from dungeon_engine.project_context import load_project
from dungeon_engine.systems.animation import AnimationSystem
from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity, EntityVisual, VisualAnimationClip
from dungeon_engine.world.loader_entities import instantiate_entity
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
                animations={
                    "open": VisualAnimationClip(frames=[1, 2, 3]),
                },
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
        self.started: list[tuple[str, str, str | None, int | None, int | None]] = []
        self.queries: list[tuple[str, str | None]] = []

    def play_animation(
        self,
        entity_id: str,
        animation_id: str,
        *,
        visual_id: str | None = None,
        frame_count: int | None = None,
        duration_ticks: int | None = None,
    ) -> bool:
        self.started.append(
            (
                entity_id,
                animation_id,
                visual_id,
                frame_count,
                duration_ticks,
            )
        )
        return True

    def is_entity_animating(self, entity_id: str, *, visual_id: str | None = None) -> bool:
        self.queries.append((entity_id, visual_id))
        return False


class _RecordingMovementSystem:
    def __init__(self) -> None:
        self.grid_positions: list[tuple[str, int, int, bool | None]] = []
        self.pixel_positions: list[tuple[str, float, float, bool | None]] = []
        self.move_by_offsets: list[
            tuple[str, float, float, float | None, int | None, float | None, str, int | None, int | None]
        ] = []

    def set_grid_position(
        self,
        entity_id: str,
        x: int,
        y: int,
        *,
        persistent: bool | None = None,
    ) -> None:
        self.grid_positions.append((entity_id, x, y, persistent))

    def set_pixel_position(
        self,
        entity_id: str,
        x: float,
        y: float,
        *,
        persistent: bool | None = None,
    ) -> None:
        self.pixel_positions.append((entity_id, x, y, persistent))

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
            project=project,
            services=build_command_services(
                area=_minimal_runtime_area(),
                world=world or World(),
                collision_system=None,
                movement_system=None,
                interaction_system=None,
                animation_system=None,
            ),
        )
        context.services.ui = CommandUiServices()
        return registry, context

    def test_strict_entity_primitives_reject_raw_symbolic_entity_refs(self) -> None:
        world = World(
            default_input_routes={
                "interact": {"entity_id": "player", "command_id": "interact"}
            }
        )
        world.add_entity(_make_runtime_entity("player", kind="player", with_visual=True))
        registry, context = self._make_command_context(world=world)
        context.services.world.movement_system = _RecordingMovementSystem()
        context.services.ui.camera = _RecordingCamera()

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
                "set_input_route",
                {
                    "action": "interact",
                    "entity_id": "self",
                    "command_id": "interact",
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
                "play_animation",
                {
                    "entity_id": "self",
                    "visual_id": "main",
                    "animation": "idle",
                },
            ),
            (
                "move_entity_position",
                {
                    "entity_id": "self",
                    "space": "world_pixel",
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

    def test_removed_entity_position_commands_raise_unknown_command(self) -> None:
        registry, context = self._make_command_context()

        for command_name in (
            "set_entity_grid_position",
            "set_entity_world_position",
            "set_entity_screen_position",
            "move_entity_world_position",
            "move_entity_screen_position",
        ):
            with self.subTest(command_name=command_name):
                with self.assertRaises(CommandExecutionError) as raised:
                    execute_registered_command(registry, context, command_name, {})
                self.assertIsNotNone(raised.exception.__cause__)
                self.assertIn(f"Unknown command '{command_name}'", str(raised.exception.__cause__))

    def test_removed_visual_shortcut_commands_raise_unknown_command(self) -> None:
        registry, context = self._make_command_context()

        for command_name in ("set_visual_frame", "set_visual_flip_x"):
            with self.subTest(command_name=command_name):
                with self.assertRaises(CommandExecutionError) as raised:
                    execute_registered_command(registry, context, command_name, {})
                self.assertIsNotNone(raised.exception.__cause__)
                self.assertIn(f"Unknown command '{command_name}'", str(raised.exception.__cause__))

    def test_animation_commands_accept_visual_id_and_named_ref_via_run_sequence(self) -> None:
        _, project = self._make_project()
        caller = _make_runtime_entity("lever", kind="lever", with_visual=True)
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)
        animation_system = _RecordingAnimationSystem()
        context.services.world.animation_system = animation_system

        play_handle = execute_registered_command(
            registry,
            context,
            "run_sequence",
            {
                "entity_refs": {
                    "caller": "lever",
                },
                "commands": [
                    {
                        "type": "play_animation",
                        "entity_id": "$ref_ids.caller",
                        "visual_id": "main",
                        "animation": "open",
                        "frame_count": 2,
                        "duration_ticks": 8,
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
            [("lever", "open", "main", 2, 8)],
        )
        self.assertEqual(animation_system.queries, [("lever", "main")])

    def test_set_entity_position_routes_by_space(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("crate", kind="crate"))
        world.add_entity(_make_runtime_entity("logo", kind="ui", space="screen"))
        registry, context = self._make_command_context(world=world)
        movement_system = _RecordingMovementSystem()
        context.services.world.movement_system = movement_system

        execute_registered_command(
            registry,
            context,
            "set_entity_position",
            {
                "entity_id": "crate",
                "space": "world_grid",
                "x": 3,
                "y": 4,
                "persistent": True,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_entity_position",
            {
                "entity_id": "logo",
                "space": "screen_pixel",
                "x": 12.5,
                "y": 8,
                "mode": "relative",
                "persistent": False,
            },
        ).update(0.0)

        self.assertEqual(movement_system.grid_positions, [("crate", 3, 4, True)])
        self.assertEqual(movement_system.pixel_positions, [("logo", 12.5, 8.0, False)])

    def test_animation_system_plays_named_clips_with_duration_and_phase(self) -> None:
        visual = EntityVisual(
            visual_id="body",
            path="assets/project/sprites/player.png",
            frame_width=16,
            frame_height=16,
            frames=[0],
            animations={
                "idle_left": VisualAnimationClip(frames=[2], flip_x=True),
                "walk_down": VisualAnimationClip(frames=[0, 3, 6, 3], preserve_phase=True),
            },
        )
        player = Entity(
            entity_id="player",
            kind="player",
            grid_x=0,
            grid_y=0,
            visuals=[visual],
        )
        world = World()
        world.add_entity(player)
        animation_system = AnimationSystem(world)

        self.assertTrue(
            animation_system.play_animation(
                "player",
                "walk_down",
                visual_id="body",
                frame_count=2,
                duration_ticks=4,
            )
        )
        self.assertEqual(visual.current_frame, 0)
        self.assertEqual(visual.animations["walk_down"].phase_index, 2)

        for _ in range(4):
            animation_system.update_tick(0.0)
        self.assertEqual(visual.current_frame, 3)
        self.assertTrue(animation_system.is_entity_animating("player", visual_id="body"))

        animation_system.update_tick(0.0)
        self.assertEqual(visual.current_frame, 3)
        self.assertFalse(animation_system.is_entity_animating("player", visual_id="body"))

        animation_system.play_animation(
            "player",
            "walk_down",
            visual_id="body",
            frame_count=2,
            duration_ticks=4,
        )
        self.assertEqual(visual.current_frame, 6)
        self.assertEqual(visual.animations["walk_down"].phase_index, 0)

        self.assertFalse(
            animation_system.play_animation("player", "idle_left", visual_id="body")
        )
        self.assertEqual(visual.current_frame, 2)
        self.assertTrue(visual.flip_x)
        self.assertFalse(animation_system.is_entity_animating("player", visual_id="body"))

    def test_instantiate_entity_applies_facing_specific_default_animation(self) -> None:
        _, project = self._make_project()
        entity = instantiate_entity(
            {
                "id": "npc",
                "kind": "npc",
                "grid_x": 1,
                "grid_y": 2,
                "facing": "left",
                "visuals": [
                    {
                        "id": "body",
                        "path": "assets/project/sprites/npc.png",
                        "frame_width": 16,
                        "frame_height": 16,
                        "default_animation": "idle_down",
                        "default_animation_by_facing": {
                            "left": "idle_left",
                            "right": "idle_right",
                        },
                        "animations": {
                            "idle_down": {"frames": [0]},
                            "idle_left": {"frames": [2], "flip_x": True},
                            "idle_right": {"frames": [2], "flip_x": False},
                        },
                    }
                ],
            },
            16,
            project=project,
            source_name="test npc",
        )

        visual = entity.require_visual("body")
        self.assertEqual(entity.facing, "left")
        self.assertEqual(visual.current_frame, 2)
        self.assertTrue(visual.flip_x)

    def test_animation_system_preserves_facing_specific_default_visual_state(self) -> None:
        visual = EntityVisual(
            visual_id="body",
            path="assets/project/sprites/npc.png",
            frame_width=16,
            frame_height=16,
            frames=[0],
            animation_fps=0.0,
            default_animation="idle_down",
            default_animation_by_facing={
                "up": "idle_up",
                "down": "idle_down",
            },
            animations={
                "idle_down": VisualAnimationClip(frames=[0]),
                "idle_up": VisualAnimationClip(frames=[1]),
            },
        )
        npc = Entity(
            entity_id="npc",
            kind="npc",
            grid_x=0,
            grid_y=0,
            facing="up",
            visuals=[visual],
        )
        npc.apply_default_visual_state()
        world = World()
        world.add_entity(npc)
        animation_system = AnimationSystem(world)

        animation_system.update_tick(0.0)

        self.assertEqual(npc.require_visual("body").current_frame, 1)

    def test_move_entity_position_supports_named_ref_via_run_sequence(self) -> None:
        caller = _make_runtime_entity("lever", kind="lever")
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(world=world)
        movement_system = _RecordingMovementSystem()
        context.services.world.movement_system = movement_system

        handle = execute_registered_command(
            registry,
            context,
            "run_sequence",
            {
                "entity_refs": {
                    "caller": "lever",
                },
                "commands": [
                    {
                        "type": "move_entity_position",
                        "entity_id": "$ref_ids.caller",
                        "space": "world_pixel",
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

    def test_set_entity_field_updates_visual_frame(self) -> None:
        _, project = self._make_project()
        caller = _make_runtime_entity("lever", kind="lever", with_visual=True)
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "set_entity_field",
            {
                "entity_id": "lever",
                "field_name": "visuals.main.current_frame",
                "value": 2,
            },
        )
        handle.update(0.0)

        self.assertEqual(world.get_entity("lever").require_visual("main").current_frame, 2)  # type: ignore[union-attr]

    def test_set_entity_field_updates_visual_flip_x(self) -> None:
        _, project = self._make_project()
        caller = _make_runtime_entity("lever", kind="lever", with_visual=True)
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "set_entity_field",
            {
                "entity_id": "lever",
                "field_name": "visuals.main.flip_x",
                "value": True,
            },
        )
        handle.update(0.0)

        self.assertTrue(world.get_entity("lever").require_visual("main").flip_x)  # type: ignore[union-attr]
