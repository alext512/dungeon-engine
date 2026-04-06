from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import CommandContext, execute_registered_command
from dungeon_engine.engine.audio import AudioPlayer
from dungeon_engine.world.area import Area
from dungeon_engine.world.world import World


def _minimal_runtime_area() -> Area:
    return Area(
        area_id="areas/test_room",
        tile_size=16,
        tilesets=[],
        tile_layers=[],
        cell_flags=[],
    )


class _RecordingAudioPlayer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def play_audio(self, path: str, *, volume: float | None = None) -> bool:
        self.calls.append(("play_audio", (path,), {"volume": volume}))
        return True

    def set_sound_volume(self, volume: float) -> None:
        self.calls.append(("set_sound_volume", (float(volume),), {}))

    def play_music(
        self,
        path: str,
        *,
        loop: bool = True,
        volume: float | None = None,
        restart_if_same: bool = False,
    ) -> bool:
        self.calls.append(
            (
                "play_music",
                (path,),
                {
                    "loop": bool(loop),
                    "volume": volume,
                    "restart_if_same": bool(restart_if_same),
                },
            )
        )
        return True

    def stop_music(self, *, fade_seconds: float = 0.0) -> bool:
        self.calls.append(("stop_music", (), {"fade_seconds": float(fade_seconds)}))
        return True

    def pause_music(self) -> bool:
        self.calls.append(("pause_music", (), {}))
        return True

    def resume_music(self) -> bool:
        self.calls.append(("resume_music", (), {}))
        return True

    def set_music_volume(self, volume: float) -> None:
        self.calls.append(("set_music_volume", (float(volume),), {}))


class _FakeAudioChannel:
    def __init__(self) -> None:
        self.volume: float | None = None

    def set_volume(self, volume: float) -> None:
        self.volume = float(volume)


class _FakeSound:
    def __init__(self, channel: _FakeAudioChannel | None) -> None:
        self.channel = channel
        self.play_calls = 0

    def play(self) -> _FakeAudioChannel | None:
        self.play_calls += 1
        return self.channel


class _FakeMusicController:
    def __init__(self) -> None:
        self.loaded_paths: list[str] = []
        self.play_calls: list[int] = []
        self.volume_calls: list[float] = []
        self.pause_calls = 0
        self.unpause_calls = 0
        self.stop_calls = 0
        self.fadeout_calls: list[int] = []
        self.busy = False

    def load(self, path: str) -> None:
        self.loaded_paths.append(str(path))

    def play(self, loops: int = 0) -> None:
        self.play_calls.append(int(loops))
        self.busy = True

    def set_volume(self, volume: float) -> None:
        self.volume_calls.append(float(volume))

    def get_busy(self) -> bool:
        return self.busy

    def pause(self) -> None:
        self.pause_calls += 1

    def unpause(self) -> None:
        self.unpause_calls += 1
        self.busy = True

    def stop(self) -> None:
        self.stop_calls += 1
        self.busy = False

    def fadeout(self, milliseconds: int) -> None:
        self.fadeout_calls.append(int(milliseconds))
        self.busy = False


class _FakeAudioAssetManager:
    def __init__(self, sound: _FakeSound | None = None, *, music_path: str = "C:/tmp/theme.ogg") -> None:
        self.sound = sound or _FakeSound(_FakeAudioChannel())
        self.music_path = Path(music_path)
        self.requested_sound_paths: list[str] = []
        self.requested_asset_paths: list[str] = []

    def get_sound(self, relative_path: str) -> _FakeSound:
        self.requested_sound_paths.append(str(relative_path))
        return self.sound

    def resolve_asset_path(self, relative_path: str) -> Path:
        self.requested_asset_paths.append(str(relative_path))
        return self.music_path


