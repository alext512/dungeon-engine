"""Main runtime wiring for play mode."""

from __future__ import annotations

import logging
from pathlib import Path
import random

import pygame

from dungeon_engine import config
from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.library import build_project_command_database
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.context_services import (
    build_command_services,
)
from dungeon_engine.commands.runner import AreaTransitionRequest, CommandContext, CommandRunner
from dungeon_engine.engine.asset_manager import AssetManager
from dungeon_engine.engine.audio import AudioPlayer
from dungeon_engine.engine.game_area_runtime import GameAreaRuntimeMixin
from dungeon_engine.engine.camera import Camera
from dungeon_engine.engine.dialogue_runtime import DialogueRuntime
from dungeon_engine.engine.game_save_runtime import GameSaveRuntimeMixin
from dungeon_engine.engine.inventory_runtime import InventoryRuntime
from dungeon_engine.engine.input_handler import InputHandler
from dungeon_engine.engine.renderer import Renderer
from dungeon_engine.engine.screen import ScreenElementManager
from dungeon_engine.systems.animation import AnimationSystem
from dungeon_engine.systems.collision import CollisionSystem
from dungeon_engine.systems.interaction import InteractionSystem
from dungeon_engine.systems.movement import MovementSystem
from dungeon_engine.world.persistence import PersistenceRuntime


