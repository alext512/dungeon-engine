"""Small persisted state for launcher convenience features."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from dungeon_engine import config


@dataclass(slots=True)
class LauncherState:
    """Remember the last project and area ids opened by each standalone launcher."""

    last_project: str | None = None
    last_game_area: str | None = None
    last_editor_area: str | None = None


def load_launcher_state(path: Path | None = None) -> LauncherState:
    """Load launcher state from disk, defaulting to an empty record."""
    state_path = path or config.LAUNCHER_STATE_PATH
    if not state_path.exists():
        return LauncherState()

    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return LauncherState()

    return LauncherState(
        last_project=_optional_str(raw.get("last_project")),
        last_game_area=_optional_str(raw.get("last_game_area")),
        last_editor_area=_optional_str(raw.get("last_editor_area")),
    )


def save_launcher_state(state: LauncherState, path: Path | None = None) -> None:
    """Write launcher state to disk."""
    state_path = path or config.LAUNCHER_STATE_PATH
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def update_launcher_state(path: Path | None = None, **updates: str | None) -> LauncherState:
    """Merge the provided values into launcher state and persist the result."""
    state = load_launcher_state(path)
    for field_name, value in updates.items():
        if hasattr(state, field_name):
            setattr(state, field_name, _optional_str(value))
    save_launcher_state(state, path)
    return state


def _optional_str(value: object) -> str | None:
    """Normalize optional JSON/string values."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None

