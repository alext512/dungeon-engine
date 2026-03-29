"""Entity template loading and visual lookup.

Loads entity template JSON files and provides quick access to the first
visual definition for sprite rendering on the canvas.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from area_editor.project_io.manifest import ProjectManifest, discover_entity_templates

log = logging.getLogger(__name__)

_EXACT_TOKEN_RE = re.compile(r"^\$(?:{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)}|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))$")
_EMBEDDED_TOKEN_RE = re.compile(r"\$(?:{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)}|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))")


@dataclass
class VisualInfo:
    """The subset of a visual definition needed for canvas rendering."""

    path: str
    frame_width: int
    frame_height: int
    frames: list[int]
    offset_x: float = 0
    offset_y: float = 0


class TemplateCatalog:
    """Load entity templates and provide visual info by template id."""

    def __init__(self) -> None:
        self._templates: dict[str, dict[str, Any]] = {}

    def load_from_manifest(self, manifest: ProjectManifest) -> None:
        """Discover and load all entity templates for the project."""
        self._templates.clear()
        for entry in discover_entity_templates(manifest):
            try:
                raw = json.loads(entry.file_path.read_text(encoding="utf-8"))
                self._templates[entry.template_id] = raw
            except Exception as exc:
                log.warning("Failed to load template %s: %s", entry.template_id, exc)

    def get_first_visual(
        self,
        template_id: str,
        parameters: dict[str, Any] | None = None,
    ) -> VisualInfo | None:
        """Return the first visual from the named template, or ``None``."""
        raw = self._templates.get(template_id)
        if raw is None:
            return None
        visuals = raw.get("visuals")
        if not visuals:
            return None
        v = self._substitute_template_parameters(visuals[0], parameters or {})
        if not isinstance(v, dict):
            return None
        path = v.get("path")
        if not isinstance(path, str) or not path or self._contains_unresolved_tokens(path):
            return None
        frame_width = v.get("frame_width", 16)
        frame_height = v.get("frame_height", 16)
        frames = v.get("frames", [0])
        if not isinstance(frame_width, int) or not isinstance(frame_height, int):
            return None
        if not isinstance(frames, list) or not all(isinstance(frame, int) for frame in frames):
            return None
        return VisualInfo(
            path=path,
            frame_width=frame_width,
            frame_height=frame_height,
            frames=frames,
            offset_x=v.get("offset_x", 0),
            offset_y=v.get("offset_y", 0),
        )

    def template_ids(self) -> list[str]:
        """Return all loaded template ids."""
        return list(self._templates.keys())

    def clear(self) -> None:
        self._templates.clear()

    def _substitute_template_parameters(
        self,
        value: Any,
        parameters: dict[str, Any],
    ) -> Any:
        if isinstance(value, dict):
            return {
                key: self._substitute_template_parameters(subvalue, parameters)
                for key, subvalue in value.items()
            }
        if isinstance(value, list):
            return [
                self._substitute_template_parameters(item, parameters)
                for item in value
            ]
        if not isinstance(value, str):
            return value

        exact_match = _EXACT_TOKEN_RE.fullmatch(value)
        if exact_match:
            key = exact_match.group("braced") or exact_match.group("plain")
            return parameters.get(key, value)

        def replace(match: re.Match[str]) -> str:
            key = match.group("braced") or match.group("plain")
            if key not in parameters:
                return match.group(0)
            return str(parameters[key])

        return _EMBEDDED_TOKEN_RE.sub(replace, value)

    @staticmethod
    def _contains_unresolved_tokens(value: str) -> bool:
        return _EMBEDDED_TOKEN_RE.search(value) is not None