class Game(GameAreaRuntimeMixin, GameSaveRuntimeMixin):
    """Own the play-mode runtime loop."""

    def __init__(self, area_path: Path, project: "ProjectContext") -> None:
        from dungeon_engine.project_context import ProjectContext  # noqa: F811

        pygame.init()

        self.internal_width = max(1, int(project.internal_width))
        self.internal_height = max(1, int(project.internal_height))
        self.output_scale = config.SCALE
        self.display_surface = pygame.display.set_mode(
            self._window_size_for_scale(self.output_scale)
        )
        self.clock = pygame.time.Clock()
        self.headless = pygame.display.get_driver() == "dummy"
        self.fixed_timestep = config.FIXED_TIMESTEP_SECONDS
        self._accumulated_time = 0.0
        self._max_catchup_ticks = 5
        self.debug_inspection_enabled = bool(project.debug_inspection_enabled)
        self.simulation_paused = False
        self._debug_step_tick_requested = False
        self.simulation_tick_count = 0

        self.area_path = Path(area_path)
        self.project = project
        self.asset_manager = AssetManager(project=project)
        self.audio_player = AudioPlayer(self.asset_manager, enabled=not self.headless)
        self.screen_manager = ScreenElementManager()
        self.persistence_runtime = PersistenceRuntime(project=project)

        self.renderer = Renderer(
            self.display_surface,
            self.asset_manager,
            internal_width=self.internal_width,
            internal_height=self.internal_height,
            output_scale=self.output_scale,
        )
        self.camera: Camera | None = None
        self.command_registry = CommandRegistry()
        register_builtin_commands(self.command_registry)
        build_project_command_database(self.project)

        self.collision_system: CollisionSystem | None = None
        self.interaction_system: InteractionSystem | None = None
        self.movement_system: MovementSystem | None = None
        self.animation_system: AnimationSystem | None = None
        self.command_runner: CommandRunner | None = None
        self.input_handler: InputHandler | None = None
        self.dialogue_runtime: DialogueRuntime | None = None
        self.inventory_runtime: InventoryRuntime | None = None
        self._pending_area_change_request: AreaTransitionRequest | None = None
        self._pending_new_game_request: AreaTransitionRequest | None = None
        self._pending_load_save_path: Path | None = None
        self._quit_requested = False

        self._load_area_runtime(self.area_path)
        self._update_window_caption()

    def run(self, max_frames: int | None = None) -> None:
        """Run the game loop until the user quits or a frame cap is reached."""
        running = True
        frame_count = 0

        while running:
            dt = self.clock.tick_busy_loop(config.FPS) / 1000.0
            events = pygame.event.get()
            running = self._run_play_frame(dt, events)

            frame_count += 1
            if max_frames is not None and frame_count >= max_frames:
                running = False

        pygame.quit()

    def _run_play_frame(self, dt: float, events: list[pygame.event.Event]) -> bool:
        """Advance the play state for one frame."""
        if self.input_handler is None:
            raise RuntimeError("Game runtime is missing an input handler.")
        if self.command_runner is None:
            raise RuntimeError("Game runtime is missing a command runner.")
        if self.movement_system is None:
            raise RuntimeError("Game runtime is missing a movement system.")
        if self.animation_system is None:
            raise RuntimeError("Game runtime is missing an animation system.")

        input_result = self.input_handler.handle_events(events)
        if input_result.should_quit:
            return False

        if self.simulation_paused:
            self._flush_immediate_command_work()
            self._accumulated_time = 0.0
            if self._debug_step_tick_requested and self.debug_inspection_enabled:
                tick_dt = self.fixed_timestep if self.fixed_timestep > 0 else dt
                self._debug_step_tick_requested = False
                self._advance_simulation_tick(tick_dt)
            else:
                self._debug_step_tick_requested = False
        else:
            self._debug_step_tick_requested = False
            if self.fixed_timestep <= 0:
                self._advance_simulation_tick(dt)
            else:
                max_accumulated = self.fixed_timestep * self._max_catchup_ticks
                self._accumulated_time = min(self._accumulated_time + dt, max_accumulated)
                catchup_ticks = 0
                while (
                    self._accumulated_time >= self.fixed_timestep
                    and catchup_ticks < self._max_catchup_ticks
                ):
                    self._advance_simulation_tick(self.fixed_timestep)
                    self._accumulated_time -= self.fixed_timestep
                    catchup_ticks += 1

        if self._quit_requested:
            return False

        self.camera.update(self.world, advance_tick=False)
        self.renderer.render(
            self.area,
            self.world,
            self.camera,
            self.screen_manager,
        )
        self._update_window_caption()
        return True

    def _advance_simulation_tick(self, dt: float) -> None:
        """Advance gameplay by one fixed simulation step."""
        if self.input_handler is None:
            raise RuntimeError("Game runtime is missing an input handler.")
        if self.command_runner is None:
            raise RuntimeError("Game runtime is missing a command runner.")
        if self.movement_system is None:
            raise RuntimeError("Game runtime is missing a movement system.")
        if self.animation_system is None:
            raise RuntimeError("Game runtime is missing an animation system.")

        self._settle_runtime_work()
        self._advance_simulation_systems_tick(dt)
        self._advance_runtime_waits_tick(dt)
        self._settle_runtime_work()
        self._process_input_intent(dt)
        self._settle_runtime_work()
        self._advance_visual_presentation_tick(dt)
        self._apply_scene_boundary_changes_if_requested()
        self.simulation_tick_count += 1

    def _settle_runtime_work(self) -> None:
        """Settle ready command and modal-runtime work without advancing time."""
        if self.command_runner is None:
            return

        max_passes = max(1, int(self.command_runner.max_settle_passes))
        for _ in range(max_passes):
            before_state = self._runtime_settle_signature()
            self.command_runner.settle()
            if self.command_runner.scene_boundary_requested:
                return
            if self.dialogue_runtime is not None:
                self.dialogue_runtime.update(0.0)
            if self.command_runner.scene_boundary_requested:
                return
            if self.inventory_runtime is not None:
                self.inventory_runtime.update(0.0)
            if self.command_runner.scene_boundary_requested:
                return
            self.command_runner.settle()
            after_state = self._runtime_settle_signature()
            if after_state == before_state:
                return

        logging.getLogger(__name__).warning(
            "Runtime settle reached %s game-level passes; command runner state was left settled as far as possible.",
            max_passes,
        )

    def _runtime_settle_signature(self) -> tuple[object, ...]:
        """Return a small snapshot used to stop game-level zero-dt settling."""
        runner_state: tuple[object, ...]
        if self.command_runner is None:
            runner_state = ()
        else:
            runner_state = (
                self.command_runner.context.command_execution_count,
                tuple(queued.name for queued in self.command_runner.pending),
                tuple(id(handle) for handle in self.command_runner.root_handles),
                tuple(
                    id(handle)
                    for handle in self.command_runner._pending_spawned_root_handles
                ),
                self.command_runner.scene_boundary_requested,
            )

        dialogue_state: tuple[object, ...]
        if self.dialogue_runtime is None:
            dialogue_state = ()
        else:
            session = self.dialogue_runtime.current_session
            dialogue_state = (
                id(session) if session is not None else None,
                len(self.dialogue_runtime.session_stack),
                (
                    id(session.pending_handle)
                    if session is not None and session.pending_handle is not None
                    else None
                ),
                None if session is None else session.timer_remaining,
            )

        inventory_state: tuple[object, ...]
        if self.inventory_runtime is None:
            inventory_state = ()
        else:
            inventory_state = (
                id(self.inventory_runtime.current_session)
                if self.inventory_runtime.current_session is not None
                else None,
            )

        return runner_state + dialogue_state + inventory_state

    def _advance_simulation_systems_tick(self, dt: float) -> None:
        """Advance non-command simulation systems by one logical tick."""
        _ = dt
        if self.movement_system is not None:
            self.movement_system.update_tick()

    def _advance_runtime_waits_tick(self, dt: float) -> None:
        """Advance async command and modal-runtime waits by one logical tick."""
        if self.command_runner is not None:
            self.command_runner.advance_tick(dt)
        if self.dialogue_runtime is not None:
            self.dialogue_runtime.update(dt)
        if self.inventory_runtime is not None:
            self.inventory_runtime.update(dt)

    def _process_input_intent(self, dt: float) -> None:
        """Convert held input intent into ordinary command requests."""
        if self.input_handler is not None:
            self.input_handler.update_held_direction_repeat(dt)

    def _advance_visual_presentation_tick(self, dt: float) -> None:
        """Advance presentation systems after simulation and command work settles."""
        if self.animation_system is not None:
            self.animation_system.update_tick(dt)
        self.screen_manager.update_tick()
        if self.camera is not None:
            self.camera.update(self.world, advance_tick=True)

    def _install_play_runtime(self) -> None:
        """Rebuild runtime systems around the current play world."""
        self.camera = Camera(self.internal_width, self.internal_height, self.area)
        self.camera.update(self.world, advance_tick=False)
        self.screen_manager.clear()

        self.collision_system = CollisionSystem(self.area, self.world)
        self.interaction_system = InteractionSystem(self.world)
        self.movement_system = MovementSystem(
            self.area,
            self.world,
            self.collision_system,
            self.persistence_runtime,
        )
        self.animation_system = AnimationSystem(self.world)
        command_services = build_command_services(
            area=self.area,
            world=self.world,
            collision_system=self.collision_system,
            movement_system=self.movement_system,
            interaction_system=self.interaction_system,
            animation_system=self.animation_system,
            text_renderer=self.renderer.text_renderer,
            screen_manager=self.screen_manager,
            camera=self.camera,
            audio_player=self.audio_player,
            persistence_runtime=self.persistence_runtime,
            request_area_change=self.request_area_change,
            request_new_game=self.request_new_game,
            request_load_game=self.request_load_game,
            save_game=self.save_game,
            request_quit=self.request_quit,
            set_simulation_paused=self._set_simulation_paused,
            get_simulation_paused=self._get_simulation_paused,
            request_step_simulation_tick=self._request_step_simulation_tick,
            adjust_output_scale=self._adjust_output_scale,
            debug_inspection_enabled=self.debug_inspection_enabled,
        )
        command_context = CommandContext(
            project=self.project,
            asset_manager=self.asset_manager,
            services=command_services,
            random_generator=random.Random(),
        )
        self.command_runner = CommandRunner(self.command_registry, command_context)
        self.dialogue_runtime = DialogueRuntime(
            project=self.project,
            screen_manager=self.screen_manager,
            text_renderer=self.renderer.text_renderer,
            registry=self.command_registry,
            command_context=command_context,
        )
        self.inventory_runtime = InventoryRuntime(
            project=self.project,
            screen_manager=self.screen_manager,
            text_renderer=self.renderer.text_renderer,
            command_context=command_context,
        )
        if command_services.ui is None:
            raise RuntimeError("Play runtime command services are missing the UI service bundle.")
        command_services.ui.dialogue_runtime = self.dialogue_runtime
        command_services.ui.inventory_runtime = self.inventory_runtime
        self.input_handler = InputHandler(
            self.command_runner,
            self.world,
            dialogue_runtime=self.dialogue_runtime,
            inventory_runtime=self.inventory_runtime,
        )
        self.movement_system.occupancy_transition_callback = self._queue_occupancy_transition_hooks

    def request_quit(self) -> None:
        """Ask the runtime loop to close the game at the end of the current frame."""
        self._quit_requested = True

    def _request_step_simulation_tick(self) -> None:
        """Request one debug simulation tick on the next paused-frame pass."""
        self._debug_step_tick_requested = True

    def _flush_immediate_command_work(self) -> None:
        """Let queued immediate commands settle while paused without advancing time."""
        if self.command_runner is None:
            return
        self._settle_runtime_work()
        self._apply_scene_boundary_changes_if_requested()

    def _has_blocking_runtime_work(self) -> bool:
        """Return whether any active runtime lane should block deferred transitions."""
        runner_busy = self.command_runner is not None and self.command_runner.has_pending_work()
        dialogue_busy = self.dialogue_runtime is not None and self.dialogue_runtime.has_pending_work()
        inventory_busy = self.inventory_runtime is not None and self.inventory_runtime.has_pending_work()
        return bool(runner_busy or dialogue_busy or inventory_busy)

    def _window_size_for_scale(self, scale: int) -> tuple[int, int]:
        """Return the integer-scaled output size for the current internal surface."""
        zoom = max(config.MIN_SCALE, int(scale))
        return (
            self.internal_width * zoom,
            self.internal_height * zoom,
        )

    def _adjust_output_scale(self, delta: int) -> None:
        """Change the integer window zoom while respecting configured bounds."""
        target_scale = max(config.MIN_SCALE, min(config.MAX_SCALE, self.output_scale + int(delta)))
        if target_scale == self.output_scale:
            return

        self.output_scale = target_scale
        self.display_surface = pygame.display.set_mode(
            self._window_size_for_scale(self.output_scale)
        )
        self.renderer.set_display_surface(self.display_surface)
        self.renderer.set_output_scale(self.output_scale)
        self._update_window_caption()

    def _set_simulation_paused(self, paused: bool) -> None:
        """Pause or resume fixed-step simulation without affecting rendering."""
        self.simulation_paused = bool(paused)
        self._accumulated_time = 0.0
        self._update_window_caption()

    def _get_simulation_paused(self) -> bool:
        """Return whether debug simulation pause is currently active."""
        return bool(self.simulation_paused)

    def _update_window_caption(self) -> None:
        """Show zoom, simulation state, and input-routing details in the window title."""
        if self.headless:
            return

        error_notice = None
        if self.command_runner is not None:
            error_notice = self.command_runner.last_error_notice

        if not self.debug_inspection_enabled:
            caption = config.WINDOW_TITLE
            if error_notice:
                caption = f"{caption} | {error_notice}"
            pygame.display.set_caption(caption)
            return

        input_summary = "none"
        if self.world is not None:
            summary_parts: list[str] = []
            for action in ("move_up", "interact", "menu"):
                target_id = self.world.get_input_target_id(action)
                summary_parts.append(f"{action}={target_id or '-'}")
            input_summary = ", ".join(summary_parts)

        state_label = "PAUSED" if self.simulation_paused else "RUNNING"
        fps_text = f"{self.clock.get_fps():.1f}"
        caption = (
            f"{config.WINDOW_TITLE} | {state_label} | Zoom x{self.output_scale} | "
            f"Render FPS {fps_text} | Tick {self.simulation_tick_count} | Inputs {input_summary}"
        )
        if error_notice:
            caption = f"{caption} | {error_notice}"
        pygame.display.set_caption(caption)
