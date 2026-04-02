"""Main runtime wiring for play mode."""

from __future__ import annotations

import copy
from pathlib import Path
import random

import pygame

from dungeon_engine import config
from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.library import build_project_command_database
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import (
    AreaTransitionRequest,
    CommandContext,
    CommandRunner,
    execute_registered_command,
)
from dungeon_engine.engine.asset_manager import AssetManager
from dungeon_engine.engine.audio import AudioPlayer
from dungeon_engine.engine.camera import Camera
from dungeon_engine.engine.dialogue_runtime import DialogueRuntime
from dungeon_engine.engine.inventory_runtime import InventoryRuntime
from dungeon_engine.engine.input_handler import InputHandler
from dungeon_engine.engine.renderer import Renderer
from dungeon_engine.engine.screen import ScreenElementManager
from dungeon_engine.systems.animation import AnimationSystem
from dungeon_engine.systems.collision import CollisionSystem
from dungeon_engine.systems.interaction import InteractionSystem
from dungeon_engine.systems.movement import MovementSystem
from dungeon_engine.world.loader import instantiate_entity, load_area, load_area_from_data
from dungeon_engine.world.persistence import (
    PersistenceRuntime,
    ResetRequest,
    apply_area_travelers,
    apply_current_global_state,
    apply_persistent_area_state,
    apply_persistent_global_state,
    capture_current_area_state,
    capture_current_global_state,
    get_persistent_area_state,
    select_entity_ids_by_tags,
)
from dungeon_engine.world.serializer import serialize_area


