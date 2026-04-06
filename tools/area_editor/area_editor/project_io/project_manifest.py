"""Preferred import surface for editor-side project manifest discovery.

The editor keeps its own project-layout interpretation layer separate from the
runtime. This named module is clearer at call sites than the older
``manifest.py`` entry point, which remains available while imports migrate.
"""

from __future__ import annotations

from .manifest import (
    AREA_ID_PREFIX,
    ITEM_ID_PREFIX,
    TEMPLATE_ID_PREFIX,
    AreaEntry,
    GlobalEntityEntry,
    ItemEntry,
    ProjectManifest,
    TemplateEntry,
    discover_areas,
    discover_entity_templates,
    discover_global_entities,
    discover_items,
    load_manifest,
)

__all__ = [
    "AREA_ID_PREFIX",
    "ITEM_ID_PREFIX",
    "TEMPLATE_ID_PREFIX",
    "AreaEntry",
    "GlobalEntityEntry",
    "ItemEntry",
    "ProjectManifest",
    "TemplateEntry",
    "discover_areas",
    "discover_entity_templates",
    "discover_global_entities",
    "discover_items",
    "load_manifest",
]