class AudioRuntimeTests(unittest.TestCase):
    def _make_command_context(self) -> tuple[CommandRegistry, CommandContext]:
        registry = CommandRegistry()
        register_builtin_commands(registry)
        context = CommandContext(
            area=_minimal_runtime_area(),
            world=World(),
            collision_system=None,  # type: ignore[arg-type]
            movement_system=None,  # type: ignore[arg-type]
            interaction_system=None,  # type: ignore[arg-type]
            animation_system=None,  # type: ignore[arg-type]
        )
        return registry, context

    def test_audio_commands_forward_parameters_to_audio_player(self) -> None:
        registry, context = self._make_command_context()
        audio_player = _RecordingAudioPlayer()
        context.audio_player = audio_player

        execute_registered_command(
            registry,
            context,
            "play_audio",
            {"path": "assets/project/sfx/click.wav", "volume": 0.25},
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_sound_volume",
            {"volume": 0.5},
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "play_music",
            {
                "path": "assets/project/music/field.ogg",
                "loop": False,
                "volume": 0.8,
                "restart_if_same": True,
            },
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "pause_music",
            {},
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "resume_music",
            {},
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "set_music_volume",
            {"volume": 0.6},
        ).update(0.0)
        execute_registered_command(
            registry,
            context,
            "stop_music",
            {"fade_seconds": 1.25},
        ).update(0.0)

        self.assertEqual(
            audio_player.calls,
            [
                ("play_audio", ("assets/project/sfx/click.wav",), {"volume": 0.25}),
                ("set_sound_volume", (0.5,), {}),
                (
                    "play_music",
                    ("assets/project/music/field.ogg",),
                    {"loop": False, "volume": 0.8, "restart_if_same": True},
                ),
                ("pause_music", (), {}),
                ("resume_music", (), {}),
                ("set_music_volume", (0.6,), {}),
                ("stop_music", (), {"fade_seconds": 1.25}),
            ],
        )

    def test_audio_player_supports_sound_volume_and_music_track_control(self) -> None:
        fake_channel = _FakeAudioChannel()
        fake_sound = _FakeSound(fake_channel)
        fake_music = _FakeMusicController()
        asset_manager = _FakeAudioAssetManager(sound=fake_sound, music_path="C:/tmp/field.ogg")
        expected_music_path = str(Path("C:/tmp/field.ogg"))

        with patch("pygame.mixer.get_init", return_value=(44100, -16, 2)):
            with patch("pygame.mixer.music", fake_music):
                player = AudioPlayer(asset_manager, enabled=True)
                player.set_sound_volume(0.5)

                self.assertTrue(player.play_audio("assets/project/sfx/click.wav", volume=0.6))
                self.assertEqual(asset_manager.requested_sound_paths, ["assets/project/sfx/click.wav"])
                self.assertEqual(fake_sound.play_calls, 1)
                self.assertAlmostEqual(fake_channel.volume or 0.0, 0.3)

                self.assertTrue(player.play_music("assets/project/music/field.ogg", volume=0.7))
                self.assertEqual(asset_manager.requested_asset_paths, ["assets/project/music/field.ogg"])
                self.assertEqual(fake_music.loaded_paths, [expected_music_path])
                self.assertEqual(fake_music.play_calls, [-1])
                self.assertAlmostEqual(player.music_volume, 0.7)
                self.assertEqual(player.current_music_path, expected_music_path)

                self.assertTrue(player.play_music("assets/project/music/field.ogg"))
                self.assertEqual(fake_music.loaded_paths, [expected_music_path])

                self.assertTrue(player.pause_music())
                self.assertTrue(player.music_paused)
                self.assertEqual(fake_music.pause_calls, 1)

                self.assertTrue(player.resume_music())
                self.assertFalse(player.music_paused)
                self.assertEqual(fake_music.unpause_calls, 1)

                player.set_music_volume(0.4)
                self.assertAlmostEqual(player.music_volume, 0.4)
                self.assertAlmostEqual(fake_music.volume_calls[-1], 0.4)

                self.assertTrue(player.stop_music(fade_seconds=0.5))
                self.assertEqual(fake_music.fadeout_calls, [500])
                self.assertIsNone(player.current_music_path)
