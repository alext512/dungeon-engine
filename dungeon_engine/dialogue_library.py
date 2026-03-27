"""Project-level reusable JSON dialogue definitions."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from dungeon_engine.logging_utils import get_logger

if TYPE_CHECKING:
    from dungeon_engine.project import ProjectContext


logger = get_logger(__name__)


@dataclass(slots=True)
class DialogueParticipant:
    """One named participant that a dialogue segment can point at."""

    participant_id: str
    name: str
    portrait_path: str
    portrait_frame_width: int | None
    portrait_frame_height: int | None
    portrait_frame: int


@dataclass(slots=True)
class DialogueOption:
    """One selectable option within a choice segment."""

    text: str
    option_id: str | None


@dataclass(slots=True)
class DialogueSegment:
    """One authored dialogue beat that may span multiple wrapped display pages."""

    segment_type: Literal["text", "choice"]
    text: str | None
    pages: list[str] | None
    options: list[DialogueOption]
    speaker_behavior: Literal["inherit", "explicit"]
    speaker_id: str | None
    show_portrait: bool | None
    advance_mode: Literal["interact", "timer", "interact_or_timer"]
    advance_seconds: float | None


@dataclass(slots=True)
class DialogueDefinition:
    """A reusable JSON-authored dialogue asset."""

    dialogue_id: str
    participants: dict[str, DialogueParticipant]
    segments: list[DialogueSegment]
    font_id: str | None
    max_lines: int | None
    text_color: tuple[int, int, int] | None
    source_path: Path
    raw_data: dict[str, Any]


_DIALOGUE_CACHE: dict[Path, dict[str, Any]] = {}


class DialogueValidationError(ValueError):
    """Raised when project dialogue content fails startup validation."""

    def __init__(self, project_root: Path, issues: list[str]) -> None:
        self.project_root = project_root
        self.issues = list(issues)
        super().__init__(
            f"Dialogue validation failed for '{project_root}' with {len(self.issues)} issue(s)."
        )

    def format_user_message(self, *, max_issues: int = 8) -> str:
        """Return a short user-facing validation summary."""
        shown_issues = self.issues[:max_issues]
        lines = [
            f"Project dialogue validation failed with {len(self.issues)} issue(s).",
            "See logs/error.log for full details.",
            "",
            "First issues:",
        ]
        lines.extend(f"- {issue}" for issue in shown_issues)
        hidden_count = len(self.issues) - len(shown_issues)
        if hidden_count > 0:
            lines.append(f"- ...and {hidden_count} more")
        return "\n".join(lines)


def load_dialogue_definition(
    project: ProjectContext,
    dialogue_id: str,
) -> DialogueDefinition:
    """Load and validate a project-level dialogue definition by id."""
    dialogue_path = project.find_dialogue_definition(dialogue_id)
    if dialogue_path is None:
        raise FileNotFoundError(
            f"Missing dialogue definition '{dialogue_id}' in project '{project.project_root}'."
        )

    cached = _DIALOGUE_CACHE.get(dialogue_path)
    if cached is None:
        cached = json.loads(dialogue_path.read_text(encoding="utf-8"))
        _DIALOGUE_CACHE[dialogue_path] = cached
    raw = copy.deepcopy(cached)

    if not isinstance(raw, dict):
        raise ValueError(f"Dialogue definition '{dialogue_id}' must be a JSON object.")

    expected_id = project.dialogue_definition_id(dialogue_path)
    if "id" in raw:
        raise ValueError(
            f"Dialogue definition '{expected_id}' must not declare 'id'; dialogue ids are path-derived."
        )
    resolved_id = expected_id

    participants = _parse_dialogue_participants(raw, resolved_id)
    segments = _parse_dialogue_segments(raw, resolved_id, participants)
    font_id = _parse_optional_string(raw.get("font_id"), field_name="font_id", dialogue_id=resolved_id)
    max_lines = _parse_optional_int(raw.get("max_lines"), field_name="max_lines", dialogue_id=resolved_id)
    text_color = _parse_optional_color(raw.get("text_color"), field_name="text_color", dialogue_id=resolved_id)

    return DialogueDefinition(
        dialogue_id=resolved_id,
        participants=participants,
        segments=segments,
        font_id=font_id,
        max_lines=max_lines,
        text_color=text_color,
        source_path=dialogue_path,
        raw_data=raw,
    )


def _parse_dialogue_participants(
    raw_dialogue: dict[str, Any],
    dialogue_id: str,
) -> dict[str, DialogueParticipant]:
    """Parse the optional participant map for a dialogue asset."""
    raw_participants = raw_dialogue.get("participants", {})
    if raw_participants is None:
        raw_participants = {}
    if not isinstance(raw_participants, dict):
        raise ValueError(f"Dialogue definition '{dialogue_id}' must use an object for 'participants'.")

    participants: dict[str, DialogueParticipant] = {}
    for participant_id, raw_participant in raw_participants.items():
        resolved_participant_id = str(participant_id).strip()
        if not resolved_participant_id:
            raise ValueError(f"Dialogue definition '{dialogue_id}' cannot use a blank participant id.")
        if not isinstance(raw_participant, dict):
            raise ValueError(
                f"Dialogue definition '{dialogue_id}' participant '{resolved_participant_id}' must be an object."
            )

        participants[resolved_participant_id] = DialogueParticipant(
            participant_id=resolved_participant_id,
            name=_parse_optional_string(
                raw_participant.get("name"),
                field_name=f"participants.{resolved_participant_id}.name",
                dialogue_id=dialogue_id,
            )
            or "",
            portrait_path=_parse_optional_string(
                raw_participant.get("portrait_path"),
                field_name=f"participants.{resolved_participant_id}.portrait_path",
                dialogue_id=dialogue_id,
            )
            or "",
            portrait_frame_width=_parse_optional_int(
                raw_participant.get("portrait_frame_width"),
                field_name=f"participants.{resolved_participant_id}.portrait_frame_width",
                dialogue_id=dialogue_id,
            ),
            portrait_frame_height=_parse_optional_int(
                raw_participant.get("portrait_frame_height"),
                field_name=f"participants.{resolved_participant_id}.portrait_frame_height",
                dialogue_id=dialogue_id,
            ),
            portrait_frame=int(raw_participant.get("portrait_frame", 0)),
        )

    return participants


def _parse_dialogue_segments(
    raw_dialogue: dict[str, Any],
    dialogue_id: str,
    participants: dict[str, DialogueParticipant],
) -> list[DialogueSegment]:
    """Parse and validate the authored segment list."""
    raw_segments = raw_dialogue.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValueError(f"Dialogue definition '{dialogue_id}' must define a non-empty 'segments' list.")

    segments: list[DialogueSegment] = []
    for segment_index, raw_segment in enumerate(raw_segments):
        if not isinstance(raw_segment, dict):
            raise ValueError(
                f"Dialogue definition '{dialogue_id}' segment {segment_index} must be an object."
            )

        raw_segment_type = str(raw_segment.get("type", "text")).strip().lower()
        if raw_segment_type not in {"text", "choice"}:
            raise ValueError(
                f"Dialogue definition '{dialogue_id}' segment {segment_index} has unknown type '{raw_segment_type}'."
            )

        raw_text = raw_segment.get("text")
        raw_pages = raw_segment.get("pages")
        if raw_text is not None and not isinstance(raw_text, str):
            raise ValueError(
                f"Dialogue definition '{dialogue_id}' segment {segment_index} must use a string for 'text'."
            )
        if raw_pages is not None:
            if not isinstance(raw_pages, list) or not raw_pages or not all(isinstance(page, str) for page in raw_pages):
                raise ValueError(
                    f"Dialogue definition '{dialogue_id}' segment {segment_index} must use a non-empty list of strings for 'pages'."
                )
        if raw_text is not None and raw_pages is not None:
            raise ValueError(
                f"Dialogue definition '{dialogue_id}' segment {segment_index} cannot define both 'text' and 'pages'."
            )

        options = _parse_dialogue_segment_options(raw_segment, dialogue_id, segment_index)
        if raw_segment_type == "text":
            if raw_text is None and raw_pages is None:
                raise ValueError(
                    f"Dialogue definition '{dialogue_id}' text segment {segment_index} must define 'text' or 'pages'."
                )
            if options:
                raise ValueError(
                    f"Dialogue definition '{dialogue_id}' text segment {segment_index} cannot define 'options'."
                )
        else:
            if not options:
                raise ValueError(
                    f"Dialogue definition '{dialogue_id}' choice segment {segment_index} must define a non-empty 'options' list."
                )

        speaker_behavior: Literal["inherit", "explicit"] = "inherit"
        speaker_id: str | None = None
        if "speaker_id" in raw_segment:
            speaker_behavior = "explicit"
            raw_speaker_id = raw_segment.get("speaker_id")
            if raw_speaker_id is None:
                speaker_id = None
            elif isinstance(raw_speaker_id, str) and raw_speaker_id.strip():
                speaker_id = str(raw_speaker_id).strip()
            else:
                raise ValueError(
                    f"Dialogue definition '{dialogue_id}' segment {segment_index} must use a non-empty string or null for 'speaker_id'."
                )
            if speaker_id is not None and speaker_id not in participants:
                raise ValueError(
                    f"Dialogue definition '{dialogue_id}' segment {segment_index} references unknown participant '{speaker_id}'."
                )

        raw_show_portrait = raw_segment.get("show_portrait")
        if raw_show_portrait is not None and not isinstance(raw_show_portrait, bool):
            raise ValueError(
                f"Dialogue definition '{dialogue_id}' segment {segment_index} must use a boolean for 'show_portrait'."
            )

        advance_mode, advance_seconds = _parse_dialogue_segment_advance(
            raw_segment,
            dialogue_id=dialogue_id,
            segment_index=segment_index,
            segment_type=raw_segment_type,
        )

        segments.append(
            DialogueSegment(
                segment_type=raw_segment_type,  # type: ignore[arg-type]
                text=str(raw_text) if raw_text is not None else None,
                pages=[str(page) for page in raw_pages] if raw_pages is not None else None,
                options=options,
                speaker_behavior=speaker_behavior,
                speaker_id=speaker_id,
                show_portrait=raw_show_portrait,
                advance_mode=advance_mode,
                advance_seconds=advance_seconds,
            )
        )

    return segments


def _parse_dialogue_segment_options(
    raw_segment: dict[str, Any],
    dialogue_id: str,
    segment_index: int,
) -> list[DialogueOption]:
    """Parse the options for one choice segment."""
    raw_options = raw_segment.get("options")
    if raw_options is None:
        return []
    if not isinstance(raw_options, list):
        raise ValueError(
            f"Dialogue definition '{dialogue_id}' segment {segment_index} must use a list for 'options'."
        )
    if not raw_options:
        return []

    option_id_usage: list[bool] = []
    seen_option_ids: set[str] = set()
    options: list[DialogueOption] = []
    for option_index, raw_option in enumerate(raw_options):
        if not isinstance(raw_option, dict):
            raise ValueError(
                f"Dialogue definition '{dialogue_id}' segment {segment_index} option {option_index} must be an object."
            )
        raw_text = raw_option.get("text")
        if not isinstance(raw_text, str):
            raise ValueError(
                f"Dialogue definition '{dialogue_id}' segment {segment_index} option {option_index} must use a string for 'text'."
            )

        option_id: str | None = None
        if "option_id" in raw_option:
            raw_option_id = raw_option.get("option_id")
            if not isinstance(raw_option_id, str) or not raw_option_id.strip():
                raise ValueError(
                    f"Dialogue definition '{dialogue_id}' segment {segment_index} option {option_index} must use a non-empty string for 'option_id'."
                )
            option_id = raw_option_id.strip()
            if option_id in seen_option_ids:
                raise ValueError(
                    f"Dialogue definition '{dialogue_id}' segment {segment_index} uses duplicate option_id '{option_id}'."
                )
            seen_option_ids.add(option_id)
            option_id_usage.append(True)
        else:
            option_id_usage.append(False)

        options.append(DialogueOption(text=raw_text, option_id=option_id))

    if any(option_id_usage) and not all(option_id_usage):
        raise ValueError(
            f"Dialogue definition '{dialogue_id}' segment {segment_index} must either give every option an 'option_id' or omit them all."
        )

    return options


def _parse_dialogue_segment_advance(
    raw_segment: dict[str, Any],
    *,
    dialogue_id: str,
    segment_index: int,
    segment_type: str,
) -> tuple[Literal["interact", "timer", "interact_or_timer"], float | None]:
    """Parse one segment's pacing settings."""
    raw_advance = raw_segment.get("advance")
    if raw_advance is None:
        raw_advance = {}
    if not isinstance(raw_advance, dict):
        raise ValueError(
            f"Dialogue definition '{dialogue_id}' segment {segment_index} must use an object for 'advance'."
        )

    advance_mode = str(raw_advance.get("mode", "interact")).strip().lower()
    if advance_mode not in {"interact", "timer", "interact_or_timer"}:
        raise ValueError(
            f"Dialogue definition '{dialogue_id}' segment {segment_index} has unknown advance mode '{advance_mode}'."
        )

    raw_seconds = raw_advance.get("seconds")
    advance_seconds: float | None = None
    if raw_seconds is not None:
        if not isinstance(raw_seconds, (int, float)) or float(raw_seconds) <= 0:
            raise ValueError(
                f"Dialogue definition '{dialogue_id}' segment {segment_index} must use a positive number for advance.seconds."
            )
        advance_seconds = float(raw_seconds)

    if segment_type == "choice" and advance_mode != "interact":
        raise ValueError(
            f"Dialogue definition '{dialogue_id}' choice segment {segment_index} only supports advance mode 'interact'."
        )
    if advance_mode == "interact" and advance_seconds is not None:
        raise ValueError(
            f"Dialogue definition '{dialogue_id}' segment {segment_index} must not define advance.seconds for interact mode."
        )
    if advance_mode in {"timer", "interact_or_timer"} and advance_seconds is None:
        raise ValueError(
            f"Dialogue definition '{dialogue_id}' segment {segment_index} must define advance.seconds for mode '{advance_mode}'."
        )

    return advance_mode, advance_seconds


