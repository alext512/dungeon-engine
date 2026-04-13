"""Entity template loading and visual lookup.

Loads entity template JSON files and provides quick access to the first
visual definition for sprite rendering on the canvas.
"""

from __future__ import annotations

import logging
import re
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from area_editor.json_io import load_json_data
from area_editor.project_io.project_manifest import (
    ProjectManifest,
    discover_entity_templates,
)

log = logging.getLogger(__name__)

_EXACT_TOKEN_RE = re.compile(r"^\$(?:{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)}|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))$")
_EMBEDDED_TOKEN_RE = re.compile(r"\$(?:{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)}|(?P<plain>[A-Za-z_][A-Za-z0-9_]*))")
_BUILTIN_VARIABLES = frozenset({
    "self",
    "self_id",
    "refs",
    "ref_ids",
    "project",
    "current_area",
    "area",
    "camera",
    "from_x",
    "from_y",
    "to_x",
    "to_y",
    "blocking_entity_id",
})


@dataclass
class VisualInfo:
    """The subset of a visual definition needed for canvas rendering."""

    path: str
    frame_width: int
    frame_height: int
    frames: list[int]
    offset_x: float = 0
    offset_y: float = 0
    flip_x: bool = False


class TemplateCatalog:
    """Load entity templates and provide visual info by template id."""

    def __init__(self) -> None:
        self._templates: dict[str, dict[str, Any]] = {}
        self._template_parameter_names: dict[str, list[str]] = {}

    def load_from_manifest(self, manifest: ProjectManifest) -> None:
        """Discover and load all entity templates for the project."""
        self._templates.clear()
        self._template_parameter_names.clear()
        for entry in discover_entity_templates(manifest):
            try:
                raw = load_json_data(entry.file_path)
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
        if not isinstance(frame_width, int) or not isinstance(frame_height, int):
            return None
        frames, flip_x = self._resolve_preview_frames_and_flip(v)
        if not isinstance(frames, list) or not all(isinstance(frame, int) for frame in frames):
            return None
        return VisualInfo(
            path=path,
            frame_width=frame_width,
            frame_height=frame_height,
            frames=frames,
            offset_x=v.get("offset_x", 0),
            offset_y=v.get("offset_y", 0),
            flip_x=flip_x,
        )

    def get_template_space(self, template_id: str) -> str | None:
        """Return the authored space for one template, if known."""
        raw = self._templates.get(template_id)
        if raw is None:
            return None
        return str(raw.get("space", "world")).strip().lower()

    def get_template_render_order(self, template_id: str) -> int | None:
        """Return the authored render order for one template, if known."""
        raw = self._templates.get(template_id)
        if raw is None:
            return None
        space = str(raw.get("space", "world")).strip().lower()
        default = 10 if space == "world" else 0
        return int(raw.get("render_order", default))

    def template_ids(self) -> list[str]:
        """Return all loaded template ids."""
        return list(self._templates.keys())

    def get_template_parameter_names(self, template_id: str) -> list[str]:
        """Return named instance parameters referenced by one template."""
        cached = self._template_parameter_names.get(template_id)
        if cached is not None:
            return list(cached)
        raw = self._templates.get(template_id)
        if raw is None:
            return []
        found: set[str] = set()
        self._collect_variable_names(raw, found)
        names = sorted(name for name in found if name not in _BUILTIN_VARIABLES)
        self._template_parameter_names[template_id] = names
        return list(names)

    def get_template_parameter_defaults(self, template_id: str) -> dict[str, Any]:
        """Return template-level default parameter values, if authored."""
        raw = self._templates.get(template_id)
        if raw is None:
            return {}
        defaults = raw.get("parameters")
        if not isinstance(defaults, dict):
            return {}
        return copy.deepcopy(defaults)

    def get_template_parameter_specs(self, template_id: str) -> dict[str, Any]:
        """Return template-level parameter specs, if authored."""
        raw = self._templates.get(template_id)
        if raw is None:
            return {}
        specs = raw.get("parameter_specs")
        if not isinstance(specs, dict):
            return {}
        return copy.deepcopy(specs)

    def get_template_entity_command_names(self, template_id: str) -> list[str]:
        """Return authored entity-command names for one template."""
        raw = self._templates.get(template_id)
        if raw is None:
            return []
        entity_commands = raw.get("entity_commands")
        if not isinstance(entity_commands, dict):
            return []
        names = [
            str(name).strip()
            for name in entity_commands.keys()
            if str(name).strip()
        ]
        return sorted(set(names))

    def clear(self) -> None:
        self._templates.clear()
        self._template_parameter_names.clear()

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

    @staticmethod
    def _resolve_preview_frames_and_flip(visual: dict[str, Any]) -> tuple[Any, bool]:
        """Mirror the runtime's visual default-frame selection for previews."""
        frames = visual.get("frames")
        flip_x = bool(visual.get("flip_x", False))

        animations = visual.get("animations")
        if isinstance(animations, dict) and animations:
            default_animation = visual.get("default_animation")
            clip = None
            if isinstance(default_animation, str) and default_animation.strip() in animations:
                clip = animations[default_animation.strip()]
            elif frames is None:
                first_animation_id = sorted(animations.keys(), key=str)[0]
                clip = animations.get(first_animation_id)

            if isinstance(clip, dict):
                clip_frames = clip.get("frames")
                if isinstance(clip_frames, list):
                    frames = clip_frames
                clip_flip = clip.get("flip_x")
                if isinstance(clip_flip, bool):
                    flip_x = clip_flip

        if frames is None:
            frames = [0]
        return frames, flip_x

    @staticmethod
    def _collect_variable_names(value: Any, found: set[str]) -> None:
        if isinstance(value, dict):
            for key, subvalue in value.items():
                if key == "parameter_specs":
                    continue
                TemplateCatalog._collect_variable_names(subvalue, found)
            return
        if isinstance(value, list):
            for item in value:
                TemplateCatalog._collect_variable_names(item, found)
            return
        if not isinstance(value, str):
            return
        for match in _EMBEDDED_TOKEN_RE.finditer(value):
            key = match.group("braced") or match.group("plain")
            if key:
                found.add(key)
