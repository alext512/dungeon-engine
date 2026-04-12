from __future__ import annotations

import copy
import unittest
from pathlib import Path

from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.context_services import build_command_services
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import CommandContext, execute_registered_command
from dungeon_engine.engine.screen import ScreenElementManager
from dungeon_engine.inventory import inventory_item_count
from dungeon_engine.items import load_item_definition
from dungeon_engine.json_io import load_json_data
from dungeon_engine.project_context import load_project
from dungeon_engine.world.loader_entities import instantiate_entity
from dungeon_engine.world.loader import load_area
from dungeon_engine.world.persistence import PersistenceRuntime
from dungeon_engine.world.persistence_data import (
    get_persistent_area_state,
    save_data_from_dict,
    save_data_to_dict,
)
from dungeon_engine.world.persistence_snapshots import apply_persistent_global_state
from dungeon_engine.world.world import World


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _complete_handle(test_case: unittest.TestCase, handle: object, *, max_steps: int = 32) -> None:
    for _ in range(max_steps):
        if getattr(handle, "complete", False):
            return
        handle.update(0.0)
    test_case.fail("Command handle did not complete within the expected number of steps.")


def _install_project_global_entities(project: object, world: World, tile_size: int) -> None:
    for index, entity_data in enumerate(project.global_entities):
        global_entity = instantiate_entity(
            {
                **copy.deepcopy(entity_data),
                "scope": "global",
            },
            tile_size,
            project=project,
            source_name=f"project global_entities[{index}]",
        )
        world.add_entity(global_entity)


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
        _install_project_global_entities(project, world, area.tile_size)
        self.assertEqual(area.camera_defaults["follow"]["entity_id"], "player_1")
        self.assertEqual(area.camera_defaults["deadzone"]["space"], "viewport_pixel")
        player = world.get_entity("player_1")
        pickup = world.get_entity("sample_glimmer_berry_pickup")
        tracker = world.get_entity("sample_global_tracker")
        self.assertIsNotNone(player)
        self.assertIsNotNone(pickup)
        self.assertIsNotNone(tracker)
        assert player is not None
        assert tracker is not None

        registry = CommandRegistry()
        register_builtin_commands(registry)
        persistence_runtime = PersistenceRuntime(project=project)
        persistence_runtime.bind_area(area.area_id, authored_world=world)
        context = CommandContext(
            project=project,
            services=build_command_services(
                area=area,
                world=world,
                screen_manager=ScreenElementManager(),
                persistence_runtime=persistence_runtime,
            ),
        )

        enter_handle = execute_registered_command(
            registry,
            context,
            "run_entity_command",
            {
                "entity_id": "sample_global_tracker",
                "command_id": "mark_start_entry",
            },
        )
        _complete_handle(self, enter_handle)
        self.assertEqual(tracker.variables["start_entries"], 1)

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

        restored_save_data = save_data_from_dict(save_data_to_dict(persistence_runtime.save_data))
        restored_area_state = get_persistent_area_state(restored_save_data, "areas/start")
        self.assertIsNotNone(restored_area_state)
        restored_area, restored_world = load_area(
            area_path,
            project=project,
            persistent_area_state=restored_area_state,
        )
        _install_project_global_entities(project, restored_world, restored_area.tile_size)
        apply_persistent_global_state(
            restored_area,
            restored_world,
            restored_save_data,
            project=project,
        )
        self.assertEqual(restored_area.area_id, "areas/start")

        restored_player = restored_world.get_entity("player_1")
        restored_tracker = restored_world.get_entity("sample_global_tracker")
        self.assertIsNotNone(restored_player)
        self.assertIsNotNone(restored_tracker)
        assert restored_player is not None
        assert restored_tracker is not None
        self.assertEqual(
            inventory_item_count(restored_player.inventory, "items/consumables/glimmer_berry"),
            0,
        )
        self.assertEqual(
            restored_player.variables["last_used_item"],
            "items/consumables/glimmer_berry",
        )
        self.assertIsNone(restored_world.get_entity("sample_glimmer_berry_pickup"))
        self.assertEqual(restored_tracker.variables["start_entries"], 1)

        title_menu = load_json_data(project_root / "dialogues" / "system" / "title_menu.json")
        new_game_command = title_menu["segments"][0]["options"][0]["commands"][0]
        self.assertEqual(new_game_command["camera_follow"]["entity_id"], "player_1")


if __name__ == "__main__":
    unittest.main()