def _parse_optional_string(
    value: Any,
    *,
    field_name: str,
    dialogue_id: str,
) -> str | None:
    """Return one optional string field."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Dialogue definition '{dialogue_id}' must use a string for '{field_name}'.")
    return str(value)


def _parse_optional_int(
    value: Any,
    *,
    field_name: str,
    dialogue_id: str,
) -> int | None:
    """Return one optional integer field."""
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(f"Dialogue definition '{dialogue_id}' must use an integer for '{field_name}'.")
    return int(value)


def _parse_optional_color(
    value: Any,
    *,
    field_name: str,
    dialogue_id: str,
) -> tuple[int, int, int] | None:
    """Return one optional RGB color tuple."""
    if value is None:
        return None
    if not isinstance(value, list) or len(value) < 3:
        raise ValueError(
            f"Dialogue definition '{dialogue_id}' must use a list with 3 channels for '{field_name}'."
        )
    try:
        return (int(value[0]), int(value[1]), int(value[2]))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Dialogue definition '{dialogue_id}' must use integer RGB channels for '{field_name}'."
        ) from exc


def validate_project_dialogues(project: ProjectContext) -> None:
    """Validate dialogue files for a project at startup."""
    known_ids: dict[str, list[Path]] = {}
    for dialogue_path in project.list_dialogue_definition_files():
        dialogue_id = project.dialogue_definition_id(dialogue_path)
        known_ids.setdefault(dialogue_id, []).append(dialogue_path)

    issues: list[str] = []
    for dialogue_id, paths in sorted(known_ids.items()):
        if len(paths) > 1:
            formatted_paths = ", ".join(str(path) for path in paths)
            issues.append(f"Duplicate dialogue id '{dialogue_id}' found in: {formatted_paths}")
            continue

        try:
            load_dialogue_definition(project, dialogue_id)
        except json.JSONDecodeError as exc:
            issues.append(
                f"{paths[0]}: invalid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})."
            )
        except Exception as exc:
            issues.append(f"{paths[0]}: {exc}")

    if issues:
        raise DialogueValidationError(project.project_root, issues)


def log_dialogue_validation_error(error: DialogueValidationError) -> None:
    """Write a full dialogue validation failure report to the persistent log."""
    logger.error(
        "Dialogue validation failed for %s with %d issue(s):\n%s",
        error.project_root,
        len(error.issues),
        "\n".join(f"- {issue}" for issue in error.issues),
    )
