"""Main runtime wiring for play mode."""

from __future__ import annotations

import copy
from pathlib import Path

import pygame

from puzzle_dungeon import config
from puzzle_dungeon.commands.builtin import register_builtin_commands
from puzzle_dungeon.commands.registry import CommandRegistry
from puzzle_dungeon.commands.runner import CommandContext, CommandRunner
from puzzle_dungeon.engine.asset_manager import AssetManager
from puzzle_dungeon.engine.camera import Camera
from puzzle_dungeon.engine.input_handler import InputHandler
from puzzle_dungeon.engine.renderer import Renderer
from puzzle_dungeon.systems.animation import AnimationSystem
from puzzle_dungeon.systems.collision import CollisionSystem
from puzzle_dungeon.systems.interaction import InteractionSystem
from puzzle_dungeon.systems.movement import MovementSystem
from puzzle_dungeon.world.loader import load_area, load_area_from_data
from puzzle_dungeon.world.persistence import (
    PersistenceRuntime,
    ResetRequest,
    get_persistent_area_state,
    select_entity_ids_by_tags,
)
from puzzle_dungeon.world.serializer import serialize_area


class Game:
    """Own the play-mode runtime loop."""

    def __init__(self, area_path: Path | None = None, project: "ProjectContext | None" = None) -> None:
        from puzzle_dungeon.project import ProjectContext  # noqa: F811

        pygame.init()

        self.output_scale = config.SCALE
        self.display_surface = pygame.display.set_mode(
            self._window_size_for_scale(self.output_scale)
        )
        self.clock = pygame.time.Clock()
        self.headless = pygame.display.get_driver() == "dummy"
        self.fixed_timestep = config.FIXED_TIMESTEP_SECONDS
        self._accumulated_time = 0.0
        self._max_catchup_ticks = 5
        self.debug_inspection_enabled = bool(project.debug_inspection_enabled) if project is not None else False
        self.simulation_paused = False
        self.simulation_tick_count = 0

        if area_path is None:
            raise ValueError("Game requires an explicit area path. Use run_game.py or Run_Game.cmd.")
        self.area_path = area_path
        self.project = project
        self.asset_manager = AssetManager(project=project)
        self.persistence_runtime = PersistenceRuntime(config.DEFAULT_SAVE_SLOT_PATH)

        document_area, document_world = load_area(self.area_path, asset_manager=self.asset_manager)
        document_data = serialize_area(document_area, document_world)
        self.play_document_data = copy.deepcopy(document_data)
        self.play_authored_area, self.play_authored_world = load_area_from_data(
            copy.deepcopy(document_data),
            source_name=str(self.area_path),
            asset_manager=self.asset_manager,
        )

        self.renderer = Renderer(
            self.display_surface,
            self.asset_manager,
            output_scale=self.output_scale,
        )
        self.camera = Camera(config.INTERNAL_WIDTH, config.INTERNAL_HEIGHT, self.play_authored_area)
        self.command_registry = CommandRegistry()
        register_builtin_commands(self.command_registry)

        self.collision_system: CollisionSystem | None = None
        self.interaction_system: InteractionSystem | None = None
        self.movement_system: MovementSystem | None = None
        self.animation_system: AnimationSystem | None = None
        self.command_runner: CommandRunner | None = None
        self.input_handler: InputHandler | None = None

        self.area = self.play_authored_area
        self.world = self.play_authored_world

        self.persistence_runtime.bind_area(self.play_authored_area.area_id)
        self._apply_reentry_resets()
        self.area, self.world = load_area_from_data(
            copy.deepcopy(document_data),
            source_name=str(self.area_path),
            asset_manager=self.asset_manager,
            persistent_area_state=get_persistent_area_state(
                self.persistence_runtime.save_data,
                self.play_authored_area.area_id,
            ),
        )
        self._install_play_runtime()
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
        assert self.input_handler is not None
        assert self.command_runner is not None
        assert self.movement_system is not None
        assert self.animation_system is not None

        input_result = self.input_handler.handle_events(events)
        if input_result.save_requested:
            self._save_persistent_state_to_disk()
        if input_result.load_requested:
            self._reload_persistent_state_from_disk()
        if input_result.should_quit:
            return False
        if input_result.toggle_pause_requested and self.debug_inspection_enabled:
            self._set_simulation_paused(not self.simulation_paused)
        if input_result.zoom_delta and self.debug_inspection_enabled:
            self._adjust_output_scale(input_result.zoom_delta)

        if self.simulation_paused:
            self._accumulated_time = 0.0
            if input_result.step_tick_requested and self.debug_inspection_enabled:
                tick_dt = self.fixed_timestep if self.fixed_timestep > 0 else dt
                self._advance_simulation_tick(tick_dt)
        else:
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

        self.camera.update(self.world, advance_tick=False)
        self.renderer.render(
            self.area,
            self.world,
            self.camera,
        )
        self._update_window_caption()
        return True

    def _advance_simulation_tick(self, dt: float) -> None:
        """Advance gameplay by one fixed simulation step."""
        assert self.input_handler is not None
        assert self.command_runner is not None
        assert self.movement_system is not None
        assert self.animation_system is not None

        self.input_handler.enqueue_held_movement_if_idle()
        self.command_runner.update(0.0)
        self.movement_system.update_tick()
        self.animation_system.update_tick(dt)
        self.camera.update(self.world, advance_tick=True)
        self.command_runner.update(dt)
        self._apply_pending_reset_if_idle()
        self.command_runner.update(0.0)
        self._apply_pending_reset_if_idle()
        self.simulation_tick_count += 1

    def _install_play_runtime(self) -> None:
        """Rebuild runtime systems around the current play world."""
        self.camera = Camera(config.INTERNAL_WIDTH, config.INTERNAL_HEIGHT, self.area)
        self.camera.follow_active_entity()
        self.camera.update(self.world, advance_tick=False)

        self.collision_system = CollisionSystem(self.area, self.world)
        self.interaction_system = InteractionSystem(self.world)
        self.movement_system = MovementSystem(self.area, self.world, self.collision_system)
        self.animation_system = AnimationSystem(self.world)
        command_context = CommandContext(
            area=self.area,
            world=self.world,
            collision_system=self.collision_system,
            movement_system=self.movement_system,
            interaction_system=self.interaction_system,
            animation_system=self.animation_system,
            camera=self.camera,
            input_handler=None,
            persistence_runtime=self.persistence_runtime,
        )
        self.command_runner = CommandRunner(self.command_registry, command_context)
        project_input_events = None if self.project is None else self.project.input_event_names
        self.input_handler = InputHandler(
            self.command_runner,
            self.world,
            action_event_names=project_input_events,
            debug_inspection_enabled=self.debug_inspection_enabled,
        )
        command_context.input_handler = self.input_handler

    def _window_size_for_scale(self, scale: int) -> tuple[int, int]:
        """Return the integer-scaled output size for the current internal surface."""
        zoom = max(config.MIN_SCALE, int(scale))
        return (
            config.INTERNAL_WIDTH * zoom,
            config.INTERNAL_HEIGHT * zoom,
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

    def _update_window_caption(self) -> None:
        """Show zoom, simulation state, and active-entity details in the window title."""
        if self.headless:
            return

        if not self.debug_inspection_enabled:
            pygame.display.set_caption(config.WINDOW_TITLE)
            return

        active_entity = self.world.get_active_entity() if self.world is not None else None
        active_summary = "none"
        if active_entity is not None:
            active_summary = (
                f"{active_entity.entity_id} "
                f"g({active_entity.grid_x},{active_entity.grid_y}) "
                f"p({active_entity.pixel_x:.0f},{active_entity.pixel_y:.0f}) "
                f"f{active_entity.current_frame}"
            )

        state_label = "PAUSED" if self.simulation_paused else "RUNNING"
        fps_text = f"{self.clock.get_fps():.1f}"
        caption = (
            f"{config.WINDOW_TITLE} | {state_label} | Zoom x{self.output_scale} | "
            f"Render FPS {fps_text} | Tick {self.simulation_tick_count} | Active {active_summary}"
        )
        pygame.display.set_caption(caption)

    def _apply_pending_reset_if_idle(self) -> None:
        """Apply queued immediate reset requests once the command lane is idle."""
        if self.command_runner is None or self.command_runner.has_pending_work():
            return

        request = self.persistence_runtime.consume_immediate_reset()
        if request is None:
            return

        if request.kind == "persistent":
            self.persistence_runtime.clear_persistent_area_state(
                self.play_authored_area.area_id,
                self.play_authored_world,
                include_tags=request.include_tags,
                exclude_tags=request.exclude_tags,
            )

        self._apply_runtime_reset(request)

    def _apply_reentry_resets(self) -> None:
        """Apply scheduled on-reentry resets before constructing the play world."""
        for request in self.persistence_runtime.consume_reentry_resets(self.play_authored_area.area_id):
            if request.kind != "persistent":
                continue
            self.persistence_runtime.clear_persistent_area_state(
                self.play_authored_area.area_id,
                self.play_authored_world,
                include_tags=request.include_tags,
                exclude_tags=request.exclude_tags,
            )

    def _apply_runtime_reset(self, request: ResetRequest) -> None:
        """Reset the whole room or matching entities against authored+persistent state."""
        selected_ids = select_entity_ids_by_tags(
            self.play_authored_world,
            include_tags=request.include_tags,
            exclude_tags=request.exclude_tags,
        )
        if not request.include_tags and not request.exclude_tags:
            self._rebuild_play_world(preserve_player=True)
            return
        if not selected_ids:
            return

        reference_area, reference_world = self._build_current_play_reference()
        _ = reference_area
        for entity_id in selected_ids:
            current_entity = self.world.get_entity(entity_id)
            reference_entity = reference_world.get_entity(entity_id)
            if reference_entity is None:
                if current_entity is not None:
                    self.world.remove_entity(entity_id)
                continue
            self.world.add_entity(copy.deepcopy(reference_entity))

    def _build_current_play_reference(self):
        """Build a fresh play world from authored data plus current persistent overrides."""
        assert self.play_document_data is not None
        return load_area_from_data(
            copy.deepcopy(self.play_document_data),
            source_name=str(self.area_path),
            asset_manager=self.asset_manager,
            persistent_area_state=get_persistent_area_state(
                self.persistence_runtime.save_data,
                self.play_authored_area.area_id,
            ),
        )

    def _rebuild_play_world(self, *, preserve_player: bool) -> None:
        """Rebuild the current play world from authored data plus persistent overrides."""
        preserved_player = copy.deepcopy(self.world.get_player()) if preserve_player else None
        self.area, self.world = self._build_current_play_reference()
        if preserved_player is not None:
            self.world.add_entity(preserved_player)
        self._install_play_runtime()

    def _save_persistent_state_to_disk(self) -> None:
        """Write the current in-memory persistent state to the save slot."""
        self.persistence_runtime.flush(force=True)

    def _reload_persistent_state_from_disk(self) -> None:
        """Reload persistent state from disk and rebuild the current room."""
        if self.command_runner is not None and self.command_runner.has_pending_work():
            return

        self.persistence_runtime.reload_from_disk()
        self._rebuild_play_world(preserve_player=True)
