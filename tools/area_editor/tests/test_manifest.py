"""Tests for project manifest loading and area discovery.

These run against a generated fixture project so they stay stable even when
repo-local example content changes.
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
from fixture_project import FixtureProject, create_editor_fixture_project

_FIXTURE_TEMP: tempfile.TemporaryDirectory[str] | None = None
_FIXTURE: FixtureProject | None = None


def setUpModule() -> None:
    global _FIXTURE_TEMP, _FIXTURE
    _FIXTURE_TEMP = tempfile.TemporaryDirectory()
    _FIXTURE = create_editor_fixture_project(Path(_FIXTURE_TEMP.name))


def tearDownModule() -> None:
    global _FIXTURE_TEMP, _FIXTURE
    if _FIXTURE_TEMP is not None:
        _FIXTURE_TEMP.cleanup()
    _FIXTURE_TEMP = None
    _FIXTURE = None


class TestManifestLoading(unittest.TestCase):
    def setUp(self) -> None:
        assert _FIXTURE is not None
        self.manifest = load_manifest(_FIXTURE.project_file)

    def test_project_root(self) -> None:
        assert _FIXTURE is not None
        self.assertEqual(self.manifest.project_root, _FIXTURE.project_root.resolve())
        self.assertEqual(self.manifest.project_file, _FIXTURE.project_file.resolve())

    def test_area_paths_resolved(self) -> None:
        self.assertTrue(len(self.manifest.area_paths) > 0)
        for area_path in self.manifest.area_paths:
            self.assertTrue(area_path.is_dir(), f"area path does not exist: {area_path}")

    def test_startup_area(self) -> None:
        self.assertEqual(self.manifest.startup_area, "areas/title_screen")

    def test_display_dimensions_loaded_from_shared_variables(self) -> None:
        self.assertEqual(self.manifest.display_width, 256)
        self.assertEqual(self.manifest.display_height, 192)

    def test_shared_variables_path_is_resolved(self) -> None:
        assert _FIXTURE is not None
        self.assertEqual(
            self.manifest.shared_variables_path,
            (_FIXTURE.project_root / "shared_variables.json").resolve(),
        )


class TestAreaDiscovery(unittest.TestCase):
    def setUp(self) -> None:
        assert _FIXTURE is not None
        self.manifest = load_manifest(_FIXTURE.project_file)
        self.areas = discover_areas(self.manifest)

    def test_discovers_expected_areas(self) -> None:
        ids = [entry.area_id for entry in self.areas]
        self.assertIn("areas/village_square", ids)
        self.assertIn("areas/village_house", ids)
        self.assertIn("areas/title_screen", ids)

    def test_area_count(self) -> None:
        self.assertEqual(len(self.areas), 3)

    def test_area_files_exist(self) -> None:
        for entry in self.areas:
            self.assertTrue(entry.file_path.is_file(), f"missing: {entry.file_path}")

    def test_area_ids_are_sorted(self) -> None:
        ids = [entry.area_id for entry in self.areas]
        self.assertEqual(ids, sorted(ids))


class TestTemplateDiscovery(unittest.TestCase):
    def test_discovers_templates(self) -> None:
        assert _FIXTURE is not None
        manifest = load_manifest(_FIXTURE.project_file)
        templates = discover_entity_templates(manifest)
        self.assertTrue(len(templates) > 0)
        ids = [entry.template_id for entry in templates]
        self.assertIn("entity_templates/area_door", ids)
        self.assertIn("entity_templates/pause_controller", ids)


class TestGlobalEntityDiscovery(unittest.TestCase):
    def test_discovers_global_entities_in_manifest_order(self) -> None:
        assert _FIXTURE is not None
        manifest = load_manifest(_FIXTURE.project_file)
        entries = discover_global_entities(manifest)

        self.assertEqual(
            [entry.entity_id for entry in entries],
            ["dialogue_controller", "pause_controller", "debug_controller"],
        )
        self.assertEqual(entries[1].template_id, "entity_templates/pause_controller")


class TestItemDiscovery(unittest.TestCase):
    def test_discovers_items_from_item_paths(self) -> None:
        assert _FIXTURE is not None
        manifest = load_manifest(_FIXTURE.project_file)
        items = discover_items(manifest)

        self.assertTrue(len(items) > 0)
        ids = [entry.item_id for entry in items]
        self.assertIn("items/apple", ids)
        self.assertIn("items/copper_key", ids)


class TestManifestFallback(unittest.TestCase):
    def test_load_by_directory(self) -> None:
        """load_manifest should accept a directory path too."""
        assert _FIXTURE is not None
        manifest = load_manifest(_FIXTURE.project_root)
        self.assertEqual(manifest.project_root, _FIXTURE.project_root.resolve())

    def test_defaults_display_dimensions_when_shared_variables_are_missing(self) -> None:
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
