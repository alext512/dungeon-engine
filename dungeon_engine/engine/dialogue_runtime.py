"""Engine-owned dialogue session runtime for the new canonical UI path."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from dungeon_engine.commands.context_types import DialogueRuntimeLike
from dungeon_engine.commands.runner import CommandContext, CommandHandle, SequenceCommandHandle
from dungeon_engine.json_io import json_data_path_candidates, load_json_data


def _normalize_command_list(commands: Any) -> list[dict[str, Any]]:
    """Return a normalized authored command list."""
    if commands in (None, ""):
        return []
    if isinstance(commands, dict):
        return [dict(commands)]
    if isinstance(commands, list):
        return [dict(command) for command in commands]
    raise TypeError("Dialogue command hooks must be a dict, list of dicts, or null.")


def _normalize_segment_hooks(segment_hooks: Any) -> list[Any]:
    """Return a normalized segment-hooks list."""
    if segment_hooks in (None, ""):
        return []
    if not isinstance(segment_hooks, list):
        raise TypeError("Dialogue segment_hooks must be a list or null.")
    return copy.deepcopy(segment_hooks)


class DialogueSessionWaitHandle(CommandHandle):
    """Wait until one specific dialogue session fully closes."""

    def __init__(self, runtime: DialogueRuntimeLike, session: "DialogueSession") -> None:
        super().__init__()
        self.runtime = runtime
        self.session = session
        self.update(0.0)

    def update(self, dt: float) -> None:
        """Complete once the tracked session is no longer live in the runtime."""
        _ = dt
        self.complete = not self.runtime.is_session_live(self.session)


@dataclass(slots=True)
class DialogueSession:
    """One active engine-owned dialogue session."""

    dialogue_path: str
    definition: dict[str, Any]
    ui_preset_name: str
    ui_preset: dict[str, Any]
    dialogue_on_start: list[dict[str, Any]]
    dialogue_on_end: list[dict[str, Any]]
    segment_hooks: list[Any]
    allow_cancel: bool
    actor_id: str | None
    caller_id: str | None
    segment_index: int = 0
    speaker_id: str | None = None
    current_segment: dict[str, Any] = field(default_factory=dict)
    current_segment_hook: dict[str, Any] = field(default_factory=dict)
    current_pages: list[str] = field(default_factory=list)
    page_index: int = 0
    current_options: list[dict[str, Any]] = field(default_factory=list)
    choice_index: int = 0
    choice_scroll_offset: int = 0
    choice_marquee_elapsed: float = 0.0
    advance_mode: str = "interact"
    advance_seconds: float = 0.0
    timer_remaining: float | None = None
    pending_handle: Any | None = None
    pending_on_complete: Callable[["DialogueSession"], None] | None = None
    closing: bool = False


class DialogueRuntime:
    """Own the active dialogue session, UI rendering, and modal input behavior."""

    PANEL_ELEMENT_ID = "engine_dialogue_panel"
    CHOICES_PANEL_ELEMENT_ID = "engine_dialogue_choices_panel"
    PORTRAIT_ELEMENT_ID = "engine_dialogue_portrait"
    TEXT_ELEMENT_ID = "engine_dialogue_text"
    MARQUEE_DELAY_SECONDS = 0.5
    MARQUEE_STEP_SECONDS = 0.18
    MARQUEE_GAP = "   "

    def __init__(
        self,
        *,
        project: Any,
        screen_manager: Any,
        text_renderer: Any,
        registry: Any,
        command_context: CommandContext,
    ) -> None:
        self.project = project
        self.screen_manager = screen_manager
        self.text_renderer = text_renderer
        self.registry = registry
        self.command_context = command_context
        self.current_session: DialogueSession | None = None
        self.session_stack: list[DialogueSession] = []
        self.option_element_ids = [f"engine_dialogue_option_{index}" for index in range(8)]

    def is_active(self) -> bool:
        """Return whether any dialogue session is currently open."""
        return self.current_session is not None

    def has_pending_work(self) -> bool:
        """Return whether any modal dialogue session is open or mid-command."""
        return self.current_session is not None or bool(self.session_stack)

    def is_session_live(self, session: DialogueSession) -> bool:
        """Return whether the provided session is still active or suspended on the stack."""
        if self.current_session is session:
            return True
        return any(stacked_session is session for stacked_session in self.session_stack)

    def handle_action(self, action_name: str) -> bool:
        """Consume one logical input action when a dialogue session is active."""
        session = self.current_session
        if session is None:
            return False

        action = str(action_name).strip()
        if not action:
            return False

        if session.pending_handle is not None:
            return True

        if action == "interact":
            if self._current_segment_type(session) == "choice":
                self._confirm_choice(session)
            else:
                self._advance_text_or_finish(session)
            return True

        if action == "menu":
            if session.allow_cancel:
                self.close_current_session()
            return True

        if action == "move_up":
            if self._current_segment_type(session) == "choice":
                self._move_choice_selection(session, delta=-1)
            return True

        if action == "move_down":
            if self._current_segment_type(session) == "choice":
                self._move_choice_selection(session, delta=1)
            return True

        if action in {"move_left", "move_right"}:
            return True

        return False

    def update(self, dt: float) -> None:
        """Advance the active session's pending commands and timer behavior."""
        session = self.current_session
        if session is None:
            return

        if session.pending_handle is not None:
            session.pending_handle.update(dt)
            if session.pending_handle.complete:
                callback = session.pending_on_complete
                session.pending_handle = None
                session.pending_on_complete = None
                if callback is not None:
                    callback(session)
            return

        if session.timer_remaining is not None and dt > 0:
            session.timer_remaining = max(0.0, float(session.timer_remaining) - float(dt))
            if session.timer_remaining > 0.0:
                self._update_choice_marquee(session, dt)
                return

            session.timer_remaining = None
            if self._current_segment_type(session) != "choice":
                self._advance_text_or_finish(session)
                return

        if dt > 0:
            self._update_choice_marquee(session, dt)
            return

    def open_session(
        self,
        *,
        dialogue_path: str,
        dialogue_on_start: Any = None,
        dialogue_on_end: Any = None,
        segment_hooks: Any = None,
        allow_cancel: bool = False,
        actor_id: str | None = None,
        caller_id: str | None = None,
        ui_preset_name: str | None = None,
    ) -> DialogueSession:
        """Open one dialogue session, pausing any active parent session."""
        resolved_dialogue_path = str(dialogue_path).strip()
        if not resolved_dialogue_path:
            raise ValueError("open_dialogue_session requires a non-empty dialogue_path.")

        if self.current_session is not None:
            self._clear_ui()
            self.session_stack.append(self.current_session)

        definition = self._load_dialogue_definition(resolved_dialogue_path)
        preset_name, preset = self._resolve_ui_preset(
            definition=definition,
            explicit_preset_name=ui_preset_name,
        )
        session = DialogueSession(
            dialogue_path=resolved_dialogue_path,
            definition=definition,
            ui_preset_name=preset_name,
            ui_preset=copy.deepcopy(preset),
            dialogue_on_start=_normalize_command_list(dialogue_on_start),
            dialogue_on_end=_normalize_command_list(dialogue_on_end),
            segment_hooks=_normalize_segment_hooks(segment_hooks),
            allow_cancel=bool(allow_cancel),
            actor_id=None if actor_id in (None, "") else str(actor_id),
            caller_id=None if caller_id in (None, "") else str(caller_id),
        )
        self.current_session = session
        self._run_command_list(
            session,
            session.dialogue_on_start,
            on_complete=lambda owner: self._show_current_segment(owner),
        )
        return session

    def close_current_session(self) -> None:
        """Close the current session, optionally resuming a paused parent session."""
        session = self.current_session
        if session is None:
            return
        if session.closing:
            return
        session.timer_remaining = None
        if session.pending_handle is not None:
            session.closing = True
            session.pending_on_complete = lambda owner: self._begin_close(owner)
            return
        self._begin_close(session)

    def _load_dialogue_definition(self, dialogue_path: str) -> dict[str, Any]:
        """Load one project-relative dialogue JSON file."""
        resolved_path = Path(dialogue_path)
        if not resolved_path.is_absolute():
            resolved_path = (self.project.project_root / resolved_path).resolve()
        if not resolved_path.exists():
            matches = [
                candidate.resolve()
                for candidate in json_data_path_candidates(resolved_path)
                if candidate.is_file()
            ]
            if len(matches) == 1:
                resolved_path = matches[0]
        definition = load_json_data(resolved_path)
        if not isinstance(definition, dict):
            raise ValueError(f"Dialogue file '{resolved_path}' must contain a JSON object.")
        return definition

    def _resolve_ui_preset(
        self,
        *,
        definition: dict[str, Any],
        explicit_preset_name: str | None,
    ) -> tuple[str, dict[str, Any]]:
        """Resolve one named dialogue UI preset with a compatibility fallback."""
        dialogue_ui = self.project.shared_variables.get("dialogue_ui", {})
        if isinstance(dialogue_ui, dict) and isinstance(dialogue_ui.get("presets"), dict):
            preset_name = (
                str(explicit_preset_name).strip()
                if explicit_preset_name not in (None, "")
                else str(definition.get("ui_preset", "")).strip()
            )
            if not preset_name:
                preset_name = str(dialogue_ui.get("default_preset", "standard")).strip() or "standard"
            presets = dict(dialogue_ui.get("presets", {}))
            preset = presets.get(preset_name)
            if not isinstance(preset, dict):
                raise KeyError(f"Unknown dialogue UI preset '{preset_name}'.")
            return preset_name, copy.deepcopy(preset)

        legacy_dialogue = self.project.shared_variables.get("dialogue", {})
        if isinstance(legacy_dialogue, dict) and legacy_dialogue:
            choice_rows = legacy_dialogue.get("choice_rows_y", [154, 164, 174])
            visible_rows = max(1, len(choice_rows)) if isinstance(choice_rows, list) else 3
            base_y = int(choice_rows[0]) if isinstance(choice_rows, list) and choice_rows else 154
            row_height = 10
            if isinstance(choice_rows, list) and len(choice_rows) >= 2:
                row_height = max(1, int(choice_rows[1]) - int(choice_rows[0]))
            preset = {
                "panel": {
                    "path": str(legacy_dialogue.get("panel_path", "assets/project/ui/dialogue_panel.png")),
                    "x": 0,
                    "y": 148,
                },
                "portrait_slot": {
                    "x": int(dict(legacy_dialogue.get("portrait_position", {})).get("x", 3)),
                    "y": int(dict(legacy_dialogue.get("portrait_position", {})).get("y", 151)),
                    "width": 38,
                    "height": 38,
                },
                "text": {
                    "plain": {
                        "x": int(dict(legacy_dialogue.get("plain_box", {})).get("x", 8)),
                        "y": int(dict(legacy_dialogue.get("plain_box", {})).get("y", 154)),
                        "width": int(dict(legacy_dialogue.get("plain_box", {})).get("width", 240)),
                        "max_lines": int(legacy_dialogue.get("max_lines", 3)),
                    },
                    "with_portrait": {
                        "x": int(dict(legacy_dialogue.get("portrait_box", {})).get("x", 56)),
                        "y": int(dict(legacy_dialogue.get("portrait_box", {})).get("y", 154)),
                        "width": int(dict(legacy_dialogue.get("portrait_box", {})).get("width", 192)),
                        "max_lines": int(legacy_dialogue.get("max_lines", 3)),
                    },
                },
                "choices": {
                    "mode": "inline",
                    "visible_rows": visible_rows,
                    "base_y": base_y,
                    "row_height": row_height,
                    "overflow": "marquee",
                    "plain": {
                        "x": int(dict(legacy_dialogue.get("plain_choice_box", {})).get("x", 8)),
                        "width": int(dict(legacy_dialogue.get("plain_choice_box", {})).get("width", 240)),
                    },
                    "with_portrait": {
                        "x": int(dict(legacy_dialogue.get("choice_box", {})).get("x", 56)),
                        "width": int(dict(legacy_dialogue.get("choice_box", {})).get("width", 188)),
                    },
                },
                "font_id": "pixelbet",
                "text_color": [245, 232, 190],
                "choice_text_color": [238, 242, 248],
                "ui_layer": 100,
                "text_layer": 101,
            }
            return "legacy_default", preset

        preset = {
            "panel": {
                "path": "assets/project/ui/dialogue_panel.png",
                "x": 0,
                "y": 148,
            },
            "portrait_slot": {
                "x": 3,
                "y": 151,
                "width": 38,
                "height": 38,
            },
            "text": {
                "plain": {"x": 8, "y": 154, "width": 240, "max_lines": 3},
                "with_portrait": {"x": 56, "y": 154, "width": 192, "max_lines": 3},
            },
            "choices": {
                "mode": "inline",
                "visible_rows": 3,
                "base_y": 154,
                "row_height": 10,
                "overflow": "marquee",
                "plain": {"x": 8, "width": 240},
                "with_portrait": {"x": 56, "width": 188},
            },
            "font_id": "pixelbet",
            "text_color": [245, 232, 190],
            "choice_text_color": [238, 242, 248],
            "ui_layer": 100,
            "text_layer": 101,
        }
        return "engine_default", preset

    def _show_current_segment(self, session: DialogueSession) -> None:
        """Prepare and render the current segment, or close at the end."""
        if self.current_session is not session:
            return

        segments = session.definition.get("segments", [])
        if not isinstance(segments, list) or session.segment_index >= len(segments):
            self._finalize_close(session)
            return

        session.current_segment = dict(segments[session.segment_index] or {})
        raw_segment_hook = {}
        if session.segment_index < len(session.segment_hooks):
            candidate_hook = session.segment_hooks[session.segment_index]
            if isinstance(candidate_hook, dict):
                raw_segment_hook = dict(candidate_hook)
        session.current_segment_hook = raw_segment_hook
        session.page_index = 0
        session.choice_index = 0
        session.choice_scroll_offset = 0
        session.choice_marquee_elapsed = 0.0
        session.timer_remaining = None
        session.closing = False

        speaker_marker = session.current_segment.get("speaker_id", "__inherit__")
        if speaker_marker != "__inherit__":
            session.speaker_id = None if speaker_marker in (None, "") else str(speaker_marker)

        session.current_options = [
            dict(option)
            for option in session.current_segment.get("options", [])
            if isinstance(option, dict)
        ]
        session.current_pages = self._build_segment_pages(session)
        advance = session.current_segment.get("advance", {})
        if not isinstance(advance, dict):
            advance = {}
        session.advance_mode = str(advance.get("mode", "interact")).strip() or "interact"
        session.advance_seconds = float(advance.get("seconds", 0.0) or 0.0)

        self._run_command_list(
            session,
            self._resolve_segment_hook_commands(session, "on_start"),
            on_complete=lambda owner: self._render_session(owner),
        )

    def _render_session(self, session: DialogueSession) -> None:
        """Render one prepared session state into screen-space elements."""
        if self.current_session is not session:
            return

        self._clear_ui()
        panel = dict(session.ui_preset.get("panel", {}))
        ui_layer = int(session.ui_preset.get("ui_layer", 100))
        text_layer = int(session.ui_preset.get("text_layer", 101))
        self.screen_manager.show_image(
            element_id=self.PANEL_ELEMENT_ID,
            asset_path=str(panel.get("path", "assets/project/ui/dialogue_panel.png")),
            x=float(panel.get("x", 0)),
            y=float(panel.get("y", 148)),
            layer=ui_layer,
        )

        has_portrait = self._render_portrait(session, layer=text_layer)
        text_box = self._select_text_box(session, has_portrait=has_portrait)
        text_to_render = self._current_page_text(session)
        if text_to_render:
            self.screen_manager.show_text(
                element_id=self.TEXT_ELEMENT_ID,
                text=text_to_render,
                x=float(text_box.get("x", 8)),
                y=float(text_box.get("y", 154)),
                layer=text_layer,
                color=tuple(int(channel) for channel in session.ui_preset.get("text_color", [245, 232, 190])),
                font_id=str(session.ui_preset.get("font_id", "pixelbet")),
                max_width=int(text_box.get("width", 240)),
            )

        if self._current_segment_type(session) == "choice":
            self._render_choices(session, has_portrait=has_portrait, layer=text_layer)

        if session.advance_mode in {"timer", "interact_or_timer"} and session.advance_seconds > 0:
            if session.timer_remaining is None:
                session.timer_remaining = float(session.advance_seconds)

    def _render_portrait(self, session: DialogueSession, *, layer: int) -> bool:
        """Render the current participant portrait when the preset and segment allow it."""
        portrait = self._resolve_current_portrait(session)
        if portrait is None:
            return False
        portrait_slot = dict(session.ui_preset.get("portrait_slot", {}))
        self.screen_manager.show_image(
            element_id=self.PORTRAIT_ELEMENT_ID,
            asset_path=str(portrait.get("path")),
            x=float(portrait_slot.get("x", 3)),
            y=float(portrait_slot.get("y", 151)),
            frame_width=int(portrait.get("frame_width", portrait_slot.get("width", 38))),
            frame_height=int(portrait.get("frame_height", portrait_slot.get("height", 38))),
            frame=int(portrait.get("frame", 0)),
            layer=layer,
        )
        return True

    def _render_choices(self, session: DialogueSession, *, has_portrait: bool, layer: int) -> None:
        """Render the current choice window."""
        layout = self._resolve_choice_layout(session, has_portrait=has_portrait)
        if layout["mode"] == "separate_panel":
            panel = dict(layout.get("panel", {}))
            panel_path = str(panel.get("path", "")).strip()
            if panel_path:
                self.screen_manager.show_image(
                    element_id=self.CHOICES_PANEL_ELEMENT_ID,
                    asset_path=panel_path,
                    x=float(panel.get("x", 0)),
                    y=float(panel.get("y", 0)),
                    layer=int(panel.get("layer", session.ui_preset.get("ui_layer", 100))),
                )
        else:
            self.screen_manager.remove(self.CHOICES_PANEL_ELEMENT_ID)

        visible_rows = int(layout["visible_rows"])
        base_y = float(layout["y"])
        row_height = float(layout["row_height"])
        choice_color = tuple(int(channel) for channel in session.ui_preset.get("choice_text_color", [238, 242, 248]))
        font_id = str(session.ui_preset.get("font_id", "pixelbet"))
        max_width = int(layout["width"])
        overflow = str(layout["overflow"])

        for element_id in self.option_element_ids:
            self.screen_manager.remove(element_id)

        window = session.current_options[
            session.choice_scroll_offset:session.choice_scroll_offset + visible_rows
        ]
        for row_index, option in enumerate(window):
            absolute_index = session.choice_scroll_offset + row_index
            is_selected = absolute_index == session.choice_index
            option_text, option_max_width = self._format_choice_text(
                session,
                option_text=str(option.get("text", "")),
                selected=is_selected,
                overflow=overflow,
                max_width=max_width,
                font_id=font_id,
            )
            self.screen_manager.show_text(
                element_id=self.option_element_ids[row_index],
                text=option_text,
                x=float(layout["x"]),
                y=base_y + (row_index * row_height),
                layer=layer,
                color=choice_color,
                font_id=font_id,
                max_width=option_max_width,
            )

    def _current_segment_type(self, session: DialogueSession) -> str:
        """Return the normalized type for the current segment."""
        return str(session.current_segment.get("type", "text")).strip() or "text"

    def _current_page_text(self, session: DialogueSession) -> str:
        """Return the visible text for the current page when any exists."""
        if not session.current_pages:
            return ""
        page_index = min(max(int(session.page_index), 0), len(session.current_pages) - 1)
        return str(session.current_pages[page_index])

    def _build_segment_pages(self, session: DialogueSession) -> list[str]:
        """Build paginated text pages for the current segment."""
        segment = session.current_segment
        explicit_pages = segment.get("pages")
        if isinstance(explicit_pages, list) and explicit_pages:
            return [str(page) for page in explicit_pages]

        raw_text = segment.get("text", "")
        text = "" if raw_text is None else str(raw_text)
        if not text:
            return []

        text_box = self._select_text_box(
            session,
            has_portrait=self._resolve_current_portrait(session) is not None,
        )
        return self.text_renderer.paginate_text(
            text,
            int(text_box.get("width", 240)),
            int(text_box.get("max_lines", 3)),
            font_id=str(session.ui_preset.get("font_id", "pixelbet")),
        )

    def _select_text_box(self, session: DialogueSession, *, has_portrait: bool) -> dict[str, Any]:
        """Return the active text box layout."""
        text = dict(session.ui_preset.get("text", {}))
        return dict(text.get("with_portrait" if has_portrait else "plain", {}))

    def _resolve_current_portrait(self, session: DialogueSession) -> dict[str, Any] | None:
        """Return the current participant portrait payload when it should be shown."""
        explicit_portrait = session.current_segment.get("portrait")
        if isinstance(explicit_portrait, dict):
            portrait_path = str(explicit_portrait.get("path", "")).strip()
            if portrait_path:
                return {
                    "path": portrait_path,
                    "frame_width": int(explicit_portrait.get("frame_width", 38)),
                    "frame_height": int(explicit_portrait.get("frame_height", 38)),
                    "frame": int(explicit_portrait.get("frame", 0)),
                }

        show_portrait = session.current_segment.get("show_portrait", "__unset__")
        if show_portrait is False:
            return None
        speaker_id = session.speaker_id
        if speaker_id in (None, ""):
            return None
        participants = session.definition.get("participants", {})
        if not isinstance(participants, dict):
            return None
        participant = participants.get(str(speaker_id))
        if not isinstance(participant, dict):
            return None
        portrait_path = str(participant.get("portrait_path", "")).strip()
        if not portrait_path:
            return None
        return {
            "path": portrait_path,
            "frame_width": int(participant.get("portrait_frame_width", 38)),
            "frame_height": int(participant.get("portrait_frame_height", 38)),
            "frame": int(participant.get("portrait_frame", 0)),
        }

    def _move_choice_selection(self, session: DialogueSession, *, delta: int) -> None:
        """Move the current choice cursor and rerender the option window."""
        option_count = len(session.current_options)
        if option_count <= 0:
            return
        next_index = max(0, min(option_count - 1, session.choice_index + int(delta)))
        if next_index == session.choice_index:
            return
        session.choice_index = next_index
        session.choice_marquee_elapsed = 0.0
        visible_rows = max(1, int(dict(session.ui_preset.get("choices", {})).get("visible_rows", 3)))
        if session.choice_index < session.choice_scroll_offset:
            session.choice_scroll_offset = session.choice_index
        elif session.choice_index >= session.choice_scroll_offset + visible_rows:
            session.choice_scroll_offset = session.choice_index - visible_rows + 1
        self._render_session(session)

    def _advance_text_or_finish(self, session: DialogueSession) -> None:
        """Advance to the next page or finish the current segment."""
        if self.current_session is not session:
            return
        session.timer_remaining = None
        if session.current_pages and session.page_index < len(session.current_pages) - 1:
            session.page_index += 1
            self._render_session(session)
            return
        self._finish_segment(session)

    def _confirm_choice(self, session: DialogueSession) -> None:
        """Execute the selected option's commands, then finish the segment."""
        if self.current_session is not session:
            return
        if not session.current_options:
            self._finish_segment(session)
            return

        option = dict(session.current_options[session.choice_index])
        option_id = str(option.get("option_id", "")).strip()
        commands = self._resolve_option_commands(session, option_id=option_id)
        runtime_params: dict[str, Any] = {
            "selected_option_id": option_id,
            "selected_option_index": int(session.choice_index),
        }
        self._run_command_list(
            session,
            commands,
            on_complete=lambda owner: self._finish_segment(owner),
            extra_runtime_params=runtime_params,
        )

    def _finish_segment(self, session: DialogueSession) -> None:
        """Run end hooks, then advance to the next segment or close the session."""
        if self.current_session is not session:
            return
        session.timer_remaining = None
        self._run_command_list(
            session,
            self._resolve_segment_hook_commands(session, "on_end"),
            on_complete=lambda owner: self._advance_segment(owner),
        )

    def _advance_segment(self, session: DialogueSession) -> None:
        """Move to the next segment or close the dialogue at the end."""
        if self.current_session is not session:
            return
        session.segment_index += 1
        segments = session.definition.get("segments", [])
        if not isinstance(segments, list) or session.segment_index >= len(segments):
            self.close_current_session()
            return
        self._show_current_segment(session)

    def _finalize_close(self, session: DialogueSession) -> None:
        """Finalize one close request, optionally resuming a parent session."""
        if self.current_session is not session:
            return
        self._clear_ui()
        if self.session_stack:
            self.current_session = self.session_stack.pop()
            self._render_session(self.current_session)
            return
        self.current_session = None

    def _begin_close(self, session: DialogueSession) -> None:
        """Run one session's close hooks exactly once before finalizing."""
        if self.current_session is not session:
            return
        session.closing = True
        self._run_command_list(
            session,
            session.dialogue_on_end,
            on_complete=lambda owner: self._finalize_close(owner),
        )

    def _resolve_segment_hook_commands(self, session: DialogueSession, hook_name: str) -> list[dict[str, Any]]:
        """Resolve one segment command list using caller hooks over inline defaults."""
        if hook_name in session.current_segment_hook:
            return _normalize_command_list(session.current_segment_hook.get(hook_name))
        return _normalize_command_list(session.current_segment.get(hook_name))

    def _resolve_option_commands(self, session: DialogueSession, *, option_id: str) -> list[dict[str, Any]]:
        """Resolve one option command list using caller hooks over inline defaults."""
        by_id = session.current_segment_hook.get("option_commands_by_id", {})
        if isinstance(by_id, dict) and option_id and option_id in by_id:
            return _normalize_command_list(by_id.get(option_id))

        by_index = session.current_segment_hook.get("option_commands", [])
        if isinstance(by_index, list) and session.choice_index < len(by_index):
            return _normalize_command_list(by_index[session.choice_index])

        option = dict(session.current_options[session.choice_index])
        return _normalize_command_list(option.get("commands"))

    def _run_command_list(
        self,
        session: DialogueSession,
        commands: Any,
        *,
        on_complete: Callable[[DialogueSession], None],
        extra_runtime_params: dict[str, Any] | None = None,
    ) -> None:
        """Run authored commands on behalf of the active dialogue session."""
        normalized_commands = _normalize_command_list(commands)
        if not normalized_commands:
            on_complete(session)
            return

        base_params: dict[str, Any] = {}
        source_entity_id = session.caller_id or session.actor_id
        if source_entity_id:
            base_params["source_entity_id"] = source_entity_id
        entity_refs: dict[str, str] = {}
        if session.actor_id:
            entity_refs["instigator"] = session.actor_id
        if session.caller_id:
            entity_refs["caller"] = session.caller_id
        if entity_refs:
            base_params["entity_refs"] = entity_refs
        if extra_runtime_params:
            base_params.update(copy.deepcopy(extra_runtime_params))

        handle = SequenceCommandHandle(
            self.registry,
            self.command_context,
            normalized_commands,
            base_params=base_params,
        )
        if handle.complete:
            on_complete(session)
            return
        session.pending_handle = handle
        session.pending_on_complete = on_complete

    def _clear_ui(self) -> None:
        """Remove all engine-owned dialogue UI elements."""
        self.screen_manager.remove(self.PANEL_ELEMENT_ID)
        self.screen_manager.remove(self.CHOICES_PANEL_ELEMENT_ID)
        self.screen_manager.remove(self.PORTRAIT_ELEMENT_ID)
        self.screen_manager.remove(self.TEXT_ELEMENT_ID)
        for element_id in self.option_element_ids:
            self.screen_manager.remove(element_id)

    def _resolve_choice_layout(self, session: DialogueSession, *, has_portrait: bool) -> dict[str, Any]:
        """Return the active choice-layout configuration for the current preset."""
        choices = dict(session.ui_preset.get("choices", {}))
        mode = str(choices.get("mode", "inline")).strip() or "inline"
        overflow = str(choices.get("overflow", "clip")).strip() or "clip"
        visible_rows = max(1, int(choices.get("visible_rows", 3)))
        row_height = max(1.0, float(choices.get("row_height", 10)))

        if mode == "separate_panel":
            panel = dict(choices.get("panel", {}))
            return {
                "mode": "separate_panel",
                "overflow": overflow,
                "visible_rows": visible_rows,
                "row_height": row_height,
                "x": float(choices.get("x", panel.get("x", 8))),
                "y": float(choices.get("y", choices.get("base_y", panel.get("y", 154)))),
                "width": max(1, int(choices.get("width", panel.get("width", 240)))),
                "panel": panel,
            }

        choice_box = dict(choices.get("with_portrait" if has_portrait else "plain", {}))
        return {
            "mode": "inline",
            "overflow": overflow,
            "visible_rows": visible_rows,
            "row_height": row_height,
            "x": float(choice_box.get("x", choices.get("x", 56 if has_portrait else 8))),
            "y": float(choices.get("y", choices.get("base_y", 154))),
            "width": max(1, int(choice_box.get("width", choices.get("width", 188 if has_portrait else 240)))),
            "panel": {},
        }

    def _format_choice_text(
        self,
        session: DialogueSession,
        *,
        option_text: str,
        selected: bool,
        overflow: str,
        max_width: int,
        font_id: str,
    ) -> tuple[str, int | None]:
        """Return one rendered choice row text plus the screen-element max_width policy."""
        prefix = ">" if selected else ""
        if overflow == "wrap":
            return f"{prefix}{option_text}", max_width
        if selected and overflow == "marquee" and self._text_overflows(prefix, option_text, max_width, font_id):
            return self._marquee_text(prefix, option_text, max_width, font_id, session.choice_marquee_elapsed), None
        return self._clip_text(prefix, option_text, max_width, font_id), None

    def _update_choice_marquee(self, session: DialogueSession, dt: float) -> None:
        """Advance the selected-option marquee when the preset requests it."""
        if dt <= 0 or self._current_segment_type(session) != "choice" or not session.current_options:
            return
        layout = self._resolve_choice_layout(
            session,
            has_portrait=self._resolve_current_portrait(session) is not None,
        )
        if str(layout.get("overflow")) != "marquee":
            return
        option = dict(session.current_options[session.choice_index])
        if not self._text_overflows(">", str(option.get("text", "")), int(layout["width"]), str(session.ui_preset.get("font_id", "pixelbet"))):
            return
        previous_step = self._marquee_step(session.choice_marquee_elapsed)
        session.choice_marquee_elapsed += float(dt)
        if self._marquee_step(session.choice_marquee_elapsed) == previous_step:
            return
        self._render_choices(
            session,
            has_portrait=self._resolve_current_portrait(session) is not None,
            layer=int(session.ui_preset.get("text_layer", 101)),
        )

    def _marquee_step(self, elapsed_seconds: float) -> int:
        """Return the current integer marquee offset step for one elapsed duration."""
        if elapsed_seconds < self.MARQUEE_DELAY_SECONDS:
            return 0
        return max(0, int((elapsed_seconds - self.MARQUEE_DELAY_SECONDS) / self.MARQUEE_STEP_SECONDS) + 1)

    def _text_overflows(self, prefix: str, text: str, max_width: int, font_id: str) -> bool:
        """Return whether one prefixed option text would overflow the available width."""
        measured_width, _ = self.text_renderer.measure_text(f"{prefix}{text}", font_id=font_id)
        return measured_width > max(0, int(max_width))

    def _clip_text(self, prefix: str, text: str, max_width: int, font_id: str) -> str:
        """Return the longest prefix+text slice that fits inside the width budget."""
        max_width = max(0, int(max_width))
        clipped = ""
        if self.text_renderer.measure_text(prefix, font_id=font_id)[0] > max_width:
            return prefix
        for character in str(text):
            candidate = clipped + character
            if self.text_renderer.measure_text(f"{prefix}{candidate}", font_id=font_id)[0] > max_width:
                break
            clipped = candidate
        return f"{prefix}{clipped}"

    def _marquee_text(
        self,
        prefix: str,
        text: str,
        max_width: int,
        font_id: str,
        elapsed_seconds: float,
    ) -> str:
        """Return one clipped marquee slice for the selected option."""
        max_width = max(0, int(max_width))
        if elapsed_seconds < self.MARQUEE_DELAY_SECONDS:
            return self._clip_text(prefix, text, max_width, font_id)
        scroll_source = f"{text}{self.MARQUEE_GAP}"
        if not scroll_source.strip():
            return prefix
        step = self._marquee_step(elapsed_seconds)
        start = step % len(scroll_source)
        rotated = f"{scroll_source[start:]}{scroll_source[:start]}"
        return self._clip_text(prefix, rotated, max_width, font_id)
