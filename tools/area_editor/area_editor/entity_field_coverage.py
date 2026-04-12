"""Editor ownership map for runtime-known authored entity fields.

Keep this aligned with ``dungeon_engine.world.loader_entities`` whenever the
runtime adds or removes authored entity fields.
"""

from __future__ import annotations

ENGINE_KNOWN_ENTITY_FIELDS = frozenset(
    {
        "id",
        "kind",
        "space",
        "scope",
        "grid_x",
        "grid_y",
        "pixel_x",
        "pixel_y",
        "template",
        "parameters",
        "tags",
        "facing",
        "solid",
        "pushable",
        "weight",
        "push_strength",
        "collision_push_strength",
        "interactable",
        "interaction_priority",
        "present",
        "visible",
        "entity_commands_enabled",
        "render_order",
        "y_sort",
        "sort_y_offset",
        "stack_order",
        "color",
        "variables",
        "visuals",
        "input_map",
        "entity_commands",
        "inventory",
        "persistence",
        "entity_commands",
    }
)

ENTITY_INSTANCE_FIELDS_TAB_FIELDS = frozenset(
    {
        "id",
        "kind",
        "space",
        "scope",
        "grid_x",
        "grid_y",
        "pixel_x",
        "pixel_y",
        "template",
        "parameters",
        "tags",
        "facing",
        "solid",
        "pushable",
        "weight",
        "push_strength",
        "collision_push_strength",
        "interactable",
        "interaction_priority",
        "present",
        "visible",
        "entity_commands_enabled",
        "color",
        "variables",
        "visuals",
        "input_map",
        "entity_commands",
        "inventory",
        "persistence",
    }
)

ENTITY_INSTANCE_FIELDS_TAB_EXTRA_FIELDS = frozenset(
    {
        "kind",
        "scope",
        "tags",
        "facing",
        "solid",
        "pushable",
        "weight",
        "push_strength",
        "collision_push_strength",
        "interactable",
        "interaction_priority",
        "present",
        "visible",
        "entity_commands_enabled",
        "color",
        "variables",
        "visuals",
        "input_map",
        "inventory",
        "persistence",
    }
)

ENTITY_INSTANCE_RENDER_PANEL_FIELDS = frozenset(
    {
        "render_order",
        "y_sort",
        "sort_y_offset",
        "stack_order",
    }
)

ENTITY_INSTANCE_RAW_JSON_ONLY_FIELDS = frozenset()

ENTITY_TEMPLATE_APPLICABLE_FIELDS = ENGINE_KNOWN_ENTITY_FIELDS - frozenset(
    {
        "id",
        "grid_x",
        "grid_y",
        "pixel_x",
        "pixel_y",
        "template",
        "parameters",
    }
)

ENTITY_TEMPLATE_STRUCTURED_FIELDS = frozenset(
    {
        "kind",
        "space",
        "scope",
        "tags",
        "facing",
        "solid",
        "pushable",
        "weight",
        "push_strength",
        "collision_push_strength",
        "interactable",
        "interaction_priority",
        "present",
        "visible",
        "entity_commands_enabled",
        "render_order",
        "y_sort",
        "sort_y_offset",
        "stack_order",
        "color",
        "variables",
        "visuals",
        "input_map",
        "entity_commands",
        "inventory",
        "persistence",
    }
)

ENTITY_TEMPLATE_READ_ONLY_SUMMARY_FIELDS = frozenset()

ENTITY_TEMPLATE_RAW_JSON_ONLY_FIELDS = (
    ENTITY_TEMPLATE_APPLICABLE_FIELDS
    - ENTITY_TEMPLATE_STRUCTURED_FIELDS
    - ENTITY_TEMPLATE_READ_ONLY_SUMMARY_FIELDS
)
