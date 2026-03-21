"""Input mapping that converts keyboard state into top-level commands."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from puzzle_dungeon.commands.runner import CommandRunner


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


class InputHandler:
    """Translate raw events and held input into command runner requests."""

    def __init__(self, command_runner: CommandRunner, player_id: str) -> None:
        self.command_runner = command_runner
        self.player_id = player_id
        self.held_directions: dict[str, bool] = {
            "up": False,
            "down": False,
            "left": False,
            "right": False,
        }
        self.direction_priority = ["up", "down", "left", "right"]

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

                if event.key in ACTION_KEYS:
                    if not self.command_runner.has_pending_work():
                        self.command_runner.enqueue(
                            "player_interact",
                            entity_id=self.player_id,
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

            self.command_runner.enqueue(
                "run_event",
                entity_id=self.player_id,
                event_id=f"move_{direction}",
                actor_entity_id=self.player_id,
            )
            return
