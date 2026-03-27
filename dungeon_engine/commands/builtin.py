"""Starter command implementations used by the first prototype slice."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

from dungeon_engine import config
from dungeon_engine.commands.library import (
    instantiate_named_command_commands,
    load_named_command_definition,
)
from dungeon_engine.dialogue_library import DialogueDefinition, DialogueSegment, load_dialogue_definition
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import (
    AreaTransitionRequest,
    CameraFollowRequest,
    CommandContext,
    CommandHandle,
    ImmediateHandle,
    SequenceCommandHandle,
    WaitFramesHandle,
)
from dungeon_engine.world.entity import DIRECTION_VECTORS
from dungeon_engine.world.loader import instantiate_entity

logger = logging.getLogger(__name__)


class MovementCommandHandle(CommandHandle):
    """Wait until all entities started by a move command finish interpolating."""

    def __init__(self, context: CommandContext, entity_ids: list[str]) -> None:
        super().__init__()
        self.context = context
        self.entity_ids = entity_ids
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when every moved entity has stopped moving."""
        self.complete = not any(
            self.context.movement_system.is_entity_moving(entity_id)
            for entity_id in self.entity_ids
        )


class AnimationCommandHandle(CommandHandle):
    """Wait until all entities started by an animation command finish playback."""

    def __init__(
        self,
        context: CommandContext,
        entity_ids: list[str],
        *,
        visual_id: str | None = None,
    ) -> None:
        super().__init__()
        self.context = context
        self.entity_ids = entity_ids
        self.visual_id = visual_id
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when every animated entity has finished."""
        self.complete = not any(
            self.context.animation_system.is_entity_animating(entity_id, visual_id=self.visual_id)
            for entity_id in self.entity_ids
        )


class CameraCommandHandle(CommandHandle):
    """Wait until an interpolated camera move finishes."""

    def __init__(self, context: CommandContext) -> None:
        super().__init__()
        self.context = context
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when the camera stops moving."""
        camera = self.context.camera
        self.complete = camera is None or not camera.is_moving()


class ScreenAnimationCommandHandle(CommandHandle):
    """Wait until a screen-space animation finishes playback."""

    def __init__(self, context: CommandContext, element_id: str) -> None:
        super().__init__()
        self.context = context
        self.element_id = element_id
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Mark the command complete when the screen element stops animating."""
        screen_manager = self.context.screen_manager
        self.complete = screen_manager is None or not screen_manager.is_animating(self.element_id)


class ActionPressCommandHandle(CommandHandle):
    """Wait for the next action-button press after the handle starts."""

    def __init__(self, context: CommandContext) -> None:
        super().__init__()
        self.context = context
        input_handler = context.input_handler
        self.start_press_count = (
            input_handler.get_action_press_count() if input_handler is not None else 0
        )
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Complete only after a later action-button press occurs."""
        input_handler = self.context.input_handler
        if input_handler is None:
            self.complete = True
            return
        self.complete = input_handler.get_action_press_count() > self.start_press_count


class DirectionReleaseCommandHandle(CommandHandle):
    """Wait until one or more logical directions are no longer held."""

    def __init__(self, context: CommandContext, directions: list[str]) -> None:
        super().__init__()
        self.context = context
        self.directions = [str(direction) for direction in directions]
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Complete when every watched direction has been released."""
        input_handler = self.context.input_handler
        if input_handler is None:
            self.complete = True
            return
        self.complete = not any(
            input_handler.is_direction_held(direction)
            for direction in self.directions
        )


class DialogueCommandHandle(CommandHandle):
    """Drive one segmented dialogue asset while input stays on the controller entity."""

    def __init__(
        self,
        registry: CommandRegistry,
        context: CommandContext,
        *,
        dialogue_definition: DialogueDefinition,
        controller_entity_id: str,
        base_params: dict[str, Any],
        dialogue_on_start: list[dict[str, Any]],
        dialogue_on_end: list[dict[str, Any]],
        segment_hooks: list[DialogueSegmentHookConfig],
        font_id: str,
        max_lines: int,
        text_color: tuple[int, int, int],
        allow_cancel: bool,
    ) -> None:
        super().__init__()
        self.registry = registry
        self.context = context
        self.dialogue_definition = dialogue_definition
        self.controller_entity_id = str(controller_entity_id)
        self.base_params = dict(base_params)
        self.dialogue_on_start = [dict(command) for command in dialogue_on_start]
        self.dialogue_on_end = [dict(command) for command in dialogue_on_end]
        self.segment_hooks = list(segment_hooks)
        self.font_id = str(font_id)
        self.max_lines = int(max_lines)
        self.text_color = text_color
        self.allow_cancel = bool(allow_cancel)
        self.allow_entity_input = True
        if context.screen_manager is None:
            raise ValueError("start_dialogue_session requires a screen manager.")
        if context.text_renderer is None:
            raise ValueError("start_dialogue_session requires a text renderer.")
        self._validate_controller_entity()

        self.current_segment_index = -1
        self.current_speaker_id: str | None = None
        self.current_segment: DialogueSegment | None = None
        self.current_hooks = DialogueSegmentHookConfig()
        self.current_prompt_chunks: list[str] = []
        self.current_prompt_index = 0
        self.current_choice_index = 0
        self.current_choice_option_count = 0
        self.current_prompt_timer = 0.0
        self.nested_handle: CommandHandle | None = None
        self.after_nested: Any | None = None
        self.waiting_for_prompt_advance = False
        self.waiting_for_choice_selection = False

        self._set_controller_visible(True)

        self._run_command_list(self.dialogue_on_start, self._advance_to_next_segment)

    def update(self, dt: float) -> None:
        """Advance nested hook commands and timer-driven prompt progression."""
        if self.complete:
            return

        if self.nested_handle is not None:
            self.nested_handle.update(dt)
            self.captures_menu_input = self.nested_handle.captures_menu_input
            self.allow_entity_input = self.nested_handle.allow_entity_input
            if not self.nested_handle.complete:
                return
            callback = self.after_nested
            self.nested_handle = None
            self.after_nested = None
            self.captures_menu_input = False
            self.allow_entity_input = True
            if callback is not None:
                callback()
            return

        self.captures_menu_input = False
        self.allow_entity_input = True

        if (
            self.waiting_for_prompt_advance
            and self.current_segment is not None
            and self.current_segment.advance_mode in {"timer", "interact_or_timer"}
        ):
            self.current_prompt_timer += max(0.0, dt)
            if self.current_prompt_timer >= float(self.current_segment.advance_seconds or 0.0):
                self.advance()

    def advance(self) -> None:
        """Advance the current prompt when the segment allows interact progression."""
        if self.complete or self.nested_handle is not None or self.current_segment is None:
            return
        if not self.waiting_for_prompt_advance:
            return
        if self.current_segment.advance_mode == "timer":
            return
        self._advance_prompt()

    def move_choice_selection(self, delta: int) -> None:
        """Move the current choice selection up or down."""
        if self.complete or self.nested_handle is not None or not self.waiting_for_choice_selection:
            return
        assert self.current_segment is not None
        if not self.current_segment.options:
            return
        self.current_choice_index = (
            self.current_choice_index + int(delta)
        ) % len(self.current_segment.options)
        self._render_choice_options()

    def confirm_choice_selection(self) -> None:
        """Run the selected option's commands, if a choice is active."""
        if self.complete or self.nested_handle is not None or not self.waiting_for_choice_selection:
            return
        assert self.current_segment is not None
        self.waiting_for_choice_selection = False
        self._clear_option_elements()
        selected_option = self.current_segment.options[self.current_choice_index]
        selected_commands = self._resolve_selected_option_commands(selected_option)
        self._run_command_list(selected_commands, self._finish_segment)

    def cancel(self) -> None:
        """Close the dialogue when this session allows cancel behavior."""
        if self.complete or self.nested_handle is not None or not self.allow_cancel:
            return
        self._finish_dialogue()

    def _validate_controller_entity(self) -> None:
        """Fail fast when the configured controller entity is missing or invalid."""
        controller = self.context.world.get_entity(self.controller_entity_id)
        if controller is None:
            raise KeyError(
                f"start_dialogue_session requires controller entity '{self.controller_entity_id}'."
            )
        if controller.space != "screen":
            raise ValueError(
                f"Dialogue controller entity '{self.controller_entity_id}' must use space='screen'."
            )

    def _advance_to_next_segment(self) -> None:
        """Move to the next authored segment or finish the dialogue when exhausted."""
        self.current_segment_index += 1
        if self.current_segment_index >= len(self.dialogue_definition.segments):
            self._finish_dialogue()
            return

        self.current_segment = self.dialogue_definition.segments[self.current_segment_index]
        self.current_hooks = (
            self.segment_hooks[self.current_segment_index]
            if self.current_segment_index < len(self.segment_hooks)
            else DialogueSegmentHookConfig()
        )
        self.current_prompt_chunks = []
        self.current_prompt_index = 0
        self.current_choice_index = 0
        self.current_prompt_timer = 0.0
        self._clear_option_elements()

        resolved_speaker_id = self.current_speaker_id
        if self.current_segment.speaker_behavior == "explicit":
            resolved_speaker_id = self.current_segment.speaker_id
        self.current_speaker_id = resolved_speaker_id
        self._apply_controller_visual_state(
            self._resolve_portrait_state(resolved_speaker_id, self.current_segment)
        )
        self._run_command_list(self.current_hooks.on_start_commands, self._after_segment_start_commands)

    def _after_segment_start_commands(self) -> None:
        """Show the first visible prompt chunk or jump directly into choice selection."""
        assert self.current_segment is not None
        self.current_prompt_chunks = self._build_segment_prompt_chunks(self.current_segment)
        self.current_prompt_index = 0

        if self.current_prompt_chunks:
            self._show_prompt_chunk(0)
            return

        if self.current_segment.segment_type == "choice":
            self._begin_choice_selection()
            return

        self._finish_segment()

    def _advance_prompt(self) -> None:
        """Advance one visible prompt chunk or enter the choice stage."""
        assert self.current_segment is not None
        if self.current_prompt_index + 1 < len(self.current_prompt_chunks):
            self._show_prompt_chunk(self.current_prompt_index + 1)
            return

        self.waiting_for_prompt_advance = False
        if self.current_segment.segment_type == "choice":
            self.context.screen_manager.remove("dialogue_text")
            self._begin_choice_selection()
            return

        self._finish_segment()

    def _show_prompt_chunk(self, chunk_index: int) -> None:
        """Render one visible wrapped prompt page for the current segment."""
        assert self.context.screen_manager is not None
        self.current_prompt_index = chunk_index
        self.current_prompt_timer = 0.0
        text_box_x = self._require_controller_numeric_var("text_box_x")
        text_box_y = self._require_controller_numeric_var("text_box_y")
        self.context.screen_manager.show_text(
            element_id="dialogue_text",
            text=self.current_prompt_chunks[chunk_index],
            x=text_box_x,
            y=text_box_y,
            layer=101,
            anchor="topleft",
            color=self.text_color,
            font_id=self.font_id,
        )
        self.waiting_for_prompt_advance = True

    def _begin_choice_selection(self) -> None:
        """Render the current choice segment's options and wait for a selection."""
        assert self.current_segment is not None
        self.current_choice_index = 0
        self.waiting_for_choice_selection = True
        self._render_choice_options()

    def _finish_segment(self) -> None:
        """Run the current segment's end hooks, then continue to the next segment."""
        self.waiting_for_prompt_advance = False
        self.waiting_for_choice_selection = False
        self._run_command_list(self.current_hooks.on_end_commands, self._advance_to_next_segment)

    def _finish_dialogue(self) -> None:
        """Clear transient dialogue UI, close the panel, then run final hooks."""
        self.close_dialogue()
        self._run_command_list(self.dialogue_on_end, self._mark_complete)

    def _mark_complete(self) -> None:
        """Finalize the handle cleanly."""
        self.close_dialogue()
        self.complete = True
        self.allow_entity_input = False

    def close_dialogue(self) -> None:
        """Tear down the live dialogue UI once."""
        self.waiting_for_prompt_advance = False
        self.waiting_for_choice_selection = False
        self._clear_prompt_and_options()
        self._hide_controller_visuals()

    def _run_command_list(
        self,
        commands: list[dict[str, Any]],
        after: Any,
    ) -> None:
        """Run one inline command list inside the dialogue state machine."""
        if not commands:
            after()
            return
        handle = SequenceCommandHandle(
            self.registry,
            self.context,
            [dict(command) for command in commands],
            base_params={
                **self.base_params,
                "_dialogue_handle": self,
            },
        )
        if handle.complete:
            after()
            return
        self.nested_handle = handle
        self.after_nested = after

    def _set_controller_visible(self, visible: bool) -> None:
        """Update the controller entity's top-level visibility."""
        controller = self.context.world.get_entity(self.controller_entity_id)
        if controller is None:
            return
        controller.visible = bool(visible)

    def _apply_controller_visual_state(self, portrait_state: dict[str, Any]) -> None:
        """Show the controller panel and update its portrait visual."""
        controller = self.context.world.get_entity(self.controller_entity_id)
        if controller is None:
            raise KeyError(f"Dialogue controller entity '{self.controller_entity_id}' is missing.")
        self._set_controller_visible(True)
        portrait_visible = bool(portrait_state["portrait_path"])

        panel_visual = controller.get_visual(self._controller_visual_id("panel_visual_id", "panel"))
        if panel_visual is not None:
            panel_visual.visible = True

        portrait_visual = controller.get_visual(
            self._controller_visual_id("portrait_visual_id", "portrait")
        )
        if portrait_visual is not None:
            if portrait_visible:
                portrait_visual.path = str(portrait_state["portrait_path"])
                if portrait_state["portrait_frame_width"] is not None:
                    portrait_visual.frame_width = int(portrait_state["portrait_frame_width"])
                if portrait_state["portrait_frame_height"] is not None:
                    portrait_visual.frame_height = int(portrait_state["portrait_frame_height"])
                portrait_visual.current_frame = int(portrait_state["portrait_frame"])
                portrait_visual.visible = True
            else:
                portrait_visual.visible = False
        self._apply_layout_variant(controller, portrait_visible=portrait_visible)

    def _hide_controller_visuals(self) -> None:
        """Hide the controller visuals after the session closes."""
        controller = self.context.world.get_entity(self.controller_entity_id)
        if controller is None:
            return
        panel_visual = controller.get_visual(self._controller_visual_id("panel_visual_id", "panel"))
        if panel_visual is not None:
            panel_visual.visible = False
        portrait_visual = controller.get_visual(
            self._controller_visual_id("portrait_visual_id", "portrait")
        )
        if portrait_visual is not None:
            portrait_visual.visible = False
        self._set_controller_visible(False)

    def _apply_layout_variant(self, controller, *, portrait_visible: bool) -> None:
        """Switch the controller's live layout vars between portrait and plain modes."""
        prefix = "portrait" if portrait_visible else "plain"
        controller.variables["text_box_x"] = self._require_layout_value(controller, f"{prefix}_text_box_x")
        controller.variables["text_box_y"] = self._require_layout_value(controller, f"{prefix}_text_box_y")
        controller.variables["text_box_width"] = self._require_layout_value(
            controller,
            f"{prefix}_text_box_width",
        )
        controller.variables["choice_text_x"] = self._require_layout_value(
            controller,
            f"{prefix}_choice_text_x",
        )
        controller.variables["choice_width"] = self._require_layout_value(
            controller,
            f"{prefix}_choice_width",
        )

    def _require_layout_value(self, controller, variable_name: str) -> float:
        """Read one numeric layout setting from the controller entity."""
        value = controller.variables.get(variable_name)
        if not isinstance(value, (int, float)):
            raise ValueError(
                f"Dialogue controller entity '{self.controller_entity_id}' must define numeric variable '{variable_name}'."
            )
        return float(value)

    def _build_segment_prompt_chunks(self, segment: DialogueSegment) -> list[str]:
        """Return the wrapped prompt chunks for the current segment."""
        assert self.context.text_renderer is not None
        prompt_width = int(self._require_controller_numeric_var("text_box_width"))
        if segment.pages:
            chunks: list[str] = []
            for page_text in segment.pages:
                chunks.extend(
                    self.context.text_renderer.paginate_text(
                        page_text,
                        prompt_width,
                        self.max_lines,
                        font_id=self.font_id,
                    )
                )
            return chunks
        if segment.text is None:
            return []
        return self.context.text_renderer.paginate_text(
            segment.text,
            prompt_width,
            self.max_lines,
            font_id=self.font_id,
        )

    def _render_choice_options(self) -> None:
        """Render the current segment's choices using inline '-' selection text."""
        assert self.current_segment is not None
        assert self.context.screen_manager is not None
        assert self.context.text_renderer is not None
        self.context.screen_manager.remove("dialogue_text")
        self._clear_option_elements()

        option_x = self._require_controller_numeric_var("choice_text_x")
        choice_rows_y = self._resolve_choice_row_positions(len(self.current_segment.options))
        self.current_choice_option_count = len(self.current_segment.options)

        for option_index, option in enumerate(self.current_segment.options):
            selected = option_index == self.current_choice_index
            display_text = f"- {option.text}" if selected else option.text
            self.context.screen_manager.show_text(
                element_id=f"dialogue_option_{option_index}",
                text=display_text,
                x=option_x,
                y=choice_rows_y[option_index],
                layer=101,
                anchor="topleft",
                color=(245, 232, 190) if selected else (238, 242, 248),
                font_id=self.font_id,
                max_width=int(self._require_controller_numeric_var("choice_width")),
            )

    def _resolve_choice_row_positions(self, option_count: int) -> list[float]:
        """Return y positions for choice rows, extending the authored list when needed."""
        configured_rows: list[float] = []
        if self.context.project is not None:
            try:
                raw_rows = self.context.project.resolve_shared_variable("dialogue.choice_rows_y")
                if isinstance(raw_rows, list):
                    configured_rows = [float(row) for row in raw_rows]
            except KeyError:
                configured_rows = []

        if len(configured_rows) >= option_count:
            return configured_rows[:option_count]

        start_y = (
            configured_rows[-1]
            if configured_rows
            else self._require_controller_numeric_var("text_box_y")
        )
        line_step = float(self.context.text_renderer.line_height(font_id=self.font_id))
        while len(configured_rows) < option_count:
            configured_rows.append(start_y if not configured_rows else configured_rows[-1] + line_step)
        return configured_rows[:option_count]

    def _resolve_selected_option_commands(self, selected_option: Any) -> list[dict[str, Any]]:
        """Return the caller-provided command list for the chosen option."""
        if self.current_hooks.option_commands_by_id is not None:
            option_id = getattr(selected_option, "option_id", None)
            if option_id is None:
                return []
            return [dict(command) for command in self.current_hooks.option_commands_by_id.get(option_id, [])]
        if self.current_hooks.option_commands is not None:
            if self.current_choice_index >= len(self.current_hooks.option_commands):
                return []
            return [dict(command) for command in self.current_hooks.option_commands[self.current_choice_index]]
        return []

    def _require_controller_numeric_var(self, name: str) -> float:
        """Return one numeric layout variable from the dialogue controller entity."""
        controller_entity = self.context.world.get_entity(self.controller_entity_id)
        if controller_entity is None:
            raise KeyError(f"Dialogue controller entity '{self.controller_entity_id}' is missing.")
        value = controller_entity.variables.get(name)
        if not isinstance(value, (int, float)):
            raise ValueError(
                f"Dialogue controller entity '{self.controller_entity_id}' must define numeric variable '{name}'."
            )
        return float(value)

    def _controller_visual_id(self, variable_name: str, default: str) -> str:
        """Return one configured controller visual id."""
        controller_entity = self.context.world.get_entity(self.controller_entity_id)
        if controller_entity is None:
            return default
        value = controller_entity.variables.get(variable_name, default)
        return str(value).strip() or default

    def _resolve_portrait_state(
        self,
        speaker_id: str | None,
        segment: DialogueSegment,
    ) -> dict[str, Any]:
        """Resolve the current portrait payload for the panel helper event."""
        if speaker_id is None:
            return {
                "portrait_path": "",
                "portrait_frame_width": None,
                "portrait_frame_height": None,
                "portrait_frame": 0,
            }

        participant = self.dialogue_definition.participants.get(speaker_id)
        if participant is None:
            return {
                "portrait_path": "",
                "portrait_frame_width": None,
                "portrait_frame_height": None,
                "portrait_frame": 0,
            }

        if segment.show_portrait is False or not participant.portrait_path:
            return {
                "portrait_path": "",
                "portrait_frame_width": None,
                "portrait_frame_height": None,
                "portrait_frame": 0,
            }

        return {
            "portrait_path": participant.portrait_path,
            "portrait_frame_width": participant.portrait_frame_width,
            "portrait_frame_height": participant.portrait_frame_height,
            "portrait_frame": participant.portrait_frame,
        }

    def _clear_prompt_and_options(self) -> None:
        """Remove any currently rendered prompt/options from the screen manager."""
        assert self.context.screen_manager is not None
        self.context.screen_manager.remove("dialogue_text")
        self._clear_option_elements()

    def _clear_option_elements(self) -> None:
        """Remove the previously rendered choice option elements."""
        assert self.context.screen_manager is not None
        max_clear_count = max(self.current_choice_option_count, 8)
        for option_index in range(max_clear_count):
            self.context.screen_manager.remove(f"dialogue_option_{option_index}")
        self.current_choice_option_count = 0


