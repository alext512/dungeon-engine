"""Resolve authored asset paths to absolute filesystem paths.

Mirrors the runtime's ``ProjectContext.resolve_asset()`` two-candidate
strategy without importing runtime code.
"""

from __future__ import annotations

from pathlib import Path


class AssetResolver:
    """Locate project assets across configured search paths."""

    def __init__(self, asset_paths: list[Path]) -> None:
        self._asset_paths = list(asset_paths)

    def resolve(self, authored_path: str) -> Path | None:
        """Find *authored_path* on disk, or return ``None``.

        Tries two candidates per asset directory:

        1. ``asset_dir.parent / authored_path``  (preferred layout)
        2. ``asset_dir / authored_path``          (direct layout)
        """
        rel = Path(authored_path)
        for asset_dir in self._asset_paths:
            rooted = asset_dir.parent / rel
            if rooted.exists():
                return rooted
            direct = asset_dir / rel
            if direct.exists():
                return direct
        return None
