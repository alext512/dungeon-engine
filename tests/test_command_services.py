from __future__ import annotations

import unittest

from dungeon_engine.commands.context_services import (
    CommandServices,
    attach_modal_command_services,
    build_play_command_services,
)


class CommandServiceAssemblyTests(unittest.TestCase):
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
