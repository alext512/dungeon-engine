from __future__ import annotations

import copy
import os
import unittest
from pathlib import Path

import pygame

from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.context_types import AreaTransitionRequest
from dungeon_engine.commands.context_services import build_command_services
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import CommandContext, execute_registered_command
from dungeon_engine.engine.dialogue_runtime import DialogueRuntime
from dungeon_engine.engine.screen import ScreenElementManager
from dungeon_engine.engine.game import Game
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


class SampleProjectWorkflowTests(unittest.TestCase):
    def test_new_project_start_area_player_visual_matches_authored_facing(self) -> None:
        project_root = _repo_root() / "projects" / "new_project"
        if not (project_root / "project.json").is_file():
            self.skipTest(
                "Optional repo-local integration fixture 'new_project' is not available in this worktree."
            )

        project = load_project(project_root / "project.json")
        area_path = project.find_area_by_id("areas/start")
        self.assertIsNotNone(area_path)
        assert area_path is not None

        area, world = load_area(area_path, project=project)
        player = world.get_entity("player_1")
        self.assertIsNotNone(player)
        assert player is not None
        self.assertEqual(player.facing, "up")
        self.assertEqual(player.require_visual("body").current_frame, 1)

    def test_new_project_game_runtime_keeps_player_visual_matching_authored_facing(self) -> None:
        project_root = _repo_root() / "projects" / "new_project"
        if not (project_root / "project.json").is_file():
            self.skipTest(
                "Optional repo-local integration fixture 'new_project' is not available in this worktree."
            )

        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

        project = load_project(project_root / "project.json")
        area_path = project.find_area_by_id("areas/start")
        self.assertIsNotNone(area_path)
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        player = game.world.get_entity("player_1")
        self.assertIsNotNone(player)
        assert player is not None

        game.animation_system.update_tick(0.0)

        self.assertEqual(player.facing, "up")
        self.assertEqual(player.require_visual("body").current_frame, 1)

    def test_new_project_area_transition_keeps_player_visual_when_destination_has_no_authored_facing(self) -> None:
        project_root = _repo_root() / "projects" / "new_project"
        if not (project_root / "project.json").is_file():
            self.skipTest(
                "Optional repo-local integration fixture 'new_project' is not available in this worktree."
            )

        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

        project = load_project(project_root / "project.json")
        area_path = project.find_area_by_id("areas/start")
        self.assertIsNotNone(area_path)
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        player = game.world.get_entity("player_1")
        self.assertIsNotNone(player)
        assert player is not None

        game.animation_system.play_animation("player_1", "idle_up", visual_id="body")
        self.assertEqual(player.require_visual("body").current_frame, 1)

        game.request_area_change(
            AreaTransitionRequest(
                area_id="areas/cave",
                destination_entity_id="cave_entrance_in",
                transfer_entity_ids=["player_1"],
            )
        )
        game._apply_pending_area_change_if_idle()

        transitioned_player = game.world.get_entity("player_1")
        self.assertIsNotNone(transitioned_player)
        assert transitioned_player is not None
        game.animation_system.update_tick(0.0)
        self.assertEqual(transitioned_player.facing, "up")
        self.assertEqual(transitioned_player.require_visual("body").current_frame, 1)

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
        hook_terminal = world.get_entity("sample_hook_terminal")
        tracker = world.get_entity("sample_global_tracker")
        self.assertIsNotNone(player)
        missing_entities = [
            entity_id
            for entity_id, entity in (
                ("sample_glimmer_berry_pickup", pickup),
                ("sample_hook_terminal", hook_terminal),
                ("sample_global_tracker", tracker),
            )
            if entity is None
        ]
        if missing_entities:
            self.skipTest(
                "Optional sample workflow entity fixture(s) not present: "
                + ", ".join(missing_entities)
            )
        assert player is not None
        assert pickup is not None
        assert hook_terminal is not None
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
        dialogue_runtime = DialogueRuntime(
            project=project,
            screen_manager=ScreenElementManager(),
            text_renderer=_StubTextRenderer(),
            registry=registry,
            command_context=context,
        )
        assert context.services.ui is not None
        context.services.ui.screen_manager = dialogue_runtime.screen_manager
        context.services.ui.text_renderer = dialogue_runtime.text_renderer
        context.services.ui.dialogue_runtime = dialogue_runtime

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

        hook_handle = execute_registered_command(
            registry,
            context,
            "run_entity_command",
            {
                "entity_id": "sample_hook_terminal",
                "command_id": "interact",
                "entity_refs": {
                    "instigator": "player_1",
                },
            },
        )
        self.assertTrue(dialogue_runtime.is_active())
        dialogue_runtime.handle_action("interact")
        _complete_handle(self, hook_handle)
        self.assertFalse(dialogue_runtime.is_active())
        self.assertEqual(hook_terminal.variables["last_hook_choice"], "hook")

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

        title_screen = load_json_data(project_root / "areas" / "title_screen.json")
        enter_camera_commands = [
            (command["type"], command.get("command_id"))
            for command in title_screen.get("enter_commands", [])[:3]
        ]
        self.assertEqual(
            enter_camera_commands,
            [
                ("run_project_command", "commands/camera/clear_camera_follow"),
                ("run_project_command", "commands/camera/clear_camera_bounds"),
                ("run_project_command", "commands/camera/clear_camera_deadzone"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
