from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_game
from dungeon_engine import config


class StartupSmokeTests(unittest.TestCase):
    def test_new_project_runs_headless_for_two_frames(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        project_root = repo_root / "projects" / "new_project"
        if not (project_root / "project.json").is_file():
            self.skipTest(
                "Optional repo-local integration fixture 'new_project' is not available in this worktree."
            )

        original_launcher_state_path = config.LAUNCHER_STATE_PATH
        with tempfile.TemporaryDirectory() as temp_dir:
            config.LAUNCHER_STATE_PATH = Path(temp_dir) / "launcher_state.json"
            try:
                with (
                    patch.object(
                        sys,
                        "argv",
                        [
                            "run_game.py",
                            "--project",
                            str(project_root),
                            "--headless",
                            "--max-frames",
                            "2",
                        ],
                    ),
                    patch.dict(os.environ, {"SDL_VIDEODRIVER": "dummy"}),
                ):
                    self.assertEqual(run_game.main(), 0)
            finally:
                config.LAUNCHER_STATE_PATH = original_launcher_state_path


if __name__ == "__main__":
    unittest.main()
