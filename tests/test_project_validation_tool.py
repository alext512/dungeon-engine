from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import validate_projects


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_minimal_project(project_root: Path) -> None:
    _write_json(
        project_root / "project.json",
        {
            "area_paths": ["areas/"],
            "entity_template_paths": ["entity_templates/"],
            "command_paths": ["commands/"],
            "item_paths": ["items/"],
            "shared_variables_path": "shared_variables.json",
        },
    )
    _write_json(project_root / "shared_variables.json", {})


class ProjectValidationToolTests(unittest.TestCase):
    def test_default_project_discovery_uses_repo_root_not_cwd(self) -> None:
        with (
            tempfile.TemporaryDirectory() as repo_dir,
            tempfile.TemporaryDirectory() as cwd_dir,
        ):
            temp_repo = Path(repo_dir)
            project_root = temp_repo / "projects" / "discovered_project"
            _write_minimal_project(project_root)
            stdout = io.StringIO()
            stderr = io.StringIO()
            original_cwd = Path.cwd()

            try:
                os.chdir(cwd_dir)
                with (
                    redirect_stdout(stdout),
                    redirect_stderr(stderr),
                    patch.object(validate_projects, "REPO_ROOT", temp_repo),
                ):
                    exit_code = validate_projects.main([])
            finally:
                os.chdir(original_cwd)

        self.assertEqual(exit_code, 0)
        self.assertIn(
            "discovered_project: startup validation OK",
            stdout.getvalue(),
        )
        self.assertEqual(stderr.getvalue(), "")

    def test_project_directory_argument_runs_startup_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "tool_valid_project"
            _write_minimal_project(project_root)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = validate_projects.main([str(project_root)])

        self.assertEqual(exit_code, 0)
        self.assertIn(
            "tool_valid_project: startup validation OK",
            stdout.getvalue(),
        )
        self.assertEqual(stderr.getvalue(), "")

    def test_project_directory_argument_can_run_headless_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "tool_valid_project"
            _write_minimal_project(project_root)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                redirect_stdout(stdout),
                redirect_stderr(stderr),
                patch.object(validate_projects, "_run_headless_smoke") as smoke,
            ):
                exit_code = validate_projects.main(
                    ["--headless-smoke", "--max-frames", "5", str(project_root)]
                )

        self.assertEqual(exit_code, 0)
        smoke.assert_called_once_with(project_root / "project.json", max_frames=5)
        self.assertIn(
            "tool_valid_project: startup validation OK",
            stdout.getvalue(),
        )
        self.assertIn(
            "tool_valid_project: headless startup smoke OK",
            stdout.getvalue(),
        )
        self.assertEqual(stderr.getvalue(), "")

    def test_headless_smoke_failure_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir) / "tool_valid_project"
            _write_minimal_project(project_root)
            stdout = io.StringIO()
            stderr = io.StringIO()

            with (
                redirect_stdout(stdout),
                redirect_stderr(stderr),
                patch.object(
                    validate_projects,
                    "_run_headless_smoke",
                    side_effect=RuntimeError("boom"),
                ),
            ):
                exit_code = validate_projects.main(["--headless-smoke", str(project_root)])

        self.assertEqual(exit_code, 1)
        self.assertIn(
            "tool_valid_project: startup validation OK",
            stdout.getvalue(),
        )
        self.assertIn(
            "headless startup smoke failed (boom)",
            stderr.getvalue(),
        )

    def test_missing_project_argument_fails_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_project = Path(temp_dir) / "missing_project"
            stdout = io.StringIO()
            stderr = io.StringIO()

            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = validate_projects.main([str(missing_project)])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("project load failed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
