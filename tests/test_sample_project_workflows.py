from __future__ import annotations

import unittest
from pathlib import Path

from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.context_services import build_command_services
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import CommandContext, execute_registered_command
from dungeon_engine.engine.screen import ScreenElementManager
from dungeon_engine.inventory import inventory_item_count
from dungeon_engine.items import load_item_definition
from dungeon_engine.project_context import load_project
from dungeon_engine.world.loader import load_area


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _complete_handle(test_case: unittest.TestCase, handle: object, *, max_steps: int = 32) -> None:
    for _ in range(max_steps):
        if getattr(handle, "complete", False):
            return
        handle.update(0.0)
    test_case.fail("Command handle did not complete within the expected number of steps.")


class SampleProjectWorkflowTests(unittest.TestCase):
    def test_new_project_pickup_and_item_use_workflow_executes(self) -> None:
        project_root = _repo_root() / "projects" / "new_project"
        if not (project_root / "project.json").is_file():
            self.skipTest(
                "Optional repo-local integration fixture 'new_project' is not available in this worktree."
            )

        project = load_project(project_root / "project.json")
        item = load_item_definition(project, "items/consumables/glimmer_berry")
        self.assertEqual(item.name, "Glimmer Berry")
        self.assertEqual(item.consume_quantity_on_use, 1)

        area_path = project.find_area_by_id("areas/start")
        self.assertIsNotNone(area_path)
        assert area_path is not None
        area, world = load_area(area_path, project=project)
        player = world.get_entity("player_1")
        pickup = world.get_entity("sample_glimmer_berry_pickup")
        self.assertIsNotNone(player)
        self.assertIsNotNone(pickup)
        assert player is not None

        registry = CommandRegistry()
        register_builtin_commands(registry)
        context = CommandContext(
            project=project,
            services=build_command_services(
                area=area,
                world=world,
                screen_manager=ScreenElementManager(),
            ),
        )

        pickup_handle = execute_registered_command(
            registry,
            context,
            "run_entity_command",
            {
                "entity_id": "sample_glimmer_berry_pickup",
                "command_id": "interact",
                "entity_refs": {
                    "instigator": "player_1",
                },
            },
        )
        _complete_handle(self, pickup_handle)

        self.assertEqual(
            inventory_item_count(player.inventory, "items/consumables/glimmer_berry"),
            1,
        )
        self.assertIsNone(world.get_entity("sample_glimmer_berry_pickup"))

        use_handle = execute_registered_command(
            registry,
            context,
            "use_inventory_item",
            {
                "entity_id": "player_1",
                "item_id": "items/consumables/glimmer_berry",
                "quantity": 1,
            },
        )
        _complete_handle(self, use_handle)

        self.assertEqual(
            inventory_item_count(player.inventory, "items/consumables/glimmer_berry"),
            0,
        )
        self.assertEqual(player.variables["last_used_item"], "items/consumables/glimmer_berry")


if __name__ == "__main__":
    unittest.main()
