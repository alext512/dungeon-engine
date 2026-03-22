"""Project-level reusable JSON dialogue definitions."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dungeon_engine.project import ProjectContext


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
    raw_id = raw.get("id", expected_id)
    resolved_id = str(raw_id).strip()
    if not resolved_id:
        raise ValueError(f"Dialogue definition '{expected_id}' must use a non-empty string for 'id'.")
    if resolved_id != expected_id:
        raise ValueError(
            f"Dialogue definition '{expected_id}' declares id '{resolved_id}', but dialogue ids are path-based. "
            f"Use '{expected_id}' or omit the 'id' field."
        )

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