@dataclass(slots=True)
class DialogueSegmentHookConfig:
    """Caller-owned hook configuration for one dialogue segment."""

    on_start_commands: list[dict[str, Any]] = field(default_factory=list)
    on_end_commands: list[dict[str, Any]] = field(default_factory=list)
    option_commands_by_id: dict[str, list[dict[str, Any]]] | None = None
    option_commands: list[list[dict[str, Any]]] | None = None


class NamedCommandHandle(CommandHandle):
    """Run a project-level named command definition while tracking recursion."""

    def __init__(
        self,
        context: CommandContext,
        command_id: str,
        sequence_handle: CommandHandle,
    ) -> None:
        super().__init__()
        self.context = context
        self.command_id = command_id
        self.sequence_handle = sequence_handle
        self._stack_pushed = False
        self._push_stack()
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Advance the underlying command sequence and pop the call stack when done."""
        if self.complete:
            return

        self.sequence_handle.update(dt)
        self.captures_menu_input = self.sequence_handle.captures_menu_input
        self.allow_entity_input = self.sequence_handle.allow_entity_input
        if self.sequence_handle.complete:
            self._pop_stack()
            self.complete = True
            self.captures_menu_input = False
            self.allow_entity_input = False

    def _push_stack(self) -> None:
        """Record entry into a named-command invocation."""
        if self._stack_pushed:
            return
        self.context.named_command_stack.append(self.command_id)
        self._stack_pushed = True

    def _pop_stack(self) -> None:
        """Remove this invocation from the named-command call stack."""
        if not self._stack_pushed:
            return
        if self.context.named_command_stack and self.context.named_command_stack[-1] == self.command_id:
            self.context.named_command_stack.pop()
        self._stack_pushed = False


def _resolve_entity_id(
    entity_id: str,
    *,
    source_entity_id: str | None,
    actor_entity_id: str | None,
    caller_entity_id: str | None = None,
) -> str:
    """Resolve special entity references used inside command specs.

    Returns an empty string when *entity_id* is blank (unconfigured parameter).
    Callers should treat an empty result as "nothing to do".
    """
    if not entity_id:
        return ""
    if entity_id == "self":
        if source_entity_id is None:
            raise ValueError("Command used 'self' without a source entity context.")
        return source_entity_id
    if entity_id == "actor":
        if actor_entity_id is None:
            raise ValueError("Command used 'actor' without an actor entity context.")
        return actor_entity_id
    if entity_id == "caller":
        if caller_entity_id is None:
            raise ValueError("Command used 'caller' without a caller entity context.")
        return caller_entity_id
    return entity_id


def _get_action_press_count(context: CommandContext) -> int:
    """Return the current action-button press counter, if available."""
    input_handler = context.input_handler
    return input_handler.get_action_press_count() if input_handler is not None else 0


def _get_menu_press_count(context: CommandContext) -> int:
    """Return the current menu-button press counter, if available."""
    input_handler = context.input_handler
    return input_handler.get_menu_press_count() if input_handler is not None else 0


def _get_direction_press_count(context: CommandContext, direction: str) -> int:
    """Return the keydown press counter for one logical direction."""
    input_handler = context.input_handler
    return input_handler.get_direction_press_count(direction) if input_handler is not None else 0


def _get_project_dialogue_defaults(context: CommandContext) -> dict[str, Any]:
    """Return project-authored dialogue defaults when available."""
    if context.project is None:
        return {}
    try:
        defaults = context.project.resolve_shared_variable("dialogue")
    except KeyError:
        return {}
    return defaults if isinstance(defaults, dict) else {}


def _get_dialogue_setting(
    dialogue_defaults: dict[str, Any],
    key: str,
    default: Any,
) -> Any:
    """Return one dialogue setting, falling back cleanly when absent."""
    return copy.deepcopy(dialogue_defaults.get(key, default))


def _normalize_color_tuple(
    value: Any,
    *,
    default: tuple[int, int, int],
) -> tuple[int, int, int]:
    """Convert a JSON color list/tuple into an RGB tuple."""
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return (int(value[0]), int(value[1]), int(value[2]))
        except (TypeError, ValueError):
            return default
    return default


def _normalize_command_specs(
    commands: list[dict[str, Any]] | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return one normalized inline command list."""
    if commands is None:
        return []
    if isinstance(commands, dict):
        return [dict(commands)]
    if isinstance(commands, list):
        return [dict(command) for command in commands]
    raise TypeError("Command hooks must be a dict, list of dicts, or null.")