class Game:
    """Own the play-mode runtime loop."""

    def __init__(self, area_path: Path, project: "ProjectContext") -> None:
        from dungeon_engine.project import ProjectContext  # noqa: F811

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
        self.movement_system = MovementSystem(self.area, self.world, self.collision_system)
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

    def request_area_change(self, request: AreaTransitionRequest) -> None:
        """Queue a transition into another authored area by area id."""
        self._pending_area_change_request = copy.deepcopy(request)
        self._pending_new_game_request = None
        self._pending_load_save_path = None

    def request_new_game(self, request: AreaTransitionRequest) -> None:
        """Queue a fresh session reset and transition into another authored area."""
        self._pending_new_game_request = copy.deepcopy(request)
        self._pending_area_change_request = None
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
        self._pending_area_change_request = None
        self._pending_new_game_request = None

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

    def _load_area_runtime(
        self,
        area_path: Path | str,
        *,
        transferred_entities: list | None = None,
        restored_input_targets: dict[str, str] | None = None,
        transition_request: AreaTransitionRequest | None = None,
    ) -> None:
        """Load one authored area plus any persistent overrides and rebuild runtime systems."""
        resolved_area_path = self._resolve_area_path(area_path)
        document_area, document_world = load_area(
            resolved_area_path,
            asset_manager=self.asset_manager,
            project=self.project,
        )
        document_data = serialize_area(document_area, document_world, project=self.project)
        play_document_data = copy.deepcopy(document_data)
        play_authored_area, play_authored_world = load_area_from_data(
            copy.deepcopy(document_data),
            source_name=str(resolved_area_path),
            asset_manager=self.asset_manager,
            project=self.project,
        )
        self._install_project_global_entities(play_authored_world, play_authored_area.tile_size)
        self._apply_reentry_resets_for_area(play_authored_area.area_id, play_authored_world)
        area, world = load_area_from_data(
            copy.deepcopy(document_data),
            source_name=str(resolved_area_path),
            asset_manager=self.asset_manager,
            persistent_area_state=get_persistent_area_state(
                self.persistence_runtime.save_data,
                play_authored_area.area_id,
            ),
            project=self.project,
        )
        self._install_project_global_entities(world, area.tile_size)
        apply_persistent_global_state(
            area,
            world,
            self.persistence_runtime.save_data,
            project=self.project,
        )
        transferred_session_entity_ids = {
            str(entity.session_entity_id)
            for entity in (transferred_entities or [])
            if getattr(entity, "session_entity_id", None)
        }
        apply_area_travelers(
            area,
            world,
            self.persistence_runtime.save_data,
            project=self.project,
            skip_session_entity_ids=transferred_session_entity_ids,
        )
        self._install_transferred_entities(
            area,
            world,
            transferred_entities or [],
            entry_id=None if transition_request is None else transition_request.entry_id,
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
        self._apply_area_camera_defaults()
        self.persistence_runtime.refresh_live_travelers(self.area, self.world)
        if restored_input_targets:
            self.world.set_input_targets(restored_input_targets, replace=False)
        self._apply_transition_camera_follow(
            None if transition_request is None else transition_request.camera_follow
        )
        self._queue_area_enter_commands()

    def _install_project_global_entities(self, world, tile_size: int) -> None:
        """Instantiate project-authored global entities into the current runtime world."""
        for index, entity_data in enumerate(self.project.global_entities):
            global_entity = instantiate_entity(
                {
                    **copy.deepcopy(entity_data),
                    "scope": "global",
                },
                tile_size,
                project=self.project,
                source_name=f"project global_entities[{index}]",
            )
            existing_entity = world.get_entity(global_entity.entity_id)
            if existing_entity is not None:
                raise ValueError(
                    f"project global_entities[{index}] entity id '{global_entity.entity_id}' "
                    f"conflicts with existing {existing_entity.scope} entity '{existing_entity.entity_id}'."
                )
            world.add_entity(global_entity)

    def _resolve_area_path(self, area_path: Path | str) -> Path:
        """Resolve an area reference (ID or already-resolved path).

        Authored references resolve by strict path-derived area id. ``Path``
        inputs are reserved for internal callers that already hold a resolved
        area file.
        """
        if isinstance(area_path, str):
            reference = area_path.strip()
            resolved = self.project.resolve_area_reference(reference)
            if resolved is not None:
                return resolved
            raise FileNotFoundError(
                f"Cannot resolve authored area id '{reference}' in project '{self.project.project_root}'."
            )

        raw_path = Path(area_path)
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
            f"Cannot resolve area reference '{area_path}'. "
            f"Searched: {searched_paths or '<none>'}."
        )

    def _queue_area_enter_commands(self) -> None:
        """Queue area-authored enter commands so they run on the next simulation tick."""
        if self.command_runner is None or not self.area.enter_commands:
            return
        self.command_runner.enqueue(
            "run_commands",
            commands=copy.deepcopy(self.area.enter_commands),
        )

    def _queue_occupancy_transition_hooks(
        self,
        instigator,
        previous_cell: tuple[int, int] | None,
        next_cell: tuple[int, int] | None,
    ) -> None:
        """Queue stationary-entity occupancy hooks for one logical tile transition."""
        if self.command_runner is None or previous_cell == next_cell:
            return

        runtime_params: dict[str, int] = {}
        if previous_cell is not None:
            runtime_params["from_x"] = int(previous_cell[0])
            runtime_params["from_y"] = int(previous_cell[1])
        if next_cell is not None:
            runtime_params["to_x"] = int(next_cell[0])
            runtime_params["to_y"] = int(next_cell[1])

        def _spawn_hook(receiver, command_id: str) -> None:
            handle = execute_registered_command(
                self.command_registry,
                self.command_runner.context,
                "run_entity_command",
                {
                    "entity_id": receiver.entity_id,
                    "command_id": command_id,
                    "entity_refs": {"instigator": instigator.entity_id},
                    "refs_mode": "merge",
                    **runtime_params,
                },
            )
            self.command_runner.spawn_root_handle(handle)

        if previous_cell is not None:
            for receiver in self.world.get_entities_at(
                previous_cell[0],
                previous_cell[1],
                exclude_entity_id=instigator.entity_id,
                include_hidden=True,
            ):
                _spawn_hook(receiver, "on_occupant_leave")

        if next_cell is not None:
            for receiver in self.world.get_entities_at(
                next_cell[0],
                next_cell[1],
                exclude_entity_id=instigator.entity_id,
                include_hidden=True,
            ):
                _spawn_hook(receiver, "on_occupant_enter")

    def _project_save_dir(self) -> Path:
        """Return the active project's save-root directory, creating it when needed."""
        save_dir = self.project.save_dir
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

    def _apply_pending_reset_if_idle(self) -> None:
        """Apply queued immediate reset requests once the command lane is idle."""
        if self.command_runner is None or self._has_blocking_runtime_work():
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
        if self.command_runner is None or self._has_blocking_runtime_work():
            return
        if self._pending_load_save_path is None:
            return

        load_path = self._pending_load_save_path
        self._pending_load_save_path = None
        self._accumulated_time = 0.0
        self._load_save_slot(load_path)

    def _apply_pending_new_game_if_idle(self) -> None:
        """Apply a queued new-game request once the command lane is idle."""
        if self.command_runner is None or self._has_blocking_runtime_work():
            return
        if self._pending_new_game_request is None:
            return

        request = self._pending_new_game_request
        self._pending_new_game_request = None
        self._accumulated_time = 0.0
        self.persistence_runtime = PersistenceRuntime(project=self.project)
        self._apply_area_transition_request(request)

    def _apply_pending_area_change_if_idle(self) -> None:
        """Apply a queued area transition once the main command lane is idle."""
        if self.command_runner is None or self._has_blocking_runtime_work():
            return
        if self._pending_area_change_request is None:
            return

        request = self._pending_area_change_request
        self._pending_area_change_request = None
        self._accumulated_time = 0.0
        self._apply_area_transition_request(request)

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
            self._rebuild_play_world()
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
        if self.play_document_data is None:
            raise RuntimeError("Game runtime is missing the current play document.")
        area, world = load_area_from_data(
            copy.deepcopy(self.play_document_data),
            source_name=str(self.area_path),
            asset_manager=self.asset_manager,
            persistent_area_state=get_persistent_area_state(
                self.persistence_runtime.save_data,
                self.play_authored_area.area_id,
            ),
            project=self.project,
        )
        self._install_project_global_entities(world, area.tile_size)
        apply_persistent_global_state(
            area,
            world,
            self.persistence_runtime.save_data,
            project=self.project,
        )
        return area, world

    def _apply_area_transition_request(self, request: AreaTransitionRequest) -> None:
        """Apply one authored area transition, optionally carrying runtime entities with it."""
        resolved_area_path = self._resolve_area_path(request.area_id)
        transferred_entities = self._capture_transition_entities(request)
        for entity in transferred_entities:
            self.persistence_runtime.prepare_traveler_for_area(
                entity,
                destination_area_id=request.area_id,
                tile_size=self.area.tile_size,
            )
        restored_input_targets = self._capture_transition_input_targets(transferred_entities)
        self._load_area_runtime(
            resolved_area_path,
            transferred_entities=transferred_entities,
            restored_input_targets=restored_input_targets,
            transition_request=request,
        )

    def _capture_transition_entities(self, request: AreaTransitionRequest) -> list:
        """Return detached entity copies that should move into the next area."""
        transferred_entities: list = []
        for entity_id in request.transfer_entity_ids:
            entity = self.world.get_entity(entity_id)
            if entity is None:
                raise KeyError(
                    f"Cannot transfer missing entity '{entity_id}' during area change to '{request.area_id}'."
                )
            if entity.scope != "area":
                raise ValueError(
                    f"Cannot transfer entity '{entity_id}' because only area-scoped entities can change areas."
                )
            transferred_entity = copy.deepcopy(entity)
            transferred_entity.movement_state.active = False
            for visual in transferred_entity.visuals:
                visual.animation_playback.active = False
            transferred_entities.append(transferred_entity)
        return transferred_entities

    def _capture_transition_input_targets(self, transferred_entities: list) -> dict[str, str]:
        """Carry routed actions that currently target transferred entities into the next area."""
        transferred_ids = {
            entity.entity_id
            for entity in transferred_entities
        }
        if not transferred_ids:
            return {}
        preserved_targets: dict[str, str] = {}
        for action, target_id in self.world.input_targets.items():
            if target_id in transferred_ids:
                preserved_targets[action] = str(target_id)
        return preserved_targets

    def _install_transferred_entities(
        self,
        area,
        world,
        transferred_entities: list,
        *,
        entry_id: str | None,
    ) -> None:
        """Place transferred entities into the loaded destination area before runtime rebuild."""
        if not transferred_entities:
            return
        entry_point = None
        if entry_id:
            entry_point = area.entry_points.get(entry_id)
            if entry_point is None:
                raise KeyError(
                    f"Area '{area.area_id}' does not define entry point '{entry_id}'."
                )

        for entity in transferred_entities:
            self._place_transferred_entity(area, entity, entry_point=entry_point)
            world.add_entity(entity)

    def _place_transferred_entity(self, area, entity, *, entry_point) -> None:
        """Move one transferred entity onto the destination entry marker when provided."""
        if entity.space != "world":
            return
        if entry_point is None:
            entity.sync_pixel_position(area.tile_size)
            return
        entity.grid_x = int(entry_point.grid_x)
        entity.grid_y = int(entry_point.grid_y)
        if entry_point.facing is not None:
            entity.set_facing_value(str(entry_point.facing))
        entity.pixel_x = (
            float(entry_point.pixel_x)
            if entry_point.pixel_x is not None
            else float(entity.grid_x * area.tile_size)
        )
        entity.pixel_y = (
            float(entry_point.pixel_y)
            if entry_point.pixel_y is not None
            else float(entity.grid_y * area.tile_size)
        )

    def _apply_transition_camera_follow(self, camera_follow) -> None:
        """Apply any authored camera-follow request after a transition rebuilds runtime state."""
        if self.camera is None or camera_follow is None:
            return
        if camera_follow.mode == "entity" and camera_follow.entity_id:
            if self.world.get_entity(camera_follow.entity_id) is None:
                raise KeyError(
                    f"Cannot follow missing transition camera entity '{camera_follow.entity_id}'."
                )
            self.camera.follow_entity(
                camera_follow.entity_id,
                offset_x=float(camera_follow.offset_x),
                offset_y=float(camera_follow.offset_y),
            )
        elif camera_follow.mode == "input_target" and camera_follow.action:
            self.camera.follow_input_target(
                camera_follow.action,
                offset_x=float(camera_follow.offset_x),
                offset_y=float(camera_follow.offset_y),
            )
        elif camera_follow.mode == "none":
            self.camera.clear_follow()
        self.camera.update(self.world, advance_tick=False)

    def _rebuild_play_world(self) -> None:
        """Rebuild the current play world from authored data plus persistent overrides."""
        self.persistence_runtime.refresh_live_travelers(self.area, self.world)
        self.area, self.world = self._build_current_play_reference()
        apply_area_travelers(
            self.area,
            self.world,
            self.persistence_runtime.save_data,
            project=self.project,
        )
        self._install_play_runtime()

    def _capture_current_area_reference(self) -> str:
        """Return a stable project-relative reference for the currently loaded area."""
        return (
            self.project.area_path_to_reference(self.area_path)
        )

    def _write_save_slot(self, save_path: Path) -> None:
        """Write the current persistent/session state to one explicit save slot."""
        self.persistence_runtime.refresh_live_travelers(self.area, self.world)
        _, persistent_reference_world = self._build_current_play_reference()
        self.persistence_runtime.save_data.current_area = self._capture_current_area_reference()
        self.persistence_runtime.save_data.current_input_targets = copy.deepcopy(
            self.world.input_targets
        )
        self.persistence_runtime.save_data.current_camera = (
            None
            if self.camera is None
            else copy.deepcopy(self.camera.to_state_dict())
        )
        self.persistence_runtime.save_data.current_area_state = capture_current_area_state(
            self.area,
            persistent_reference_world,
            self.world,
            project=self.project,
        )
        self.persistence_runtime.save_data.current_global_entities = capture_current_global_state(
            self.area,
            persistent_reference_world,
            self.world,
            project=self.project,
        )
        self.persistence_runtime.set_save_path(save_path)
        try:
            self.persistence_runtime.flush(force=True)
        finally:
            # The exact saved room state is for file output and one-time load restore only.
            self.persistence_runtime.save_data.current_camera = None
            self.persistence_runtime.save_data.current_area_state = None
            self.persistence_runtime.save_data.current_global_entities = None

    def _load_save_slot(self, save_path: Path) -> None:
        """Load one explicit save slot and rebuild the runtime from its saved session."""
        self.persistence_runtime.set_save_path(save_path)
        if not self.persistence_runtime.reload_from_disk():
            raise FileNotFoundError(f"Save file '{save_path}' was not found.")

        current_area_state = copy.deepcopy(self.persistence_runtime.save_data.current_area_state)
        current_global_entities = copy.deepcopy(
            self.persistence_runtime.save_data.current_global_entities
        )
        current_input_targets = copy.deepcopy(
            self.persistence_runtime.save_data.current_input_targets
        )
        current_camera = copy.deepcopy(
            self.persistence_runtime.save_data.current_camera
        )
        self.persistence_runtime.save_data.current_area_state = None
        self.persistence_runtime.save_data.current_global_entities = None
        self.persistence_runtime.save_data.current_input_targets = None
        self.persistence_runtime.save_data.current_camera = None
        target_area_path = self._resolve_saved_area_path()
        self._load_area_runtime(target_area_path)
        if current_area_state is not None:
            apply_persistent_area_state(
                self.area,
                self.world,
                current_area_state,
                project=self.project,
            )
        apply_current_global_state(
            self.area,
            self.world,
            current_global_entities,
            project=self.project,
        )
        self._apply_saved_input_targets(current_input_targets)
        self._apply_saved_camera_state(current_camera)

    def _resolve_saved_area_path(self) -> Path:
        """Resolve the saved session's current area reference, falling back safely."""
        current_area_path = str(self.persistence_runtime.save_data.current_area).strip()
        if current_area_path:
            return self._resolve_area_path(current_area_path)

        startup_area = self.project.startup_area
        if startup_area:
            return self._resolve_area_path(startup_area)
        return self.area_path.resolve()

    def _apply_saved_input_targets(self, saved_input_targets: dict[str, str] | None) -> None:
        """Restore the saved logical-input routing after the current room is rebuilt."""
        if saved_input_targets:
            self.world.set_input_targets(saved_input_targets, replace=True)

    def _apply_saved_camera_state(self, saved_camera_state: dict[str, object] | None) -> None:
        """Restore the saved camera state after the current room is rebuilt."""
        if saved_camera_state is None or self.camera is None:
            return
        self.camera.apply_state_dict(saved_camera_state, self.world)

    def _apply_area_camera_defaults(self) -> None:
        """Apply authored area camera defaults when the room has any."""
        if self.camera is None or not self.area.camera_defaults:
            return
        self.camera.apply_state_dict(self._build_area_camera_state(), self.world)

    def _build_area_camera_state(self) -> dict[str, object]:
        """Translate one area's authored camera defaults into runtime camera state data."""
        return copy.deepcopy(self.area.camera_defaults)
