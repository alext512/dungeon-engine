"""Main runtime wiring for play mode."""

from __future__ import annotations

import copy
from pathlib import Path

import pygame

from dungeon_engine import config
from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.library import build_named_command_database
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import CommandContext, CommandRunner
from dungeon_engine.engine.asset_manager import AssetManager
from dungeon_engine.engine.audio import AudioPlayer
from dungeon_engine.engine.camera import Camera
from dungeon_engine.engine.input_handler import InputHandler
from dungeon_engine.engine.renderer import Renderer
from dungeon_engine.engine.screen import ScreenElementManager
from dungeon_engine.engine.text import TextSessionManager
from dungeon_engine.systems.animation import AnimationSystem
from dungeon_engine.systems.collision import CollisionSystem
from dungeon_engine.systems.interaction import InteractionSystem
from dungeon_engine.systems.movement import MovementSystem
from dungeon_engine.world.loader import load_area, load_area_from_data
from dungeon_engine.world.persistence import (
    PersistenceRuntime,
    ResetRequest,
    apply_persistent_area_state,
    capture_current_area_state,
    get_persistent_area_state,
    select_entity_ids_by_tags,
)
from dungeon_engine.world.serializer import serialize_area


class Game:
    """Own the play-mode runtime loop."""

    def __init__(self, area_path: Path | None = None, project: "ProjectContext | None" = None) -> None:
        from dungeon_engine.project import ProjectContext  # noqa: F811

        pygame.init()

        self.internal_width = (
            max(1, int(project.internal_width))
            if project is not None
            else config.INTERNAL_WIDTH
        )
        self.internal_height = (
            max(1, int(project.internal_height))
            if project is not None
            else config.INTERNAL_HEIGHT
        )
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
        self.area_path = Path(area_path)
        self.project = project
        self.asset_manager = AssetManager(project=project)
        self.audio_player = AudioPlayer(self.asset_manager, enabled=not self.headless)
        self.screen_manager = ScreenElementManager()
        self.persistence_runtime = PersistenceRuntime()

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
        if self.project is not None:
            build_named_command_database(self.project)

        self.collision_system: CollisionSystem | None = None
        self.interaction_system: InteractionSystem | None = None
        self.movement_system: MovementSystem | None = None
        self.animation_system: AnimationSystem | None = None
        self.command_runner: CommandRunner | None = None
        self.input_handler: InputHandler | None = None
        self.text_session_manager: TextSessionManager | None = None
        self._pending_area_change_path: Path | None = None
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
        assert self.input_handler is not None
        assert self.command_runner is not None
        assert self.movement_system is not None
        assert self.animation_system is not None

        input_result = self.input_handler.handle_events(events)
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
        assert self.input_handler is not None
        assert self.command_runner is not None
        assert self.movement_system is not None
        assert self.animation_system is not None

        self.input_handler.enqueue_held_movement_if_idle()
        self.command_runner.update(0.0)
        self.movement_system.update_tick()
        self.animation_system.update_tick(dt)
        self.screen_manager.update_tick()
        self.camera.update(self.world, advance_tick=True)
        self.command_runner.update(dt)
        self._apply_pending_reset_if_idle()
        self.command_runner.update(0.0)
        self._apply_pending_reset_if_idle()
        self._apply_pending_load_if_idle()
        self._apply_pending_area_change_if_idle()
        self.simulation_tick_count += 1

    def _install_play_runtime(self) -> None:
        """Rebuild runtime systems around the current play world."""
        self.camera = Camera(self.internal_width, self.internal_height, self.area)
        self.camera.follow_active_entity()
        self.camera.update(self.world, advance_tick=False)
        self.screen_manager.clear()

        self.collision_system = CollisionSystem(self.area, self.world)
        self.interaction_system = InteractionSystem(self.world)
        self.movement_system = MovementSystem(self.area, self.world, self.collision_system)
        self.animation_system = AnimationSystem(self.world)
        self.text_session_manager = TextSessionManager(self.renderer.text_renderer)
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
            text_session_manager=self.text_session_manager,
            camera=self.camera,
            audio_player=self.audio_player,
            screen_manager=self.screen_manager,
            command_runner=None,
            input_handler=None,
            persistence_runtime=self.persistence_runtime,
            request_area_change=self.request_area_change,
            request_load_game=self.request_load_game,
            save_game=self.save_game,
            request_quit=self.request_quit,
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

    def request_area_change(self, area_path: str | Path) -> None:
        """Queue a transition into another authored area."""
        self._pending_area_change_path = self._resolve_area_path(area_path)
        self._pending_load_save_path = None

    def request_load_game(self, save_path: str | None = None) -> None:
        """Queue a save-slot load so it applies after the current command lane finishes."""
        resolved_save_path = (
            self._resolve_save_slot_path(save_path)
            if save_path is not None
            else self._prompt_for_load_save_path()
        )
        if resolved_save_path is None:
            return
        self._pending_load_save_path = resolved_save_path
        self._pending_area_change_path = None

    def save_game(self, save_path: str | None = None) -> bool:
        """Open a project-scoped save dialog or write to an explicit save path."""
        resolved_save_path = (
            self._resolve_save_slot_path(save_path)
            if save_path is not None
            else self._prompt_for_save_save_path()
        )
        if resolved_save_path is None:
            return False
        self._write_save_slot(resolved_save_path)
        return True

    def request_quit(self) -> None:
        """Ask the runtime loop to close the game at the end of the current frame."""
        self._quit_requested = True

    def _load_area_runtime(self, area_path: Path | str) -> None:
        """Load one authored area plus any persistent overrides and rebuild runtime systems."""
        resolved_area_path = self._resolve_area_path(area_path)
        document_area, document_world = load_area(
            resolved_area_path,
            asset_manager=self.asset_manager,
        )
        document_data = serialize_area(document_area, document_world)
        play_document_data = copy.deepcopy(document_data)
        play_authored_area, play_authored_world = load_area_from_data(
            copy.deepcopy(document_data),
            source_name=str(resolved_area_path),
            asset_manager=self.asset_manager,
        )
        self._apply_reentry_resets_for_area(play_authored_area.area_id, play_authored_world)
        area, world = load_area_from_data(
            copy.deepcopy(document_data),
            source_name=str(resolved_area_path),
            asset_manager=self.asset_manager,
            persistent_area_state=get_persistent_area_state(
                self.persistence_runtime.save_data,
                play_authored_area.area_id,
            ),
        )

        self.area_path = resolved_area_path
        self.play_document_data = play_document_data
        self.play_authored_area = play_authored_area
        self.play_authored_world = play_authored_world
        self.area = area
        self.world = world
        self.persistence_runtime.bind_area(
            self.play_authored_area.area_id,
            authored_world=self.play_authored_world,
        )
        self._install_play_runtime()

    def _resolve_area_path(self, area_path: Path | str) -> Path:
        """Resolve an area reference against the active project or current area location."""
        raw_path = Path(area_path)

        if self.project is not None:
            resolved = self.project.resolve_area_path(raw_path)
            if resolved is not None:
                return resolved

        candidate_inputs = [raw_path]
        if raw_path.suffix.lower() != ".json":
            candidate_inputs.append(raw_path.with_suffix(".json"))

        candidates: list[Path] = []
        seen: set[Path] = set()

        def _record(candidate: Path) -> None:
            resolved_candidate = candidate.resolve()
            if resolved_candidate in seen:
                return
            seen.add(resolved_candidate)
            candidates.append(candidate)

        for candidate_input in candidate_inputs:
            if candidate_input.is_absolute():
                _record(candidate_input)
                continue
            _record(self.area_path.parent / candidate_input)

        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()

        searched_paths = ", ".join(str(candidate) for candidate in candidates)
        raise FileNotFoundError(
            f"Cannot resolve area path '{area_path}'. "
            f"Searched: {searched_paths or '<none>'}."
        )

    def _project_save_dir(self) -> Path:
        """Return the active project's save-root directory, creating it when needed."""
        save_dir = self.project.save_dir if self.project is not None else config.SAVES_DIR
        save_dir.mkdir(parents=True, exist_ok=True)
        return save_dir.resolve()

    def _resolve_save_slot_path(self, save_path: str | Path) -> Path:
        """Resolve and validate a save-slot path inside the active project's save directory."""
        raw_path = Path(save_path)
        save_dir = self._project_save_dir()
        candidate = raw_path if raw_path.is_absolute() else save_dir / raw_path
        if candidate.suffix.lower() != ".json":
            candidate = candidate.with_suffix(".json")
        resolved = candidate.resolve()
        try:
            resolved.relative_to(save_dir)
        except ValueError as exc:
            raise ValueError(
                f"Save path '{resolved}' must stay inside '{save_dir}'."
            ) from exc
        return resolved

    def _default_save_slot_name(self) -> str:
        """Return a sensible default file name for project-scoped save dialogs."""
        current_save_path = self.persistence_runtime.save_path
        if current_save_path is not None:
            try:
                current_save_path.resolve().relative_to(self._project_save_dir())
                return current_save_path.name
            except ValueError:
                pass
        return "save_1.json"

    def _prompt_for_save_save_path(self) -> Path | None:
        """Open a Save As dialog rooted to the active project's save directory."""
        if self.headless:
            raise ValueError("save_game without an explicit save_path is unavailable in headless mode.")

        import tkinter as tk
        from tkinter import filedialog

        save_dir = self._project_save_dir()
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.asksaveasfilename(
            title="Save game",
            initialdir=str(save_dir),
            initialfile=self._default_save_slot_name(),
            defaultextension=".json",
            filetypes=[("JSON save files", "*.json"), ("All files", "*.*")],
        )
        root.destroy()
        if not file_path:
            return None
        return self._resolve_save_slot_path(Path(file_path))

    def _prompt_for_load_save_path(self) -> Path | None:
        """Open a load dialog rooted to the active project's save directory."""
        if self.headless:
            raise ValueError("load_game without an explicit save_path is unavailable in headless mode.")

        import tkinter as tk
        from tkinter import filedialog

        save_dir = self._project_save_dir()
        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename(
            title="Load game",
            initialdir=str(save_dir),
            initialfile=self._default_save_slot_name(),
            filetypes=[("JSON save files", "*.json"), ("All files", "*.*")],
        )
        root.destroy()
        if not file_path:
            return None
        return self._resolve_save_slot_path(Path(file_path))

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

    def _update_window_caption(self) -> None:
        """Show zoom, simulation state, and active-entity details in the window title."""
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
        if error_notice:
            caption = f"{caption} | {error_notice}"
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

    def _apply_pending_load_if_idle(self) -> None:
        """Apply a queued save-slot load once the command lane is idle."""
        if self.command_runner is None or self.command_runner.has_pending_work():
            return
        if self._pending_load_save_path is None:
            return

        load_path = self._pending_load_save_path
        self._pending_load_save_path = None
        self._accumulated_time = 0.0
        self._load_save_slot(load_path)

    def _apply_pending_area_change_if_idle(self) -> None:
        """Apply a queued area transition once the main command lane is idle."""
        if self.command_runner is None or self.command_runner.has_pending_work():
            return
        if self._pending_area_change_path is None:
            return

        next_area_path = self._pending_area_change_path
        self._pending_area_change_path = None
        self._accumulated_time = 0.0
        self._load_area_runtime(next_area_path)

    def _apply_reentry_resets_for_area(self, area_id: str, authored_world) -> None:
        """Apply scheduled on-reentry persistent resets before constructing an area runtime."""
        for request in self.persistence_runtime.consume_reentry_resets(area_id):
            if request.kind != "persistent":
                continue
            self.persistence_runtime.clear_persistent_area_state(
                area_id,
                authored_world,
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

    def _capture_current_area_reference(self) -> str:
        """Return a stable project-relative reference for the currently loaded area."""
        return (
            self.project.area_path_to_reference(self.area_path)
            if self.project is not None
            else str(self.area_path.resolve())
        )

    def _write_save_slot(self, save_path: Path) -> None:
        """Write the current persistent/session state to one explicit save slot."""
        active_entity = self.world.get_active_entity()
        _, persistent_reference_world = self._build_current_play_reference()
        self.persistence_runtime.save_data.current_area = self._capture_current_area_reference()
        self.persistence_runtime.save_data.active_entity = (
            active_entity.entity_id if active_entity is not None else ""
        )
        self.persistence_runtime.save_data.current_area_state = capture_current_area_state(
            self.area,
            persistent_reference_world,
            self.world,
        )
        self.persistence_runtime.set_save_path(save_path)
        try:
            self.persistence_runtime.flush(force=True)
        finally:
            # The exact saved room state is for file output and one-time load restore only.
            self.persistence_runtime.save_data.current_area_state = None

    def _load_save_slot(self, save_path: Path) -> None:
        """Load one explicit save slot and rebuild the runtime from its saved session."""
        self.persistence_runtime.set_save_path(save_path)
        if not self.persistence_runtime.reload_from_disk():
            raise FileNotFoundError(f"Save file '{save_path}' was not found.")

        current_area_state = copy.deepcopy(self.persistence_runtime.save_data.current_area_state)
        self.persistence_runtime.save_data.current_area_state = None
        target_area_path = self._resolve_saved_area_path()
        self._load_area_runtime(target_area_path)
        if current_area_state is not None:
            apply_persistent_area_state(self.area, self.world, current_area_state)
        self._apply_saved_active_entity()

    def _resolve_saved_area_path(self) -> Path:
        """Resolve the saved session's current area reference, falling back safely."""
        current_area_path = str(self.persistence_runtime.save_data.current_area).strip()
        if current_area_path:
            return self._resolve_area_path(current_area_path)

        startup_area = self.project.startup_area if self.project is not None else None
        if startup_area:
            return self._resolve_area_path(startup_area)
        return self.area_path.resolve()

    def _apply_saved_active_entity(self) -> None:
        """Restore the saved active entity after the current room has been rebuilt."""
        active_entity_id = str(self.persistence_runtime.save_data.active_entity).strip()
        if active_entity_id and self.world.get_entity(active_entity_id) is not None:
            self.world.set_active_entity(active_entity_id)

        if self.camera is not None:
            self.camera.follow_active_entity()
            self.camera.update(self.world, advance_tick=False)

