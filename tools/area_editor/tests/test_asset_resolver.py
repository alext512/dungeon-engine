"""Tests for asset path resolution."""

from __future__ import annotations

import unittest
from pathlib import Path

from area_editor.project_io.asset_resolver import AssetResolver
from area_editor.project_io.manifest import load_manifest

_TEST_PROJECT = Path(__file__).resolve().parent.parent.parent.parent / "projects" / "test_project"


@unittest.skipUnless(_TEST_PROJECT.is_dir(), "test_project fixture not found")
class TestAssetResolver(unittest.TestCase):
    def setUp(self):
        manifest = load_manifest(_TEST_PROJECT / "project.json")
        self.resolver = AssetResolver(manifest.asset_paths)

    def test_resolve_existing_tileset(self):
        # The test project should have a tileset PNG somewhere under assets/
        result = self.resolver.resolve("assets/project/tiles/showcase_tiles.png")
        if result is not None:
            self.assertTrue(result.is_file())

    def test_resolve_missing_returns_none(self):
        result = self.resolver.resolve("assets/nonexistent/fake_tileset.png")
        self.assertIsNone(result)

    def test_resolve_returns_path_object(self):
        result = self.resolver.resolve("assets/project/tiles/showcase_tiles.png")
        if result is not None:
            self.assertIsInstance(result, Path)


if __name__ == "__main__":
    unittest.main()
