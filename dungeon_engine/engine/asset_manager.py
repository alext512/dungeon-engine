"""Load and slice simple PNG assets for tiles and sprite sheets."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from dungeon_engine.project import ProjectContext


class AssetManager:
    """Cache loaded images and sliced frames for the prototype asset pipeline.

    Asset paths are always resolved through the active project's configured
    asset search paths.
    """

    def __init__(self, project: ProjectContext) -> None:
        self._project = project
        self._image_cache: dict[Path, pygame.Surface] = {}
        self._frame_cache: dict[tuple[Path, int, int], list[pygame.Surface]] = {}
        self._sound_cache: dict[Path, pygame.mixer.Sound] = {}

    def _resolve(self, relative_path: str) -> Path:
        """Turn a relative asset path into an absolute filesystem path."""
        resolved = self._project.resolve_asset(relative_path)
        if resolved is not None:
            return resolved
        raise FileNotFoundError(
            f"Asset '{relative_path}' could not be resolved in project '{self._project.project_root}'."
        )

    def resolve_asset_path(self, relative_path: str) -> Path:
        """Return the absolute filesystem path for one authored asset path."""
        return self._resolve(relative_path)

    def get_frame(
        self,
        relative_path: str,
        frame_width: int,
        frame_height: int,
        frame_index: int,
    ) -> pygame.Surface:
        """Return a single frame from a sheet or standalone image."""
        asset_path = self._resolve(relative_path)
        frames = self._get_frames(asset_path, frame_width, frame_height)
        if not frames:
            raise ValueError(f"No frames available in asset '{asset_path}'.")
        safe_index = max(0, min(frame_index, len(frames) - 1))
        return frames[safe_index]

    def get_image(self, relative_path: str) -> pygame.Surface:
        """Return a cached full image surface by path relative to the data folder."""
        asset_path = self.resolve_asset_path(relative_path)
        return self._load_image(asset_path)

    def get_image_size(self, relative_path: str) -> tuple[int, int]:
        """Return (width, height) in pixels for a tileset or sprite image."""
        image = self.get_image(relative_path)
        return (image.get_width(), image.get_height())

    def get_sound(self, relative_path: str) -> pygame.mixer.Sound:
        """Return a cached sound object by path relative to the active project."""
        asset_path = self.resolve_asset_path(relative_path)
        return self._load_sound(asset_path)

    def get_frame_count(
        self,
        relative_path: str,
        frame_width: int,
        frame_height: int,
    ) -> int:
        """Return the total number of frames in a sprite sheet."""
        img_w, img_h = self.get_image_size(relative_path)
        columns = max(1, img_w // frame_width)
        rows = max(1, img_h // frame_height)
        return columns * rows

    def get_columns(
        self,
        relative_path: str,
        frame_width: int,
    ) -> int:
        """Return how many tile columns the image has."""
        img_w, _ = self.get_image_size(relative_path)
        return max(1, img_w // frame_width)

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

    def _load_sound(self, asset_path: Path) -> pygame.mixer.Sound:
        """Load a sound once and keep it in memory."""
        cached = self._sound_cache.get(asset_path)
        if cached is not None:
            return cached

        sound = pygame.mixer.Sound(str(asset_path))
        self._sound_cache[asset_path] = sound
        return sound

