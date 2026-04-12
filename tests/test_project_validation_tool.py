from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import tempfile
import unittest
from pathlib import Path

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
