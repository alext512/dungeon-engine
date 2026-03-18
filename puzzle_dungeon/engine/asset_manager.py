"""Load and slice simple PNG assets for tiles and sprite sheets."""

from __future__ import annotations

from pathlib import Path

import pygame

from puzzle_dungeon import config


class AssetManager:
    """Cache loaded images and sliced frames for the prototype asset pipeline."""

    def __init__(self) -> None:
        self._image_cache: dict[Path, pygame.Surface] = {}
        self._frame_cache: dict[tuple[Path, int, int], list[pygame.Surface]] = {}

    def get_frame(
        self,
        relative_path: str,
        frame_width: int,
        frame_height: int,
        frame_index: int,
    ) -> pygame.Surface:
        """Return a single frame from a sheet or standalone image."""
        asset_path = config.DATA_DIR / relative_path
        frames = self._get_frames(asset_path, frame_width, frame_height)
        if not frames:
            raise ValueError(f"No frames available in asset '{asset_path}'.")
        safe_index = max(0, min(frame_index, len(frames) - 1))
        return frames[safe_index]

    def get_image(self, relative_path: str) -> pygame.Surface:
        """Return a cached full image surface by path relative to the data folder."""
        asset_path = config.DATA_DIR / relative_path
        return self._load_image(asset_path)

    def _get_frames(
        self,
        asset_path: Path,
        frame_width: int,
        frame_height: int,
    ) -> list[pygame.Surface]:
        """Slice an image into a list of fixed-size frames and cache the result."""
        cache_key = (asset_path, frame_width, frame_height)
        cached = self._frame_cache.get(cache_key)
        if cached is not None:
            return cached

        image = self._load_image(asset_path)
        columns = max(1, image.get_width() // frame_width)
        rows = max(1, image.get_height() // frame_height)
        frames: list[pygame.Surface] = []
        for row in range(rows):
            for column in range(columns):
                frame = pygame.Surface((frame_width, frame_height), pygame.SRCALPHA)
                frame.blit(
                    image,
                    (0, 0),
                    pygame.Rect(
                        column * frame_width,
                        row * frame_height,
                        frame_width,
                        frame_height,
                    ),
                )
                frames.append(frame)

        self._frame_cache[cache_key] = frames
        return frames

    def _load_image(self, asset_path: Path) -> pygame.Surface:
        """Load an image once and keep it in memory."""
        cached = self._image_cache.get(asset_path)
        if cached is not None:
            return cached

        image = pygame.image.load(str(asset_path)).convert_alpha()
        self._image_cache[asset_path] = image
        return image
