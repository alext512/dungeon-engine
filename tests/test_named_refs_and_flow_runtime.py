from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import (
    CommandContext,
    CommandRunner,
    execute_registered_command,
)
from dungeon_engine.project_context import load_project
from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity, EntityCommandDefinition, EntityVisual
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


class NamedRefsAndFlowRuntimeTests(unittest.TestCase):
    def _make_project(
        self,
        *,
        commands: dict[str, dict[str, object]] | None = None,
    ) -> tuple[Path, object]:
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

        for relative_path, command_payload in (commands or {}).items():
            _write_json(project_root / "commands" / relative_path, command_payload)

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

    def test_run_project_command_can_compute_entity_field_values_from_params(self) -> None:
        _, project = self._make_project(
            commands={
                "player/move_one_tile.json": {
                    "params": ["direction", "facing_visual"],
                    "commands": [
                        {
                            "type": "set_entity_fields",
                            "entity_id": "$self_id",
                            "set": {
                                "visuals": {
                                    "down": {
                                        "visible": {
                                            "$any_in_collection": {
                                                "value": ["$facing_visual"],
                                                "op": "eq",
                                                "match": "down",
                                            }
                                        },
                                        "current_frame": 0,
                                    },
                                    "up": {
                                        "visible": {
                                            "$any_in_collection": {
                                                "value": ["$facing_visual"],
                                                "op": "eq",
                                                "match": "up",
                                            }
                                        },
                                        "current_frame": 1,
                                    },
                                    "side": {
                                        "visible": {
                                            "$any_in_collection": {
                                                "value": ["$facing_visual"],
                                                "op": "eq",
                                                "match": "side",
                                            }
                                        },
                                        "current_frame": 2,
                                        "flip_x": {
                                            "$any_in_collection": {
                                                "value": ["$direction"],
                                                "op": "eq",
                                                "match": "left",
                                            }
                                        },
                                    },
                                }
                            },
                        }
                    ],
                }
            }
        )
        player = Entity(
            entity_id="player",
            kind="player",
            grid_x=0,
            grid_y=0,
            visuals=[
                EntityVisual(
                    visual_id="down",
                    path="assets/project/sprites/test.png",
                    frame_width=16,
                    frame_height=16,
                    frames=[0],
                    visible=True,
                ),
                EntityVisual(
                    visual_id="up",
                    path="assets/project/sprites/test.png",
                    frame_width=16,
                    frame_height=16,
                    frames=[1],
                    visible=False,
                ),
                EntityVisual(
                    visual_id="side",
                    path="assets/project/sprites/test.png",
                    frame_width=16,
                    frame_height=16,
                    frames=[2],
                    visible=False,
                    flip_x=False,
                ),
            ],
        )
        world = World()
        world.add_entity(player)
        registry, context = self._make_command_context(project=project, world=world)

        left_handle = execute_registered_command(
            registry,
            context,
            "run_project_command",
            {
                "command_id": "commands/player/move_one_tile",
                "source_entity_id": "player",
                "direction": "left",
                "facing_visual": "side",
            },
        )
        left_handle.update(0.0)

        self.assertFalse(player.require_visual("down").visible)
        self.assertFalse(player.require_visual("up").visible)
        self.assertTrue(player.require_visual("side").visible)
        self.assertTrue(player.require_visual("side").flip_x)

        up_handle = execute_registered_command(
            registry,
            context,
            "run_project_command",
            {
                "command_id": "commands/player/move_one_tile",
                "source_entity_id": "player",
                "direction": "up",
                "facing_visual": "up",
            },
        )
        up_handle.update(0.0)

        self.assertFalse(player.require_visual("down").visible)
        self.assertTrue(player.require_visual("up").visible)
        self.assertFalse(player.require_visual("side").visible)
        self.assertFalse(player.require_visual("side").flip_x)

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
