"""Validate repo-local or explicitly provided project manifests."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dungeon_engine.project_context import load_project
from dungeon_engine.startup_validation import validate_project_startup


def _manifest_path(path: Path) -> Path:
    """Return the manifest path for a project directory or manifest file."""
    resolved = path.resolve()
    if resolved.is_dir():
        return resolved / "project.json"
    return resolved


def _default_project_manifests() -> list[Path]:
    """Return repo-local project manifests under projects/."""
    return sorted(Path("projects").glob("*/project.json"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate project manifests through the startup validation path.",
    )
    parser.add_argument(
        "projects",
        nargs="*",
        type=Path,
        help="Project directories or project.json files. Defaults to projects/*/project.json.",
    )
    args = parser.parse_args(argv)

    project_manifests = (
        [_manifest_path(path) for path in args.projects]
        if args.projects
        else _default_project_manifests()
    )
    if not project_manifests:
        print("No repo-local project manifests found under projects/.")
        return 0

    failed = False
    for project_json in project_manifests:
        try:
            project = load_project(project_json)
        except Exception as exc:
            print(f"{project_json}: project load failed ({exc}).", file=sys.stderr)
            failed = True
            continue

        error = validate_project_startup(
            project,
            ui_title="Project Validation",
            show_dialog=False,
        )
        if error is None:
            print(f"{project.project_root.name}: startup validation OK")
            continue
        print(
            f"{project_json}: startup validation failed ({type(error).__name__}).",
            file=sys.stderr,
        )
        failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
