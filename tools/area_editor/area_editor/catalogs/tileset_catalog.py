"""Tileset image loading, GID resolution, and tile-frame extraction.

Loads tileset PNGs as ``QPixmap`` instances and caches individual tile
frames so the canvas never decodes the same frame twice.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QPixmap

from area_editor.documents.area_document import TilesetRef
from area_editor.project_io.asset_resolver import AssetResolver

log = logging.getLogger(__name__)

# Bright magenta placeholder for missing / out-of-range tiles.
_PLACEHOLDER_COLOR = QColor(255, 0, 255)


class TilesetCatalog:
    """Load tileset images and extract individual tile frames by GID."""

    def __init__(self, resolver: AssetResolver) -> None:
        self._resolver = resolver
        self._sheet_cache: dict[str, QPixmap | None] = {}
        self._frame_cache: dict[tuple[str, int], QPixmap] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_tile_pixmap(
        self,
        gid: int,
        tilesets: list[TilesetRef],
        fallback_size: int = 16,
    ) -> QPixmap | None:
        """Return the tile-frame pixmap for *gid*, or ``None`` for empty."""
        if gid == 0:
            return None

        tileset, local_index = self._resolve_gid(gid, tilesets)
        if tileset is None:
            return self._placeholder(fallback_size)

        cache_key = (tileset.path, local_index)
        cached = self._frame_cache.get(cache_key)
        if cached is not None:
            return cached

        sheet = self._load_sheet(tileset.path)
        if sheet is None:
            return self._placeholder(tileset.tile_width)

        cols = sheet.width() // tileset.tile_width
        if cols == 0:
            return self._placeholder(tileset.tile_width)

        col = local_index % cols
        row = local_index // cols

        src = QRect(
            col * tileset.tile_width,
            row * tileset.tile_height,
            tileset.tile_width,
            tileset.tile_height,
        )

        # Out-of-range guard
        if (src.right() >= sheet.width()) or (src.bottom() >= sheet.height()):
            log.warning(
                "GID %d (local %d) is out of range for tileset %s (%dx%d)",
                gid,
                local_index,
                tileset.path,
                sheet.width(),
                sheet.height(),
            )
            return self._placeholder(tileset.tile_width)

        frame = sheet.copy(src)
        self._frame_cache[cache_key] = frame
        return frame

    def get_sprite_frame(
        self,
        authored_path: str,
        frame_width: int,
        frame_height: int,
        frame_index: int = 0,
    ) -> QPixmap | None:
        """Extract a single frame from a sprite sheet by path and index.

        Used for entity visual rendering (not GID-based).
        """
        cache_key = (authored_path, frame_index)
        cached = self._frame_cache.get(cache_key)
        if cached is not None:
            return cached

        sheet = self._load_sheet(authored_path)
        if sheet is None:
            return None

        cols = sheet.width() // frame_width
        if cols == 0:
            return None

        col = frame_index % cols
        row = frame_index // cols
        src = QRect(
            col * frame_width,
            row * frame_height,
            frame_width,
            frame_height,
        )

        if src.right() >= sheet.width() or src.bottom() >= sheet.height():
            return None

        frame = sheet.copy(src)
        self._frame_cache[cache_key] = frame
        return frame

    def get_sheet(self, authored_path: str) -> QPixmap | None:
        """Return the full tileset sheet pixmap, or ``None`` if missing."""
        return self._load_sheet(authored_path)

    def get_frame_count(self, authored_path: str, tile_width: int, tile_height: int) -> int:
        """Return the number of whole frames in a sheet for the given slice size."""
        if tile_width <= 0 or tile_height <= 0:
            return 0
        sheet = self._load_sheet(authored_path)
        if sheet is None:
            return 0
        return (sheet.width() // tile_width) * (sheet.height() // tile_height)

    def get_tileset_frame_count(self, tileset: TilesetRef) -> int:
        """Return the frame count for one tileset reference."""
        return self.get_frame_count(tileset.path, tileset.tile_width, tileset.tile_height)

    def clear(self) -> None:
        """Drop all cached data (e.g. when switching projects)."""
        self._sheet_cache.clear()
        self._frame_cache.clear()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_gid(
        gid: int,
        tilesets: list[TilesetRef],
    ) -> tuple[TilesetRef | None, int]:
        """Find the tileset that owns *gid* and return (tileset, local_index)."""
        best: TilesetRef | None = None
        for ts in tilesets:
            if ts.firstgid <= gid:
                if best is None or ts.firstgid > best.firstgid:
                    best = ts
        if best is None:
            return None, 0
        return best, gid - best.firstgid

    def _load_sheet(self, authored_path: str) -> QPixmap | None:
        if authored_path in self._sheet_cache:
            return self._sheet_cache[authored_path]

        resolved = self._resolver.resolve(authored_path)
        if resolved is None or not resolved.is_file():
            log.warning("Tileset image not found: %s", authored_path)
            self._sheet_cache[authored_path] = None
            return None

        pm = QPixmap(str(resolved))
        if pm.isNull():
            log.warning("Failed to load tileset image: %s", resolved)
            self._sheet_cache[authored_path] = None
            return None

        self._sheet_cache[authored_path] = pm
        return pm

    @staticmethod
    def _placeholder(size: int) -> QPixmap:
        pm = QPixmap(size, size)
        pm.fill(_PLACEHOLDER_COLOR)
        return pm
