"""Main runtime wiring for play mode and the early in-app editor."""

from __future__ import annotations

import copy
from pathlib import Path

import pygame

from puzzle_dungeon import config
from puzzle_dungeon.commands.builtin import register_builtin_commands
from puzzle_dungeon.commands.registry import CommandRegistry
from puzzle_dungeon.commands.runner import CommandContext, CommandRunner
from puzzle_dungeon.editor.editor_ui import EditorUI
from puzzle_dungeon.editor.level_editor import EditorAction, LevelEditor
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
    """Own the runtime loop, editor document state, and playtest state."""

    def __init__(self) -> None:
        pygame.init()

        self.display_surface = pygame.display.set_mode(
            (config.INTERNAL_WIDTH * config.SCALE, config.INTERNAL_HEIGHT * config.SCALE)
        )
        pygame.display.set_caption(f"{config.WINDOW_TITLE} - Map")
        self.display_window = pygame.Window.from_display_module()
        self.clock = pygame.time.Clock()
        self.headless = pygame.display.get_driver() == "dummy"
        self.focused_window_id: int | None = getattr(self.display_window, 'id', None)

        self.area_path = Path(config.AREAS_DIR / "test_room.json")
        self.asset_manager = AssetManager()
        self.persistence_runtime = PersistenceRuntime(config.DEFAULT_SAVE_SLOT_PATH)
        editor_area, editor_world = load_area(self.area_path, asset_manager=self.asset_manager)
        self.editor = LevelEditor(self.area_path, editor_area, editor_world, asset_manager=self.asset_manager)
        self.renderer = Renderer(self.display_surface, self.asset_manager)
        self.mode = "play"
        self.editor_ui = EditorUI(self.asset_manager)

        self.area = editor_area
        self.world = editor_world
        self.camera = Camera(config.INTERNAL_WIDTH, config.INTERNAL_HEIGHT, self.area)
        self.command_registry = CommandRegistry()
        register_builtin_commands(self.command_registry)

        self.collision_system: CollisionSystem | None = None
        self.interaction_system: InteractionSystem | None = None
        self.movement_system: MovementSystem | None = None
        self.animation_system: AnimationSystem | None = None
        self.command_runner: CommandRunner | None = None
        self.input_handler: InputHandler | None = None
        self.play_document_data: dict[str, object] | None = None
        self.play_authored_area = editor_area
        self.play_authored_world = editor_world
        self.editor_camera = Camera(
            self.editor.map_viewport_rect.width,
            self.editor.map_viewport_rect.height,
            self.editor.area,
            clamp_to_area=False,
        )

        self._activate_play_mode()

    def run(self, max_frames: int | None = None) -> None:
        """Run the game loop until the user quits or a frame cap is reached."""
        running = True
        frame_count = 0

        while running:
            dt = self.clock.tick(config.FPS) / 1000.0
            events = pygame.event.get()
            self._update_focus_tracking(events)

            if self.mode == "play":
                running = self._run_play_frame(dt, events)
            else:
                running = self._run_editor_frame(dt, events)

            frame_count += 1
            if max_frames is not None and frame_count >= max_frames:
                running = False

        self.persistence_runtime.flush()
        pygame.quit()

    def _run_play_frame(self, dt: float, events: list[pygame.event.Event]) -> bool:
        """Advance the playtest state for one frame."""
        if self._contains_keydown(events, pygame.K_F1):
            self._activate_editor_mode()
            return True

        assert self.input_handler is not None
        assert self.command_runner is not None
        assert self.movement_system is not None
        assert self.animation_system is not None

        if self.input_handler.handle_events(events):
            self.persistence_runtime.flush()
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
        self.renderer.render(self.area, self.world, self.camera)
        self.persistence_runtime.flush()
        return True

    def _run_editor_frame(self, dt: float, events: list[pygame.event.Event]) -> bool:
        """Advance the editor state for one frame."""
        # EditorUI gets first crack at events (toolbar, popups, move-pending)
        unconsumed: list[pygame.event.Event] = []
        for event in events:
            if not self.editor_ui.handle_event(event, self.editor, self.editor_camera):
                unconsumed.append(event)

        # Check if toolbar Play button was pressed (F1 handled by editor)
        actions = self.editor.handle_events(unconsumed, self.editor_camera)
        for action in actions:
            if action.kind == "quit":
                return False
            if action.kind == "toggle_play":
                self._activate_play_mode()
                return True
            if action.kind == "reload_document":
                self.editor.reload_from_disk()
                self.editor_camera.set_area(self.editor.area)
                self.area = self.editor.area
                self.world = self.editor.world

        self.area = self.editor.area
        self.world = self.editor.world
        self.editor.update(dt, self.editor_camera)
        self.renderer.render_with_editor(
            self.area, self.world, self.editor_camera, self.editor, self.editor_ui
        )
        return True

    def _activate_play_mode(self) -> None:
        """Build a fresh playtest runtime from the current editable document."""
        document_data = serialize_area(self.editor.area, self.editor.world)
        self.play_document_data = copy.deepcopy(document_data)
        self.play_authored_area, self.play_authored_world = load_area_from_data(
            copy.deepcopy(document_data),
            source_name=str(self.area_path),
            asset_manager=self.asset_manager,
        )
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
        self.mode = "play"

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

    def _activate_editor_mode(self) -> None:
        """Return to the authoritative editor document without carrying playtest mutations back."""
        self.persistence_runtime.flush()
        self.mode = "editor"
        self.area = self.editor.area
        self.world = self.editor.world
        self.editor_camera.set_area(self.area)
        self.editor_camera.set_position(self.camera.x, self.camera.y)

    def _contains_keydown(self, events: list[pygame.event.Event], key: int) -> bool:
        """Return True when a keydown event for the requested key exists in this frame."""
        return any(event.type == pygame.KEYDOWN and event.key == key for event in events)

    def _update_focus_tracking(self, events: list[pygame.event.Event]) -> None:
        """Track window focus events (kept for compatibility)."""
        pass

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
