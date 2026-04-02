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
INVENTORY_KEYS = {pygame.K_i}

HELD_DIRECTION_REPEAT_INITIAL_DELAY_SECONDS = 0.18
HELD_DIRECTION_REPEAT_INTERVAL_SECONDS = 0.12


@dataclass(slots=True)
class InputFrameResult:
    """High-level play actions requested during one input frame."""

    should_quit: bool = False


class InputHandler:
    """Translate raw events and held input into command runner requests."""

    def __init__(
        self,
        command_runner: CommandRunner,
        world: World,
        dialogue_runtime: object | None = None,
        inventory_runtime: object | None = None,
    ) -> None:
        self.command_runner = command_runner
        self.world = world
        self.dialogue_runtime = dialogue_runtime
        self.inventory_runtime = inventory_runtime
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
        self.direction_repeat_cooldowns: dict[str, float] = {
            "up": HELD_DIRECTION_REPEAT_INITIAL_DELAY_SECONDS,
            "down": HELD_DIRECTION_REPEAT_INITIAL_DELAY_SECONDS,
            "left": HELD_DIRECTION_REPEAT_INITIAL_DELAY_SECONDS,
            "right": HELD_DIRECTION_REPEAT_INITIAL_DELAY_SECONDS,
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
                    self._enqueue_action_if_mapped("menu")
                    continue

                debug_action_name = {
                    pygame.K_F6: "debug_toggle_pause",
                    pygame.K_F7: "debug_step_tick",
                    pygame.K_LEFTBRACKET: "debug_zoom_out",
                    pygame.K_RIGHTBRACKET: "debug_zoom_in",
                }.get(event.key)
                if debug_action_name is not None:
                    self._enqueue_action_if_mapped(debug_action_name)
                    continue

                if event.key in ACTION_KEYS:
                    self.action_press_count += 1
                    self._enqueue_action_if_mapped("interact")
                    continue

                if event.key in INVENTORY_KEYS:
                    self._enqueue_action_if_mapped("inventory")
                    continue

                direction = KEY_TO_DIRECTION.get(event.key)
                if direction is not None:
                    was_held = self.held_directions[direction]
                    self.held_directions[direction] = True
                    if was_held:
                        continue
                    self.direction_press_counts[direction] += 1
                    self._enqueue_direction_press(direction)
                continue

            if event.type == pygame.KEYUP:
                direction = KEY_TO_DIRECTION.get(event.key)
                if direction is not None:
                    self.held_directions[direction] = False
                    self._reset_direction_repeat(direction)

        return result

    def enqueue_held_movement_if_idle(self) -> None:
        """No-op shim retained for the unified held-repeat path."""
        return

    def update_held_direction_repeat(self, dt: float) -> None:
        """Repeat held directional input with an initial pause and steady interval."""
        if dt <= 0:
            return

        for direction in self.direction_priority:
            if not self.held_directions[direction]:
                self._reset_direction_repeat(direction)
                continue

            self.direction_repeat_cooldowns[direction] -= float(dt)

        for direction in self.direction_priority:
            if not self.held_directions[direction]:
                continue
            if self.direction_repeat_cooldowns[direction] > 0:
                continue

            action_name = f"move_{direction}"
            if not self._enqueue_held_direction_if_possible(action_name):
                continue

            self.direction_repeat_cooldowns[direction] = (
                HELD_DIRECTION_REPEAT_INTERVAL_SECONDS
            )
            return

    def _enqueue_direction_press(self, direction: str) -> None:
        """Dispatch the first key press immediately."""
        self._reset_direction_repeat(direction)
        action_name = f"move_{direction}"
        self._enqueue_action_if_mapped(action_name)

    def _enqueue_held_direction_if_possible(self, action_name: str) -> bool:
        """Dispatch one held directional action using the normal routed flow model."""
        if self._dispatch_modal_action(action_name):
            return True
        target_entity = self.world.get_input_target(action_name)
        if target_entity is None:
            return False
        if (
            action_name.startswith("move_")
            and target_entity.is_world_space()
            and target_entity.movement_state.active
        ):
            return False
        command_name = self._resolve_input_target_command_name(action_name, target_entity)
        if not command_name:
            return False
        return self.command_runner.dispatch_input_entity_command(
            entity_id=target_entity.entity_id,
            command_id=command_name,
        )

    def _reset_direction_repeat(self, direction: str) -> None:
        """Reset one logical direction's held-repeat timer."""
        self.direction_repeat_cooldowns[direction] = (
            HELD_DIRECTION_REPEAT_INITIAL_DELAY_SECONDS
        )

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
        """Run the mapped entity command for the routed entity when one exists."""
        if self._dispatch_modal_action(action_name):
            return True
        target_entity = self.world.get_input_target(action_name)
        if target_entity is None:
            return False
        command_name = self._resolve_input_target_command_name(action_name, target_entity)
        if not command_name:
            return False
        return self.command_runner.dispatch_input_entity_command(
            entity_id=target_entity.entity_id,
            command_id=command_name,
        )

    def _resolve_input_target_command_name(self, action_name: str, target_entity) -> str:
        """Resolve an input action to a named entity command on the routed entity."""
        command_name = target_entity.input_map.get(action_name)
        if command_name is not None:
            return str(command_name).strip()
        return ""

    def _dispatch_modal_action(self, action_name: str) -> bool:
        """Let active modal runtimes consume or block logical input before world routing."""
        for runtime in (self.dialogue_runtime, self.inventory_runtime):
            if runtime is None:
                continue
            is_active = getattr(runtime, "is_active", None)
            runtime_active = bool(is_active()) if callable(is_active) else False
            if not runtime_active:
                has_pending_work = getattr(runtime, "has_pending_work", None)
                runtime_active = bool(has_pending_work()) if callable(has_pending_work) else False
            if not runtime_active:
                continue
            handle_action = getattr(runtime, "handle_action", None)
            if callable(handle_action) and handle_action(action_name):
                return True
            return True
        return False

