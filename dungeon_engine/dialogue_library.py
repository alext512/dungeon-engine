"""Project-level reusable JSON dialogue definitions."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dungeon_engine.logging_utils import get_logger

if TYPE_CHECKING:
    from dungeon_engine.project import ProjectContext


logger = get_logger(__name__)


@dataclass(slots=True)
class DialogueDefinition:
    """A reusable JSON-authored dialogue asset."""

    dialogue_id: str
    speaker: str
    text: str | None
    pages: list[str] | None
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

    raw_speaker = raw.get("speaker", "")
    if raw_speaker is None:
        raw_speaker = ""

    raw_text = raw.get("text")
    raw_pages = raw.get("pages")
    if raw_text is None and raw_pages is None:
        raise ValueError(f"Dialogue definition '{resolved_id}' must define either 'text' or 'pages'.")
    if raw_text is not None and raw_pages is not None:
        raise ValueError(f"Dialogue definition '{resolved_id}' cannot define both 'text' and 'pages'.")
    if raw_text is not None and not isinstance(raw_text, str):
        raise ValueError(f"Dialogue definition '{resolved_id}' must use a string for 'text'.")
    if raw_pages is not None:
        if not isinstance(raw_pages, list) or not all(isinstance(page, str) for page in raw_pages):
            raise ValueError(f"Dialogue definition '{resolved_id}' must use a list of strings for 'pages'.")

    return DialogueDefinition(
        dialogue_id=resolved_id,
        speaker=str(raw_speaker),
        text=str(raw_text) if raw_text is not None else None,
        pages=[str(page) for page in raw_pages] if raw_pages is not None else None,
        source_path=dialogue_path,
        raw_data=raw,
    )


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
