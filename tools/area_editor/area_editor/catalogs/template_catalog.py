"""Entity template loading and visual lookup.

Loads entity template JSON files and provides quick access to the first
visual definition for sprite rendering on the canvas.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from area_editor.project_io.manifest import ProjectManifest, discover_entity_templates

log = logging.getLogger(__name__)


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

    def get_first_visual(self, template_id: str) -> VisualInfo | None:
        """Return the first visual from the named template, or ``None``."""
        raw = self._templates.get(template_id)
        if raw is None:
            return None
        visuals = raw.get("visuals")
        if not visuals:
            return None
        v = visuals[0]
        path = v.get("path")
        if not path:
            return None
        return VisualInfo(
            path=path,
            frame_width=v.get("frame_width", 16),
            frame_height=v.get("frame_height", 16),
            frames=v.get("frames", [0]),
            offset_x=v.get("offset_x", 0),
            offset_y=v.get("offset_y", 0),
        )

    def template_ids(self) -> list[str]:
        """Return all loaded template ids."""
        return list(self._templates.keys())

    def clear(self) -> None:
        self._templates.clear()
