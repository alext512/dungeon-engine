"""Tests for asset path resolution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from area_editor.project_io.asset_resolver import AssetResolver
from area_editor.project_io.project_manifest import load_manifest
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


class TestAssetResolver(unittest.TestCase):
    def setUp(self) -> None:
        assert _FIXTURE is not None
        manifest = load_manifest(_FIXTURE.project_file)
        self.resolver = AssetResolver(manifest.asset_paths)

    def test_resolve_existing_tileset(self) -> None:
        result = self.resolver.resolve("assets/project/tiles/showcase_tiles.png")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.is_file())

    def test_resolve_missing_returns_none(self) -> None:
        result = self.resolver.resolve("assets/nonexistent/fake_tileset.png")
        self.assertIsNone(result)

    def test_resolve_returns_path_object(self) -> None:
        result = self.resolver.resolve("assets/project/tiles/showcase_tiles.png")
        self.assertIsNotNone(result)
        self.assertIsInstance(result, Path)


if __name__ == "__main__":
    unittest.main()
