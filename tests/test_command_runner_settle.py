from __future__ import annotations

import unittest

from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.context_services import build_command_services
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import CommandContext, CommandRunner, ImmediateHandle
from dungeon_engine.world.area import Area
from dungeon_engine.world.world import World


def _minimal_runtime_area() -> Area:
    return Area(
        area_id="areas/test_room",
        tile_size=16,
        tilesets=[],
        tile_layers=[],
        cell_flags=[],
    )


class CommandRunnerSettleTests(unittest.TestCase):
    def _make_runner(
        self,
        *,
        max_settle_passes: int = 128,
        max_immediate_commands_per_settle: int = 8192,
    ) -> tuple[CommandRunner, World]:
        registry = CommandRegistry()
        register_builtin_commands(registry)
        world = World()
        context = CommandContext(
            project=None,
            services=build_command_services(
                area=_minimal_runtime_area(),
                world=world,
                collision_system=None,
                movement_system=None,
                interaction_system=None,
                animation_system=None,
            ),
        )
        runner = CommandRunner(
            registry,
            context,
            max_settle_passes=max_settle_passes,
            max_immediate_commands_per_settle=max_immediate_commands_per_settle,
        )
        return runner, world

    def test_settle_runs_immediate_sequence_to_completion(self) -> None:
        runner, world = self._make_runner()

        runner.enqueue(
            "run_sequence",
            commands=[
                {"type": "set_current_area_var", "name": "a", "value": True},
                {"type": "set_current_area_var", "name": "b", "value": True},
            ],
        )

        runner.settle()

        self.assertTrue(world.variables["a"])
        self.assertTrue(world.variables["b"])
        self.assertFalse(runner.has_pending_work())

    def test_settle_does_not_advance_wait_frames(self) -> None:
        runner, world = self._make_runner()

        runner.enqueue(
            "run_sequence",
            commands=[
                {"type": "wait_frames", "frames": 1},
                {"type": "set_current_area_var", "name": "done", "value": True},
            ],
        )

        runner.settle()
        runner.settle()

        self.assertNotIn("done", world.variables)
        self.assertTrue(runner.has_pending_work())

        runner.advance_tick(1 / 60)
        runner.settle()

        self.assertTrue(world.variables["done"])
        self.assertFalse(runner.has_pending_work())

    def test_settle_does_not_advance_wait_seconds(self) -> None:
        runner, world = self._make_runner()

        runner.enqueue(
            "run_sequence",
            commands=[
                {"type": "wait_seconds", "seconds": 0.1},
                {"type": "set_current_area_var", "name": "done", "value": True},
            ],
        )

        runner.settle()
        runner.settle()

        self.assertNotIn("done", world.variables)
        self.assertTrue(runner.has_pending_work())

        runner.advance_tick(0.2)
        runner.settle()

        self.assertTrue(world.variables["done"])
        self.assertFalse(runner.has_pending_work())

    def test_spawn_flow_starts_child_and_parent_immediately(self) -> None:
        runner, world = self._make_runner()

        runner.enqueue(
            "run_sequence",
            commands=[
                {
                    "type": "spawn_flow",
                    "commands": [
                        {
                            "type": "set_current_area_var",
                            "name": "child_started",
                            "value": True,
                        },
                        {"type": "wait_frames", "frames": 1},
                        {
                            "type": "set_current_area_var",
                            "name": "child_done",
                            "value": True,
                        },
                    ],
                },
                {
                    "type": "set_current_area_var",
                    "name": "parent_continued",
                    "value": True,
                },
            ],
        )

        runner.settle()

        self.assertTrue(world.variables["child_started"])
        self.assertTrue(world.variables["parent_continued"])
        self.assertNotIn("child_done", world.variables)
        self.assertTrue(runner.has_pending_work())

        runner.advance_tick(1 / 60)
        runner.settle()

        self.assertTrue(world.variables["child_done"])
        self.assertFalse(runner.has_pending_work())

    def test_settle_runs_spawned_immediate_children_until_waiting(self) -> None:
        runner, world = self._make_runner()

        runner.enqueue(
            "run_sequence",
            commands=[
                {
                    "type": "wait_frames",
                    "frames": 1,
                },
                {
                    "type": "spawn_flow",
                    "commands": [
                        {
                            "type": "set_current_area_var",
                            "name": "spawned_immediate",
                            "value": True,
                        },
                        {"type": "wait_frames", "frames": 1},
                        {
                            "type": "set_current_area_var",
                            "name": "spawned_later",
                            "value": True,
                        },
                    ],
                },
            ],
        )

        runner.settle()
        self.assertNotIn("spawned_immediate", world.variables)

        runner.advance_tick(1 / 60)
        runner.settle()

        self.assertTrue(world.variables["spawned_immediate"])
        self.assertNotIn("spawned_later", world.variables)

    def test_safety_limit_errors_instead_of_deferring_ready_work(self) -> None:
        registry = CommandRegistry()
        register_builtin_commands(registry)

        world = World()
        context = CommandContext(
            project=None,
            services=build_command_services(
                area=_minimal_runtime_area(),
                world=world,
                collision_system=None,
                movement_system=None,
                interaction_system=None,
                animation_system=None,
            ),
        )
        runner = CommandRunner(
            registry,
            context,
            max_settle_passes=16,
            max_immediate_commands_per_settle=5,
        )

        @registry.register("enqueue_self")
        def enqueue_self(context: CommandContext, **_: object):
            context.command_runner.enqueue("enqueue_self")
            return ImmediateHandle()

        runner.enqueue("enqueue_self")

        runner.settle()

        self.assertEqual(runner.last_error_notice, "Command error: see logs/error.log")
        self.assertFalse(runner.has_pending_work())

    def test_scene_boundary_stops_following_sequence_commands(self) -> None:
        registry = CommandRegistry()
        register_builtin_commands(registry)

        world = World()
        context = CommandContext(
            project=None,
            services=build_command_services(
                area=_minimal_runtime_area(),
                world=world,
                collision_system=None,
                movement_system=None,
                interaction_system=None,
                animation_system=None,
            ),
        )
        runner = CommandRunner(registry, context)

        @registry.register("request_scene_boundary")
        def request_scene_boundary(context: CommandContext, **_: object):
            context.command_runner.request_scene_boundary()
            return ImmediateHandle()

        runner.enqueue(
            "run_sequence",
            commands=[
                {"type": "set_current_area_var", "name": "before", "value": True},
                {"type": "request_scene_boundary"},
                {"type": "set_current_area_var", "name": "after", "value": True},
            ],
        )

        runner.settle()

        self.assertTrue(world.variables["before"])
        self.assertNotIn("after", world.variables)
        self.assertTrue(runner.scene_boundary_requested)
        self.assertFalse(runner.has_pending_work())


if __name__ == "__main__":
    unittest.main()
