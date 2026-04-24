from __future__ import annotations

import unittest

from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.context_services import CommandUiServices, build_command_services
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import (
    CommandContext,
    CommandExecutionError,
    execute_command_spec,
    execute_registered_command,
)
from dungeon_engine.engine.input_handler import InputHandler
from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity
from dungeon_engine.world.world import World


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
) -> Entity:
    return Entity(
        entity_id=entity_id,
        kind=kind,
        grid_x=0,
        grid_y=0,
        space=space,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        visuals=[],
    )


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
        self.state_stack: list[dict[str, object]] = []

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

    def push_state(self) -> None:
        self.state_stack.append(self.to_state_dict())

    def pop_state(self, world: World | None) -> None:
        if not self.state_stack:
            raise ValueError("Camera state stack is empty.")
        self.apply_state_dict(self.state_stack.pop(), world)

    def to_state_dict(self) -> dict[str, object]:
        follow: dict[str, object] = {
            "mode": self.follow_mode or "none",
            "offset_x": self.follow_offset_x,
            "offset_y": self.follow_offset_y,
        }
        if self.followed_entity_id is not None:
            follow["entity_id"] = self.followed_entity_id
        if self.follow_input_action is not None:
            follow["action"] = self.follow_input_action
        data: dict[str, object] = {
            "x": self.x,
            "y": self.y,
            "follow": follow,
        }
        if self.bounds is not None:
            data["bounds"] = dict(self.bounds)
        if self.deadzone is not None:
            data["deadzone"] = dict(self.deadzone)
        return data

    def apply_state_dict(self, state: dict[str, object], world: World | None) -> None:
        _ = world
        self.bounds = None
        self.deadzone = None
        if "bounds" in state and state["bounds"] is not None:
            self.bounds = dict(state["bounds"])  # type: ignore[arg-type]
        if "deadzone" in state and state["deadzone"] is not None:
            self.deadzone = dict(state["deadzone"])  # type: ignore[arg-type]
        self.x = float(state.get("x", self.x))
        self.y = float(state.get("y", self.y))
        raw_follow = state.get("follow")
        follow = raw_follow if isinstance(raw_follow, dict) else {"mode": "none"}
        mode = str(follow.get("mode", "none"))
        self.follow_mode = mode
        self.followed_entity_id = None
        self.follow_input_action = None
        self.follow_offset_x = float(follow.get("offset_x", 0.0))
        self.follow_offset_y = float(follow.get("offset_y", 0.0))
        if mode == "entity":
            entity_id = str(follow.get("entity_id", "")).strip()
            if entity_id:
                self.followed_entity_id = entity_id
            else:
                self.follow_mode = "none"
        elif mode == "input_target":
            action = str(follow.get("action", "")).strip()
            if action:
                self.follow_input_action = action
            else:
                self.follow_mode = "none"


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


