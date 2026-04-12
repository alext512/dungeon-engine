"""Validate repo-local or explicitly provided project manifests."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile

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
    return sorted((REPO_ROOT / "projects").glob("*/project.json"))


def _positive_int(raw_value: str) -> int:
    """Parse one strictly positive integer CLI value."""
    value = int(raw_value)
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return value


@contextmanager
def _temporary_argv(argv: list[str]):
    """Temporarily replace sys.argv while calling run_game.main()."""
    original_argv = sys.argv[:]
    sys.argv = argv
    try:
        yield
    finally:
        sys.argv = original_argv


def _run_headless_smoke(project_json: Path, *, max_frames: int) -> None:
    """Exercise the real run_game.py startup path in headless mode."""
    import run_game
    from dungeon_engine import config

    original_launcher_state_path = config.LAUNCHER_STATE_PATH
    original_sdl_driver = os.environ.get("SDL_VIDEODRIVER")
    with tempfile.TemporaryDirectory() as temp_dir:
        config.LAUNCHER_STATE_PATH = Path(temp_dir) / "launcher_state.json"
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        try:
            with _temporary_argv(
                [
                    "run_game.py",
                    "--project",
                    str(project_json),
                    "--headless",
                    "--max-frames",
                    str(max_frames),
                ]
            ):
                exit_code = run_game.main()
        finally:
            config.LAUNCHER_STATE_PATH = original_launcher_state_path
            if original_sdl_driver is None:
                os.environ.pop("SDL_VIDEODRIVER", None)
            else:
                os.environ["SDL_VIDEODRIVER"] = original_sdl_driver

    if exit_code != 0:
        raise RuntimeError(f"run_game.py exited with code {exit_code}.")


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
    parser.add_argument(
        "--headless-smoke",
        action="store_true",
        help="Also run the normal startup path headlessly for each project that passes validation.",
    )
    parser.add_argument(
        "--max-frames",
        type=_positive_int,
        default=2,
        help="Frame count for --headless-smoke. Defaults to 2.",
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
            if args.headless_smoke:
                try:
                    _run_headless_smoke(project_json, max_frames=args.max_frames)
                except Exception as exc:
                    print(
                        f"{project_json}: headless startup smoke failed ({exc}).",
                        file=sys.stderr,
                    )
                    failed = True
                else:
                    print(f"{project.project_root.name}: headless startup smoke OK")
            continue
        print(
            f"{project_json}: startup validation failed ({type(error).__name__}).",
            file=sys.stderr,
        )
        failed = True

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
