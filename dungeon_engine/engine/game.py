"""Main runtime wiring for play mode."""

from __future__ import annotations

from pathlib import Path
import random

import pygame

from dungeon_engine import config
from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.library import build_project_command_database
from dungeon_engine.commands.registry import CommandRegistry
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

        self.command_runner.update(0.0)
        if self.dialogue_runtime is not None:
            self.dialogue_runtime.update(0.0)
        if self.inventory_runtime is not None:
            self.inventory_runtime.update(0.0)
        self.movement_system.update_tick()
        self.input_handler.update_held_direction_repeat(dt)
        self.animation_system.update_tick(dt)
        self.command_runner.update(dt)
        if self.dialogue_runtime is not None:
            self.dialogue_runtime.update(dt)
        if self.inventory_runtime is not None:
            self.inventory_runtime.update(dt)
        self.screen_manager.update_tick()
        self.camera.update(self.world, advance_tick=True)
        self._apply_pending_reset_if_idle()
        self.command_runner.update(0.0)
        if self.dialogue_runtime is not None:
            self.dialogue_runtime.update(0.0)
        if self.inventory_runtime is not None:
            self.inventory_runtime.update(0.0)
        self._apply_pending_reset_if_idle()
        self._apply_pending_load_if_idle()
        self._apply_pending_new_game_if_idle()
        self._apply_pending_area_change_if_idle()
        self.simulation_tick_count += 1

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
        command_context = CommandContext(
            area=self.area,
            world=self.world,
            collision_system=self.collision_system,
            movement_system=self.movement_system,
            interaction_system=self.interaction_system,
            animation_system=self.animation_system,
            project=self.project,
            asset_manager=self.asset_manager,
            text_renderer=self.renderer.text_renderer,
            camera=self.camera,
            audio_player=self.audio_player,
            screen_manager=self.screen_manager,
            dialogue_runtime=None,
            inventory_runtime=None,
            command_runner=None,
            random_generator=random.Random(),
            persistence_runtime=self.persistence_runtime,
            request_area_change=self.request_area_change,
            request_new_game=self.request_new_game,
            request_load_game=self.request_load_game,
            save_game=self.save_game,
            request_quit=self.request_quit,
            debug_inspection_enabled=self.debug_inspection_enabled,
            set_simulation_paused=self._set_simulation_paused,
            get_simulation_paused=self._get_simulation_paused,
            request_step_simulation_tick=self._request_step_simulation_tick,
            adjust_output_scale=self._adjust_output_scale,
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
        command_context.dialogue_runtime = self.dialogue_runtime
        command_context.inventory_runtime = self.inventory_runtime
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
        for _ in range(8):
            before_state = (
                len(self.command_runner.pending),
                len(self.command_runner.root_handles),
                tuple(id(handle) for handle in self.command_runner.root_handles),
                False if self.dialogue_runtime is None else self.dialogue_runtime.has_pending_work(),
                False if self.inventory_runtime is None else self.inventory_runtime.has_pending_work(),
            )
            self.command_runner.update(0.0)
            if self.dialogue_runtime is not None:
                self.dialogue_runtime.update(0.0)
            if self.inventory_runtime is not None:
                self.inventory_runtime.update(0.0)
            after_state = (
                len(self.command_runner.pending),
                len(self.command_runner.root_handles),
                tuple(id(handle) for handle in self.command_runner.root_handles),
                False if self.dialogue_runtime is None else self.dialogue_runtime.has_pending_work(),
                False if self.inventory_runtime is None else self.inventory_runtime.has_pending_work(),
            )
            if not self._has_blocking_runtime_work():
                break
            if after_state == before_state:
                break

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