def _normalize_option_command_batches(
    raw_batches: list[Any],
) -> list[list[dict[str, Any]]]:
    """Normalize one positional option-command binding list."""
    normalized_batches: list[list[dict[str, Any]]] = []
    for raw_batch in raw_batches:
        normalized_batches.append(_normalize_command_specs(raw_batch))
    return normalized_batches


def _parse_dialogue_segment_hook_configs(
    dialogue_definition: DialogueDefinition,
    raw_segment_hooks: list[dict[str, Any] | None] | None,
) -> list[DialogueSegmentHookConfig]:
    """Parse caller-supplied segment hooks for one dialogue session start."""
    if raw_segment_hooks is None:
        return []
    if not isinstance(raw_segment_hooks, list):
        raise TypeError("start_dialogue_session segment_hooks must be a list or null.")
    if len(raw_segment_hooks) > len(dialogue_definition.segments):
        raise ValueError(
            f"start_dialogue_session segment_hooks cannot define more than {len(dialogue_definition.segments)} entries for dialogue '{dialogue_definition.dialogue_id}'."
        )

    parsed_hooks: list[DialogueSegmentHookConfig] = []
    for segment_index, raw_hook in enumerate(raw_segment_hooks):
        if raw_hook is None:
            raw_hook = {}
        if not isinstance(raw_hook, dict):
            raise TypeError(
                f"start_dialogue_session segment_hooks[{segment_index}] must be an object or null."
            )

        raw_option_commands_by_id = raw_hook.get("option_commands_by_id")
        raw_option_commands = raw_hook.get("option_commands")
        if raw_option_commands_by_id is not None and raw_option_commands is not None:
            raise ValueError(
                f"start_dialogue_session segment_hooks[{segment_index}] cannot define both option_commands_by_id and option_commands."
            )

        option_commands_by_id: dict[str, list[dict[str, Any]]] | None = None
        if raw_option_commands_by_id is not None:
            if not isinstance(raw_option_commands_by_id, dict):
                raise TypeError(
                    f"start_dialogue_session segment_hooks[{segment_index}].option_commands_by_id must be an object."
                )
            option_commands_by_id = {}
            for option_id, raw_commands in raw_option_commands_by_id.items():
                resolved_option_id = str(option_id).strip()
                if not resolved_option_id:
                    raise ValueError(
                        f"start_dialogue_session segment_hooks[{segment_index}] cannot use a blank option id key."
                    )
                option_commands_by_id[resolved_option_id] = _normalize_command_specs(raw_commands)

        option_commands: list[list[dict[str, Any]]] | None = None
        if raw_option_commands is not None:
            if not isinstance(raw_option_commands, list):
                raise TypeError(
                    f"start_dialogue_session segment_hooks[{segment_index}].option_commands must be a list."
                )
            option_commands = _normalize_option_command_batches(raw_option_commands)

        parsed_hooks.append(
            DialogueSegmentHookConfig(
                on_start_commands=_normalize_command_specs(raw_hook.get("on_start")),
                on_end_commands=_normalize_command_specs(raw_hook.get("on_end")),
                option_commands_by_id=option_commands_by_id,
                option_commands=option_commands,
            )
        )

    for segment_index, hook_config in enumerate(parsed_hooks):
        segment = dialogue_definition.segments[segment_index]
        if segment.segment_type != "choice":
            if hook_config.option_commands_by_id is not None or hook_config.option_commands is not None:
                raise ValueError(
                    f"start_dialogue_session segment_hooks[{segment_index}] may only define option commands for choice segments."
                )
            continue

        if hook_config.option_commands is not None and len(hook_config.option_commands) > len(segment.options):
            raise ValueError(
                f"start_dialogue_session segment_hooks[{segment_index}].option_commands cannot define more than {len(segment.options)} entries."
            )

        if hook_config.option_commands_by_id is not None:
            option_ids = {option.option_id for option in segment.options if option.option_id is not None}
            if len(option_ids) != len(segment.options):
                raise ValueError(
                    f"start_dialogue_session segment_hooks[{segment_index}].option_commands_by_id requires option_id on every option in dialogue '{dialogue_definition.dialogue_id}'."
                )
            unknown_ids = sorted(option_id for option_id in hook_config.option_commands_by_id if option_id not in option_ids)
            if unknown_ids:
                raise ValueError(
                    f"start_dialogue_session segment_hooks[{segment_index}] references unknown option ids: {', '.join(unknown_ids)}."
                )

    return parsed_hooks


def _find_dialogue_handle(handle: CommandHandle | None) -> DialogueCommandHandle | None:
    """Return the first active dialogue handle nested inside a command tree."""
    if handle is None:
        return None
    if isinstance(handle, DialogueCommandHandle):
        return handle

    nested_handle = getattr(handle, "current_handle", None)
    found = _find_dialogue_handle(nested_handle)
    if found is not None:
        return found

    sequence_handle = getattr(handle, "sequence_handle", None)
    found = _find_dialogue_handle(sequence_handle)
    if found is not None:
        return found

    primary_handle = getattr(handle, "primary_handle", None)
    found = _find_dialogue_handle(primary_handle)
    if found is not None:
        return found

    start_handle = getattr(handle, "start_handle", None)
    found = _find_dialogue_handle(start_handle)
    if found is not None:
        return found

    end_handle = getattr(handle, "end_handle", None)
    return _find_dialogue_handle(end_handle)


def _resolve_variables(
    context: CommandContext,
    *,
    scope: str,
    entity_id: str | None = None,
    source_entity_id: str | None = None,
    actor_entity_id: str | None = None,
    caller_entity_id: str | None = None,
) -> dict[str, Any]:
    """Return the variables dict for the given scope."""
    if scope == "world":
        return context.world.variables
    if scope == "entity":
        if entity_id is None:
            raise ValueError("Entity scope requires entity_id.")
        resolved = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        entity = context.world.get_entity(resolved)
        if entity is None:
            raise KeyError(f"Entity '{resolved}' not found.")
        return entity.variables
    raise ValueError(f"Unknown variable scope '{scope}'.")


def _store_variable(
    context: CommandContext,
    *,
    scope: str,
    name: str,
    value: Any,
    entity_id: str | None = None,
    source_entity_id: str | None = None,
    actor_entity_id: str | None = None,
    caller_entity_id: str | None = None,
) -> None:
    """Store one resolved value into entity/world variables."""
    variables = _resolve_variables(
        context,
        scope=scope,
        entity_id=entity_id,
        source_entity_id=source_entity_id,
        actor_entity_id=actor_entity_id,
        caller_entity_id=caller_entity_id,
    )
    variables[str(name)] = copy.deepcopy(value)


def _resolve_text_session_source(
    context: CommandContext,
    *,
    dialogue_id: str | None = None,
    text: str | None = None,
    pages: list[str] | None = None,
    font_id: str = config.DEFAULT_DIALOGUE_FONT_ID,
    max_lines: int | None = None,
) -> tuple[str | None, list[str] | None, str, int | None]:
    """Resolve dialogue/text-session source data from inline text or a dialogue asset."""
    dialogue_data: dict[str, Any] = {}
    if dialogue_id is not None:
        if context.project is None:
            raise ValueError("Text sessions with dialogue_id require an active project.")
        dialogue_definition = load_dialogue_definition(context.project, str(dialogue_id))
        dialogue_data = dict(dialogue_definition.raw_data)

    resolved_text = text
    resolved_pages = pages
    resolved_font_id = str(font_id)
    resolved_max_lines = max_lines

    if resolved_text is None and dialogue_data.get("text") is not None:
        resolved_text = str(dialogue_data["text"])
    if resolved_pages is None and dialogue_data.get("pages") is not None:
        raw_pages = dialogue_data["pages"]
        if isinstance(raw_pages, list):
            resolved_pages = [str(page) for page in raw_pages]
    if resolved_font_id == config.DEFAULT_DIALOGUE_FONT_ID and dialogue_data.get("font_id") is not None:
        resolved_font_id = str(dialogue_data["font_id"])
    if resolved_max_lines is None and dialogue_data.get("max_lines") is not None:
        resolved_max_lines = int(dialogue_data["max_lines"])

    if resolved_text is None and not resolved_pages:
        raise ValueError("Text session preparation requires text or pages.")

    return resolved_text, resolved_pages, resolved_font_id, resolved_max_lines


def _resolve_facing_direction(entity, direction: str | None) -> str:
    """Return an explicit direction, defaulting to the entity's current facing."""
    resolved_direction = str(direction or entity.facing)
    if resolved_direction not in DIRECTION_VECTORS:
        raise ValueError(f"Unknown direction '{resolved_direction}'.")
    return resolved_direction


def _get_facing_tile(entity, direction: str | None = None) -> tuple[int, int, str]:
    """Return the tile in front of an entity for a resolved direction."""
    resolved_direction = _resolve_facing_direction(entity, direction)
    delta_x, delta_y = DIRECTION_VECTORS[resolved_direction]  # type: ignore[index]
    return entity.grid_x + delta_x, entity.grid_y + delta_y, resolved_direction


def _get_facing_target_entity(
    context: CommandContext,
    *,
    actor_entity_id: str,
    direction: str | None = None,
    prefer_blocking: bool = False,
):
    """Return the topmost entity ahead of the actor, optionally preferring blockers."""
    actor = context.world.get_entity(actor_entity_id)
    if actor is None:
        raise KeyError(f"Cannot resolve facing target for missing entity '{actor_entity_id}'.")

    target_x, target_y, _ = _get_facing_tile(actor, direction)
    if prefer_blocking:
        blocking_entity = context.collision_system.get_blocking_entity(
            target_x,
            target_y,
            ignore_entity_id=actor.entity_id,
        )
        if blocking_entity is not None:
            return blocking_entity

    for entity in reversed(
        context.world.get_entities_at(
            target_x,
            target_y,
            exclude_entity_id=actor.entity_id,
        )
    ):
        return entity
    return None


def _persist_entity_field(
    context: CommandContext,
    *,
    entity_id: str,
    field_name: str,
    value: Any,
    entity: Any,
) -> None:
    """Persist a single entity field when runtime persistence is available."""
    if context.persistence_runtime is None:
        return
    context.persistence_runtime.set_entity_field(
        entity_id,
        field_name,
        value,
        entity=entity,
        tile_size=context.area.tile_size,
    )


def _persist_entity_event_enabled(
    context: CommandContext,
    *,
    entity_id: str,
    event_id: str,
    enabled: bool,
    entity: Any,
) -> None:
    """Persist an event enabled-state change when runtime persistence is available."""
    if context.persistence_runtime is None:
        return
    context.persistence_runtime.set_entity_event_enabled(
        entity_id,
        event_id,
        enabled,
        entity=entity,
        tile_size=context.area.tile_size,
    )


def _normalize_input_map(value: Any) -> dict[str, str]:
    """Convert JSON-like input-map data into a stable string-to-string mapping."""
    if not isinstance(value, dict):
        raise ValueError("input_map must be an object.")
    return {
        str(action): str(event_name)
        for action, event_name in value.items()
    }


def _serialize_entity_visuals(entity: Any) -> list[dict[str, Any]]:
    """Serialize runtime visuals for persistent field mutations."""
    serialized: list[dict[str, Any]] = []
    for visual in entity.visuals:
        serialized.append(
            {
                "id": visual.visual_id,
                "path": visual.path,
                "frame_width": visual.frame_width,
                "frame_height": visual.frame_height,
                "frames": list(visual.frames),
                "animation_fps": visual.animation_fps,
                "animate_when_moving": visual.animate_when_moving,
                "current_frame": visual.current_frame,
                "flip_x": visual.flip_x,
                "visible": visual.visible,
                "tint": list(visual.tint),
                "offset_x": visual.offset_x,
                "offset_y": visual.offset_y,
                "draw_order": visual.draw_order,
            }
        )
    return serialized


