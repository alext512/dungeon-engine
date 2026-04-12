from __future__ import annotations

import unittest

from dungeon_engine.commands.context_services import (
    COMMAND_SERVICE_INJECTION_NAMES,
    CommandRuntimeServices,
    CommandServices,
    attach_modal_command_services,
    build_play_command_services,
    resolve_service_injection,
)
from dungeon_engine.commands.context_types import AreaTransitionRequest


def _play_service_kwargs(**overrides: object) -> dict[str, object]:
    sentinel = object()
    kwargs: dict[str, object] = {
        "area": sentinel,
        "world": sentinel,
        "collision_system": sentinel,
        "movement_system": sentinel,
        "interaction_system": sentinel,
        "animation_system": sentinel,
        "text_renderer": sentinel,
        "screen_manager": sentinel,
        "camera": sentinel,
        "audio_player": sentinel,
        "persistence_runtime": sentinel,
        "request_area_change": lambda _request: None,
        "request_new_game": lambda _request: None,
        "request_load_game": lambda _path: None,
        "save_game": lambda _path: True,
        "request_quit": lambda: None,
        "set_simulation_paused": lambda _paused: None,
        "get_simulation_paused": lambda: False,
        "request_step_simulation_tick": lambda: None,
        "adjust_output_scale": lambda _scale: None,
    }
    kwargs.update(overrides)
    return kwargs


class CommandServiceAssemblyTests(unittest.TestCase):
    def test_advertised_service_injections_resolve_from_empty_services(self) -> None:
        services = CommandServices()

        for injection_name in sorted(COMMAND_SERVICE_INJECTION_NAMES):
            with self.subTest(injection_name=injection_name):
                value = resolve_service_injection(services, injection_name)
                expected = False if injection_name == "debug_inspection_enabled" else None
                self.assertIs(value, expected)

    def test_unknown_service_injection_name_is_rejected(self) -> None:
        with self.assertRaises(KeyError):
            resolve_service_injection(CommandServices(), "unknown_service")

    def test_runtime_transition_callback_is_typed_service_payload(self) -> None:
        recorded_requests: list[AreaTransitionRequest] = []

        services = CommandServices(
            runtime=CommandRuntimeServices(
                request_area_change=recorded_requests.append,
            ),
        )

        request_area_change = resolve_service_injection(
            services,
            "request_area_change",
        )
        request_area_change(AreaTransitionRequest(area_id="areas/next_room"))

        self.assertEqual(
            recorded_requests,
            [AreaTransitionRequest(area_id="areas/next_room")],
        )

    def test_build_play_command_services_creates_production_bundles(self) -> None:
        sentinel = object()

        services = build_play_command_services(
            area=sentinel,  # type: ignore[arg-type]
            world=sentinel,  # type: ignore[arg-type]
            collision_system=sentinel,  # type: ignore[arg-type]
            movement_system=sentinel,  # type: ignore[arg-type]
            interaction_system=sentinel,  # type: ignore[arg-type]
            animation_system=sentinel,  # type: ignore[arg-type]
            text_renderer=sentinel,  # type: ignore[arg-type]
            screen_manager=sentinel,  # type: ignore[arg-type]
            camera=sentinel,  # type: ignore[arg-type]
            audio_player=sentinel,  # type: ignore[arg-type]
            persistence_runtime=sentinel,  # type: ignore[arg-type]
            request_area_change=lambda _request: None,
            request_new_game=lambda _request: None,
            request_load_game=lambda _path: None,
            save_game=lambda _path: True,
            request_quit=lambda: None,
            set_simulation_paused=lambda _paused: None,
            get_simulation_paused=lambda: False,
            request_step_simulation_tick=lambda: None,
            adjust_output_scale=lambda _scale: None,
            debug_inspection_enabled=True,
        )

        self.assertIsNotNone(services.world)
        self.assertIsNotNone(services.ui)
        self.assertIsNotNone(services.audio)
        self.assertIsNotNone(services.persistence)
        self.assertIsNotNone(services.runtime)
        assert services.ui is not None
        assert services.runtime is not None
        self.assertIsNone(services.ui.dialogue_runtime)
        self.assertIsNone(services.ui.inventory_runtime)
        self.assertTrue(services.runtime.debug_inspection_enabled)

    def test_build_play_command_services_rejects_missing_required_service(self) -> None:
        required_names = (
            "area",
            "world",
            "collision_system",
            "movement_system",
            "interaction_system",
            "animation_system",
            "text_renderer",
            "screen_manager",
            "camera",
            "audio_player",
            "persistence_runtime",
            "request_area_change",
            "request_new_game",
            "request_load_game",
            "save_game",
            "request_quit",
            "set_simulation_paused",
            "get_simulation_paused",
            "request_step_simulation_tick",
            "adjust_output_scale",
        )

        for required_name in required_names:
            with self.subTest(required_name=required_name):
                with self.assertRaisesRegex(RuntimeError, required_name):
                    build_play_command_services(
                        **_play_service_kwargs(**{required_name: None})
                    )

    def test_attach_modal_command_services_requires_ui_bundle(self) -> None:
        with self.assertRaises(RuntimeError):
            attach_modal_command_services(
                CommandServices(),
                dialogue_runtime=object(),  # type: ignore[arg-type]
                inventory_runtime=object(),  # type: ignore[arg-type]
            )

    def test_attach_modal_command_services_sets_ui_modal_runtimes(self) -> None:
        sentinel = object()
        services = build_play_command_services(
            area=sentinel,  # type: ignore[arg-type]
            world=sentinel,  # type: ignore[arg-type]
            collision_system=sentinel,  # type: ignore[arg-type]
            movement_system=sentinel,  # type: ignore[arg-type]
            interaction_system=sentinel,  # type: ignore[arg-type]
            animation_system=sentinel,  # type: ignore[arg-type]
            text_renderer=sentinel,  # type: ignore[arg-type]
            screen_manager=sentinel,  # type: ignore[arg-type]
            camera=sentinel,  # type: ignore[arg-type]
            audio_player=sentinel,  # type: ignore[arg-type]
            persistence_runtime=sentinel,  # type: ignore[arg-type]
            request_area_change=lambda _request: None,
            request_new_game=lambda _request: None,
            request_load_game=lambda _path: None,
            save_game=lambda _path: True,
            request_quit=lambda: None,
            set_simulation_paused=lambda _paused: None,
            get_simulation_paused=lambda: False,
            request_step_simulation_tick=lambda: None,
            adjust_output_scale=lambda _scale: None,
        )
        dialogue_runtime = object()
        inventory_runtime = object()

        attach_modal_command_services(
            services,
            dialogue_runtime=dialogue_runtime,  # type: ignore[arg-type]
            inventory_runtime=inventory_runtime,  # type: ignore[arg-type]
        )

        assert services.ui is not None
        self.assertIs(services.ui.dialogue_runtime, dialogue_runtime)
        self.assertIs(services.ui.inventory_runtime, inventory_runtime)


if __name__ == "__main__":
    unittest.main()
