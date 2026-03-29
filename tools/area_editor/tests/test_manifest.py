"""Tests for project manifest loading and area discovery.

These run against the real test_project fixtures — no mocks needed.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from area_editor.project_io.manifest import (
    discover_areas,
    discover_entity_templates,
    load_manifest,
)

# Relative path from tools/area_editor/ to the test project.
_TEST_PROJECT = Path(__file__).resolve().parent.parent.parent.parent / "projects" / "test_project"


@unittest.skipUnless(_TEST_PROJECT.is_dir(), "test_project fixture not found")
class TestManifestLoading(unittest.TestCase):
    def setUp(self):
        self.manifest = load_manifest(_TEST_PROJECT / "project.json")

    def test_project_root(self):
        self.assertEqual(self.manifest.project_root, _TEST_PROJECT.resolve())

    def test_area_paths_resolved(self):
        self.assertTrue(len(self.manifest.area_paths) > 0)
        for p in self.manifest.area_paths:
            self.assertTrue(p.is_dir(), f"area path does not exist: {p}")

    def test_startup_area(self):
        self.assertEqual(self.manifest.startup_area, "areas/title_screen")


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
class TestManifestFallback(unittest.TestCase):
    def test_load_by_directory(self):
        """load_manifest should accept a directory path too."""
        manifest = load_manifest(_TEST_PROJECT)
        self.assertEqual(manifest.project_root, _TEST_PROJECT.resolve())


if __name__ == "__main__":
    unittest.main()