def _apply_entity_field_value(
    entity: Any,
    field_name: str,
    value: Any,
) -> tuple[str, Any]:
    """Apply one supported runtime entity field mutation and return its persistent form."""
    path = [segment for segment in str(field_name).split(".") if segment]
    if not path:
        raise ValueError("set_entity_field requires a non-empty field name.")

    root = path[0]
    if root == "facing":
        if len(path) != 1:
            raise ValueError("facing does not support nested field paths.")
        entity.facing = _resolve_facing_direction(entity, str(value))  # type: ignore[assignment]
        return "facing", entity.facing

    if root == "solid":
        if len(path) != 1:
            raise ValueError("solid does not support nested field paths.")
        entity.solid = bool(value)
        return "solid", entity.solid

    if root == "pushable":
        if len(path) != 1:
            raise ValueError("pushable does not support nested field paths.")
        entity.pushable = bool(value)
        return "pushable", entity.pushable

    if root == "present":
        if len(path) != 1:
            raise ValueError("present does not support nested field paths.")
        entity.set_present(bool(value))
        return "present", entity.present

    if root == "visible":
        if len(path) != 1:
            raise ValueError("visible does not support nested field paths.")
        entity.visible = bool(value)
        return "visible", entity.visible

    if root == "events_enabled":
        if len(path) != 1:
            raise ValueError("events_enabled does not support nested field paths.")
        entity.set_events_enabled(bool(value))
        return "events_enabled", entity.events_enabled

    if root == "layer":
        if len(path) != 1:
            raise ValueError("layer does not support nested field paths.")
        entity.layer = int(value)
        return "layer", entity.layer

    if root == "stack_order":
        if len(path) != 1:
            raise ValueError("stack_order does not support nested field paths.")
        entity.stack_order = int(value)
        return "stack_order", entity.stack_order

    if root == "color":
        if len(path) != 1:
            raise ValueError("color does not support nested field paths.")
        if not isinstance(value, (list, tuple)) or len(value) < 3:
            raise ValueError("color must be a list or tuple with at least 3 channels.")
        entity.color = (int(value[0]), int(value[1]), int(value[2]))
        return "color", list(entity.color)

    if root == "visuals":
        if len(path) < 3:
            raise ValueError("visuals field mutations must use visuals.<visual_id>.<field>.")
        visual = entity.require_visual(str(path[1]))
        visual_field = str(path[2])
        if visual_field == "flip_x":
            visual.flip_x = bool(value)
        elif visual_field == "visible":
            visual.visible = bool(value)
        elif visual_field == "current_frame":
            visual.current_frame = int(value)
        elif visual_field == "tint":
            if not isinstance(value, (list, tuple)) or len(value) < 3:
                raise ValueError("visual tint must be a list or tuple with at least 3 channels.")
            visual.tint = (int(value[0]), int(value[1]), int(value[2]))
        else:
            raise ValueError(f"Unsupported visuals field '{visual_field}'.")
        return "visuals", _serialize_entity_visuals(entity)

    if root == "input_map":
        if len(path) == 1:
            entity.input_map = _normalize_input_map(value)
        elif len(path) == 2:
            entity.input_map[str(path[1])] = str(value)
        else:
            raise ValueError("input_map only supports one nested key level.")
        return "input_map", copy.deepcopy(entity.input_map)

    raise ValueError(
        f"Unsupported entity field '{field_name}'. "
        "Use set_var for variables and dedicated commands for events/template rebuilds."
    )


_COMPARE_OPS: dict[str, Any] = {
    "eq": lambda a, b: a == b,
    "neq": lambda a, b: a != b,
    "gt": lambda a, b: a is not None and b is not None and a > b,
    "lt": lambda a, b: a is not None and b is not None and a < b,
    "gte": lambda a, b: a is not None and b is not None and a >= b,
    "lte": lambda a, b: a is not None and b is not None and a <= b,
}


