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

        self.display_surface = pygame.display.set_mode(
            (config.INTERNAL_WIDTH * config.SCALE, config.INTERNAL_HEIGHT * config.SCALE)
        )
        pygame.display.set_caption(config.WINDOW_TITLE)
        self.clock = pygame.time.Clock()
        self.headless = pygame.display.get_driver() == "dummy"

        self.area_path = area_path or Path(config.AREAS_DIR / "test_room.json")
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

        self.renderer = Renderer(self.display_surface, self.asset_manager)
        self.camera = Camera(config.INTERNAL_WIDTH, config.INTERNAL_HEIGHT, self.play_authored_area)
        self.command_registry = CommandRegistry()
        register_builtin_commands(self.command_registry)

        self.collision_system: CollisionSystem | None = None
        self.interaction_system: InteractionSystem | None = None
        self.movement_system: MovementSystem | None = None
        self.animation_system: AnimationSystem | None = None
        self.command_runner: CommandRunner | None = None
        self.input_handler: InputHandler | None = None
        self.play_status_message: str = ""
        self.play_status_timer: float = 0.0

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

    def run(self, max_frames: int | None = None) -> None:
        """Run the game loop until the user quits or a frame cap is reached."""
        running = True
        frame_count = 0

        while running:
            dt = self.clock.tick(config.FPS) / 1000.0
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

        self.command_runner.update(0.0)
        self.movement_system.update(dt)
        self.animation_system.update(dt)
        self.command_runner.update(dt)
        self._apply_pending_reset_if_idle()
        self.input_handler.enqueue_held_movement_if_idle()
        self.command_runner.update(0.0)
        self._apply_pending_reset_if_idle()
        self.camera.update(self.world.get_player())
        self._update_play_status(dt)
        self.renderer.render(
            self.area,
            self.world,
            self.camera,
            status_message=self.play_status_message,
            has_save_file=self.persistence_runtime.has_save_file(),
            persistent_state_dirty=self.persistence_runtime.dirty,
        )
        return True

    def _install_play_runtime(self) -> None:
        """Rebuild runtime systems around the current play world."""
        self.camera = Camera(config.INTERNAL_WIDTH, config.INTERNAL_HEIGHT, self.area)
        self.camera.update(self.world.get_player())

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
            persistence_runtime=self.persistence_runtime,
        )
        self.command_runner = CommandRunner(self.command_registry, command_context)
        self.input_handler = InputHandler(self.command_runner, self.world.player_id)

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
        self._set_play_status(
            f"Saved persistent state to {self.persistence_runtime.save_path.name}"
        )

    def _reload_persistent_state_from_disk(self) -> None:
        """Reload persistent state from disk and rebuild the current room."""
        if self.command_runner is not None and self.command_runner.has_pending_work():
            self._set_play_status("Finish the current action before loading")
            return

        save_exists = self.persistence_runtime.reload_from_disk()
        self._rebuild_play_world(preserve_player=True)
        if save_exists:
            self._set_play_status(
                f"Reloaded persistent state from {self.persistence_runtime.save_path.name}"
            )
        else:
            self._set_play_status("No save file found; using room JSON only")

    def _set_play_status(self, message: str, *, duration: float = 2.5) -> None:
        """Show a short play-mode status message in the HUD."""
        self.play_status_message = message
        self.play_status_timer = duration

    def _update_play_status(self, dt: float) -> None:
        """Expire transient play-mode status messages over time."""
        if self.play_status_timer <= 0.0:
            return
        self.play_status_timer = max(0.0, self.play_status_timer - dt)
        if self.play_status_timer == 0.0:
            self.play_status_message = ""
