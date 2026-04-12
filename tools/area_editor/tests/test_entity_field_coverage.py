"""Tests for the editor/runtime entity-field ownership map."""

from __future__ import annotations

import unittest

from area_editor.entity_field_coverage import (
    ENGINE_KNOWN_ENTITY_FIELDS,
    ENTITY_INSTANCE_FIELDS_TAB_EXTRA_FIELDS,
    ENTITY_INSTANCE_FIELDS_TAB_FIELDS,
    ENTITY_INSTANCE_RAW_JSON_ONLY_FIELDS,
    ENTITY_INSTANCE_RENDER_PANEL_FIELDS,
    ENTITY_TEMPLATE_APPLICABLE_FIELDS,
    ENTITY_TEMPLATE_RAW_JSON_ONLY_FIELDS,
    ENTITY_TEMPLATE_READ_ONLY_SUMMARY_FIELDS,
    ENTITY_TEMPLATE_STRUCTURED_FIELDS,
)
from area_editor.widgets.entity_instance_json_panel import _MANAGED_EXTRA_KEYS


class TestEntityFieldCoverage(unittest.TestCase):
    def test_instance_field_ownership_covers_runtime_known_entity_fields(self) -> None:
        covered_fields = (
            ENTITY_INSTANCE_FIELDS_TAB_FIELDS
            | ENTITY_INSTANCE_RENDER_PANEL_FIELDS
            | ENTITY_INSTANCE_RAW_JSON_ONLY_FIELDS
        )

        self.assertEqual(ENGINE_KNOWN_ENTITY_FIELDS, covered_fields)
        self.assertFalse(
            ENTITY_INSTANCE_FIELDS_TAB_FIELDS & ENTITY_INSTANCE_RENDER_PANEL_FIELDS
        )
        self.assertFalse(
            ENTITY_INSTANCE_FIELDS_TAB_FIELDS & ENTITY_INSTANCE_RAW_JSON_ONLY_FIELDS
        )
        self.assertFalse(
            ENTITY_INSTANCE_RENDER_PANEL_FIELDS & ENTITY_INSTANCE_RAW_JSON_ONLY_FIELDS
        )

    def test_instance_fields_widget_uses_the_documented_extra_field_set(self) -> None:
        self.assertEqual(ENTITY_INSTANCE_FIELDS_TAB_EXTRA_FIELDS, _MANAGED_EXTRA_KEYS)

    def test_instance_has_no_raw_only_runtime_entity_fields(self) -> None:
        self.assertEqual(ENTITY_INSTANCE_RAW_JSON_ONLY_FIELDS, frozenset())

    def test_template_field_ownership_covers_applicable_runtime_entity_fields(self) -> None:
        covered_fields = (
            ENTITY_TEMPLATE_STRUCTURED_FIELDS
            | ENTITY_TEMPLATE_READ_ONLY_SUMMARY_FIELDS
            | ENTITY_TEMPLATE_RAW_JSON_ONLY_FIELDS
        )

        self.assertEqual(ENTITY_TEMPLATE_APPLICABLE_FIELDS, covered_fields)
        self.assertFalse(
            ENTITY_TEMPLATE_STRUCTURED_FIELDS & ENTITY_TEMPLATE_READ_ONLY_SUMMARY_FIELDS
        )
        self.assertFalse(
            ENTITY_TEMPLATE_STRUCTURED_FIELDS & ENTITY_TEMPLATE_RAW_JSON_ONLY_FIELDS
        )
        self.assertFalse(
            ENTITY_TEMPLATE_READ_ONLY_SUMMARY_FIELDS & ENTITY_TEMPLATE_RAW_JSON_ONLY_FIELDS
        )

    def test_template_has_no_raw_only_runtime_entity_fields(self) -> None:
        self.assertEqual(ENTITY_TEMPLATE_RAW_JSON_ONLY_FIELDS, frozenset())
