"""Small runtime audio helper for one-shot sound effects."""

from __future__ import annotations

from dungeon_engine.logging_utils import get_logger


logger = get_logger(__name__)


class AudioPlayer:
    """Play simple one-shot sound effects through pygame's mixer."""

    def __init__(self, asset_manager, *, enabled: bool = True) -> None:
        self.asset_manager = asset_manager
        self.enabled = bool(enabled)
        self.available = False
        self._ensure_mixer()

    def play_audio(self, relative_path: str) -> bool:
        """Play a single audio asset if audio is available."""
        if not self.enabled or not self.available:
            return False
        if not relative_path:
            return False

        try:
            sound = self.asset_manager.get_sound(relative_path)
            sound.play()
            return True
        except Exception:
            logger.warning("Failed to play audio '%s'.", relative_path, exc_info=True)
            return False

    def _ensure_mixer(self) -> None:
        """Try to initialize the mixer once without crashing the game."""
        if not self.enabled:
            return

        try:
            import pygame

            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            self.available = pygame.mixer.get_init() is not None
        except Exception:
            logger.warning("Audio mixer unavailable; continuing without sound.", exc_info=True)
            self.available = False
