"""Tests for project manifest loading and area discovery.

These run against the real test_project fixtures — no mocks needed.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from area_editor.project_io.project_manifest import (
    discover_areas,
    discover_entity_templates,
    discover_global_entities,
    discover_items,
    load_manifest,
)

# Relative path from tools/area_editor/ to the test project.
_TEST_PROJECT = Path(__file__).resolve().parent.parent.parent.parent / "projects" / "test_project"
_PHYSICS_PROJECT = (
    Path(__file__).resolve().parent.parent.parent.parent / "projects" / "physics_contract_demo"
)


@unittest.skipUnless(_TEST_PROJECT.is_dir(), "test_project fixture not found")
class TestManifestLoading(unittest.TestCase):
    def setUp(self):
        self.manifest = load_manifest(_TEST_PROJECT / "project.json")

    def test_project_root(self):
        self.assertEqual(self.manifest.project_root, _TEST_PROJECT.resolve())
        self.assertEqual(self.manifest.project_file, (_TEST_PROJECT / "project.json").resolve())

    def test_area_paths_resolved(self):
        self.assertTrue(len(self.manifest.area_paths) > 0)
        for p in self.manifest.area_paths:
            self.assertTrue(p.is_dir(), f"area path does not exist: {p}")

    def test_startup_area(self):
        self.assertEqual(self.manifest.startup_area, "areas/title_screen")

    def test_display_dimensions_loaded_from_shared_variables(self):
        self.assertEqual(self.manifest.display_width, 256)
        self.assertEqual(self.manifest.display_height, 192)

    def test_shared_variables_path_is_resolved(self):
        self.assertEqual(
            self.manifest.shared_variables_path,
            (_TEST_PROJECT / "shared_variables.json").resolve(),
        )


@unittest.skipUnless(_TEST_PROJECT.is_dir(), "test_project fixture not found")
class TestAreaDiscovery(unittest.TestCase):
    def setUp(self):
        self.manifest = load_manifest(_TEST_PROJECT / "project.json")
        self.areas = discover_areas(self.manifest)

    def test_discovers_expected_areas(self):
        ids = [a.area_id for a in self.areas]
        self.assertIn("areas/village_square", ids)
        self.assertIn("areas/village_house", ids)
        self.assertIn("areas/title_screen", ids)

    def test_area_count(self):
        self.assertEqual(len(self.areas), 3)

    def test_area_files_exist(self):
        for entry in self.areas:
            self.assertTrue(entry.file_path.is_file(), f"missing: {entry.file_path}")

    def test_area_ids_are_sorted(self):
        ids = [a.area_id for a in self.areas]
        self.assertEqual(ids, sorted(ids))


@unittest.skipUnless(_TEST_PROJECT.is_dir(), "test_project fixture not found")
class TestTemplateDiscovery(unittest.TestCase):
    def test_discovers_templates(self):
        manifest = load_manifest(_TEST_PROJECT / "project.json")
        templates = discover_entity_templates(manifest)
        self.assertTrue(len(templates) > 0)
        ids = [t.template_id for t in templates]
        # The test project should have at least area_door
        self.assertIn("entity_templates/area_door", ids)


@unittest.skipUnless(_TEST_PROJECT.is_dir(), "test_project fixture not found")
class TestGlobalEntityDiscovery(unittest.TestCase):
    def test_discovers_global_entities_in_manifest_order(self):
        manifest = load_manifest(_TEST_PROJECT / "project.json")
        entries = discover_global_entities(manifest)

        self.assertEqual(
            [entry.entity_id for entry in entries],
            ["dialogue_controller", "pause_controller", "debug_controller"],
        )
        self.assertEqual(entries[1].template_id, "entity_templates/pause_controller")


@unittest.skipUnless(_PHYSICS_PROJECT.is_dir(), "physics_contract_demo fixture not found")
class TestItemDiscovery(unittest.TestCase):
    def test_discovers_items_from_item_paths(self):
        manifest = load_manifest(_PHYSICS_PROJECT / "project.json")
        items = discover_items(manifest)

        self.assertTrue(len(items) > 0)
        ids = [entry.item_id for entry in items]
        self.assertIn("items/apple", ids)
        self.assertIn("items/copper_key", ids)


@unittest.skipUnless(_TEST_PROJECT.is_dir(), "test_project fixture not found")
class TestManifestFallback(unittest.TestCase):
    def test_load_by_directory(self):
        """load_manifest should accept a directory path too."""
        manifest = load_manifest(_TEST_PROJECT)
        self.assertEqual(manifest.project_root, _TEST_PROJECT.resolve())

    def test_defaults_display_dimensions_when_shared_variables_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            project_root.mkdir()
            (project_root / "project.json").write_text(
                '{\n  "startup_area": "areas/demo"\n}\n',
                encoding="utf-8",
            )

            manifest = load_manifest(project_root / "project.json")

            self.assertEqual(manifest.display_width, 320)
            self.assertEqual(manifest.display_height, 240)


if __name__ == "__main__":
    unittest.main()
