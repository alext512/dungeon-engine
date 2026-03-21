"""Project manifest: tells the engine where to find areas, entities, and assets.

A project is a folder containing a ``project.json`` file that declares search
paths for game data. All paths inside the manifest are relative to the folder
that contains the ``project.json`` file.

Example ``project.json``::

    {
        "entity_paths": ["entities/"],
        "asset_paths": ["assets/"],
        "area_paths": ["areas/"]
    }

If any section is omitted the engine falls back to conventional folders inside
the selected project root:

- ``entities/``
- ``assets/``
- ``areas/``
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass
class ProjectContext:
    """Resolved search paths for a single project."""

    project_root: Path
    entity_paths: list[Path] = field(default_factory=list)
    asset_paths: list[Path] = field(default_factory=list)
    area_paths: list[Path] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Entity template discovery
    # ------------------------------------------------------------------

    def list_entity_template_ids(self) -> list[str]:
        """Return sorted unique template ids from all entity paths."""
        ids: set[str] = set()
        for directory in self.entity_paths:
            if directory.is_dir():
                ids.update(p.stem for p in directory.glob("*.json"))
        return sorted(ids)

    def find_entity_template(self, template_id: str) -> Path | None:
        """Return the first matching template path, or *None*."""
        for directory in self.entity_paths:
            candidate = directory / f"{template_id}.json"
            if candidate.exists():
                return candidate
        return None

    # ------------------------------------------------------------------
    # Asset resolution
    # ------------------------------------------------------------------

    def resolve_asset(self, relative_path: str) -> Path | None:
        """Find an asset file across all asset search paths.

        ``relative_path`` is the path stored in area/entity JSON
        (e.g. ``"assets/tiles/basic_tiles.png"``).
        """
        rel_path = Path(relative_path)
        for directory in self.asset_paths:
            # Preferred layout: asset_paths entries point at the asset root
            # itself (for example ".../test_project/assets"), while authored
            # content stores paths like "assets/tiles/foo.png".
            rooted_candidate = directory.parent / rel_path
            if rooted_candidate.exists():
                return rooted_candidate

            direct_candidate = directory / rel_path
            if direct_candidate.exists():
                return direct_candidate
        return None

    # ------------------------------------------------------------------
    # Tileset discovery
    # ------------------------------------------------------------------

    def list_tileset_paths(self) -> list[str]:
        """Scan asset search paths recursively for PNGs.

        Returns paths relative to the asset root they were found in, using
        the same ``"assets/tiles/foo.png"`` convention the engine expects.
        """
        result: dict[str, Path] = {}
        for asset_dir in self.asset_paths:
            if not asset_dir.is_dir():
                continue
            for png in asset_dir.rglob("*.png"):
                # Key = relative from the asset_dir parent so existing JSON
                # paths like "assets/tiles/basic.png" keep working.
                rel = str(png.relative_to(asset_dir.parent)).replace("\\", "/")
                if rel not in result:
                    result[rel] = png
        return sorted(result.keys())

    # ------------------------------------------------------------------
    # Area discovery
    # ------------------------------------------------------------------

    def list_area_files(self) -> list[Path]:
        """Return all area JSON files across all area paths."""
        files: list[Path] = []
        seen: set[Path] = set()
        for directory in self.area_paths:
            if not directory.is_dir():
                continue
            for f in sorted(directory.glob("*.json")):
                resolved = f.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    files.append(f)
        return files


def load_project(project_path: Path) -> ProjectContext:
    """Load a project manifest and return a resolved context.

    ``project_path`` can be:
    - A path to ``project.json`` directly
    - A path to a folder that contains ``project.json``
    """
    if project_path.is_dir():
        project_file = project_path / "project.json"
    else:
        project_file = project_path

    project_root = project_file.parent.resolve()

    if project_file.exists():
        raw: dict[str, Any] = json.loads(project_file.read_text(encoding="utf-8"))
    else:
        raw = {}

    def _resolve_paths(key: str, default_name: str) -> list[Path]:
        entries = raw.get(key, [])
        if not entries:
            fallback = project_root / default_name
            return [fallback] if fallback.is_dir() else []
        return [(project_root / p).resolve() for p in entries]

    return ProjectContext(
        project_root=project_root,
        entity_paths=_resolve_paths("entity_paths", "entities"),
        asset_paths=_resolve_paths("asset_paths", "assets"),
        area_paths=_resolve_paths("area_paths", "areas"),
    )


def default_project(project_root: Path | None = None) -> ProjectContext:
    """Return a project context using standard folders under the chosen root."""
    root = (project_root or Path.cwd()).resolve()

    def _optional_dir(path: Path) -> list[Path]:
        return [path] if path.is_dir() else []

    return ProjectContext(
        project_root=root,
        entity_paths=_optional_dir(root / "entities"),
        asset_paths=_optional_dir(root / "assets"),
        area_paths=_optional_dir(root / "areas"),
    )
