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
        self.menu_press_count = 0
        self.direction_press_counts: dict[str, int] = {
            "up": 0,
            "down": 0,
            "left": 0,
            "right": 0,
        }

    def handle_events(self, events: list[pygame.event.Event]) -> InputFrameResult:
        """Update held input state and report high-level play actions."""
        result = InputFrameResult()
        for event in events:
            if event.type == pygame.QUIT:
                result.should_quit = True
                continue

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.menu_press_count += 1
                    if self._can_route_input_while_busy() and self._enqueue_action_if_mapped("menu"):
                        continue
                    if not self.command_runner.has_pending_work() and self._enqueue_action_if_mapped("menu"):
                        continue
                    if self.command_runner.has_pending_work():
                        continue
                    result.should_quit = True
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
                    if self._can_route_input_while_busy():
                        self._enqueue_action_if_mapped("interact")
                    elif not self.command_runner.has_pending_work():
                        self._enqueue_action_if_mapped("interact")
                    continue

                direction = KEY_TO_DIRECTION.get(event.key)
                if direction is not None:
                    self.held_directions[direction] = True
                    self.direction_press_counts[direction] += 1
                    action_name = f"move_{direction}"
                    if self._can_route_input_while_busy():
                        self._enqueue_action_if_mapped(action_name)
                    elif not self.command_runner.has_pending_work():
                        self._enqueue_action_if_mapped(action_name)
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

            action_name = f"move_{direction}"
            if self._enqueue_action_if_mapped(action_name):
                return

    def set_action_event_name(self, action: str, event_name: str) -> None:
        """Change the fallback entity event for a named logical input action."""
        if action not in self.action_event_names:
            raise KeyError(f"Unknown input action '{action}'.")
        self.action_event_names[action] = str(event_name)

    def get_action_press_count(self) -> int:
        """Return how many action-button keydown events have occurred."""
        return int(self.action_press_count)

    def get_menu_press_count(self) -> int:
        """Return how many menu-button keydown events have occurred."""
        return int(self.menu_press_count)

    def get_direction_press_count(self, direction: str) -> int:
        """Return how many keydown events have occurred for one logical direction."""
        if direction not in self.direction_press_counts:
            raise KeyError(f"Unknown direction '{direction}'.")
        return int(self.direction_press_counts[direction])

    def is_direction_held(self, direction: str) -> bool:
        """Return whether one logical direction is currently held."""
        if direction not in self.held_directions:
            raise KeyError(f"Unknown direction '{direction}'.")
        return bool(self.held_directions[direction])

    def _enqueue_action_if_mapped(self, action_name: str) -> bool:
        """Run the mapped event for the routed entity when one exists."""
        target_entity = self.world.get_input_target(action_name)
        if target_entity is None:
            return False
        event_name = self._resolve_input_target_event_name(action_name, target_entity)
        if not event_name:
            return False
        return self.command_runner.dispatch_input_event(
            entity_id=target_entity.entity_id,
            event_id=event_name,
            actor_entity_id=target_entity.entity_id,
        )

    def _resolve_input_target_event_name(self, action_name: str, target_entity) -> str:
        """Resolve an input action to an event name on the routed entity."""
        event_name = target_entity.input_map.get(action_name)
        if event_name is not None:
            return str(event_name).strip()
        return self.action_event_names.get(action_name, "").strip()

    def _can_route_input_while_busy(self) -> bool:
        """Return True when logical actions should still go to routed entities."""
        if not self.command_runner.has_pending_work():
            return True
        active_handle = self.command_runner.active_handle
        return bool(active_handle is not None and active_handle.allow_entity_input)

