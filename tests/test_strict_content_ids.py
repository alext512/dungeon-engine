from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

import run_game
from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.library import (
    ProjectCommandValidationError,
    validate_project_commands,
)
from dungeon_engine.inventory import inventory_item_count
from dungeon_engine.items import (
    ItemDefinitionValidationError,
    load_item_definition,
    validate_project_items,
)
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import (
    AreaTransitionRequest,
    CommandRunner,
    CommandExecutionError,
    CommandContext,
    SequenceCommandHandle,
    execute_command_spec,
    execute_registered_command,
)
from dungeon_engine.world.area import Area, TileLayer
from dungeon_engine.world.entity import (
    Entity,
    EntityCommandDefinition,
    EntityVisual,
    InventoryStack,
    InventoryState,
)
from dungeon_engine.world.world import World
from dungeon_engine.project_context import load_project
from dungeon_engine.startup_validation import (
    StaticReferenceValidationError,
    validate_project_startup,
)
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
from dungeon_engine.engine.renderer import Renderer
from dungeon_engine.engine.screen import ScreenElementManager
from dungeon_engine.engine.text import TextRenderer
from dungeon_engine.systems.collision import CollisionSystem
from dungeon_engine.systems.interaction import InteractionSystem
from dungeon_engine.systems.movement import MovementSystem


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _minimal_area() -> dict[str, object]:
    return {
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
                "render_order": 0,
                "grid": [[1]],
            }
        ],
        "cell_flags": [[{"blocked": False}]],
        "entities": [],
    }


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


class _RecordingMovementSystem:
    def __init__(self) -> None:
        self.grid_steps: list[tuple[str, str, float | None, int | None, float | None, str]] = []
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
        persistent: bool | None = None,
    ) -> list[str]:
        _ = persistent
        self.grid_steps.append(
            (entity_id, direction, duration, frames_needed, speed_px_per_second, grid_sync)
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
        persistent: bool | None = None,
    ) -> list[str]:
        _ = persistent
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
        persistent: bool | None = None,
    ) -> list[str]:
        _ = persistent
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
        persistent: bool | None = None,
    ) -> list[str]:
        _ = persistent
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
        persistent: bool | None = None,
    ) -> list[str]:
        _ = persistent
        self.move_by_grid_offsets.append(
            (entity_id, x, y, duration, frames_needed, speed_px_per_second, grid_sync)
        )
        return [entity_id]

    def teleport_to_grid_position(
        self,
        entity_id: str,
        x: int,
        y: int,
        *,
        persistent: bool | None = None,
    ) -> None:
        _ = persistent
        self.teleport_grid_positions.append((entity_id, x, y))

    def teleport_to_position(
        self,
        entity_id: str,
        x: float,
        y: float,
        *,
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
        persistent: bool | None = None,
    ) -> None:
        _ = persistent
        self.teleport_positions.append((entity_id, x, y, target_grid_x, target_grid_y))

    def set_grid_position(
        self,
        entity_id: str,
        x: int,
        y: int,
        *,
        persistent: bool | None = None,
    ) -> None:
        _ = persistent
        self.teleport_grid_positions.append((entity_id, x, y))

    def set_pixel_position(
        self,
        entity_id: str,
        x: float,
        y: float,
        *,
        persistent: bool | None = None,
    ) -> None:
        _ = persistent
        self.teleport_positions.append((entity_id, x, y, None, None))

    def is_entity_moving(self, entity_id: str) -> bool:
        return entity_id in self.moving_entities


