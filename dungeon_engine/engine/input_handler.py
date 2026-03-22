"""Input mapping that converts keyboard state into top-level commands."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from dungeon_engine.commands.runner import CommandRunner
from dungeon_engine.world.world import World


KEY_TO_DIRECTION = {
    pygame.K_UP: "up",
    pygame.K_w: "up",
    pygame.K_DOWN: "down",
    pygame.K_s: "down",
    pygame.K_LEFT: "left",
    pygame.K_a: "left",
    pygame.K_RIGHT: "right",
    pygame.K_d: "right",
}

ACTION_KEYS = {
    pygame.K_SPACE,
    pygame.K_RETURN,
    pygame.K_KP_ENTER,
}


@dataclass(slots=True)
class InputFrameResult:
    """High-level play actions requested during one input frame."""

    should_quit: bool = False
    save_requested: bool = False
    load_requested: bool = False
    toggle_pause_requested: bool = False
    step_tick_requested: bool = False
    zoom_delta: int = 0


class InputHandler:
    """Translate raw events and held input into command runner requests."""

    def __init__(
        self,
        command_runner: CommandRunner,
        world: World,
        action_event_names: dict[str, str] | None = None,
        *,
        debug_inspection_enabled: bool = False,
    ) -> None:
        self.command_runner = command_runner
        self.world = world
        self.debug_inspection_enabled = bool(debug_inspection_enabled)
        self.action_event_names: dict[str, str] = dict(action_event_names or {
            "move_up": "move_up",
            "move_down": "move_down",
            "move_left": "move_left",
            "move_right": "move_right",
            "interact": "interact",
        })
        self.held_directions: dict[str, bool] = {
            "up": False,
            "down": False,
            "left": False,
            "right": False,
        }
        self.direction_priority = ["up", "down", "left", "right"]
        self.action_press_count = 0

    def handle_events(self, events: list[pygame.event.Event]) -> InputFrameResult:
        """Update held input state and report high-level play actions."""
        result = InputFrameResult()
        for event in events:
            if event.type == pygame.QUIT:
                result.should_quit = True
                continue

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    result.should_quit = True
                    continue

                if event.key == pygame.K_F5:
                    result.save_requested = True
                    continue

                if event.key == pygame.K_F9:
                    result.load_requested = True
                    continue

                if self.debug_inspection_enabled and event.key == pygame.K_F6:
                    result.toggle_pause_requested = True
                    continue

                if self.debug_inspection_enabled and event.key == pygame.K_F7:
                    result.step_tick_requested = True
                    continue

                if self.debug_inspection_enabled and event.key == pygame.K_LEFTBRACKET:
                    result.zoom_delta -= 1
                    continue

                if self.debug_inspection_enabled and event.key == pygame.K_RIGHTBRACKET:
                    result.zoom_delta += 1
                    continue

                if event.key in ACTION_KEYS:
                    self.action_press_count += 1
                    if not self.command_runner.has_pending_work():
                        active_entity_id = self.world.active_entity_id
                        interact_event_name = self.action_event_names.get("interact", "").strip()
                        if not interact_event_name:
                            continue
                        self.command_runner.enqueue(
                            "run_event",
                            entity_id=active_entity_id,
                            event_id=interact_event_name,
                            actor_entity_id=active_entity_id,
                        )
                    continue

                direction = KEY_TO_DIRECTION.get(event.key)
                if direction is not None:
                    self.held_directions[direction] = True
                continue

            if event.type == pygame.KEYUP:
                direction = KEY_TO_DIRECTION.get(event.key)
                if direction is not None:
                    self.held_directions[direction] = False

        return result

    def enqueue_held_movement_if_idle(self) -> None:
        """Start the next movement command as soon as the runner becomes idle."""
        if self.command_runner.has_pending_work():
            return

        for direction in self.direction_priority:
            if not self.held_directions[direction]:
                continue

            active_entity_id = self.world.active_entity_id
            action_name = f"move_{direction}"
            event_name = self.action_event_names.get(action_name, "").strip()
            if not event_name:
                continue
            self.command_runner.enqueue(
                "run_event",
                entity_id=active_entity_id,
                event_id=event_name,
                actor_entity_id=active_entity_id,
            )
            return

    def set_action_event_name(self, action: str, event_name: str) -> None:
        """Change which entity event a named input action triggers."""
        if action not in self.action_event_names:
            raise KeyError(f"Unknown input action '{action}'.")
        self.action_event_names[action] = str(event_name)

    def get_action_press_count(self) -> int:
        """Return how many action-button keydown events have occurred."""
        return int(self.action_press_count)

