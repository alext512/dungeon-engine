"""Compatibility wrapper for the runtime project context surface.

Prefer importing runtime project-loading helpers from
``dungeon_engine.project_context``. This module remains as a stable
compatibility entry point for older imports.
"""

from __future__ import annotations

from .project_context import (
    AREA_ID_PREFIX,
    COMMAND_ID_PREFIX,
    ENTITY_TEMPLATE_ID_PREFIX,
    ITEM_ID_PREFIX,
    ProjectContext,
    _load_shared_variables,
    _normalize_content_id,
    _optional_manifest_str,
    _prefix_relative_id,
    _relative_id_from_canonical,
    _resolve_global_entities,
    _resolve_input_targets,
    _resolve_optional_path,
    _resolve_project_dimension,
    load_project,
)

__all__ = [
    "AREA_ID_PREFIX",
    "COMMAND_ID_PREFIX",
    "ENTITY_TEMPLATE_ID_PREFIX",
    "ITEM_ID_PREFIX",
    "ProjectContext",
    "_load_shared_variables",
    "_normalize_content_id",
    "_optional_manifest_str",
    "_prefix_relative_id",
    "_relative_id_from_canonical",
    "_resolve_global_entities",
    "_resolve_input_targets",
    "_resolve_optional_path",
    "_resolve_project_dimension",
    "load_project",
]