class _RecordingInputDispatchRunner:
    def __init__(self) -> None:
        self.dispatched: list[tuple[str, str]] = []

    def has_pending_work(self) -> bool:
        return False

    def dispatch_input_entity_command(
        self,
        *,
        entity_id: str,
        command_id: str,
    ) -> bool:
        self.dispatched.append((entity_id, command_id))
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
        items: dict[str, dict[str, object]] | None = None,
        dialogues: dict[str, dict[str, object]] | None = None,
        shared_variables: dict[str, object] | None = None,
    ) -> tuple[Path, object]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        project_root = Path(temp_dir.name)

        project_payload: dict[str, object] = {
            "area_paths": ["areas/"],
            "entity_template_paths": ["entity_templates/"],
            "command_paths": ["commands/"],
            "item_paths": ["items/"],
            "shared_variables_path": "shared_variables.json",
        }
        if startup_area is not None:
            project_payload["startup_area"] = startup_area
        if input_targets is not None:
            project_payload["input_targets"] = input_targets
        if global_entities is not None:
            project_payload["global_entities"] = global_entities

        _write_json(project_root / "project.json", project_payload)
        if shared_variables is not None:
            _write_json(project_root / "shared_variables.json", shared_variables)

        for relative_path, template_payload in (entity_templates or {}).items():
            _write_json(project_root / "entity_templates" / relative_path, template_payload)
        for relative_path, area_payload in (areas or {}).items():
            _write_json(project_root / "areas" / relative_path, area_payload)
        for relative_path, command_payload in (commands or {}).items():
            _write_json(project_root / "commands" / relative_path, command_payload)
        for relative_path, item_payload in (items or {}).items():
            _write_json(project_root / "items" / relative_path, item_payload)
        for relative_path, dialogue_payload in (dialogues or {}).items():
            _write_json(project_root / "dialogues" / relative_path, dialogue_payload)

        return project_root, load_project(project_root / "project.json")

    def _repo_project_manifest_path(self, project_name: str) -> Path:
        return Path(__file__).resolve().parents[1] / "projects" / project_name / "project.json"

    def _load_repo_project_or_skip(self, project_name: str) -> object:
        project_path = self._repo_project_manifest_path(project_name)
        if not project_path.is_file():
            self.skipTest(
                f"Optional repo-local integration fixture '{project_name}' is not available in this worktree."
            )
        return load_project(project_path)

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

    def _complete_handle(self, handle: object, *, max_steps: int = 32) -> None:
        for _ in range(max_steps):
            if getattr(handle, "complete", False):
                return
            handle.update(0.0)
        self.fail("Command handle did not complete within the expected number of steps.")

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

    def _make_occupancy_runtime(
        self,
        *,
        area: Area,
        world: World,
    ) -> tuple[CommandRegistry, CommandContext, MovementSystem]:
        registry, context = self._make_command_context(area=area, world=world)
        collision = CollisionSystem(area, world)
        movement = MovementSystem(area, world, collision)
        context.collision_system = collision
        context.interaction_system = InteractionSystem(world)
        context.movement_system = movement

        def _dispatch_occupancy_hooks(
            instigator: Entity,
            previous_cell: tuple[int, int] | None,
            next_cell: tuple[int, int] | None,
        ) -> None:
            runtime_params: dict[str, int] = {}
            if previous_cell is not None:
                runtime_params["from_x"] = int(previous_cell[0])
                runtime_params["from_y"] = int(previous_cell[1])
            if next_cell is not None:
                runtime_params["to_x"] = int(next_cell[0])
                runtime_params["to_y"] = int(next_cell[1])

            def _run_hook(receiver: Entity, command_id: str) -> None:
                handle = execute_registered_command(
                    registry,
                    context,
                    "run_entity_command",
                    {
                        "entity_id": receiver.entity_id,
                        "command_id": command_id,
                        "entity_refs": {"instigator": instigator.entity_id},
                        "refs_mode": "merge",
                        **runtime_params,
                    },
                )
                handle.update(0.0)

            if previous_cell is not None:
                for receiver in world.get_entities_at(
                    previous_cell[0],
                    previous_cell[1],
                    exclude_entity_id=instigator.entity_id,
                    include_hidden=True,
                ):
                    _run_hook(receiver, "on_occupant_leave")

            if next_cell is not None:
                for receiver in world.get_entities_at(
                    next_cell[0],
                    next_cell[1],
                    exclude_entity_id=instigator.entity_id,
                    include_hidden=True,
                ):
                    _run_hook(receiver, "on_occupant_enter")

        movement.occupancy_transition_callback = _dispatch_occupancy_hooks
        return registry, context, movement

    def test_collision_system_uses_blocked_cells_and_solid_entities(self) -> None:
        area = Area(
            area_id="areas/test_room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": True}]],
        )
        world = World()
        blocker = _make_runtime_entity("blocker", kind="block")
        blocker.grid_x = 0
        blocker.grid_y = 0
        blocker.solid = True
        world.add_entity(blocker)

        collision = CollisionSystem(area, world)

        self.assertFalse(collision.can_move_to(1, 0))
        self.assertFalse(collision.can_move_to(0, 0))
        self.assertEqual(collision.get_blocking_entity(0, 0), blocker)

    def test_interaction_system_prefers_explicit_priority_and_facing(self) -> None:
        world = World()
        actor = _make_runtime_entity("actor", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        actor.facing = "right"
        world.add_entity(actor)

        low = _make_runtime_entity(
            "low",
            kind="npc",
            entity_commands={"interact": EntityCommandDefinition(enabled=True, commands=[])},
        )
        low.grid_x = 1
        low.grid_y = 0
        low.interactable = True
        low.interaction_priority = 1
        world.add_entity(low)

        high = _make_runtime_entity(
            "high",
            kind="npc",
            entity_commands={"interact": EntityCommandDefinition(enabled=True, commands=[])},
        )
        high.grid_x = 1
        high.grid_y = 0
        high.interactable = True
        high.interaction_priority = 10
        world.add_entity(high)

        interaction = InteractionSystem(world)
        self.assertEqual(interaction.get_facing_target("actor"), high)

    def test_move_in_direction_steps_actor_and_updates_facing(self) -> None:
        area = Area(
            area_id="areas/test_room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        world.add_entity(actor)
        registry, context = self._make_command_context(area=area, world=world)
        movement_system = _RecordingMovementSystem()
        context.movement_system = movement_system
        context.collision_system = CollisionSystem(area, world)

        handle = execute_registered_command(
            registry,
            context,
            "move_in_direction",
            {
                "entity_id": "player",
                "direction": "right",
                "frames_needed": 6,
                "wait": False,
            },
        )
        handle.update(0.0)

        self.assertEqual(actor.get_effective_facing(), "right")
        self.assertEqual(
            movement_system.grid_steps,
            [("player", "right", None, 6, None, "immediate")],
        )

    def test_move_in_direction_runs_on_blocked_hook_with_context(self) -> None:
        area = Area(
            area_id="areas/test_room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity(
            "player",
            kind="player",
            entity_commands={
                "on_blocked": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "blocked",
                            "value": True,
                        },
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "blocked_direction",
                            "value": "$direction",
                        },
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "blocked_entity",
                            "value": "$blocking_entity_id",
                        },
                    ]
                )
            },
        )
        actor.grid_x = 0
        actor.grid_y = 0
        world.add_entity(actor)
        blocker = _make_runtime_entity("crate", kind="block")
        blocker.grid_x = 1
        blocker.grid_y = 0
        blocker.solid = True
        world.add_entity(blocker)
        registry, context = self._make_command_context(area=area, world=world)
        movement_system = _RecordingMovementSystem()
        context.movement_system = movement_system
        context.collision_system = CollisionSystem(area, world)

        handle = execute_registered_command(
            registry,
            context,
            "move_in_direction",
            {
                "entity_id": "player",
                "direction": "right",
                "wait": False,
            },
        )
        handle.update(0.0)

        self.assertTrue(actor.variables["blocked"])  # type: ignore[index]
        self.assertEqual(actor.variables["blocked_direction"], "right")
        self.assertEqual(actor.variables["blocked_entity"], "crate")
        self.assertEqual(movement_system.grid_steps, [])

    def test_move_in_direction_pushes_one_blocker_using_entity_push_strength(self) -> None:
        area = Area(
            area_id="areas/test_room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": False}, {"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        actor.push_strength = 1
        world.add_entity(actor)
        blocker = _make_runtime_entity("crate", kind="block")
        blocker.grid_x = 1
        blocker.grid_y = 0
        blocker.solid = True
        blocker.pushable = True
        blocker.weight = 1
        world.add_entity(blocker)
        registry, context = self._make_command_context(area=area, world=world)
        movement_system = _RecordingMovementSystem()
        context.movement_system = movement_system
        context.collision_system = CollisionSystem(area, world)

        handle = execute_registered_command(
            registry,
            context,
            "move_in_direction",
            {
                "entity_id": "player",
                "direction": "right",
                "frames_needed": 8,
                "wait": False,
            },
        )
        handle.update(0.0)

        self.assertEqual(actor.get_effective_facing(), "right")
        self.assertEqual(
            movement_system.grid_steps,
            [
                ("crate", "right", None, 8, None, "immediate"),
                ("player", "right", None, 8, None, "immediate"),
            ],
        )

    def test_push_facing_moves_only_the_blocker(self) -> None:
        area = Area(
            area_id="areas/test_room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": False}, {"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        actor.facing = "right"
        actor.push_strength = 1
        world.add_entity(actor)
        blocker = _make_runtime_entity("crate", kind="block")
        blocker.grid_x = 1
        blocker.grid_y = 0
        blocker.solid = True
        blocker.pushable = True
        blocker.weight = 1
        world.add_entity(blocker)
        registry, context = self._make_command_context(area=area, world=world)
        movement_system = _RecordingMovementSystem()
        context.movement_system = movement_system
        context.collision_system = CollisionSystem(area, world)

        handle = execute_registered_command(
            registry,
            context,
            "push_facing",
            {
                "entity_id": "player",
                "frames_needed": 5,
                "wait": False,
            },
        )
        handle.update(0.0)

        self.assertEqual((actor.grid_x, actor.grid_y), (0, 0))
        self.assertEqual(
            movement_system.grid_steps,
            [("crate", "right", None, 5, None, "immediate")],
        )

    def test_interact_facing_dispatches_target_interact_with_instigator(self) -> None:
        area = Area(
            area_id="areas/test_room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        actor.facing = "right"
        world.add_entity(actor)
        target = _make_runtime_entity(
            "sign",
            kind="sign",
            entity_commands={
                "interact": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$ref_ids.instigator",
                            "name": "interacted",
                            "value": True,
                        }
                    ]
                )
            },
        )
        target.grid_x = 1
        target.grid_y = 0
        target.interactable = True
        world.add_entity(target)
        registry, context = self._make_command_context(area=area, world=world)
        context.interaction_system = InteractionSystem(world)

        handle = execute_registered_command(
            registry,
            context,
            "interact_facing",
            {
                "entity_id": "player",
            },
        )
        handle.update(0.0)

        self.assertTrue(actor.variables["interacted"])  # type: ignore[index]

    def test_move_in_direction_runs_occupant_enter_and_leave_hooks(self) -> None:
        area = Area(
            area_id="areas/test_room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": False}, {"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        actor.sync_pixel_position(area.tile_size)
        world.add_entity(actor)
        button = _make_runtime_entity(
            "button",
            kind="button",
            entity_commands={
                "on_occupant_enter": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "entered_by",
                            "value": "$ref_ids.instigator",
                        }
                    ]
                ),
                "on_occupant_leave": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "left_by",
                            "value": "$ref_ids.instigator",
                        }
                    ]
                ),
            },
        )
        button.grid_x = 1
        button.grid_y = 0
        button.sync_pixel_position(area.tile_size)
        world.add_entity(button)
        registry, context, movement_system = self._make_occupancy_runtime(area=area, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "move_in_direction",
            {
                "entity_id": "player",
                "direction": "right",
                "frames_needed": 0,
                "wait": False,
            },
        )
        handle.update(0.0)
        movement_system.update_tick()

        self.assertEqual(button.variables["entered_by"], "player")

        handle = execute_registered_command(
            registry,
            context,
            "move_in_direction",
            {
                "entity_id": "player",
                "direction": "right",
                "frames_needed": 0,
                "wait": False,
            },
        )
        handle.update(0.0)
        movement_system.update_tick()

        self.assertEqual(button.variables["left_by"], "player")

    def test_set_present_false_runs_occupant_leave_hook(self) -> None:
        area = Area(
            area_id="areas/test_room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1]], render_order=0)],
            cell_flags=[[{"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        world.add_entity(actor)
        button = _make_runtime_entity(
            "button",
            kind="button",
            entity_commands={
                "on_occupant_leave": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "released_by",
                            "value": "$ref_ids.instigator",
                        }
                    ]
                )
            },
        )
        button.grid_x = 0
        button.grid_y = 0
        world.add_entity(button)
        registry, context = self._make_command_context(area=area, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "set_present",
            {
                "entity_id": "player",
                "present": False,
            },
        )
        handle.update(0.0)

        self.assertFalse(actor.present)
        self.assertEqual(button.variables["released_by"], "player")

    def test_set_present_true_runs_occupant_enter_hook(self) -> None:
        area = Area(
            area_id="areas/test_room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1]], render_order=0)],
            cell_flags=[[{"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        actor.set_present(False)
        world.add_entity(actor)
        button = _make_runtime_entity(
            "button",
            kind="button",
            entity_commands={
                "on_occupant_enter": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "entered_by",
                            "value": "$ref_ids.instigator",
                        }
                    ]
                )
            },
        )
        button.grid_x = 0
        button.grid_y = 0
        world.add_entity(button)
        registry, context = self._make_command_context(area=area, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "set_present",
            {
                "entity_id": "player",
                "present": True,
            },
        )
        handle.update(0.0)

        self.assertTrue(actor.present)
        self.assertEqual(button.variables["entered_by"], "player")

    def test_destroy_entity_runs_occupant_leave_hook_before_removal(self) -> None:
        area = Area(
            area_id="areas/test_room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1]], render_order=0)],
            cell_flags=[[{"blocked": False}]],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 0
        actor.grid_y = 0
        world.add_entity(actor)
        button = _make_runtime_entity(
            "button",
            kind="button",
            entity_commands={
                "on_occupant_leave": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "released_by",
                            "value": "$ref_ids.instigator",
                        }
                    ]
                )
            },
        )
        button.grid_x = 0
        button.grid_y = 0
        world.add_entity(button)
        registry, context = self._make_command_context(area=area, world=world)

        handle = execute_registered_command(
            registry,
            context,
            "destroy_entity",
            {
                "entity_id": "player",
            },
        )
        handle.update(0.0)

        self.assertIsNone(world.get_entity("player"))
        self.assertEqual(button.variables["released_by"], "player")

    def test_renderer_collect_world_render_items_interleaves_tiles_and_entities(self) -> None:
        import pygame

        area = Area(
            area_id="areas/test_room",
            tile_size=16,
            tilesets=[],
            tile_layers=[
                TileLayer(name="ground", grid=[[1]], render_order=0, y_sort=False, stack_order=0),
                TileLayer(name="front_wall", grid=[[1]], render_order=10, y_sort=True, stack_order=0),
                TileLayer(name="roof", grid=[[1]], render_order=20, y_sort=False, stack_order=0),
            ],
            cell_flags=[[{"blocked": False}]],
        )
        world = World()
        player = _make_runtime_entity("player", kind="player")
        player.grid_x = 0
        player.grid_y = 0
        player.sync_pixel_position(area.tile_size)
        player.render_order = 10
        player.y_sort = True
        player.stack_order = 0
        world.add_entity(player)

        renderer = Renderer(pygame.Surface((16, 16)), object())
        items = sorted(renderer._collect_world_render_items(area, world), key=lambda item: item.sort_key)

        self.assertEqual(
            [item.draw_kind for item in items],
            ["tile_layer", "tile_cell", "entity", "tile_layer"],
        )
        self.assertEqual(items[0].payload[0].name, "ground")
        self.assertEqual(items[1].payload[0].name, "front_wall")
        self.assertEqual(items[2].payload[0].entity_id, "player")
        self.assertEqual(items[3].payload[0].name, "roof")

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
        ):
            with self.assertRaises(CommandExecutionError) as raised:
                params = {}
                if command_name == "wait_for_direction_release":
                    params = {"direction": "down"}
                elif command_name == "query_facing_state":
                    params = {"entity_id": "self", "store_state_var": "move_attempt_state"}
                elif command_name == "run_facing_event":
                    params = {"entity_id": "self", "command_id": "interact"}
                execute_registered_command(registry, context, command_name, params)
            self.assertIsNotNone(raised.exception.__cause__)
            self.assertIn(f"Unknown command '{command_name}'", str(raised.exception.__cause__))

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
                                "$add": [
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
                                "$add": [
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
                            "type": "if",
                            "left": "$self.interact_target",
                            "op": "neq",
                            "right": None,
                            "then": [
                                {
                                    "type": "run_entity_command",
                                    "entity_id": "$self.interact_target.entity_id",
                                    "command_id": "interact",
                                    "entity_refs": {
                                        "instigator": "$self_id",
                                    },
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
            entity_commands={
                "interact": EntityCommandDefinition(
                    commands=[
                        {
                            "type": "set_current_area_var",
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
                "type": "run_project_command",
                "command_id": "commands/interact_one_tile",
            },
            base_params={
                "source_entity_id": "player",
                "entity_refs": {
                    "instigator": "player",
                },
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
            "add_entity_var",
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
        execute_command_spec(
            registry,
            context,
            {
                "type": "if",
                "left": {
                    "$entity_var": {
                        "entity_id": "dialogue_controller",
                        "name": "mode",
                    }
                },
                "op": "eq",
                "right": "menu",
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

    def test_explicit_current_area_var_primitives_manage_values_and_branching(self) -> None:
        registry, context = self._make_command_context()

        execute_registered_command(
            registry,
            context,
            "set_current_area_var",
            {
                "name": "mode",
                "value": "play",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "add_current_area_var",
            {
                "name": "turn_count",
                "amount": 3,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "append_current_area_var",
            {
                "name": "visited_rooms",
                "value": "areas/village_square",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "append_current_area_var",
            {
                "name": "visited_rooms",
                "value": "areas/village_house",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_current_area_var_length",
            {
                "name": "visited_room_count",
                "value": context.world.variables["visited_rooms"],
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_current_area_var",
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
            "pop_current_area_var",
            {
                "name": "visited_rooms",
                "store_var": "popped_room",
                "default": "",
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "if",
                "left": "$current_area.mode",
                "op": "eq",
                "right": "play",
                "then": [
                    {
                        "type": "set_current_area_var",
                        "name": "world_branch_hit",
                        "value": True,
                    }
                ],
            },
        ).update(0.0)

        self.assertEqual(context.world.variables["mode"], "play")
        self.assertEqual(context.world.variables["turn_count"], 3)
        self.assertEqual(context.world.variables["visited_room_count"], 2)
        self.assertEqual(context.world.variables["latest_room"], "areas/village_house")
        self.assertEqual(context.world.variables["visited_rooms"], ["areas/village_square"])
        self.assertEqual(context.world.variables["popped_room"], "areas/village_house")
        self.assertTrue(context.world.variables["world_branch_hit"])

    def test_toggle_var_primitives_flip_boolean_values(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("switch", kind="switch"))
        registry, context = self._make_command_context(world=world)

        execute_registered_command(
            registry,
            context,
            "toggle_entity_var",
            {
                "entity_id": "switch",
                "name": "enabled",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "toggle_entity_var",
            {
                "entity_id": "switch",
                "name": "enabled",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "toggle_current_area_var",
            {
                "name": "paused",
            },
        ).update(0.0)

        switch = world.get_entity("switch")
        assert switch is not None
        self.assertFalse(switch.variables["enabled"])
        self.assertTrue(context.world.variables["paused"])

        switch.variables["enabled"] = "yes"
        with self.assertRaises(CommandExecutionError):
            execute_registered_command(
                registry,
                context,
                "toggle_entity_var",
                {
                    "entity_id": "switch",
                    "name": "enabled",
                },
            ).update(0.0)

    def test_set_entity_fields_updates_multiple_sections(self) -> None:
        world = World()
        lever = _make_runtime_entity("lever", kind="lever", with_visual=True)
        lever.variables["active"] = False
        lever.visuals.append(
            EntityVisual(
                visual_id="shadow",
                path="assets/project/sprites/shadow.png",
                frame_width=16,
                frame_height=16,
                frames=[0],
            )
        )
        world.add_entity(lever)
        registry, context = self._make_command_context(world=world)

        execute_registered_command(
            registry,
            context,
            "set_entity_fields",
            {
                "entity_id": "lever",
                "set": {
                    "fields": {
                        "visible": False,
                    },
                    "variables": {
                        "active": True,
                    },
                    "visuals": {
                        "main": {
                            "offset_x": 2,
                            "offset_y": -1,
                            "animation_fps": 6,
                            "tint": [1, 2, 3],
                        },
                        "shadow": {
                            "visible": False,
                        },
                    },
                },
            },
        ).update(0.0)

        updated = world.get_entity("lever")
        assert updated is not None
        self.assertFalse(updated.visible)
        self.assertTrue(updated.variables["active"])
        main_visual = updated.require_visual("main")
        self.assertEqual(main_visual.tint, (1, 2, 3))
        self.assertEqual(main_visual.offset_x, 2.0)
        self.assertEqual(main_visual.offset_y, -1.0)
        self.assertEqual(main_visual.animation_fps, 6.0)
        self.assertFalse(updated.require_visual("shadow").visible)

    def test_set_entity_fields_is_all_or_nothing(self) -> None:
        world = World()
        lever = _make_runtime_entity("lever", kind="lever", with_visual=True)
        lever.variables["active"] = False
        world.add_entity(lever)
        registry, context = self._make_command_context(world=world)

        with self.assertRaises(CommandExecutionError):
            execute_registered_command(
                registry,
                context,
                "set_entity_fields",
                {
                    "entity_id": "lever",
                    "set": {
                        "fields": {
                            "visible": False,
                        },
                        "variables": {
                            "active": True,
                        },
                        "visuals": {
                            "main": {
                                "path": "assets/project/other.png",
                            }
                        },
                    },
                },
            ).update(0.0)

        unchanged = world.get_entity("lever")
        assert unchanged is not None
        self.assertTrue(unchanged.visible)
        self.assertFalse(unchanged.variables["active"])
        self.assertEqual(unchanged.require_visual("main").path, "assets/project/sprites/test.png")

    def test_explicit_var_primitives_persist_when_requested(self) -> None:
        _, project = self._make_project()
        authored_world = World()
        authored_world.add_entity(_make_runtime_entity("dialogue_controller", kind="system", space="screen"))
        runtime = PersistenceRuntime(project=project)
        runtime.bind_area("areas/test_room", authored_world=authored_world)

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
            "set_current_area_var",
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

    def test_entity_persistence_policy_round_trips_through_loader_and_serializer(self) -> None:
        _, project = self._make_project()
        entity = instantiate_entity(
            {
                "id": "brown_box",
                "kind": "box",
                "grid_x": 2,
                "grid_y": 3,
                "persistence": {
                    "entity_state": True,
                    "variables": {
                        "shake_timer": False,
                        "times_pushed": True,
                    },
                },
            },
            16,
            project=project,
            source_name="test entity",
        )

        self.assertTrue(entity.persistence.entity_state)
        self.assertEqual(
            entity.persistence.variables,
            {
                "shake_timer": False,
                "times_pushed": True,
            },
        )

        area = _minimal_runtime_area()
        world = World()
        world.add_entity(entity)
        serialized = serialize_area(area, world, project=project)
        self.assertEqual(
            serialized["entities"][0]["persistence"],
            {
                "entity_state": True,
                "variables": {
                    "shake_timer": False,
                    "times_pushed": True,
                },
            },
        )

    def test_entity_var_persistence_inherits_entity_state_policy(self) -> None:
        _, project = self._make_project()
        authored_entity = _make_runtime_entity("dialogue_controller", kind="system", space="screen")
        authored_world = World()
        authored_world.add_entity(authored_entity)
        runtime = PersistenceRuntime(project=project)
        runtime.bind_area("areas/test_room", authored_world=authored_world)

        live_entity = _make_runtime_entity("dialogue_controller", kind="system", space="screen")
        live_entity.persistence.entity_state = True
        live_world = World()
        live_world.add_entity(live_entity)
        registry, context = self._make_command_context(
            project=project,
            world=live_world,
            persistence_runtime=runtime,
        )

        execute_registered_command(
            registry,
            context,
            "set_entity_var",
            {
                "entity_id": "dialogue_controller",
                "name": "mode",
                "value": "choice",
            },
        ).update(0.0)

        area_state = runtime.current_area_state()
        assert area_state is not None
        self.assertEqual(
            area_state.entities["dialogue_controller"].overrides["variables"]["mode"],
            "choice",
        )

    def test_entity_var_persistence_variable_override_wins_when_entity_state_is_transient(self) -> None:
        _, project = self._make_project()
        authored_entity = _make_runtime_entity("brown_box", kind="box")
        authored_world = World()
        authored_world.add_entity(authored_entity)
        runtime = PersistenceRuntime(project=project)
        runtime.bind_area("areas/test_room", authored_world=authored_world)

        live_entity = _make_runtime_entity("brown_box", kind="box")
        live_entity.persistence.variables["times_pushed"] = True
        live_world = World()
        live_world.add_entity(live_entity)
        registry, context = self._make_command_context(
            project=project,
            world=live_world,
            persistence_runtime=runtime,
        )

        execute_registered_command(
            registry,
            context,
            "add_entity_var",
            {
                "entity_id": "brown_box",
                "name": "times_pushed",
                "amount": 1,
            },
        ).update(0.0)

        area_state = runtime.current_area_state()
        assert area_state is not None
        self.assertEqual(
            area_state.entities["brown_box"].overrides["variables"]["times_pushed"],
            1,
        )

    def test_explicit_entity_var_persistent_false_overrides_entity_policy(self) -> None:
        _, project = self._make_project()
        authored_entity = _make_runtime_entity("dialogue_controller", kind="system", space="screen")
        authored_world = World()
        authored_world.add_entity(authored_entity)
        runtime = PersistenceRuntime(project=project)
        runtime.bind_area("areas/test_room", authored_world=authored_world)

        live_entity = _make_runtime_entity("dialogue_controller", kind="system", space="screen")
        live_entity.persistence.entity_state = True
        live_world = World()
        live_world.add_entity(live_entity)
        registry, context = self._make_command_context(
            project=project,
            world=live_world,
            persistence_runtime=runtime,
        )

        execute_registered_command(
            registry,
            context,
            "set_entity_var",
            {
                "entity_id": "dialogue_controller",
                "name": "mode",
                "value": "choice",
                "persistent": False,
            },
        ).update(0.0)

        area_state = runtime.current_area_state()
        self.assertTrue(area_state is None or "dialogue_controller" not in area_state.entities)

    def test_entity_field_persistence_inherits_entity_state_policy(self) -> None:
        _, project = self._make_project()
        authored_entity = _make_runtime_entity("dialogue_controller", kind="system", space="screen")
        authored_world = World()
        authored_world.add_entity(authored_entity)
        runtime = PersistenceRuntime(project=project)
        runtime.bind_area("areas/test_room", authored_world=authored_world)

        live_entity = _make_runtime_entity("dialogue_controller", kind="system", space="screen")
        live_entity.persistence.entity_state = True
        live_world = World()
        live_world.add_entity(live_entity)
        registry, context = self._make_command_context(
            project=project,
            world=live_world,
            persistence_runtime=runtime,
        )

        execute_registered_command(
            registry,
            context,
            "set_visible",
            {
                "entity_id": "dialogue_controller",
                "visible": False,
            },
        ).update(0.0)

        area_state = runtime.current_area_state()
        assert area_state is not None
        self.assertFalse(area_state.entities["dialogue_controller"].overrides["visible"])

    def test_destroy_entity_inherits_entity_state_persistence(self) -> None:
        _, project = self._make_project()
        authored_entity = _make_runtime_entity("dialogue_controller", kind="system", space="screen")
        authored_world = World()
        authored_world.add_entity(authored_entity)
        runtime = PersistenceRuntime(project=project)
        runtime.bind_area("areas/test_room", authored_world=authored_world)

        live_entity = _make_runtime_entity("dialogue_controller", kind="system", space="screen")
        live_entity.persistence.entity_state = True
        live_world = World()
        live_world.add_entity(live_entity)
        registry, context = self._make_command_context(
            project=project,
            world=live_world,
            persistence_runtime=runtime,
        )

        execute_registered_command(
            registry,
            context,
            "destroy_entity",
            {
                "entity_id": "dialogue_controller",
            },
        ).update(0.0)

        area_state = runtime.current_area_state()
        assert area_state is not None
        self.assertTrue(area_state.entities["dialogue_controller"].removed)

    def test_spawn_entity_inherits_entity_state_persistence(self) -> None:
        _, project = self._make_project()
        authored_world = World()
        runtime = PersistenceRuntime(project=project)
        runtime.bind_area("areas/test_room", authored_world=authored_world)

        live_world = World()
        registry, context = self._make_command_context(
            project=project,
            world=live_world,
            persistence_runtime=runtime,
        )

        execute_registered_command(
            registry,
            context,
            "spawn_entity",
            {
                "entity": {
                    "id": "menu_cursor",
                    "kind": "system",
                    "space": "screen",
                    "pixel_x": 4,
                    "pixel_y": 8,
                    "persistence": {
                        "entity_state": True,
                    },
                },
            },
        ).update(0.0)

        area_state = runtime.current_area_state()
        assert area_state is not None
        self.assertIn("menu_cursor", area_state.entities)
        self.assertIsNotNone(area_state.entities["menu_cursor"].spawned)

    def test_movement_system_grid_step_inherits_entity_state_persistence(self) -> None:
        _, project = self._make_project()
        area = Area(
            area_id="areas/test_room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": False}]],
        )
        authored_world = World()
        authored_player = _make_runtime_entity("player", kind="player")
        authored_player.grid_x = 0
        authored_player.grid_y = 0
        authored_player.sync_pixel_position(area.tile_size)
        authored_world.add_entity(authored_player)
        runtime = PersistenceRuntime(project=project)
        runtime.bind_area(area.area_id, authored_world=authored_world)

        live_world = World()
        live_player = _make_runtime_entity("player", kind="player")
        live_player.grid_x = 0
        live_player.grid_y = 0
        live_player.sync_pixel_position(area.tile_size)
        live_player.persistence.entity_state = True
        live_world.add_entity(live_player)

        movement_system = MovementSystem(
            area,
            live_world,
            CollisionSystem(area, live_world),
            runtime,
        )
        movement_system.request_grid_step("player", "right", frames_needed=0)
        movement_system.update_tick()

        area_state = runtime.current_area_state()
        assert area_state is not None
        self.assertEqual(area_state.entities["player"].overrides["grid_x"], 1)
        self.assertEqual(area_state.entities["player"].overrides["grid_y"], 0)

    def test_movement_system_explicit_transient_override_skips_persistence(self) -> None:
        _, project = self._make_project()
        area = Area(
            area_id="areas/test_room",
            tile_size=16,
            tilesets=[],
            tile_layers=[TileLayer(name="ground", grid=[[1, 1]], render_order=0)],
            cell_flags=[[{"blocked": False}, {"blocked": False}]],
        )
        authored_world = World()
        authored_player = _make_runtime_entity("player", kind="player")
        authored_player.grid_x = 0
        authored_player.grid_y = 0
        authored_player.sync_pixel_position(area.tile_size)
        authored_world.add_entity(authored_player)
        runtime = PersistenceRuntime(project=project)
        runtime.bind_area(area.area_id, authored_world=authored_world)

        live_world = World()
        live_player = _make_runtime_entity("player", kind="player")
        live_player.grid_x = 0
        live_player.grid_y = 0
        live_player.sync_pixel_position(area.tile_size)
        live_player.persistence.entity_state = True
        live_world.add_entity(live_player)

        movement_system = MovementSystem(
            area,
            live_world,
            CollisionSystem(area, live_world),
            runtime,
        )
        movement_system.request_grid_step("player", "right", frames_needed=0, persistent=False)
        movement_system.update_tick()

        area_state = runtime.current_area_state()
        self.assertTrue(area_state is None or "player" not in area_state.entities)

    def test_add_inventory_item_inherits_entity_state_persistence(self) -> None:
        _, project = self._make_project(
            items={
                "apple.json": _minimal_item(name="Apple", max_stack=9),
            }
        )
        area = _minimal_runtime_area()
        authored_world = World()
        authored_player = _make_runtime_entity("player", kind="player")
        authored_world.add_entity(authored_player)
        runtime = PersistenceRuntime(project=project)
        runtime.bind_area(area.area_id, authored_world=authored_world)

        live_world = World()
        live_player = _make_runtime_entity("player", kind="player")
        live_player.persistence.entity_state = True
        live_player.inventory = InventoryState(max_stacks=2, stacks=[])
        live_world.add_entity(live_player)
        registry, context = self._make_command_context(
            project=project,
            world=live_world,
            area=area,
            persistence_runtime=runtime,
        )

        execute_registered_command(
            registry,
            context,
            "add_inventory_item",
            {
                "entity_id": "player",
                "item_id": "items/apple",
                "quantity": 2,
                "quantity_mode": "atomic",
            },
        ).update(0.0)

        area_state = runtime.current_area_state()
        assert area_state is not None
        self.assertEqual(
            area_state.entities["player"].overrides["inventory"],
            {
                "max_stacks": 2,
                "stacks": [
                    {"item_id": "items/apple", "quantity": 2},
                ],
            },
        )

    def test_reset_transient_state_with_entity_id_restores_traveler_baseline(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        _, project = self._make_project(
            startup_area="areas/room_a",
            areas={
                "room_a.json": {
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [{"name": "ground", "render_order": 0, "grid": [[0, 0, 0]]}],
                    "cell_flags": [[{"blocked": False}, {"blocked": False}, {"blocked": False}]],
                    "entities": [
                        {"id": "player", "kind": "player", "grid_x": 0, "grid_y": 0},
                        {
                            "id": "crate",
                            "kind": "crate",
                            "grid_x": 1,
                            "grid_y": 0,
                            "persistence": {"entity_state": False},
                        },
                    ],
                },
                "room_b.json": {
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [{"name": "ground", "render_order": 0, "grid": [[0, 0, 0]]}],
                    "cell_flags": [[{"blocked": False}, {"blocked": False}, {"blocked": False}]],
                    "entry_points": {"landing": {"grid_x": 2, "grid_y": 0}},
                    "entities": [],
                },
            },
        )

        area_a_path = project.resolve_area_reference("areas/room_a")
        assert area_a_path is not None
        game = Game(area_path=area_a_path, project=project)
        self.addCleanup(pygame.quit)

        game.request_area_change(
            AreaTransitionRequest(
                area_id="areas/room_b",
                entry_id="landing",
                transfer_entity_ids=["crate"],
            )
        )
        game._apply_pending_area_change_if_idle()

        crate = game.world.get_entity("crate")
        assert crate is not None
        crate.variables["temporary"] = True
        game.movement_system.set_grid_position("crate", 0, 0)

        game.command_runner.enqueue("reset_transient_state", entity_id="crate")
        game.command_runner.update(0.0)
        game._apply_pending_reset_if_idle()

        reset_crate = game.world.get_entity("crate")
        assert reset_crate is not None
        self.assertEqual((reset_crate.grid_x, reset_crate.grid_y), (2, 0))
        self.assertNotIn("temporary", reset_crate.variables)

    def test_active_area_change_drops_transient_traveler_state(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        _, project = self._make_project(
            startup_area="areas/room_a",
            areas={
                "room_a.json": {
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [{"name": "ground", "render_order": 0, "grid": [[0, 0, 0]]}],
                    "cell_flags": [[{"blocked": False}, {"blocked": False}, {"blocked": False}]],
                    "entities": [
                        {"id": "player", "kind": "player", "grid_x": 0, "grid_y": 0},
                        {
                            "id": "crate",
                            "kind": "crate",
                            "grid_x": 1,
                            "grid_y": 0,
                            "persistence": {"entity_state": False},
                        },
                    ],
                },
                "room_b.json": {
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [{"name": "ground", "render_order": 0, "grid": [[0, 0, 0]]}],
                    "cell_flags": [[{"blocked": False}, {"blocked": False}, {"blocked": False}]],
                    "entry_points": {"landing": {"grid_x": 2, "grid_y": 0}},
                    "entities": [],
                },
                "room_c.json": {
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [{"name": "ground", "render_order": 0, "grid": [[0, 0, 0]]}],
                    "cell_flags": [[{"blocked": False}, {"blocked": False}, {"blocked": False}]],
                    "entities": [],
                },
            },
        )

        area_a_path = project.resolve_area_reference("areas/room_a")
        assert area_a_path is not None
        game = Game(area_path=area_a_path, project=project)
        self.addCleanup(pygame.quit)

        game.request_area_change(
            AreaTransitionRequest(
                area_id="areas/room_b",
                entry_id="landing",
                transfer_entity_ids=["crate"],
            )
        )
        game._apply_pending_area_change_if_idle()

        crate = game.world.get_entity("crate")
        assert crate is not None
        crate.variables["temporary"] = True
        game.movement_system.set_grid_position("crate", 0, 0)

        game.request_area_change(AreaTransitionRequest(area_id="areas/room_c"))
        game._apply_pending_area_change_if_idle()
        game.request_area_change(AreaTransitionRequest(area_id="areas/room_b"))
        game._apply_pending_area_change_if_idle()

        restored_crate = game.world.get_entity("crate")
        assert restored_crate is not None
        self.assertEqual((restored_crate.grid_x, restored_crate.grid_y), (2, 0))
        self.assertNotIn("temporary", restored_crate.variables)

    def test_area_change_can_place_transferred_entity_at_destination_marker_entity(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        _, project = self._make_project(
            startup_area="areas/room_a",
            areas={
                "room_a.json": {
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [{"name": "ground", "render_order": 0, "grid": [[0, 0, 0]]}],
                    "cell_flags": [[{"blocked": False}, {"blocked": False}, {"blocked": False}]],
                    "entities": [
                        {"id": "crate", "kind": "crate", "grid_x": 0, "grid_y": 0, "facing": "down"},
                    ],
                },
                "room_b.json": {
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [{"name": "ground", "render_order": 0, "grid": [[0, 0, 0], [0, 0, 0]]}],
                    "cell_flags": [[{"blocked": False}, {"blocked": False}, {"blocked": False}], [{"blocked": False}, {"blocked": False}, {"blocked": False}]],
                    "entities": [
                        {
                            "id": "spawn_marker",
                            "kind": "transition_target",
                            "grid_x": 2,
                            "grid_y": 1,
                            "facing": "left",
                            "visible": False,
                        }
                    ],
                },
            },
        )

        area_a_path = project.resolve_area_reference("areas/room_a")
        assert area_a_path is not None
        game = Game(area_path=area_a_path, project=project)
        self.addCleanup(pygame.quit)

        game.request_area_change(
            AreaTransitionRequest(
                area_id="areas/room_b",
                destination_entity_id="spawn_marker",
                transfer_entity_ids=["crate"],
            )
        )
        game._apply_pending_area_change_if_idle()

        crate = game.world.get_entity("crate")
        assert crate is not None
        self.assertEqual((crate.grid_x, crate.grid_y), (2, 1))
        self.assertEqual(crate.facing, "left")

    def test_current_area_runtime_token_replaces_world_token(self) -> None:
        world = World()
        world.variables["phase"] = "opening"
        world.add_entity(_make_runtime_entity("controller", kind="system", space="screen"))
        registry, context = self._make_command_context(world=world)

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "controller",
                "name": "copied_phase",
                "value": "$current_area.phase",
            },
        ).update(0.0)

        controller = world.get_entity("controller")
        assert controller is not None
        self.assertEqual(controller.variables["copied_phase"], "opening")

        with self.assertRaises(KeyError):
            execute_command_spec(
                registry,
                context,
                {
                    "type": "set_entity_var",
                    "entity_id": "controller",
                    "name": "legacy_phase",
                    "value": "$world.phase",
                },
            ).update(0.0)

    def test_cross_area_state_commands_persist_target_area_state_and_update_loaded_area(self) -> None:
        _, project = self._make_project(
            areas={
                "current_room.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "switch_1",
                            "kind": "switch",
                            "grid_x": 0,
                            "grid_y": 0,
                            "variables": {"enabled": False},
                        }
                    ],
                },
                "other_room.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "gate_1",
                            "kind": "gate",
                            "grid_x": 0,
                            "grid_y": 0,
                            "variables": {"open": False},
                        }
                    ],
                },
            }
        )
        runtime = PersistenceRuntime(project=project)
        world = World()
        switch = _make_runtime_entity("switch_1", kind="switch")
        switch.variables["enabled"] = False
        world.add_entity(switch)
        current_area = Area(
            area_id="areas/current_room",
            tile_size=16,
            tilesets=[],
            tile_layers=[],
            cell_flags=[],
        )
        registry, context = self._make_command_context(
            project=project,
            world=world,
            area=current_area,
            persistence_runtime=runtime,
        )

        execute_registered_command(
            registry,
            context,
            "set_area_var",
            {
                "area_id": "areas/other_room",
                "name": "bridge_lowered",
                "value": True,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_area_var",
            {
                "area_id": "areas/current_room",
                "name": "alarm_on",
                "value": True,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_area_entity_var",
            {
                "area_id": "areas/other_room",
                "entity_id": "gate_1",
                "name": "open",
                "value": True,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_area_entity_var",
            {
                "area_id": "areas/current_room",
                "entity_id": "switch_1",
                "name": "enabled",
                "value": True,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_area_entity_field",
            {
                "area_id": "areas/other_room",
                "entity_id": "gate_1",
                "field_name": "visible",
                "value": False,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_area_entity_field",
            {
                "area_id": "areas/current_room",
                "entity_id": "switch_1",
                "field_name": "visible",
                "value": False,
            },
        ).update(0.0)

        self.assertTrue(world.variables["alarm_on"])
        updated_switch = world.get_entity("switch_1")
        assert updated_switch is not None
        self.assertTrue(updated_switch.variables["enabled"])
        self.assertFalse(updated_switch.visible)

        self.assertTrue(runtime.save_data.areas["areas/other_room"].variables["bridge_lowered"])
        self.assertTrue(runtime.save_data.areas["areas/current_room"].variables["alarm_on"])
        self.assertTrue(
            runtime.save_data.areas["areas/other_room"].entities["gate_1"].overrides["variables"]["open"]
        )
        self.assertTrue(
            runtime.save_data.areas["areas/current_room"].entities["switch_1"].overrides["variables"][
                "enabled"
            ]
        )
        self.assertFalse(runtime.save_data.areas["areas/other_room"].entities["gate_1"].overrides["visible"])
        self.assertFalse(
            runtime.save_data.areas["areas/current_room"].entities["switch_1"].overrides["visible"]
        )

    def test_area_entity_ref_reads_area_owned_state_plus_persistent_overrides(self) -> None:
        _, project = self._make_project(
            areas={
                "other_room.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "gate_1",
                            "kind": "gate",
                            "grid_x": 0,
                            "grid_y": 0,
                            "variables": {"open": False},
                        }
                    ],
                }
            }
        )
        runtime = PersistenceRuntime(project=project)
        runtime.set_area_entity_variable("areas/other_room", "gate_1", "open", True)
        runtime.set_area_entity_field("areas/other_room", "gate_1", "visible", False)

        world = World()
        world.add_entity(_make_runtime_entity("controller", kind="system", space="screen"))
        registry, context = self._make_command_context(
            project=project,
            world=world,
            persistence_runtime=runtime,
        )

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "controller",
                "name": "snapshot",
                "value": {
                    "$area_entity_ref": {
                        "area_id": "areas/other_room",
                        "entity_id": "gate_1",
                        "select": {
                            "fields": ["entity_id", "visible"],
                            "variables": ["open"],
                        },
                        "default": None,
                    }
                },
            },
        ).update(0.0)

        controller = world.get_entity("controller")
        assert controller is not None
        self.assertEqual(
            controller.variables["snapshot"],
            {
                "entity_id": "gate_1",
                "visible": False,
                "variables": {"open": True},
            },
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
                "entity_refs": {
                    "instigator": "player",
                    "caller": "lever",
                },
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
            registry.get_deferred_params("run_entity_command"),
            {"dialogue_on_start", "dialogue_on_end", "segment_hooks"},
        )
        self.assertEqual(registry.get_deferred_params("if"), {"then", "else"})

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

    def test_world_rejects_same_scope_entity_id_collisions(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("gate_1", kind="gate"))

        with self.assertRaises(ValueError):
            world.add_entity(_make_runtime_entity("gate_1", kind="sign"))

        restored_entity = world.get_entity("gate_1")
        assert restored_entity is not None
        self.assertEqual(restored_entity.kind, "gate")

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
                "area_id": "areas/village_square",
                "entry_id": "startup",
                "destination_entity_id": "spawn_player",
            },
        )
        handle.update(0.0)

        self.assertEqual(len(recorded_requests), 1)
        self.assertEqual(recorded_requests[0].area_id, "areas/village_square")
        self.assertEqual(recorded_requests[0].entry_id, "startup")
        self.assertEqual(recorded_requests[0].destination_entity_id, "spawn_player")

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

        handle = execute_command_spec(
            registry,
            context,
            {
                "type": "change_area",
                "area_id": "areas/village_house",
                "entry_id": "from_square",
                "destination_entity_id": "village_house_spawn",
                "transfer_entity_ids": ["$ref_ids.instigator"],
                "camera_follow": {
                    "mode": "entity",
                    "entity_id": "$ref_ids.instigator",
                    "offset_x": 12,
                    "offset_y": -8,
                },
            },
            base_params={"entity_refs": {"instigator": "player"}},
        )
        handle.update(0.0)

        self.assertEqual(len(recorded_requests), 1)
        request = recorded_requests[0]
        self.assertEqual(request.area_id, "areas/village_house")
        self.assertEqual(request.entry_id, "from_square")
        self.assertEqual(request.destination_entity_id, "village_house_spawn")
        self.assertEqual(request.transfer_entity_ids, ["player"])
        self.assertIsNotNone(request.camera_follow)
        assert request.camera_follow is not None
        self.assertEqual(request.camera_follow.mode, "entity")
        self.assertEqual(request.camera_follow.entity_id, "player")
        self.assertEqual(request.camera_follow.offset_x, 12.0)
        self.assertEqual(request.camera_follow.offset_y, -8.0)

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

        project = self._load_repo_project_or_skip("test_project")
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

        project = self._load_repo_project_or_skip("test_project")
        title_area_path = project.resolve_area_reference("areas/title_screen")
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

        project = self._load_repo_project_or_skip("test_project")
        title_area_path = project.resolve_area_reference("areas/title_screen")
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
            startup_area="areas/title_screen",
            areas={
                "title_screen.json": {
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [
                        {
                            "name": "ground",
                            "render_order": 0,
                            "grid": [[0]],
                        }
                    ],
                    "cell_flags": [[{"blocked": False}]],
                    "entities": [
                        {
                            "id": "player",
                            "kind": "player",
                            "grid_x": 0,
                            "grid_y": 0,
                        }
                    ],
                },
                "village_square.json": {
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [
                        {
                            "name": "ground",
                            "render_order": 0,
                            "grid": [[0]],
                        }
                    ],
                    "cell_flags": [[{"blocked": False}]],
                    "entities": [
                        {
                            "id": "player",
                            "kind": "player",
                            "grid_x": 0,
                            "grid_y": 0,
                        }
                    ],
                },
            },
        )

        title_area_path = project.resolve_area_reference("areas/title_screen")
        assert title_area_path is not None
        game = Game(area_path=title_area_path, project=project)
        self.addCleanup(pygame.quit)

        save_path = project.project_root / "saves" / "slot_1.json"
        game.persistence_runtime.save_data.globals["seen_intro"] = True
        game.persistence_runtime.set_save_path(save_path)
        game.request_new_game(AreaTransitionRequest(area_id="areas/village_square"))
        game._apply_pending_new_game_if_idle()

        self.assertEqual(game.area.area_id, "areas/village_square")
        self.assertEqual(game.persistence_runtime.save_data.globals, {})
        self.assertIsNone(game.persistence_runtime.save_path)
        self.assertIsNone(game.persistence_runtime.save_data.current_input_targets)

    def test_title_screen_dialogue_accepts_direction_and_confirm_input(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project = self._load_repo_project_or_skip("test_project")
        title_area_path = project.resolve_area_reference("areas/title_screen")
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

        self.assertEqual(game.area.area_id, "areas/village_square")
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_title_screen_dialogue_held_direction_repeats_after_delay(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project = self._load_repo_project_or_skip("test_project")
        title_area_path = project.resolve_area_reference("areas/title_screen")
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

        project = self._load_repo_project_or_skip("physics_contract_demo")
        area_path = project.resolve_area_reference("areas/physics_contract_demo")
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

        project = self._load_repo_project_or_skip("physics_contract_demo")
        area_path = project.resolve_area_reference("areas/physics_contract_demo")
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

        self.assertTrue(player.movement_state.active)
        self.assertTrue(visual.animation_playback.active)
        self.assertIn(visual.current_frame, {6, 7, 8})
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_sample_player_position_snapshots_stay_lightweight(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project = self._load_repo_project_or_skip("physics_contract_demo")
        area_path = project.resolve_area_reference("areas/physics_contract_demo")
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

        while player.movement_state.active:
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

        project = self._load_repo_project_or_skip("physics_contract_demo")
        area_path = project.resolve_area_reference("areas/physics_contract_demo")
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
            if game.area.is_blocked(target_x, target_y):
                continue
            blocking_entities = [
                entity
                for entity in game.world.get_entities_at(
                    target_x,
                    target_y,
                    exclude_entity_id="player",
                    include_hidden=True,
                )
                if entity.is_effectively_solid()
            ]
            if blocking_entities:
                continue
            selected_event_id = event_id
            break

        self.assertIsNotNone(selected_event_id)

        game.command_runner.enqueue(
            "run_entity_command",
            entity_id="player",
            command_id=selected_event_id,
        )
        game._advance_simulation_tick(1 / 60)
        self.assertTrue(player.movement_state.active)

        for _ in range(4):
            game.command_runner.enqueue(
                "run_entity_command",
                entity_id="player",
                command_id=selected_event_id,
            )
            game._advance_simulation_tick(1 / 60)

        for _ in range(24):
            game._advance_simulation_tick(1 / 60)

        self.assertIsNone(game.command_runner.last_error_notice)

    def test_sample_player_opposite_direction_during_walk_does_not_flip_mid_step(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project = self._load_repo_project_or_skip("physics_contract_demo")
        area_path = project.resolve_area_reference("areas/physics_contract_demo")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        player = game.world.get_entity("player")
        assert player is not None

        game.command_runner.enqueue(
            "run_entity_command",
            entity_id="player",
            command_id="move_right",
        )
        game._advance_simulation_tick(1 / 60)

        visual = player.require_visual("body")
        self.assertTrue(player.movement_state.active)
        self.assertTrue(visual.flip_x)

        game.command_runner.enqueue(
            "run_entity_command",
            entity_id="player",
            command_id="move_left",
        )
        game._advance_simulation_tick(1 / 60)

        self.assertTrue(player.movement_state.active)
        self.assertTrue(visual.flip_x)
        self.assertEqual(player.get_effective_facing(), "right")
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_sample_push_block_does_not_move_into_blocked_cells(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project = self._load_repo_project_or_skip("physics_contract_demo")
        area_path = project.resolve_area_reference("areas/physics_contract_demo")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        block = game.world.get_entity("house_block")
        assert block is not None

        game.movement_system.set_grid_position("house_block", 5, 2)
        game.movement_system.set_pixel_position(
            "house_block",
            5 * game.area.tile_size,
            2 * game.area.tile_size,
        )

        game.command_runner.enqueue(
            "run_entity_command",
            entity_id="house_block",
            command_id="push_from_left",
        )
        game._advance_simulation_tick(1 / 60)

        self.assertEqual((block.grid_x, block.grid_y), (5, 2))
        self.assertEqual(
            (block.pixel_x, block.pixel_y),
            (5 * game.area.tile_size, 2 * game.area.tile_size),
        )
        self.assertFalse(block.movement_state.active)
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_demo_dialogue_runtime_intercepts_input_and_runs_inline_choice_commands(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project = self._load_repo_project_or_skip("physics_contract_demo")
        area_path = project.resolve_area_reference("areas/physics_contract_demo")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        player = game.world.get_entity("player")
        indicator = game.world.get_entity("occupancy_indicator")
        assert player is not None
        assert indicator is not None

        game.movement_system.set_grid_position("player", 4, 4)
        game.movement_system.set_pixel_position(
            "player",
            4 * game.area.tile_size,
            4 * game.area.tile_size,
        )
        player.set_facing_value("right")

        self.assertFalse(indicator.visible)

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)])
        game._advance_simulation_tick(1 / 60)

        self.assertIsNotNone(game.dialogue_runtime)
        assert game.dialogue_runtime is not None
        self.assertTrue(game.dialogue_runtime.is_active())
        self.assertEqual((player.grid_x, player.grid_y), (4, 4))

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_LEFT)])
        game._advance_simulation_tick(1 / 60)
        self.assertEqual((player.grid_x, player.grid_y), (4, 4))
        game.input_handler.handle_events([pygame.event.Event(pygame.KEYUP, key=pygame.K_LEFT)])

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)])
        game._advance_simulation_tick(1 / 60)

        session = game.dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.segment_index, 1)
        self.assertEqual(session.choice_index, 0)

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN)])
        game._advance_simulation_tick(1 / 60)
        session = game.dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.choice_index, 1)
        self.assertEqual((player.grid_x, player.grid_y), (4, 4))
        game.input_handler.handle_events([pygame.event.Event(pygame.KEYUP, key=pygame.K_DOWN)])

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP)])
        game._advance_simulation_tick(1 / 60)
        session = game.dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.choice_index, 0)
        game.input_handler.handle_events([pygame.event.Event(pygame.KEYUP, key=pygame.K_UP)])

        game.input_handler.handle_events([pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN)])
        game._advance_simulation_tick(1 / 60)

        self.assertFalse(game.dialogue_runtime.is_active())
        self.assertTrue(indicator.visible)
        self.assertEqual((player.grid_x, player.grid_y), (4, 4))
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_dialogue_choice_window_scrolls_after_three_visible_rows(self) -> None:
        project = self._load_repo_project_or_skip("test_project")
        controller = instantiate_entity(
            {
                "id": "dialogue_controller",
                "template": "entity_templates/dialogue_panel",
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
                "run_project_command",
                {
                    "command_id": command_id,
                    "source_entity_id": "dialogue_controller",
                    **params,
                },
            )
            while not handle.complete:
                handle.update(0.0)

        _run_named("commands/dialogue/render_choice")

        option_0 = context.screen_manager.get_element("dialogue_option_0")
        option_1 = context.screen_manager.get_element("dialogue_option_1")
        option_2 = context.screen_manager.get_element("dialogue_option_2")
        assert option_0 is not None
        assert option_1 is not None
        assert option_2 is not None
        self.assertEqual(option_0.text, ">One")
        self.assertEqual(option_1.text, "Two")
        self.assertEqual(option_2.text, "Three")

        _run_named("commands/dialogue/move_selection", delta=1)
        _run_named("commands/dialogue/move_selection", delta=1)
        _run_named("commands/dialogue/move_selection", delta=1)

        self.assertEqual(controller.variables["dialogue_choice_index"], 3)
        self.assertEqual(controller.variables["dialogue_choice_scroll_offset"], 1)

        option_0 = context.screen_manager.get_element("dialogue_option_0")
        option_1 = context.screen_manager.get_element("dialogue_option_1")
        option_2 = context.screen_manager.get_element("dialogue_option_2")
        assert option_0 is not None
        assert option_1 is not None
        assert option_2 is not None
        self.assertEqual(option_0.text, "Two")
        self.assertEqual(option_1.text, "Three")
        self.assertEqual(option_2.text, ">Four")
        self.assertIsNone(context.screen_manager.get_element("dialogue_cursor"))

    def test_sample_timer_dialogue_segment_advances_without_input(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project = self._load_repo_project_or_skip("test_project")
        area_path = project.resolve_area_reference("areas/village_square")
        assert area_path is not None

        game = Game(area_path=area_path, project=project)
        self.addCleanup(pygame.quit)

        for _ in range(3):
            game._advance_simulation_tick(1 / 60)

        controller = game.world.get_entity("dialogue_controller")
        assert controller is not None

        game.command_runner.enqueue(
            "run_entity_command",
            entity_id="dialogue_controller",
            command_id="open_dialogue",
            dialogue_path="dialogues/showcase/village_square_note.json",
            dialogue_on_start=[],
            dialogue_on_end=[],
            segment_hooks=[],
            allow_cancel=False,
            entity_refs={"instigator": "player", "caller": "player"},
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

        project = self._load_repo_project_or_skip("test_project")
        area_path = project.resolve_area_reference("areas/village_house")
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
            "run_entity_command",
            entity_id="house_lever",
            command_id="interact",
            entity_refs={"instigator": "player"},
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
        self.assertFalse(gate.is_effectively_solid())
        self.assertEqual(lever.require_visual("main").tint, (150, 150, 150))
        self.assertIsNone(game.command_runner.last_error_notice)

    def test_controller_owned_dialogue_restores_nested_snapshot_and_input_routes(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project = self._load_repo_project_or_skip("test_project")
        area_path = project.resolve_area_reference("areas/village_square")
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
                    "type": "run_entity_command",
                    "entity_id": "dialogue_controller",
                    "command_id": "open_dialogue",
                    "dialogue_path": "dialogues/system/title_menu.json",
                    "dialogue_on_start": [],
                    "dialogue_on_end": [],
                    "segment_hooks": [],
                    "allow_cancel": False,
                },
                {
                    "type": "run_entity_command",
                    "entity_id": "dialogue_controller",
                    "command_id": "open_dialogue",
                    "dialogue_path": "dialogues/system/save_prompt.json",
                    "dialogue_on_start": [],
                    "dialogue_on_end": [],
                    "segment_hooks": [],
                    "allow_cancel": True,
                },
            ],
            entity_refs={"instigator": "player", "caller": "lever"},
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
            "run_project_command",
            command_id="commands/dialogue/close_current_dialogue",
            source_entity_id="dialogue_controller",
            entity_refs={"instigator": "player", "caller": "lever"},
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
            "run_project_command",
            command_id="commands/dialogue/close_current_dialogue",
            source_entity_id="dialogue_controller",
            entity_refs={"instigator": "player", "caller": "lever"},
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
            startup_area="areas/room_a",
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
                            "render_order": 0,
                            "grid": [[0]],
                        }
                    ],
                    "cell_flags": [[{"blocked": False}]],
                    "entities": [
                        {
                            "id": "player",
                            "kind": "player",
                            "grid_x": 0,
                            "grid_y": 0,
                        }
                    ],
                }
            },
        )

        area_path = project.resolve_area_reference("areas/room_a")
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
            base_params={"entity_refs": {"instigator": "player"}},
        )

        self.assertTrue(handle.complete)
        for action in ("interact", "menu", "move_up", "move_down", "move_left", "move_right"):
            self.assertEqual(game.world.get_input_target_id(action), "player")

        save_payload = json.loads(save_path.read_text(encoding="utf-8"))
        restored_save_data = save_data_from_dict(save_payload)

        self.assertNotIn("active_entity", save_payload)
        self.assertNotIn("input_route_stack", save_payload)
        self.assertIsNotNone(restored_save_data.current_input_targets)
        assert restored_save_data.current_input_targets is not None
        self.assertTrue(
            all(
                restored_save_data.current_input_targets.get(action) == "player"
                for action in ("interact", "menu", "move_up", "move_down", "move_left", "move_right")
            )
        )

    def test_load_game_restores_saved_input_targets(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        _, project = self._make_project(
            startup_area="areas/room_a",
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
                            "render_order": 0,
                            "grid": [[0]],
                        }
                    ],
                    "cell_flags": [[{"blocked": False}]],
                    "entities": [
                        {
                            "id": "player",
                            "kind": "player",
                            "grid_x": 0,
                            "grid_y": 0,
                        }
                    ],
                }
            },
        )

        area_path = project.resolve_area_reference("areas/room_a")
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
                            "grid_x": 0,
                            "grid_y": 0,
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
                    "grid_x": 0,
                    "grid_y": 0,
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
        current_player.set_facing_value("right")
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
        self.assertEqual(restored_player.get_effective_facing(), "right")
        self.assertEqual(restored_visual.current_frame, 2)

    def test_save_game_restores_explicit_camera_state(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        project = self._load_repo_project_or_skip("test_project")
        area_path = project.resolve_area_reference("areas/village_square")
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
        self.assertEqual(camera_state["follow"]["mode"], "entity")
        self.assertEqual(camera_state["follow"]["entity_id"], "player")
        self.assertEqual(camera_state["follow"]["offset_x"], 14.0)
        self.assertEqual(camera_state["follow"]["offset_y"], -6.0)
        self.assertEqual(
            camera_state["bounds"],
            {"x": 16.0, "y": 16.0, "width": 160.0, "height": 112.0},
        )
        self.assertEqual(
            camera_state["deadzone"],
            {"x": 80.0, "y": 56.0, "width": 32.0, "height": 24.0},
        )

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
            area_id="areas/room_a",
            tile_size=16,
            tilesets=[],
            tile_layers=[],
            cell_flags=[],
        )
        area_b = Area(
            area_id="areas/room_b",
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

        serialized_save_data = save_data_to_dict(runtime.save_data)
        self.assertNotIn("next_session_entity_serial", serialized_save_data)
        self.assertEqual(
            serialized_save_data["travelers"]["crate"],
            {
                "current_area": "areas/room_b",
                "entity": {
                    "id": "crate",
                    "grid_x": 5,
                    "grid_y": 6,
                    "kind": "crate",
                    "space": "world",
                    "scope": "area",
                    "present": True,
                    "visible": True,
                    "facing": "down",
                    "solid": False,
                    "pushable": False,
                    "weight": 1,
                    "push_strength": 0,
                    "collision_push_strength": 0,
                    "interactable": False,
                    "interaction_priority": 0,
                    "entity_commands_enabled": True,
                    "render_order": 10,
                    "y_sort": True,
                    "sort_y_offset": 0,
                    "stack_order": 0,
                    "color": [255, 255, 255],
                    "tags": [],
                    "variables": {"moved": True},
                },
                "origin_area": "areas/room_a",
            },
        )
        restored_save_data = save_data_from_dict(serialized_save_data)

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
        self.assertEqual(restored_crate.origin_area_id, "areas/room_a")

    def test_game_area_change_without_returning_traveler_suppresses_origin_placeholder(self) -> None:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        import pygame
        from dungeon_engine.engine.game import Game

        _, project = self._make_project(
            startup_area="areas/room_a",
            areas={
                "room_a.json": {
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [
                        {
                            "name": "ground",
                            "render_order": 0,
                            "grid": [[0, 0, 0]],
                        }
                    ],
                    "cell_flags": [[{"blocked": False}, {"blocked": False}, {"blocked": False}]],
                    "entities": [
                        {
                            "id": "player",
                            "kind": "player",
                            "grid_x": 0,
                            "grid_y": 0,
                        },
                        {
                            "id": "crate",
                            "kind": "crate",
                            "grid_x": 1,
                            "grid_y": 0,
                        },
                    ],
                },
                "room_b.json": {
                    "tile_size": 16,
                    "variables": {},
                    "tilesets": [],
                    "tile_layers": [
                        {
                            "name": "ground",
                            "render_order": 0,
                            "grid": [[0, 0, 0]],
                        }
                    ],
                    "cell_flags": [[{"blocked": False}, {"blocked": False}, {"blocked": False}]],
                    "entry_points": {
                        "landing": {
                            "grid_x": 2,
                            "grid_y": 0,
                        }
                    },
                    "entities": [],
                },
            },
        )

        area_a_path = project.resolve_area_reference("areas/room_a")
        assert area_a_path is not None
        game = Game(area_path=area_a_path, project=project)
        self.addCleanup(pygame.quit)

        crate = game.world.get_entity("crate")
        assert crate is not None
        crate.variables["moved"] = True

        game.request_area_change(
            AreaTransitionRequest(
                area_id="areas/room_b",
                entry_id="landing",
                transfer_entity_ids=["crate"],
            )
        )
        game._apply_pending_area_change_if_idle()

        self.assertEqual(game.area.area_id, "areas/room_b")
        moved_crate = game.world.get_entity("crate")
        assert moved_crate is not None
        self.assertEqual(moved_crate.grid_x, 2)
        self.assertEqual(moved_crate.grid_y, 0)
        self.assertTrue(moved_crate.variables["moved"])  # type: ignore[index]

        game.request_area_change(AreaTransitionRequest(area_id="areas/room_a"))
        game._apply_pending_area_change_if_idle()

        self.assertEqual(game.area.area_id, "areas/room_a")
        self.assertIsNone(game.world.get_entity("crate"))


if __name__ == "__main__":
    unittest.main()