class InputAndCameraRuntimeTests(unittest.TestCase):
    def _make_command_context(
        self,
        *,
        world: World | None = None,
    ) -> tuple[CommandRegistry, CommandContext]:
        registry = CommandRegistry()
        register_builtin_commands(registry)
        context = CommandContext(
            project=None,
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

    def test_input_handler_only_dispatches_actions_with_explicit_input_map_entries(self) -> None:
        import pygame

        world = World(default_input_targets={"interact": "player"})
        player = _make_runtime_entity("player", kind="player")
        world.add_entity(player)
        runner = _RecordingInputDispatchRunner()
        input_handler = InputHandler(runner, world)

        input_handler.handle_events(
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_SPACE})]
        )
        self.assertEqual(runner.dispatched, [])

        player.input_map["interact"] = "confirm"
        input_handler.handle_events(
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_SPACE})]
        )

        self.assertEqual(runner.dispatched, [("player", "confirm")])

    def test_input_handler_routes_inventory_key_only_when_explicitly_mapped(self) -> None:
        import pygame

        world = World(default_input_targets={"inventory": "player"})
        player = _make_runtime_entity("player", kind="player")
        world.add_entity(player)
        runner = _RecordingInputDispatchRunner()
        input_handler = InputHandler(runner, world)

        input_handler.handle_events(
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_i})]
        )
        self.assertEqual(runner.dispatched, [])

        player.input_map["inventory"] = "open_inventory"
        input_handler.handle_events(
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_i})]
        )

        self.assertEqual(runner.dispatched, [("player", "open_inventory")])

    def test_input_handler_blocks_immediate_direction_press_while_world_move_is_active(self) -> None:
        import pygame

        world = World(default_input_targets={"move_right": "player"})
        player = _make_runtime_entity("player", kind="player")
        player.input_map["move_right"] = "walk_right"
        player.movement_state.active = True
        world.add_entity(player)
        runner = _RecordingInputDispatchRunner()
        input_handler = InputHandler(runner, world)

        input_handler.handle_events(
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RIGHT})]
        )

        self.assertEqual(runner.dispatched, [])

    def test_input_handler_blocks_world_routing_when_inventory_modal_is_active(self) -> None:
        import pygame

        class _BlockingModalRuntime:
            def __init__(self) -> None:
                self.actions: list[str] = []

            def is_active(self) -> bool:
                return True

            def handle_action(self, action_name: str) -> bool:
                self.actions.append(str(action_name))
                return False

        world = World(default_input_targets={"inventory": "player"})
        player = _make_runtime_entity("player", kind="player")
        player.input_map["inventory"] = "open_inventory"
        world.add_entity(player)
        runner = _RecordingInputDispatchRunner()
        modal_runtime = _BlockingModalRuntime()
        input_handler = InputHandler(runner, world, inventory_runtime=modal_runtime)

        input_handler.handle_events(
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_i})]
        )

        self.assertEqual(modal_runtime.actions, ["inventory"])
        self.assertEqual(runner.dispatched, [])

    def test_input_handler_escape_without_menu_target_does_not_quit(self) -> None:
        import pygame

        world = World()
        runner = _RecordingInputDispatchRunner()
        input_handler = InputHandler(runner, world)

        result = input_handler.handle_events(
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})]
        )

        self.assertFalse(result.should_quit)
        self.assertEqual(runner.dispatched, [])

    def test_input_handler_routes_debug_keys_only_when_explicit_targets_exist(self) -> None:
        import pygame

        world = World(
            default_input_targets={
                "debug_toggle_pause": "debug_controller",
                "debug_step_tick": "debug_controller",
                "debug_zoom_out": "debug_controller",
                "debug_zoom_in": "debug_controller",
            }
        )
        debug_controller = _make_runtime_entity("debug_controller", kind="system")
        world.add_entity(debug_controller)
        runner = _RecordingInputDispatchRunner()
        input_handler = InputHandler(runner, world)

        input_handler.handle_events(
            [pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_F6})]
        )
        self.assertEqual(runner.dispatched, [])

        debug_controller.input_map["debug_toggle_pause"] = "toggle_pause"
        debug_controller.input_map["debug_step_tick"] = "step_tick"
        debug_controller.input_map["debug_zoom_out"] = "zoom_out"
        debug_controller.input_map["debug_zoom_in"] = "zoom_in"

        input_handler.handle_events(
            [
                pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_F6}),
                pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_F7}),
                pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_LEFTBRACKET}),
                pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_RIGHTBRACKET}),
            ]
        )

        self.assertEqual(
            runner.dispatched,
            [
                ("debug_controller", "toggle_pause"),
                ("debug_controller", "step_tick"),
                ("debug_controller", "zoom_out"),
                ("debug_controller", "zoom_in"),
            ],
        )

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

    def test_route_inputs_to_entity_command_supports_instigator_ref_via_run_sequence(self) -> None:
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
            "run_sequence",
            {
                "entity_refs": {
                    "instigator": "player",
                },
                "commands": [
                    {
                        "type": "route_inputs_to_entity",
                        "entity_id": "$ref_ids.instigator",
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

    def test_set_camera_follow_entity_supports_named_ref_via_run_sequence(self) -> None:
        caller = _make_runtime_entity("lever", kind="lever")
        world = World()
        world.add_entity(caller)
        registry, context = self._make_command_context(world=world)
        camera = _RecordingCamera()
        context.services.ui.camera = camera

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
                        "type": "set_camera_follow_entity",
                        "entity_id": "$ref_ids.caller",
                        "offset_x": 4,
                        "offset_y": -2,
                    }
                ],
            },
        )
        handle.update(0.0)

        self.assertEqual(camera.followed_entity_id, "lever")
        self.assertEqual(camera.follow_offset_x, 4.0)
        self.assertEqual(camera.follow_offset_y, -2.0)
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
        context.services.ui.camera = camera

        handle = execute_registered_command(
            registry,
            context,
            "set_camera_follow_input_target",
            {
                "action": "menu",
            },
        )
        handle.update(0.0)

        self.assertEqual(camera.follow_mode, "input_target")
        self.assertEqual(camera.follow_input_action, "menu")
        self.assertEqual(len(camera.update_calls), 1)
        self.assertIs(camera.update_calls[0][0], world)
        self.assertFalse(camera.update_calls[0][1])

    def test_set_camera_policy_push_and_pop_restore_previous_camera_policy(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        registry, context = self._make_command_context(world=world)
        camera = _RecordingCamera()
        context.services.ui.camera = camera

        execute_registered_command(
            registry,
            context,
            "set_camera_policy",
            {
                "follow": {
                    "mode": "entity",
                    "entity_id": "player",
                    "offset_x": 3,
                    "offset_y": -1,
                },
                "bounds": {
                    "x": 1,
                    "y": 2,
                    "width": 3,
                    "height": 4,
                    "space": "world_grid",
                },
                "deadzone": {
                    "x": 2,
                    "y": 1,
                    "width": 5,
                    "height": 4,
                    "space": "viewport_grid",
                },
            },
        ).update(0.0)
        execute_registered_command(registry, context, "push_camera_state", {}).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_camera_policy",
            {
                "follow": None,
                "bounds": None,
                "deadzone": None,
            },
        ).update(0.0)

        self.assertEqual(camera.follow_mode, "none")
        self.assertIsNone(camera.bounds)
        self.assertIsNone(camera.deadzone)

        execute_registered_command(registry, context, "pop_camera_state", {}).update(0.0)

        self.assertEqual(camera.follow_mode, "entity")
        self.assertEqual(camera.followed_entity_id, "player")
        self.assertEqual(camera.follow_offset_x, 3.0)
        self.assertEqual(camera.follow_offset_y, -1.0)
        self.assertEqual(
            camera.bounds,
            {"x": 16.0, "y": 32.0, "width": 48.0, "height": 64.0},
        )
        self.assertEqual(
            camera.deadzone,
            {"x": 32.0, "y": 16.0, "width": 80.0, "height": 64.0},
        )

    def test_clear_camera_commands_reset_one_section_without_replacing_others(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        registry, context = self._make_command_context(world=world)
        camera = _RecordingCamera()
        context.services.ui.camera = camera

        execute_registered_command(
            registry,
            context,
            "set_camera_follow_entity",
            {
                "entity_id": "player",
                "offset_x": 5,
                "offset_y": -3,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_camera_bounds",
            {
                "x": 1,
                "y": 2,
                "width": 3,
                "height": 4,
                "space": "world_grid",
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_camera_deadzone",
            {
                "x": 2,
                "y": 1,
                "width": 5,
                "height": 4,
                "space": "viewport_grid",
            },
        ).update(0.0)

        execute_registered_command(registry, context, "clear_camera_follow", {}).update(0.0)
        self.assertEqual(camera.follow_mode, "none")
        self.assertIsNotNone(camera.bounds)
        self.assertIsNotNone(camera.deadzone)

        execute_registered_command(registry, context, "clear_camera_bounds", {}).update(0.0)
        self.assertIsNone(camera.bounds)
        self.assertIsNotNone(camera.deadzone)

        execute_registered_command(registry, context, "clear_camera_deadzone", {}).update(0.0)
        self.assertIsNone(camera.deadzone)

    def test_set_camera_follow_player_is_removed(self) -> None:
        world = World()
        registry, context = self._make_command_context(world=world)
        camera = _RecordingCamera()
        context.services.ui.camera = camera

        with self.assertRaises(CommandExecutionError) as raised:
            execute_registered_command(
                registry,
                context,
                "set_camera_follow_player",
                {},
            )

        self.assertIsNotNone(raised.exception.__cause__)
        self.assertIn("Unknown command 'set_camera_follow_player'", str(raised.exception.__cause__))

    def test_removed_camera_commands_raise_unknown_command(self) -> None:
        world = World()
        registry, context = self._make_command_context(world=world)
        context.services.ui.camera = _RecordingCamera()

        for command_name in (
            "set_camera_follow",
            "set_camera_state",
            "set_camera_bounds_rect",
        ):
            with self.subTest(command_name=command_name):
                with self.assertRaises(CommandExecutionError) as raised:
                    execute_registered_command(registry, context, command_name, {})
                self.assertIsNotNone(raised.exception.__cause__)
                self.assertIn(f"Unknown command '{command_name}'", str(raised.exception.__cause__))

    def test_set_var_from_camera_is_removed(self) -> None:
        world = World()
        registry, context = self._make_command_context(world=world)
        camera = _RecordingCamera()
        context.services.ui.camera = camera

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
        self.assertIn("Unknown command 'set_var_from_camera'", str(raised.exception.__cause__))

    def test_set_input_event_name_is_removed(self) -> None:
        world = World()
        registry, context = self._make_command_context(world=world)

        with self.assertRaises(CommandExecutionError) as raised:
            execute_registered_command(
                registry,
                context,
                "set_input_event_name",
                {
                    "action": "interact",
                    "command_id": "confirm",
                },
            )

        self.assertIsNotNone(raised.exception.__cause__)
        self.assertIn("Unknown command 'set_input_event_name'", str(raised.exception.__cause__))

    def test_explicit_camera_query_helpers_are_removed(self) -> None:
        world = World()
        registry, context = self._make_command_context(world=world)
        camera = _RecordingCamera()
        context.services.ui.camera = camera

        for command_name, params, expected_message in (
            (
                "set_world_var_from_camera",
                {"name": "camera_x", "field": "x"},
                "Unknown command 'set_world_var_from_camera'",
            ),
            (
                "set_entity_var_from_camera",
                {"entity_id": "player", "name": "camera_x", "field": "x"},
                "Unknown command 'set_entity_var_from_camera'",
            ),
        ):
            with self.assertRaises(CommandExecutionError) as raised:
                execute_registered_command(
                    registry,
                    context,
                    command_name,
                    params,
                )

            self.assertIsNotNone(raised.exception.__cause__)
            self.assertIn(expected_message, str(raised.exception.__cause__))

    def test_camera_tokens_support_bounds_deadzone_and_follow_state(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        registry, context = self._make_command_context(world=world)
        camera = _RecordingCamera()
        context.services.ui.camera = camera

        bounds_handle = execute_registered_command(
            registry,
            context,
            "set_camera_bounds",
            {
                "x": 1,
                "y": 2,
                "width": 3,
                "height": 4,
                "space": "world_grid",
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
                "space": "viewport_pixel",
            },
        )
        deadzone_handle.update(0.0)
        self.assertEqual(
            camera.deadzone,
            {"x": 8.0, "y": 12.0, "width": 24.0, "height": 30.0},
        )

        follow_set_handle = execute_registered_command(
            registry,
            context,
            "set_camera_follow_entity",
            {
                "entity_id": "player",
                "offset_x": 6,
                "offset_y": -2,
            },
        )
        follow_set_handle.update(0.0)

        query_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_current_area_var",
                "name": "camera_bounds",
                "value": "$camera.bounds",
            },
        )
        query_handle.update(0.0)
        self.assertEqual(
            world.variables["camera_bounds"],
            {"x": 16.0, "y": 32.0, "width": 48.0, "height": 64.0},
        )

        entity_query_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "player",
                "name": "camera_has_bounds",
                "value": "$camera.has_bounds",
            },
        )
        entity_query_handle.update(0.0)

        player = world.get_entity("player")
        assert player is not None
        self.assertTrue(player.variables["camera_has_bounds"])
        self.assertEqual(world.variables["camera_bounds"]["x"], 16.0)

        follow_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_current_area_var",
                "name": "follow_target",
                "value": "$camera.follow.entity_id",
            },
        )
        follow_handle.update(0.0)
        self.assertEqual(world.variables["follow_target"], "player")

        follow_mode_handle = execute_command_spec(
            registry,
            context,
            {
                "type": "set_current_area_var",
                "name": "follow_mode",
                "value": "$camera.follow.mode",
            },
        )
        follow_mode_handle.update(0.0)
        self.assertEqual(world.variables["follow_mode"], "entity")
