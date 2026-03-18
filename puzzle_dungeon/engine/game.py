"""Main runtime wiring for play mode and the early in-app editor."""

from __future__ import annotations

from pathlib import Path

import pygame

from puzzle_dungeon import config
from puzzle_dungeon.commands.builtin import register_builtin_commands
from puzzle_dungeon.commands.registry import CommandRegistry
from puzzle_dungeon.commands.runner import CommandContext, CommandRunner
from puzzle_dungeon.editor.browser_window import EditorBrowserWindow
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
        self.focused_window_id = self.display_window.id

        self.area_path = Path(config.AREAS_DIR / "test_room.json")
        editor_area, editor_world = load_area(self.area_path)
        self.editor = LevelEditor(self.area_path, editor_area, editor_world)
        self.asset_manager = AssetManager()
        self.renderer = Renderer(self.display_surface, self.asset_manager)
        self.mode = "play"
        self.browser_window: EditorBrowserWindow | None = None

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
                map_events, browser_events = self._split_editor_events(events)
                running = self._run_editor_frame(dt, map_events, browser_events)

            frame_count += 1
            if max_frames is not None and frame_count >= max_frames:
                running = False

        pygame.quit()
        if self.browser_window is not None:
            self.browser_window.destroy()

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
            return False

        self.command_runner.update(0.0)
        self.movement_system.update(dt)
        self.animation_system.update(dt)
        self.command_runner.update(dt)
        self.input_handler.enqueue_held_movement_if_idle()
        self.command_runner.update(0.0)
        self.camera.update(self.world.get_player())
        self.renderer.render(self.area, self.world, self.camera)
        return True

    def _run_editor_frame(
        self,
        dt: float,
        map_events: list[pygame.event.Event],
        browser_events: list[pygame.event.Event],
    ) -> bool:
        """Advance the editor state for one frame."""
        actions = self.editor.handle_events(map_events, self.editor_camera)
        browser = self._ensure_browser_window()
        if browser is not None:
            actions.extend(browser.process(self.editor, browser_events))
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
        self.renderer.render_with_editor(self.area, self.world, self.editor_camera, self.editor)
        return True

    def _activate_play_mode(self) -> None:
        """Build a fresh playtest runtime from the current editable document."""
        document_data = serialize_area(self.editor.area, self.editor.world)
        self.area, self.world = load_area_from_data(document_data, source_name=str(self.area_path))
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
        )
        self.command_runner = CommandRunner(self.command_registry, command_context)
        self.input_handler = InputHandler(self.command_runner, self.world.player_id)
        self.mode = "play"
        if self.browser_window is not None:
            self.browser_window.hide()

    def _activate_editor_mode(self) -> None:
        """Return to the authoritative editor document without carrying playtest mutations back."""
        self.mode = "editor"
        self.area = self.editor.area
        self.world = self.editor.world
        self.editor_camera.set_area(self.area)
        self.editor_camera.set_position(self.camera.x, self.camera.y)
        browser = self._ensure_browser_window()
        if browser is not None:
            browser.show(self.editor)

    def _contains_keydown(self, events: list[pygame.event.Event], key: int) -> bool:
        """Return True when a keydown event for the requested key exists in this frame."""
        return any(event.type == pygame.KEYDOWN and event.key == key for event in events)

    def _ensure_browser_window(self) -> EditorBrowserWindow | None:
        """Create the dedicated editor browser window when GUI mode is available."""
        if self.headless:
            return None
        if self.browser_window is None:
            self.browser_window = EditorBrowserWindow(self.asset_manager)
        return self.browser_window

    def _update_focus_tracking(self, events: list[pygame.event.Event]) -> None:
        """Track the most recently focused window for routing generic mouse/key events."""
        for event in events:
            if event.type == pygame.WINDOWFOCUSGAINED:
                window_id = self._event_window_id(event)
                if window_id is not None:
                    self.focused_window_id = window_id

    def _split_editor_events(
        self,
        events: list[pygame.event.Event],
    ) -> tuple[list[pygame.event.Event], list[pygame.event.Event]]:
        """Split multi-window editor events between the map and browser windows."""
        browser = self._ensure_browser_window()
        if browser is None or not browser.visible:
            return (events, [])

        map_events: list[pygame.event.Event] = []
        browser_events: list[pygame.event.Event] = []
        for event in events:
            target_id = self._event_window_id(event)
            if target_id is None and event.type in {
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEBUTTONUP,
                pygame.MOUSEMOTION,
                pygame.MOUSEWHEEL,
                pygame.KEYDOWN,
                pygame.KEYUP,
                pygame.TEXTINPUT,
            }:
                target_id = self.focused_window_id

            if target_id == browser.id:
                browser_events.append(event)
            else:
                map_events.append(event)
        return (map_events, browser_events)

    def _event_window_id(self, event: pygame.event.Event) -> int | None:
        """Extract a best-effort SDL window id from a pygame event."""
        window_attr = getattr(event, "window", None)
        if window_attr is not None:
            if hasattr(window_attr, "id"):
                return int(window_attr.id)
            if isinstance(window_attr, int):
                return window_attr

        window_id = getattr(event, "windowID", None)
        if window_id is not None:
            return int(window_id)
        return None
