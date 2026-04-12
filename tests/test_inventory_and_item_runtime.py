from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.context_services import (
    CommandAudioServices,
    CommandUiServices,
    build_command_services,
)
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import (
    CommandContext,
    CommandExecutionError,
    CommandRunner,
    execute_command_spec,
    execute_registered_command,
)
from dungeon_engine.engine.inventory_runtime import InventoryRuntime
from dungeon_engine.engine.screen import ScreenElementManager
from dungeon_engine.inventory import inventory_item_count
from dungeon_engine.items import (
    ItemDefinitionValidationError,
    load_item_definition,
    validate_project_items,
)
from dungeon_engine.project_context import load_project
from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import (
    Entity,
    EntityCommandDefinition,
    InventoryStack,
    InventoryState,
)
from dungeon_engine.world.loader import instantiate_entity
from dungeon_engine.world.serializer import serialize_area
from dungeon_engine.world.world import World


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


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


def _inventory_shared_variables() -> dict[str, object]:
    return {
        "inventory_ui": {
            "default_preset": "standard",
            "presets": {
                "standard": {
                    "deny_sfx_path": "assets/project/sfx/bump.wav",
                }
            },
        }
    }


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
    entity_commands: dict[str, EntityCommandDefinition] | None = None,
) -> Entity:
    return Entity(
        entity_id=entity_id,
        kind=kind,
        grid_x=0,
        grid_y=0,
        space=space,  # type: ignore[arg-type]
        scope="area",
        visuals=[],
        entity_commands=entity_commands or {},
    )


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


class InventoryAndItemRuntimeTests(unittest.TestCase):
    def _make_project(
        self,
        *,
        items: dict[str, dict[str, object]] | None = None,
        shared_variables: dict[str, object] | None = None,
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
        _write_json(project_root / "shared_variables.json", shared_variables or {})
        for relative_path, item_payload in (items or {}).items():
            _write_json(project_root / "items" / relative_path, item_payload)

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
        context.services.audio = CommandAudioServices()
        return registry, context

    def _complete_handle(self, handle: object, *, max_steps: int = 32) -> None:
        for _ in range(max_steps):
            if getattr(handle, "complete", False):
                return
            handle.update(0.0)
        self.fail("Command handle did not complete within the expected number of steps.")

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
        assert context.services.ui is not None
        context.services.ui.screen_manager = inventory_runtime.screen_manager
        context.services.ui.text_renderer = inventory_runtime.text_renderer
        context.services.ui.inventory_runtime = inventory_runtime
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
                "grid_x": 0,
                "grid_y": 0,
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
            "grid_x": 0,
            "grid_y": 0,
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
        context.services.audio.audio_player = _RecordingAudioPlayer()
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
        self.assertEqual(context.services.audio.audio_player.paths, ["assets/project/sfx/bump.wav"])  # type: ignore[attr-defined]