def register_builtin_commands(registry: CommandRegistry) -> None:
    """Register the minimal command set needed for the first movement slice."""

    def _set_entity_field_handle(
        context: CommandContext,
        *,
        entity_id: str,
        field_name: str,
        value: Any,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
    ) -> CommandHandle:
        """Apply one generic entity field mutation through the shared helper."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("set_entity_field: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set field on missing entity '{resolved_id}'.")
        persisted_field_name, persisted_value = _apply_entity_field_value(
            entity,
            str(field_name),
            value,
        )
        if persistent:
            _persist_entity_field(
                context,
                entity_id=resolved_id,
                field_name=persisted_field_name,
                value=persisted_value,
                entity=entity,
            )
        return ImmediateHandle()

    def _step_entity(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        direction: str,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str = "immediate",
        allow_push: bool = True,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("move_entity_one_tile: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        moved_entity_ids = context.movement_system.request_grid_step(
            resolved_id,
            direction,  # type: ignore[arg-type]
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync=grid_sync,  # type: ignore[arg-type]
            allow_push=allow_push,
        )
        if not moved_entity_ids:
            return ImmediateHandle()
        if not wait:
            return ImmediateHandle()
        return MovementCommandHandle(context, moved_entity_ids)

    def _move_entity_to_position(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        target_x: float,
        target_y: float,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str = "none",
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("move_entity: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        moved_entity_ids = context.movement_system.request_move_to_position(
            resolved_id,
            target_x,
            target_y,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync=grid_sync,  # type: ignore[arg-type]
            target_grid_x=target_grid_x,
            target_grid_y=target_grid_y,
        )
        if not moved_entity_ids:
            return ImmediateHandle()
        if not wait:
            return ImmediateHandle()
        return MovementCommandHandle(context, moved_entity_ids)

    def _move_entity(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        x: int | float,
        y: int | float,
        space: str = "pixel",
        mode: str = "absolute",
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str | None = None,
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("move_entity: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        if space not in {"pixel", "grid"}:
            raise ValueError(f"Unknown movement space '{space}'.")
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown movement mode '{mode}'.")

        effective_grid_sync = grid_sync
        if effective_grid_sync is None:
            effective_grid_sync = "on_complete" if space == "grid" else "none"

        if space == "pixel" and mode == "absolute":
            return _move_entity_to_position(
                context,
                entity_id=resolved_id,
                target_x=float(x),
                target_y=float(y),
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
                duration=duration,
                frames_needed=frames_needed,
                speed_px_per_second=speed_px_per_second,
                grid_sync=effective_grid_sync,
                target_grid_x=target_grid_x,
                target_grid_y=target_grid_y,
                wait=wait,
            )

        if space == "pixel" and mode == "relative":
            moved_entity_ids = context.movement_system.request_move_by_offset(
                resolved_id,
                float(x),
                float(y),
                duration=duration,
                frames_needed=frames_needed,
                speed_px_per_second=speed_px_per_second,
                grid_sync=effective_grid_sync,  # type: ignore[arg-type]
                target_grid_x=target_grid_x,
                target_grid_y=target_grid_y,
            )
            if not moved_entity_ids:
                return ImmediateHandle()
            if not wait:
                return ImmediateHandle()
            return MovementCommandHandle(context, moved_entity_ids)

        if space == "grid" and mode == "absolute":
            moved_entity_ids = context.movement_system.request_move_to_grid_position(
                resolved_id,
                int(x),
                int(y),
                duration=duration,
                frames_needed=frames_needed,
                speed_px_per_second=speed_px_per_second,
                grid_sync=effective_grid_sync,  # type: ignore[arg-type]
            )
            if not moved_entity_ids:
                return ImmediateHandle()
            if not wait:
                return ImmediateHandle()
            return MovementCommandHandle(context, moved_entity_ids)

        moved_entity_ids = context.movement_system.request_move_by_grid_offset(
            resolved_id,
            int(x),
            int(y),
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync=effective_grid_sync,  # type: ignore[arg-type]
        )
        if not moved_entity_ids:
            return ImmediateHandle()
        if not wait:
            return ImmediateHandle()
        return MovementCommandHandle(context, moved_entity_ids)

    def _teleport_entity(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        x: int | float,
        y: int | float,
        space: str = "pixel",
        mode: str = "absolute",
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
        **_: Any,
    ) -> CommandHandle:
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("teleport_entity: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        if space not in {"pixel", "grid"}:
            raise ValueError(f"Unknown teleport space '{space}'.")
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown teleport mode '{mode}'.")

        if space == "grid":
            entity = context.world.get_entity(resolved_id)
            if entity is None:
                raise KeyError(f"Cannot teleport missing entity '{resolved_id}'.")
            grid_x = int(x) if mode == "absolute" else entity.grid_x + int(x)
            grid_y = int(y) if mode == "absolute" else entity.grid_y + int(y)
            context.movement_system.teleport_to_grid_position(resolved_id, grid_x, grid_y)
            return ImmediateHandle()

        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot teleport missing entity '{resolved_id}'.")
        pixel_x = float(x) if mode == "absolute" else entity.pixel_x + float(x)
        pixel_y = float(y) if mode == "absolute" else entity.pixel_y + float(y)
        context.movement_system.teleport_to_position(
            resolved_id,
            pixel_x,
            pixel_y,
            target_grid_x=target_grid_x,
            target_grid_y=target_grid_y,
        )
        return ImmediateHandle()

    def _play_animation(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        visual_id: str | None = None,
        frame_sequence: list[int],
        frames_per_sprite_change: int = 1,
        hold_last_frame: bool = True,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("play_animation: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        context.animation_system.start_frame_animation(
            resolved_id,
            frame_sequence,
            visual_id=visual_id,
            frames_per_sprite_change=frames_per_sprite_change,
            hold_last_frame=hold_last_frame,
        )
        if not wait:
            return ImmediateHandle()
        return AnimationCommandHandle(context, [resolved_id], visual_id=visual_id)

    @registry.register("set_facing")
    def set_facing(
        context: CommandContext,
        *,
        entity_id: str,
        direction: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Set an entity's facing direction without moving it."""
        return _set_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="facing",
            value=direction,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )

    @registry.register("query_facing_state")
    def query_facing_state(
        context: CommandContext,
        *,
        entity_id: str,
        store_state_var: str,
        store_entity_id_var: str | None = None,
        direction: str | None = None,
        movable_event_id: str | None = None,
        scope: str = "entity",
        variable_entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Store whether the tile in front is free, movable, or blocked."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("query_facing_state: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        actor = context.world.get_entity(resolved_id)
        if actor is None:
            raise KeyError(f"Cannot query facing state for missing entity '{resolved_id}'.")

        target_x, target_y, _ = _get_facing_tile(actor, direction)
        blocking_entity = context.collision_system.get_blocking_entity(
            target_x,
            target_y,
            ignore_entity_id=resolved_id,
        )
        if blocking_entity is None:
            state = (
                "free"
                if context.collision_system.can_move_to(
                    target_x,
                    target_y,
                    ignore_entity_id=resolved_id,
                )
                else "blocked"
            )
            blocking_entity_id = ""
        else:
            blocking_entity_id = blocking_entity.entity_id
            if movable_event_id and blocking_entity.has_enabled_event(str(movable_event_id)):
                state = "movable"
            elif blocking_entity.pushable:
                state = "movable"
            else:
                state = "blocked"

        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=variable_entity_id if scope == "entity" and variable_entity_id is not None else resolved_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        variables[store_state_var] = state
        if store_entity_id_var:
            variables[store_entity_id_var] = blocking_entity_id
        return ImmediateHandle()

    @registry.register("run_facing_event")
    def run_facing_event(
        context: CommandContext,
        *,
        entity_id: str,
        event_id: str,
        direction: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Run a named event on the entity directly in front of an actor."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("run_facing_event: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        target_entity = _get_facing_target_entity(
            context,
            actor_entity_id=resolved_id,
            direction=direction,
            prefer_blocking=True,
        )
        if target_entity is None:
            return ImmediateHandle()
        event = target_entity.get_event(event_id)
        if not target_entity.has_enabled_event(event_id) or event is None or not event.commands:
            return ImmediateHandle()
        return SequenceCommandHandle(
            registry,
            context,
            event.commands,
            base_params={
                "source_entity_id": target_entity.entity_id,
                "actor_entity_id": resolved_id,
                **({"caller_entity_id": caller_entity_id} if caller_entity_id is not None else {}),
            },
        )

    @registry.register("move_entity_one_tile")
    def move_entity_one_tile(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        direction: str,
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str = "immediate",
        allow_push: bool = True,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Move an entity by one grid tile while keeping motion configurable."""
        return _step_entity(
            context,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
            direction=direction,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync=grid_sync,
            allow_push=allow_push,
            wait=wait,
        )

    @registry.register("move_entity")
    def move_entity(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        x: int | float,
        y: int | float,
        space: str = "pixel",
        mode: str = "absolute",
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        grid_sync: str | None = None,
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Move an entity using pixel/grid and absolute/relative addressing."""
        return _move_entity(
            context,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
            x=x,
            y=y,
            space=space,
            mode=mode,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
            grid_sync=grid_sync,
            target_grid_x=target_grid_x,
            target_grid_y=target_grid_y,
            wait=wait,
        )

    @registry.register("teleport_entity")
    def teleport_entity(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        x: int | float,
        y: int | float,
        space: str = "pixel",
        mode: str = "absolute",
        target_grid_x: int | None = None,
        target_grid_y: int | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Instantly reposition an entity using pixel/grid and absolute/relative addressing."""
        return _teleport_entity(
            context,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
            x=x,
            y=y,
            space=space,
            mode=mode,
            target_grid_x=target_grid_x,
            target_grid_y=target_grid_y,
        )

    @registry.register("wait_for_move")
    def wait_for_move(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        visual_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Block the command lane until the requested entity stops moving."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("wait_for_move: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        if not context.movement_system.is_entity_moving(resolved_id):
            return ImmediateHandle()
        return MovementCommandHandle(context, [resolved_id])

    @registry.register("play_animation")
    def play_animation(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        visual_id: str | None = None,
        frame_sequence: list[int],
        frames_per_sprite_change: int = 1,
        hold_last_frame: bool = True,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Play a one-shot sprite frame sequence on an entity."""
        return _play_animation(
            context,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
            visual_id=visual_id,
            frame_sequence=frame_sequence,
            frames_per_sprite_change=frames_per_sprite_change,
            hold_last_frame=hold_last_frame,
            wait=wait,
        )

    @registry.register("wait_for_animation")
    def wait_for_animation(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        visual_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Block the command lane until the requested entity stops animating."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("wait_for_animation: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        if not context.animation_system.is_entity_animating(resolved_id, visual_id=visual_id):
            return ImmediateHandle()
        return AnimationCommandHandle(context, [resolved_id], visual_id=visual_id)

    @registry.register("stop_animation")
    def stop_animation(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        visual_id: str | None = None,
        reset_to_default: bool = False,
        **_: Any,
    ) -> CommandHandle:
        """Stop command-driven animation playback on an entity."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("stop_animation: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        context.animation_system.stop_animation(
            resolved_id,
            visual_id=visual_id,
            reset_to_default=reset_to_default,
        )
        return ImmediateHandle()

    @registry.register("set_visual_frame")
    def set_visual_frame(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        visual_id: str | None = None,
        frame: int,
        **_: Any,
    ) -> CommandHandle:
        """Set the currently displayed visual frame directly."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("set_visual_frame: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set visual frame on missing entity '{resolved_id}'.")
        visual = entity.require_visual(visual_id) if visual_id is not None else entity.get_primary_visual()
        if visual is None:
            raise KeyError(f"Entity '{resolved_id}' has no visual to set a frame on.")
        visual.current_frame = int(frame)
        return ImmediateHandle()

    @registry.register("set_visual_flip_x")
    def set_visual_flip_x(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        visual_id: str | None = None,
        flip_x: bool,
        **_: Any,
    ) -> CommandHandle:
        """Set whether an entity's visual should be mirrored horizontally."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("set_visual_flip_x: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set visual flip_x on missing entity '{resolved_id}'.")
        visual = entity.require_visual(visual_id) if visual_id is not None else entity.get_primary_visual()
        if visual is None:
            raise KeyError(f"Entity '{resolved_id}' has no visual to set flip_x on.")
        visual.flip_x = bool(flip_x)
        return ImmediateHandle()

    @registry.register("play_audio")
    def play_audio(
        context: CommandContext,
        *,
        path: str,
        **_: Any,
    ) -> CommandHandle:
        """Play a one-shot audio asset from the active project's assets."""
        if context.audio_player is None:
            return ImmediateHandle()
        context.audio_player.play_audio(str(path))
        return ImmediateHandle()

    @registry.register("show_screen_image")
    def show_screen_image(
        context: CommandContext,
        *,
        element_id: str,
        path: str,
        x: int | float,
        y: int | float,
        frame_width: int | None = None,
        frame_height: int | None = None,
        frame: int = 0,
        layer: int = 0,
        anchor: str = "topleft",
        flip_x: bool = False,
        tint: tuple[int, int, int] = (255, 255, 255),
        visible: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Create or replace a screen-space image element."""
        if context.screen_manager is None:
            raise ValueError("Cannot show a screen image without a screen manager.")
        context.screen_manager.show_image(
            element_id=str(element_id),
            asset_path=str(path),
            x=float(x),
            y=float(y),
            frame_width=int(frame_width) if frame_width is not None else None,
            frame_height=int(frame_height) if frame_height is not None else None,
            frame=int(frame),
            layer=int(layer),
            anchor=str(anchor),  # type: ignore[arg-type]
            flip_x=bool(flip_x),
            tint=tuple(int(channel) for channel in tint),
            visible=bool(visible),
        )
        return ImmediateHandle()

    @registry.register("show_screen_text")
    def show_screen_text(
        context: CommandContext,
        *,
        element_id: str,
        text: str,
        x: int | float,
        y: int | float,
        layer: int = 0,
        anchor: str = "topleft",
        color: tuple[int, int, int] = config.COLOR_TEXT,
        font_id: str = config.DEFAULT_UI_FONT_ID,
        max_width: int | None = None,
        visible: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Create or replace a screen-space text element."""
        if context.screen_manager is None:
            raise ValueError("Cannot show screen text without a screen manager.")
        context.screen_manager.show_text(
            element_id=str(element_id),
            text=str(text),
            x=float(x),
            y=float(y),
            layer=int(layer),
            anchor=str(anchor),  # type: ignore[arg-type]
            color=tuple(int(channel) for channel in color),
            font_id=str(font_id),
            max_width=int(max_width) if max_width is not None else None,
            visible=bool(visible),
        )
        return ImmediateHandle()

    @registry.register("set_screen_text")
    def set_screen_text(
        context: CommandContext,
        *,
        element_id: str,
        text: str,
        **_: Any,
    ) -> CommandHandle:
        """Replace the text content of an existing screen-space text element."""
        if context.screen_manager is None:
            raise ValueError("Cannot set screen text without a screen manager.")
        context.screen_manager.set_text(str(element_id), str(text))
        return ImmediateHandle()

    @registry.register("remove_screen_element")
    def remove_screen_element(
        context: CommandContext,
        *,
        element_id: str,
        **_: Any,
    ) -> CommandHandle:
        """Remove one screen-space element."""
        if context.screen_manager is None:
            raise ValueError("Cannot remove a screen element without a screen manager.")
        context.screen_manager.remove(str(element_id))
        return ImmediateHandle()

    @registry.register("clear_screen_elements")
    def clear_screen_elements(
        context: CommandContext,
        *,
        layer: int | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Clear all screen-space elements, optionally only one layer."""
        if context.screen_manager is None:
            raise ValueError("Cannot clear screen elements without a screen manager.")
        context.screen_manager.clear(layer=layer)
        return ImmediateHandle()

    @registry.register("play_screen_animation")
    def play_screen_animation(
        context: CommandContext,
        *,
        element_id: str,
        frame_sequence: list[int],
        ticks_per_frame: int = 1,
        hold_last_frame: bool = True,
        wait: bool = True,
        **_: Any,
    ) -> CommandHandle:
        """Start a one-shot frame animation on an existing screen image."""
        if context.screen_manager is None:
            raise ValueError("Cannot play a screen animation without a screen manager.")
        context.screen_manager.start_animation(
            element_id=str(element_id),
            frame_sequence=[int(frame) for frame in frame_sequence],
            ticks_per_frame=int(ticks_per_frame),
            hold_last_frame=bool(hold_last_frame),
        )
        if not wait:
            return ImmediateHandle()
        return ScreenAnimationCommandHandle(context, str(element_id))

    @registry.register("wait_for_screen_animation")
    def wait_for_screen_animation(
        context: CommandContext,
        *,
        element_id: str,
        **_: Any,
    ) -> CommandHandle:
        """Block until the requested screen-space animation finishes."""
        if context.screen_manager is None:
            raise ValueError("Cannot wait for a screen animation without a screen manager.")
        if not context.screen_manager.is_animating(str(element_id)):
            return ImmediateHandle()
        return ScreenAnimationCommandHandle(context, str(element_id))

    @registry.register("wait_frames")
    def wait_frames(
        context: CommandContext,
        *,
        frames: int,
        **_: Any,
    ) -> CommandHandle:
        """Pause the current command lane for a fixed number of simulation ticks."""
        return WaitFramesHandle(int(frames))

    @registry.register("wait_for_action_press")
    def wait_for_action_press(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Pause until the next Space/Enter-style action press occurs."""
        return ActionPressCommandHandle(context)

    @registry.register("wait_for_direction_release")
    def wait_for_direction_release(
        context: CommandContext,
        *,
        direction: str | None = None,
        directions: list[str] | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Pause until the watched logical direction keys are released."""
        watched_directions: list[str]
        if directions is not None:
            watched_directions = [str(item) for item in directions]
        elif direction is not None:
            watched_directions = [str(direction)]
        else:
            raise ValueError("wait_for_direction_release requires direction or directions.")
        if not watched_directions:
            return ImmediateHandle()
        valid_directions = {"up", "down", "left", "right"}
        for watched_direction in watched_directions:
            if watched_direction not in valid_directions:
                raise ValueError(f"Unknown direction '{watched_direction}'.")
        return DirectionReleaseCommandHandle(context, watched_directions)

    @registry.register("run_dialogue")
    def run_dialogue(
        *_: Any,
        **__: Any,
    ) -> CommandHandle:
        """Reject the removed engine-owned dialogue command path."""
        raise ValueError(
            "run_dialogue was removed. Start dialogues by sending an event to the dialogue controller entity and using 'start_dialogue_session'."
        )

    @registry.register("start_dialogue_session")
    def start_dialogue_session(
        context: CommandContext,
        *,
        dialogue_id: str,
        controller_entity_id: str = "self",
        on_start: list[dict[str, Any]] | dict[str, Any] | None = None,
        on_end: list[dict[str, Any]] | dict[str, Any] | None = None,
        segment_hooks: list[dict[str, Any] | None] | None = None,
        allow_cancel: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Start a controller-owned dialogue session and wait until it finishes."""
        if context.screen_manager is None:
            raise ValueError("Cannot start a dialogue session without a screen manager.")
        if context.text_renderer is None:
            raise ValueError("Cannot start a dialogue session without a text renderer.")
        if context.project is None:
            raise ValueError("start_dialogue_session requires an active project.")

        dialogue_definition = load_dialogue_definition(context.project, str(dialogue_id))
        dialogue_defaults = _get_project_dialogue_defaults(context)
        resolved_font_id = str(dialogue_definition.font_id or config.DEFAULT_DIALOGUE_FONT_ID)
        resolved_max_lines = int(
            dialogue_definition.max_lines
            if dialogue_definition.max_lines is not None
            else _get_dialogue_setting(dialogue_defaults, "max_lines", 2)
        )
        if resolved_max_lines <= 0:
            raise ValueError("start_dialogue_session requires max_lines > 0.")
        parsed_segment_hooks = _parse_dialogue_segment_hook_configs(dialogue_definition, segment_hooks)

        return DialogueCommandHandle(
            registry,
            context,
            dialogue_definition=dialogue_definition,
            controller_entity_id=_resolve_entity_id(
                controller_entity_id,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            ),
            base_params={
                **({"source_entity_id": source_entity_id} if source_entity_id is not None else {}),
                **({"actor_entity_id": actor_entity_id} if actor_entity_id is not None else {}),
                **({"caller_entity_id": caller_entity_id} if caller_entity_id is not None else {}),
            },
            dialogue_on_start=_normalize_command_specs(on_start),
            dialogue_on_end=_normalize_command_specs(on_end),
            segment_hooks=parsed_segment_hooks,
            font_id=resolved_font_id,
            max_lines=resolved_max_lines,
            text_color=_normalize_color_tuple(
                dialogue_definition.text_color
                if dialogue_definition.text_color is not None
                else _get_dialogue_setting(dialogue_defaults, "text_color", None),
                default=config.COLOR_TEXT,
            ),
            allow_cancel=allow_cancel,
        )

    @registry.register("dialogue_advance")
    def dialogue_advance(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Advance the currently active dialogue prompt when possible."""
        handle = _find_dialogue_handle(getattr(context.command_runner, "active_handle", None))
        if handle is not None:
            handle.advance()
        return ImmediateHandle()

    @registry.register("dialogue_move_selection")
    def dialogue_move_selection(
        context: CommandContext,
        *,
        direction: str,
        **_: Any,
    ) -> CommandHandle:
        """Move the current dialogue selection up or down."""
        handle = _find_dialogue_handle(getattr(context.command_runner, "active_handle", None))
        if handle is None:
            return ImmediateHandle()
        normalized_direction = str(direction).strip().lower()
        if normalized_direction == "up":
            handle.move_choice_selection(-1)
        elif normalized_direction == "down":
            handle.move_choice_selection(1)
        else:
            raise ValueError("dialogue_move_selection direction must be 'up' or 'down'.")
        return ImmediateHandle()

    @registry.register("dialogue_confirm_choice")
    def dialogue_confirm_choice(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Confirm the current dialogue choice selection when one is active."""
        handle = _find_dialogue_handle(getattr(context.command_runner, "active_handle", None))
        if handle is not None:
            handle.confirm_choice_selection()
        return ImmediateHandle()

    @registry.register("dialogue_cancel")
    def dialogue_cancel(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Cancel the current dialogue session when that session allows it."""
        handle = _find_dialogue_handle(getattr(context.command_runner, "active_handle", None))
        if handle is not None:
            handle.cancel()
        return ImmediateHandle()

    @registry.register("prepare_text_session")
    def prepare_text_session(
        context: CommandContext,
        *,
        entity_id: str,
        session_id: str,
        mode: str = "pages",
        dialogue_id: str | None = None,
        text: str | None = None,
        pages: list[str] | None = None,
        font_id: str = config.DEFAULT_DIALOGUE_FONT_ID,
        max_width: int | None = None,
        max_lines: int | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Prepare one reusable text session for later reads/advances."""
        if context.text_session_manager is None:
            raise ValueError("Cannot prepare text sessions without a text session manager.")

        resolved_entity_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_entity_id:
            logger.warning("prepare_text_session: skipping because entity_id resolved to blank.")
            return ImmediateHandle()

        resolved_text, resolved_pages, resolved_font_id, resolved_max_lines = _resolve_text_session_source(
            context,
            dialogue_id=dialogue_id,
            text=text,
            pages=pages,
            font_id=font_id,
            max_lines=max_lines,
        )
        dialogue_defaults = _get_project_dialogue_defaults(context)
        resolved_mode = str(mode).strip().lower()
        resolved_max_width = int(max_width) if max_width is not None else None
        if resolved_max_width is None or resolved_max_width <= 0:
            raise ValueError("prepare_text_session requires a positive max_width.")
        if resolved_mode == "pages":
            resolved_max_lines = int(
                resolved_max_lines
                if resolved_max_lines is not None
                else _get_dialogue_setting(dialogue_defaults, "max_lines", 2)
            )
        context.text_session_manager.prepare_session(
            resolved_entity_id,
            str(session_id),
            mode=resolved_mode,
            font_id=resolved_font_id,
            max_width=resolved_max_width,
            max_lines=resolved_max_lines,
            text=resolved_text,
            pages=resolved_pages,
        )
        return ImmediateHandle()

    @registry.register("read_text_session")
    def read_text_session(
        context: CommandContext,
        *,
        entity_id: str,
        session_id: str,
        store_text_var: str,
        store_has_more_var: str | None = None,
        store_position_var: str | None = None,
        store_total_var: str | None = None,
        scope: str = "entity",
        store_entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Read the current visible chunk from one prepared text session into vars."""
        if context.text_session_manager is None:
            raise ValueError("Cannot read text sessions without a text session manager.")

        resolved_entity_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_entity_id:
            logger.warning("read_text_session: skipping because entity_id resolved to blank.")
            return ImmediateHandle()

        resolved_store_entity_id = store_entity_id
        if scope == "entity":
            resolved_store_entity_id = _resolve_entity_id(
                store_entity_id or resolved_entity_id,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )
            if not resolved_store_entity_id:
                logger.warning("read_text_session: skipping because store_entity_id resolved to blank.")
                return ImmediateHandle()

        result = context.text_session_manager.read_session(
            resolved_entity_id,
            str(session_id),
        )
        _store_variable(
            context,
            scope=scope,
            entity_id=resolved_store_entity_id,
            name=store_text_var,
            value=result.text,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if store_has_more_var:
            _store_variable(
                context,
                scope=scope,
                entity_id=resolved_store_entity_id,
                name=store_has_more_var,
                value=result.has_more,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )
        if store_position_var:
            _store_variable(
                context,
                scope=scope,
                entity_id=resolved_store_entity_id,
                name=store_position_var,
                value=result.position,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )
        if store_total_var:
            _store_variable(
                context,
                scope=scope,
                entity_id=resolved_store_entity_id,
                name=store_total_var,
                value=result.total,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )
        return ImmediateHandle()

    @registry.register("advance_text_session")
    def advance_text_session(
        context: CommandContext,
        *,
        entity_id: str,
        session_id: str,
        amount: int = 1,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Advance one prepared text session to its next chunk/window."""
        if context.text_session_manager is None:
            raise ValueError("Cannot advance text sessions without a text session manager.")

        resolved_entity_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_entity_id:
            logger.warning("advance_text_session: skipping because entity_id resolved to blank.")
            return ImmediateHandle()

        context.text_session_manager.advance_session(
            resolved_entity_id,
            str(session_id),
            amount=int(amount),
        )
        return ImmediateHandle()

    @registry.register("reset_text_session")
    def reset_text_session(
        context: CommandContext,
        *,
        entity_id: str,
        session_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Reset one prepared text session back to its first chunk/window."""
        if context.text_session_manager is None:
            raise ValueError("Cannot reset text sessions without a text session manager.")

        resolved_entity_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_entity_id:
            logger.warning("reset_text_session: skipping because entity_id resolved to blank.")
            return ImmediateHandle()

        context.text_session_manager.reset_session(
            resolved_entity_id,
            str(session_id),
        )
        return ImmediateHandle()

    @registry.register("run_detached_commands")
    def run_detached_commands(
        context: CommandContext,
        *,
        commands: list[dict[str, Any]],
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Run a command list in the background without blocking the main lane."""
        if context.command_runner is None:
            raise ValueError("Cannot run detached commands without an active command runner.")
        handle = SequenceCommandHandle(
            registry,
            context,
            commands,
            base_params={
                **({"source_entity_id": source_entity_id} if source_entity_id is not None else {}),
                **({"actor_entity_id": actor_entity_id} if actor_entity_id is not None else {}),
                **({"caller_entity_id": caller_entity_id} if caller_entity_id is not None else {}),
            },
        )
        context.command_runner.spawn_background_handle(handle)
        return ImmediateHandle()

    @registry.register("run_commands")
    def run_commands(
        context: CommandContext,
        *,
        commands: list[dict[str, Any]] | dict[str, Any] | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Run an inline command list on the main lane."""
        if not commands:
            return ImmediateHandle()
        if isinstance(commands, dict):
            normalized_commands = [dict(commands)]
        elif isinstance(commands, list):
            normalized_commands = [dict(command) for command in commands]
        else:
            raise TypeError("run_commands requires a dict, list of dicts, or null.")
        return SequenceCommandHandle(
            registry,
            context,
            normalized_commands,
            base_params={
                **({"source_entity_id": source_entity_id} if source_entity_id is not None else {}),
                **({"actor_entity_id": actor_entity_id} if actor_entity_id is not None else {}),
                **({"caller_entity_id": caller_entity_id} if caller_entity_id is not None else {}),
            },
        )

    @registry.register("interact_facing")
    def interact_facing(
        context: CommandContext,
        *,
        entity_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Activate the first enabled interact target in front of an actor."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("interact_facing: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        target_entity = context.interaction_system.get_facing_target(resolved_id)
        if target_entity is None:
            return ImmediateHandle()
        interact_event = target_entity.get_event("interact")
        if (
            not target_entity.has_enabled_event("interact")
            or interact_event is None
            or not interact_event.commands
        ):
            return ImmediateHandle()
        return SequenceCommandHandle(
            registry,
            context,
            interact_event.commands,
            base_params={
                "source_entity_id": target_entity.entity_id,
                "actor_entity_id": resolved_id,
                **({"caller_entity_id": caller_entity_id} if caller_entity_id is not None else {}),
            },
        )

    @registry.register("run_event")
    def run_event(
        context: CommandContext,
        *,
        entity_id: str,
        event_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **event_parameters: Any,
    ) -> CommandHandle:
        """Execute a named event on a target entity when it is enabled."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("run_event: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot run event on missing entity '{resolved_id}'.")
        if not entity.present:
            return ImmediateHandle()
        event = entity.get_event(event_id)
        if not entity.has_enabled_event(event_id) or event is None or not event.commands:
            return ImmediateHandle()

        base_params: dict[str, Any] = dict(event_parameters)
        base_params["source_entity_id"] = resolved_id
        if actor_entity_id is not None:
            base_params["actor_entity_id"] = actor_entity_id
        if caller_entity_id is not None:
            base_params["caller_entity_id"] = caller_entity_id
        return SequenceCommandHandle(
            registry,
            context,
            event.commands,
            base_params=base_params,
        )

    @registry.register("run_named_command")
    def run_named_command(
        context: CommandContext,
        *,
        command_id: str,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **command_parameters: Any,
    ) -> CommandHandle:
        """Execute a reusable project-level command definition from the command library."""
        if context.project is None:
            raise ValueError("Cannot run a named command without an active project context.")

        resolved_command_id = str(command_id).strip()
        if not resolved_command_id:
            logger.warning("run_named_command: skipping because command_id resolved to blank.")
            return ImmediateHandle()

        if resolved_command_id in context.named_command_stack:
            stack_preview = " -> ".join([*context.named_command_stack, resolved_command_id])
            raise ValueError(f"Detected recursive named-command cycle: {stack_preview}")

        definition = load_named_command_definition(context.project, resolved_command_id)
        instantiated_commands = instantiate_named_command_commands(definition, command_parameters)
        if not instantiated_commands:
            return ImmediateHandle()

        base_params: dict[str, Any] = {}
        if source_entity_id is not None:
            base_params["source_entity_id"] = source_entity_id
        if actor_entity_id is not None:
            base_params["actor_entity_id"] = actor_entity_id
        if caller_entity_id is not None:
            base_params["caller_entity_id"] = caller_entity_id

        sequence_handle = SequenceCommandHandle(
            registry,
            context,
            instantiated_commands,
            base_params=base_params,
            auto_start=False,
        )
        if sequence_handle.complete:
            return ImmediateHandle()
        return NamedCommandHandle(context, resolved_command_id, sequence_handle)

    @registry.register("set_event_enabled")
    def set_event_enabled(
        context: CommandContext,
        *,
        entity_id: str,
        event_id: str,
        enabled: bool,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Enable or disable a named event on an entity."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("set_event_enabled: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot set event enabled state on missing entity '{resolved_id}'.")
        entity.set_event_enabled(event_id, enabled)
        if persistent:
            _persist_entity_event_enabled(
                context,
                entity_id=resolved_id,
                event_id=event_id,
                enabled=enabled,
                entity=entity,
            )
        return ImmediateHandle()

    @registry.register("set_events_enabled")
    def set_events_enabled(
        context: CommandContext,
        *,
        entity_id: str,
        enabled: bool,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Enable or disable all named events on an entity at once."""
        return _set_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="events_enabled",
            value=enabled,
            persistent=persistent,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )

    @registry.register("set_input_target")
    def set_input_target(
        context: CommandContext,
        *,
        action: str,
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Route one logical input action to a specific entity or clear it."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        ) if entity_id not in (None, "") else None
        context.world.set_input_target(str(action), resolved_id)
        return ImmediateHandle()

    @registry.register("set_entity_field")
    def set_entity_field(
        context: CommandContext,
        *,
        entity_id: str,
        field_name: str,
        value: Any,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Change one supported runtime field on an entity."""
        return _set_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name=field_name,
            value=value,
            persistent=persistent,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )

    @registry.register("route_inputs_to_entity")
    def route_inputs_to_entity(
        context: CommandContext,
        *,
        entity_id: str | None = None,
        actions: list[str] | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Route selected logical inputs, or all inputs, to one entity."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        ) if entity_id not in (None, "") else None
        if resolved_id in (None, ""):
            context.world.route_inputs_to_entity(None, actions=actions)
            return ImmediateHandle()
        context.world.route_inputs_to_entity(resolved_id, actions=actions)
        return ImmediateHandle()

    @registry.register("push_input_routes")
    def push_input_routes(
        context: CommandContext,
        *,
        actions: list[str] | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Remember the current routed targets for one set of logical inputs."""
        context.world.push_input_routes(actions=actions)
        return ImmediateHandle()

    @registry.register("pop_input_routes")
    def pop_input_routes(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Restore the last remembered routed targets for one set of logical inputs."""
        context.world.pop_input_routes()
        return ImmediateHandle()

    @registry.register("close_dialogue")
    def close_dialogue(
        context: CommandContext,
        *,
        _dialogue_handle: Any | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Close the current dialogue session before continuing later commands."""
        if _dialogue_handle is None or not hasattr(_dialogue_handle, "close_dialogue"):
            raise ValueError(
                "close_dialogue can only run inside an active dialogue command sequence."
            )
        _dialogue_handle.close_dialogue()
        return ImmediateHandle()

    @registry.register("set_input_event_name")
    def set_input_event_name(
        context: CommandContext,
        *,
        action: str,
        event_name: str,
        **_: Any,
    ) -> CommandHandle:
        """Change which event name the engine looks up for an input action."""
        if context.input_handler is None:
            raise ValueError("Cannot change input event names without an input handler.")
        context.input_handler.set_action_event_name(str(action), str(event_name))
        return ImmediateHandle()

    @registry.register("change_area")
    def change_area(
        context: CommandContext,
        *,
        area_id: str = "",
        entry_id: str | None = None,
        transfer_entity_id: str | None = None,
        transfer_entity_ids: list[str] | None = None,
        camera_follow_entity_id: str | None = None,
        camera_follow_input_action: str | None = None,
        camera_offset_x: int | float = 0,
        camera_offset_y: int | float = 0,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Queue a transition into another authored area once the command lane is idle."""
        if context.request_area_change is None:
            raise ValueError("Cannot change area without an active area-transition handler.")

        resolved_reference = str(area_id).strip()
        if not resolved_reference:
            raise ValueError("change_area requires a non-empty area_id.")

        if camera_follow_entity_id not in (None, "") and camera_follow_input_action not in (None, ""):
            raise ValueError(
                "change_area camera follow must target either one entity or one input action, not both."
            )

        resolved_transfer_ids: list[str] = []
        raw_transfer_ids = []
        if transfer_entity_id not in (None, ""):
            raw_transfer_ids.append(transfer_entity_id)
        raw_transfer_ids.extend(list(transfer_entity_ids or []))
        for raw_entity_id in raw_transfer_ids:
            resolved_entity_id = _resolve_entity_id(
                raw_entity_id,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )
            if not resolved_entity_id:
                logger.warning(
                    "change_area: skipping blank transfer entity reference %r.",
                    raw_entity_id,
                )
                continue
            if resolved_entity_id not in resolved_transfer_ids:
                resolved_transfer_ids.append(resolved_entity_id)

        camera_follow_request: CameraFollowRequest | None = None
        if camera_follow_entity_id not in (None, ""):
            resolved_camera_entity_id = _resolve_entity_id(
                camera_follow_entity_id,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )
            if resolved_camera_entity_id:
                camera_follow_request = CameraFollowRequest(
                    mode="entity",
                    entity_id=resolved_camera_entity_id,
                    offset_x=float(camera_offset_x),
                    offset_y=float(camera_offset_y),
                )
        elif camera_follow_input_action not in (None, ""):
            camera_follow_request = CameraFollowRequest(
                mode="input_target",
                input_action=str(camera_follow_input_action).strip(),
                offset_x=float(camera_offset_x),
                offset_y=float(camera_offset_y),
            )

        context.request_area_change(
            AreaTransitionRequest(
                area_id=resolved_reference,
                entry_id=str(entry_id).strip() or None,
                transfer_entity_ids=resolved_transfer_ids,
                camera_follow=camera_follow_request,
            )
        )
        return ImmediateHandle()

    @registry.register("new_game")
    def new_game(
        context: CommandContext,
        *,
        area_id: str = "",
        entry_id: str | None = None,
        camera_follow_entity_id: str | None = None,
        camera_follow_input_action: str | None = None,
        camera_offset_x: int | float = 0,
        camera_offset_y: int | float = 0,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Queue a fresh game session and transition into the requested area."""
        if context.request_new_game is None:
            raise ValueError("Cannot start a new game without an active session-reset handler.")

        resolved_reference = str(area_id).strip()
        if not resolved_reference:
            raise ValueError("new_game requires a non-empty area_id.")

        if camera_follow_entity_id not in (None, "") and camera_follow_input_action not in (None, ""):
            raise ValueError(
                "new_game camera follow must target either one entity or one input action, not both."
            )

        camera_follow_request: CameraFollowRequest | None = None
        if camera_follow_entity_id not in (None, ""):
            resolved_camera_entity_id = _resolve_entity_id(
                camera_follow_entity_id,
                source_entity_id=source_entity_id,
                actor_entity_id=actor_entity_id,
                caller_entity_id=caller_entity_id,
            )
            if resolved_camera_entity_id:
                camera_follow_request = CameraFollowRequest(
                    mode="entity",
                    entity_id=resolved_camera_entity_id,
                    offset_x=float(camera_offset_x),
                    offset_y=float(camera_offset_y),
                )
        elif camera_follow_input_action not in (None, ""):
            camera_follow_request = CameraFollowRequest(
                mode="input_target",
                input_action=str(camera_follow_input_action).strip(),
                offset_x=float(camera_offset_x),
                offset_y=float(camera_offset_y),
            )

        context.request_new_game(
            AreaTransitionRequest(
                area_id=resolved_reference,
                entry_id=str(entry_id).strip() or None,
                camera_follow=camera_follow_request,
            )
        )
        return ImmediateHandle()

    @registry.register("load_game")
    def load_game(
        context: CommandContext,
        *,
        save_path: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Queue a save-slot load, optionally targeting an explicit relative save path."""
        if context.request_load_game is None:
            raise ValueError("Cannot load a game without an active save-slot loader.")
        context.request_load_game(str(save_path) if save_path is not None else None)
        return ImmediateHandle()

    @registry.register("save_game")
    def save_game(
        context: CommandContext,
        *,
        save_path: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Open a save-slot dialog or write to an explicit relative save path."""
        if context.save_game is None:
            raise ValueError("Cannot save a game without an active save-slot writer.")
        context.save_game(str(save_path) if save_path is not None else None)
        return ImmediateHandle()

    @registry.register("quit_game")
    def quit_game(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Request that the runtime close the game window."""
        if context.request_quit is None:
            raise ValueError("Cannot quit the game without an active runtime quit handler.")
        context.request_quit()
        return ImmediateHandle()

    @registry.register("set_camera_follow_entity")
    def set_camera_follow_entity(
        context: CommandContext,
        *,
        entity_id: str,
        offset_x: int | float = 0,
        offset_y: int | float = 0,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Make the camera follow a specific entity."""
        if context.camera is None:
            raise ValueError("Cannot change camera follow without an active camera.")
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("set_camera_follow_entity: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        if context.world.get_entity(resolved_id) is None:
            raise KeyError(f"Cannot follow missing entity '{resolved_id}'.")
        context.camera.follow_entity(
            resolved_id,
            offset_x=float(offset_x),
            offset_y=float(offset_y),
        )
        context.camera.update(context.world, advance_tick=False)
        return ImmediateHandle()

    @registry.register("set_camera_follow_player")
    def set_camera_follow_player(
        context: CommandContext,
        *,
        offset_x: int | float = 0,
        offset_y: int | float = 0,
        **_: Any,
    ) -> CommandHandle:
        """Fail fast for the removed player-specific camera follow command."""
        raise ValueError(
            "set_camera_follow_player is removed; use 'set_camera_follow_entity' "
            "or 'set_camera_follow_input_target' instead."
        )

    @registry.register("set_camera_follow_input_target")
    def set_camera_follow_input_target(
        context: CommandContext,
        *,
        action: str,
        offset_x: int | float = 0,
        offset_y: int | float = 0,
        **_: Any,
    ) -> CommandHandle:
        """Make the camera follow whichever entity currently receives one logical input."""
        if context.camera is None:
            raise ValueError("Cannot change camera follow without an active camera.")
        context.camera.follow_input_target(
            str(action),
            offset_x=float(offset_x),
            offset_y=float(offset_y),
        )
        context.camera.update(context.world, advance_tick=False)
        return ImmediateHandle()

    @registry.register("clear_camera_follow")
    def clear_camera_follow(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Stop automatically following any entity."""
        if context.camera is None:
            raise ValueError("Cannot clear camera follow without an active camera.")
        context.camera.clear_follow()
        return ImmediateHandle()

    @registry.register("set_camera_bounds_rect")
    def set_camera_bounds_rect(
        context: CommandContext,
        *,
        x: int | float,
        y: int | float,
        width: int | float,
        height: int | float,
        space: str = "pixel",
        **_: Any,
    ) -> CommandHandle:
        """Clamp camera movement/follow to one rectangle in world or grid space."""
        if context.camera is None:
            raise ValueError("Cannot set camera bounds without an active camera.")
        if space not in {"pixel", "grid"}:
            raise ValueError(f"Unknown camera bounds space '{space}'.")
        scale = context.area.tile_size if space == "grid" else 1
        context.camera.set_bounds_rect(
            float(x) * scale,
            float(y) * scale,
            float(width) * scale,
            float(height) * scale,
        )
        context.camera.update(context.world, advance_tick=False)
        return ImmediateHandle()

    @registry.register("clear_camera_bounds")
    def clear_camera_bounds(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Remove any active camera bounds rectangle."""
        if context.camera is None:
            raise ValueError("Cannot clear camera bounds without an active camera.")
        context.camera.clear_bounds()
        context.camera.update(context.world, advance_tick=False)
        return ImmediateHandle()

    @registry.register("set_camera_deadzone")
    def set_camera_deadzone(
        context: CommandContext,
        *,
        x: int | float,
        y: int | float,
        width: int | float,
        height: int | float,
        space: str = "pixel",
        **_: Any,
    ) -> CommandHandle:
        """Keep followed targets inside one deadzone rectangle in viewport space."""
        if context.camera is None:
            raise ValueError("Cannot set a camera deadzone without an active camera.")
        if space not in {"pixel", "grid"}:
            raise ValueError(f"Unknown camera deadzone space '{space}'.")
        scale = context.area.tile_size if space == "grid" else 1
        context.camera.set_deadzone_rect(
            float(x) * scale,
            float(y) * scale,
            float(width) * scale,
            float(height) * scale,
        )
        context.camera.update(context.world, advance_tick=False)
        return ImmediateHandle()

    @registry.register("clear_camera_deadzone")
    def clear_camera_deadzone(
        context: CommandContext,
        **_: Any,
    ) -> CommandHandle:
        """Remove any active camera deadzone rectangle."""
        if context.camera is None:
            raise ValueError("Cannot clear a camera deadzone without an active camera.")
        context.camera.clear_deadzone()
        context.camera.update(context.world, advance_tick=False)
        return ImmediateHandle()

    @registry.register("set_var_from_camera")
    def set_var_from_camera(
        context: CommandContext,
        *,
        name: str,
        field: str,
        scope: str = "world",
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        persistent: bool = False,
        **_: Any,
    ) -> CommandHandle:
        """Copy one camera state field into a world/entity variable."""
        if context.camera is None:
            raise ValueError("Cannot read camera state without an active camera.")
        camera_state = context.camera.to_state_dict()
        camera_fields = {
            "mode": camera_state.get("follow_mode"),
            "follow_mode": camera_state.get("follow_mode"),
            "follow_entity_id": camera_state.get("follow_entity_id"),
            "follow_input_action": camera_state.get("follow_input_action"),
            "x": camera_state.get("x"),
            "y": camera_state.get("y"),
            "follow_offset_x": camera_state.get("follow_offset_x"),
            "follow_offset_y": camera_state.get("follow_offset_y"),
            "bounds": camera_state.get("bounds"),
            "deadzone": camera_state.get("deadzone"),
            "has_bounds": camera_state.get("bounds") is not None,
            "has_deadzone": camera_state.get("deadzone") is not None,
        }
        if field not in camera_fields:
            raise ValueError(f"Unknown camera field '{field}'.")
        value = copy.deepcopy(camera_fields[field])
        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        variables[name] = value
        if persistent and context.persistence_runtime is not None:
            if scope == "world":
                context.persistence_runtime.set_world_variable(name, value)
            else:
                if entity_id is None:
                    raise ValueError("Persistent camera variable set requires entity_id.")
                resolved_id = _resolve_entity_id(
                    entity_id,
                    source_entity_id=source_entity_id,
                    actor_entity_id=actor_entity_id,
                    caller_entity_id=caller_entity_id,
                )
                entity = context.world.get_entity(resolved_id)
                if entity is None:
                    raise KeyError(f"Cannot persist variable on missing entity '{resolved_id}'.")
                context.persistence_runtime.set_entity_variable(
                    resolved_id,
                    name,
                    value,
                    entity=entity,
                    tile_size=context.area.tile_size,
                )
        return ImmediateHandle()

    @registry.register("move_camera")
    def move_camera(
        context: CommandContext,
        *,
        x: int | float,
        y: int | float,
        space: str = "pixel",
        mode: str = "absolute",
        duration: float | None = None,
        frames_needed: int | None = None,
        speed_px_per_second: float | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Move the camera in pixel or grid space, absolute or relative."""
        if context.camera is None:
            raise ValueError("Cannot move camera without an active camera.")
        if space not in {"pixel", "grid"}:
            raise ValueError(f"Unknown camera movement space '{space}'.")
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown camera movement mode '{mode}'.")

        target_x = float(x)
        target_y = float(y)
        if space == "grid":
            target_x *= context.area.tile_size
            target_y *= context.area.tile_size
        if mode == "relative":
            target_x += context.camera.x
            target_y += context.camera.y

        context.camera.start_move_to(
            target_x,
            target_y,
            duration=duration,
            frames_needed=frames_needed,
            speed_px_per_second=speed_px_per_second,
        )
        if not context.camera.is_moving():
            return ImmediateHandle()
        return CameraCommandHandle(context)

    @registry.register("teleport_camera")
    def teleport_camera(
        context: CommandContext,
        *,
        x: int | float,
        y: int | float,
        space: str = "pixel",
        mode: str = "absolute",
        **_: Any,
    ) -> CommandHandle:
        """Move the camera instantly in pixel or grid space."""
        if context.camera is None:
            raise ValueError("Cannot teleport camera without an active camera.")
        if space not in {"pixel", "grid"}:
            raise ValueError(f"Unknown camera teleport space '{space}'.")
        if mode not in {"absolute", "relative"}:
            raise ValueError(f"Unknown camera teleport mode '{mode}'.")

        target_x = float(x)
        target_y = float(y)
        if space == "grid":
            target_x *= context.area.tile_size
            target_y *= context.area.tile_size
        if mode == "relative":
            target_x += context.camera.x
            target_y += context.camera.y

        context.camera.teleport_to(target_x, target_y)
        return ImmediateHandle()

    @registry.register("set_visible")
    def set_visible(
        context: CommandContext,
        *,
        entity_id: str,
        visible: bool,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Change whether an entity is rendered and targetable."""
        return _set_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="visible",
            value=visible,
            persistent=persistent,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )

    @registry.register("set_solid")
    def set_solid(
        context: CommandContext,
        *,
        entity_id: str,
        solid: bool,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Change whether an entity blocks movement."""
        return _set_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="solid",
            value=solid,
            persistent=persistent,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )

    @registry.register("set_present")
    def set_present(
        context: CommandContext,
        *,
        entity_id: str,
        present: bool,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Change whether an entity participates in the current scene."""
        return _set_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="present",
            value=present,
            persistent=persistent,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )

    @registry.register("set_color")
    def set_color(
        context: CommandContext,
        *,
        entity_id: str,
        color: list[int],
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Change an entity's debug-render color."""
        return _set_entity_field_handle(
            context,
            entity_id=entity_id,
            field_name="color",
            value=color,
            persistent=persistent,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )

    @registry.register("destroy_entity")
    def destroy_entity(
        context: CommandContext,
        *,
        entity_id: str,
        persistent: bool = False,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Destroy an entity instance completely."""
        resolved_id = _resolve_entity_id(
            entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        if not resolved_id:
            logger.warning("destroy_entity: skipping because entity_id resolved to blank.")
            return ImmediateHandle()
        entity = context.world.get_entity(resolved_id)
        if entity is None:
            raise KeyError(f"Cannot destroy missing entity '{resolved_id}'.")
        context.world.remove_entity(resolved_id)
        if persistent and context.persistence_runtime is not None:
            context.persistence_runtime.remove_entity(resolved_id, entity=entity)
        return ImmediateHandle()

    @registry.register("spawn_entity")
    def spawn_entity(
        context: CommandContext,
        *,
        entity: dict[str, Any] | None = None,
        entity_id: str | None = None,
        template: str | None = None,
        kind: str | None = None,
        x: int | None = None,
        y: int | None = None,
        parameters: dict[str, Any] | None = None,
        present: bool = True,
        persistent: bool = False,
        **_: Any,
    ) -> CommandHandle:
        """Create a new entity instance in the current world."""
        entity_data = copy.deepcopy(entity) if entity is not None else {}
        if not entity_data:
            if entity_id is None:
                raise ValueError("spawn_entity requires entity_id when no entity dict is provided.")
            if x is None or y is None:
                raise ValueError("spawn_entity requires x and y when no entity dict is provided.")
            entity_data = {
                "id": entity_id,
                "x": int(x),
                "y": int(y),
                "present": bool(present),
            }
            if template is not None:
                entity_data["template"] = template
            if kind is not None:
                entity_data["kind"] = kind
            if parameters:
                entity_data["parameters"] = copy.deepcopy(parameters)
        else:
            entity_data.setdefault("present", bool(present))

        new_entity_id = str(entity_data.get("id", "")).strip()
        if not new_entity_id:
            raise ValueError("spawn_entity requires an entity id.")
        if context.world.get_entity(new_entity_id) is not None:
            raise KeyError(f"Cannot spawn duplicate entity '{new_entity_id}'.")

        new_entity = instantiate_entity(
            entity_data,
            context.area.tile_size,
            project=context.project,
            source_name=f"spawned entity '{new_entity_id}'",
        )
        context.world.add_entity(new_entity)
        if persistent and context.persistence_runtime is not None:
            context.persistence_runtime.record_spawned_entity(
                new_entity,
                tile_size=context.area.tile_size,
            )
        return ImmediateHandle()

    @registry.register("set_var")
    def set_var(
        context: CommandContext,
        *,
        name: str,
        value: Any,
        scope: str = "entity",
        persistent: bool = False,
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Set a variable to a value in the given scope."""
        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        persisted_value = copy.deepcopy(value)
        variables[name] = persisted_value
        if persistent and context.persistence_runtime is not None:
            if scope == "world":
                context.persistence_runtime.set_world_variable(name, persisted_value)
            else:
                if entity_id is None:
                    raise ValueError("Persistent entity variable set requires entity_id.")
                resolved_id = _resolve_entity_id(
                    entity_id,
                    source_entity_id=source_entity_id,
                    actor_entity_id=actor_entity_id,
                    caller_entity_id=caller_entity_id,
                )
                entity = context.world.get_entity(resolved_id)
                if entity is None:
                    raise KeyError(f"Cannot persist variable on missing entity '{resolved_id}'.")
                context.persistence_runtime.set_entity_variable(
                    resolved_id,
                    name,
                    persisted_value,
                    entity=entity,
                    tile_size=context.area.tile_size,
                )
        return ImmediateHandle()

    @registry.register("increment_var")
    def increment_var(
        context: CommandContext,
        *,
        name: str,
        amount: int | float = 1,
        scope: str = "entity",
        persistent: bool = False,
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Add an amount to a numeric variable (defaults to 0 if missing)."""
        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        variables[name] = variables.get(name, 0) + amount
        if persistent and context.persistence_runtime is not None:
            if scope == "world":
                context.persistence_runtime.set_world_variable(name, variables[name])
            else:
                if entity_id is None:
                    raise ValueError("Persistent entity variable increment requires entity_id.")
                resolved_id = _resolve_entity_id(
                    entity_id,
                    source_entity_id=source_entity_id,
                    actor_entity_id=actor_entity_id,
                    caller_entity_id=caller_entity_id,
                )
                entity = context.world.get_entity(resolved_id)
                if entity is None:
                    raise KeyError(f"Cannot persist variable on missing entity '{resolved_id}'.")
                context.persistence_runtime.set_entity_variable(
                    resolved_id,
                    name,
                    variables[name],
                    entity=entity,
                    tile_size=context.area.tile_size,
                )
        return ImmediateHandle()

    @registry.register("set_var_length")
    def set_var_length(
        context: CommandContext,
        *,
        name: str,
        value: Any = None,
        scope: str = "entity",
        persistent: bool = False,
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Store the length of a collection-like value."""
        if value is None:
            length_value = 0
        else:
            try:
                length_value = len(value)
            except TypeError as exc:
                raise TypeError("set_var_length requires a sized value or null.") from exc

        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        variables[name] = length_value
        if persistent and context.persistence_runtime is not None:
            if scope == "world":
                context.persistence_runtime.set_world_variable(name, length_value)
            else:
                if entity_id is None:
                    raise ValueError("Persistent entity variable set requires entity_id.")
                resolved_id = _resolve_entity_id(
                    entity_id,
                    source_entity_id=source_entity_id,
                    actor_entity_id=actor_entity_id,
                    caller_entity_id=caller_entity_id,
                )
                entity = context.world.get_entity(resolved_id)
                if entity is None:
                    raise KeyError(f"Cannot persist variable on missing entity '{resolved_id}'.")
                context.persistence_runtime.set_entity_variable(
                    resolved_id,
                    name,
                    length_value,
                    entity=entity,
                    tile_size=context.area.tile_size,
                )
        return ImmediateHandle()

    @registry.register("set_var_from_collection_item")
    def set_var_from_collection_item(
        context: CommandContext,
        *,
        name: str,
        value: Any = None,
        index: int | None = None,
        key: str | None = None,
        default: Any = None,
        scope: str = "entity",
        persistent: bool = False,
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        **_: Any,
    ) -> CommandHandle:
        """Store one item from a list/tuple or dict into a variable."""
        extracted_value = copy.deepcopy(default)
        if key is not None:
            if value is None:
                extracted_value = copy.deepcopy(default)
            elif not isinstance(value, dict):
                raise TypeError("set_var_from_collection_item with key requires a dict value.")
            elif key in value:
                extracted_value = copy.deepcopy(value[key])
        else:
            if index is None:
                raise ValueError("set_var_from_collection_item requires either key or index.")
            if value is None:
                extracted_value = copy.deepcopy(default)
            elif not isinstance(value, (list, tuple)):
                raise TypeError("set_var_from_collection_item with index requires a list or tuple value.")
            else:
                resolved_index = int(index)
                if 0 <= resolved_index < len(value):
                    extracted_value = copy.deepcopy(value[resolved_index])

        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        variables[name] = extracted_value
        if persistent and context.persistence_runtime is not None:
            if scope == "world":
                context.persistence_runtime.set_world_variable(name, extracted_value)
            else:
                if entity_id is None:
                    raise ValueError("Persistent entity variable set requires entity_id.")
                resolved_id = _resolve_entity_id(
                    entity_id,
                    source_entity_id=source_entity_id,
                    actor_entity_id=actor_entity_id,
                    caller_entity_id=caller_entity_id,
                )
                entity = context.world.get_entity(resolved_id)
                if entity is None:
                    raise KeyError(f"Cannot persist variable on missing entity '{resolved_id}'.")
                context.persistence_runtime.set_entity_variable(
                    resolved_id,
                    name,
                    extracted_value,
                    entity=entity,
                    tile_size=context.area.tile_size,
                )
        return ImmediateHandle()

    @registry.register("check_var")
    def check_var(
        context: CommandContext,
        *,
        name: str,
        op: str = "eq",
        value: Any = None,
        scope: str = "entity",
        entity_id: str | None = None,
        source_entity_id: str | None = None,
        actor_entity_id: str | None = None,
        caller_entity_id: str | None = None,
        then: list[dict[str, Any]] | None = None,
        **kw: Any,
    ) -> CommandHandle:
        """Branch based on a variable condition."""
        variables = _resolve_variables(
            context,
            scope=scope,
            entity_id=entity_id,
            source_entity_id=source_entity_id,
            actor_entity_id=actor_entity_id,
            caller_entity_id=caller_entity_id,
        )
        current = variables.get(name)
        comparator = _COMPARE_OPS.get(op)
        if comparator is None:
            raise ValueError(f"Unknown comparison operator '{op}'.")
        condition_met = comparator(current, value)
        branch = then if condition_met else kw.get("else")
        if branch:
            base_params: dict[str, Any] = {}
            if source_entity_id is not None:
                base_params["source_entity_id"] = source_entity_id
            if actor_entity_id is not None:
                base_params["actor_entity_id"] = actor_entity_id
            if caller_entity_id is not None:
                base_params["caller_entity_id"] = caller_entity_id
            return SequenceCommandHandle(registry, context, branch, base_params=base_params)
        return ImmediateHandle()

    @registry.register("reset_transient_state")
    def reset_transient_state(
        context: CommandContext,
        *,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        apply: str = "immediate",
        **_: Any,
    ) -> CommandHandle:
        """Reset the current room against authored data plus persistent overrides."""
        if context.persistence_runtime is None:
            return ImmediateHandle()
        context.persistence_runtime.request_reset(
            kind="transient",
            apply=apply,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
        )
        return ImmediateHandle()

    @registry.register("reset_persistent_state")
    def reset_persistent_state(
        context: CommandContext,
        *,
        include_tags: list[str] | None = None,
        exclude_tags: list[str] | None = None,
        apply: str = "immediate",
        **_: Any,
    ) -> CommandHandle:
        """Clear persistent overrides for the current room or matching tagged entities."""
        if context.persistence_runtime is None:
            return ImmediateHandle()
        context.persistence_runtime.request_reset(
            kind="persistent",
            apply=apply,
            include_tags=include_tags,
            exclude_tags=exclude_tags,
        )
        return ImmediateHandle()
