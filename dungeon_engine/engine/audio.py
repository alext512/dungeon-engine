"""Runtime audio helper for one-shot sound effects and one music track."""

from __future__ import annotations

from dungeon_engine.logging_utils import get_logger


logger = get_logger(__name__)


class AudioPlayer:
    """Play one-shot sound effects plus one dedicated music track."""

    def __init__(self, asset_manager, *, enabled: bool = True) -> None:
        self.asset_manager = asset_manager
        self.enabled = bool(enabled)
        self.available = False
        self.sound_volume = 1.0
        self.music_volume = 1.0
        self.current_music_path: str | None = None
        self.music_loop = True
        self.music_paused = False
        self._ensure_mixer()

    def play_audio(self, relative_path: str, *, volume: float | None = None) -> bool:
        """Play a single sound effect if audio is available."""
        if not self.enabled or not self.available:
            return False
        if not relative_path:
            return False

        try:
            sound = self.asset_manager.get_sound(relative_path)
            channel = sound.play()
            if channel is None:
                return False
            channel.set_volume(self._effective_sound_volume(volume))
            return True
        except Exception:
            logger.warning("Failed to play audio '%s'.", relative_path, exc_info=True)
            return False

    def set_sound_volume(self, volume: float) -> None:
        """Set the default one-shot sound-effect volume multiplier."""
        self.sound_volume = self._clamp_volume(volume)

    def play_music(
        self,
        relative_path: str,
        *,
        loop: bool = True,
        volume: float | None = None,
        restart_if_same: bool = False,
    ) -> bool:
        """Start or resume one music track on the dedicated music channel."""
        if not self.enabled or not self.available:
            return False
        if not relative_path:
            return False

        try:
            import pygame

            resolved_path = str(self.asset_manager.resolve_asset_path(relative_path))
            requested_volume = self.music_volume if volume is None else self._clamp_volume(volume)
            same_track = self.current_music_path == resolved_path

            self.music_volume = requested_volume
            self.music_loop = bool(loop)
            pygame.mixer.music.set_volume(self.music_volume)

            if same_track and not restart_if_same:
                if self.music_paused:
                    pygame.mixer.music.unpause()
                    self.music_paused = False
                    return True
                if pygame.mixer.music.get_busy():
                    return True

            pygame.mixer.music.load(resolved_path)
            pygame.mixer.music.play(-1 if self.music_loop else 0)
            pygame.mixer.music.set_volume(self.music_volume)
            self.current_music_path = resolved_path
            self.music_paused = False
            return True
        except Exception:
            logger.warning("Failed to play music '%s'.", relative_path, exc_info=True)
            return False

    def stop_music(self, *, fade_seconds: float = 0.0) -> bool:
        """Stop the current music track, optionally fading out first."""
        if not self.enabled or not self.available:
            return False

        try:
            import pygame

            fade_ms = max(0, int(float(fade_seconds) * 1000.0))
            if fade_ms > 0:
                pygame.mixer.music.fadeout(fade_ms)
            else:
                pygame.mixer.music.stop()
            self.current_music_path = None
            self.music_paused = False
            return True
        except Exception:
            logger.warning("Failed to stop music.", exc_info=True)
            return False

    def pause_music(self) -> bool:
        """Pause the current music track if one is active."""
        if not self.enabled or not self.available or self.current_music_path is None or self.music_paused:
            return False

        try:
            import pygame

            pygame.mixer.music.pause()
            self.music_paused = True
            return True
        except Exception:
            logger.warning("Failed to pause music.", exc_info=True)
            return False

    def resume_music(self) -> bool:
        """Resume the paused music track."""
        if not self.enabled or not self.available or not self.music_paused:
            return False

        try:
            import pygame

            pygame.mixer.music.unpause()
            self.music_paused = False
            return True
        except Exception:
            logger.warning("Failed to resume music.", exc_info=True)
            return False

    def set_music_volume(self, volume: float) -> None:
        """Set the dedicated music-channel volume."""
        self.music_volume = self._clamp_volume(volume)
        if not self.enabled or not self.available:
            return
        try:
            import pygame

            pygame.mixer.music.set_volume(self.music_volume)
        except Exception:
            logger.warning("Failed to set music volume.", exc_info=True)

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

    def _effective_sound_volume(self, volume: float | None) -> float:
        """Return one clamped per-play sound-effect volume."""
        requested_volume = 1.0 if volume is None else float(volume)
        return self._clamp_volume(self.sound_volume * requested_volume)

    def _clamp_volume(self, volume: float | int) -> float:
        """Clamp one authored volume into pygame's expected 0..1 range."""
        return max(0.0, min(1.0, float(volume)))
