"""Standalone game entry point - pick a project and area JSON file, then play."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the puzzle dungeon game.")
    parser.add_argument(
        "area",
        nargs="?",
        default=None,
        help="Path to an area JSON file. If omitted, reopens the last area or uses a file picker.",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Path to a project folder or project.json. "
             "If omitted, reopens the last project or uses a file picker.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Use SDL's dummy video driver for automated smoke tests.",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Stop automatically after the given number of frames.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.headless:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    from puzzle_dungeon import config
    from puzzle_dungeon.display_setup import configure_process_dpi_awareness
    from puzzle_dungeon.engine.game import Game
    from puzzle_dungeon.launcher_state import load_launcher_state, update_launcher_state
    from puzzle_dungeon.logging_utils import install_exception_logging
    from puzzle_dungeon.project import load_project
    from puzzle_dungeon.world.loader import set_active_project

    if not args.headless:
        configure_process_dpi_awareness()

    logger = install_exception_logging()
    launcher_state = load_launcher_state()

    project_path = _choose_project_path(args.project, launcher_state, config.PROJECT_ROOT.parent)
    if project_path is None:
        print("No project selected.")
        return 0

    project = load_project(project_path)
    update_launcher_state(last_project=str(project_path))
    set_active_project(project)

    area_path = _choose_area_path(args.area, project, launcher_state.last_game_area)
    if area_path is None:
        print("No area file selected.")
        return 0

    update_launcher_state(
        last_project=str(project_path),
        last_game_area=str(area_path.resolve()),
    )

    try:
        game = Game(area_path=area_path, project=project)
        game.run(max_frames=args.max_frames)
        return 0
    except Exception:
        logger.exception("Fatal error while running the game")
        raise


def _choose_project_path(cli_project, launcher_state, fallback_dir) -> Path | None:
    """Choose a project path from CLI, persisted state, or file picker."""
    if cli_project:
        return _normalize_project_path(Path(cli_project))

    remembered = _existing_path(launcher_state.last_project)
    if remembered is not None:
        return _normalize_project_path(remembered)

    picked = _pick_project_file(_default_project_dir(launcher_state, fallback_dir))
    if picked is None:
        return None
    return _normalize_project_path(picked)


def _choose_area_path(cli_area, project, remembered_area) -> Path | None:
    """Choose an area path from CLI, persisted state, or file picker."""
    if cli_area:
        return _resolve_area_path(project, Path(cli_area))

    remembered = _resolve_remembered_area(project, remembered_area)
    if remembered is not None:
        return remembered

    area_files = project.list_area_files()
    default_dir = area_files[0].parent if area_files else project.project_root
    return _pick_area_file(default_dir)


def _pick_project_file(default_dir) -> Path | None:
    """Open a file dialog to pick a project.json file."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()

    file_path = filedialog.askopenfilename(
        title="Select project.json",
        initialdir=str(default_dir),
        filetypes=[("Project file", "project.json"), ("JSON files", "*.json"), ("All files", "*.*")],
    )
    root.destroy()

    if not file_path:
        return None
    return Path(file_path)


def _pick_area_file(default_dir) -> Path | None:
    """Open a file dialog to pick an area JSON file."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()

    file_path = filedialog.askopenfilename(
        title="Select area file",
        initialdir=str(default_dir),
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
    )
    root.destroy()

    if not file_path:
        return None
    return Path(file_path)


def _resolve_area_path(project, area_path: Path) -> Path:
    """Resolve an area argument against the current project."""
    candidates: list[Path] = [area_path]
    if not area_path.is_absolute():
        candidates.append(project.project_root / area_path)
        candidates.extend(area_dir / area_path for area_dir in project.area_paths)

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return area_path.resolve()


def _normalize_project_path(project_path: Path) -> Path:
    """Normalize a project argument into an absolute project.json path."""
    resolved = project_path.resolve()
    if resolved.is_dir():
        return (resolved / "project.json").resolve()
    return resolved


def _existing_path(path_str: str | None) -> Path | None:
    """Return an existing path from persisted launcher state."""
    if not path_str:
        return None
    candidate = Path(path_str)
    if candidate.exists():
        return candidate.resolve()
    return None


def _default_project_dir(launcher_state, fallback_dir) -> Path:
    """Pick a sensible initial directory for the project picker."""
    remembered = _existing_path(launcher_state.last_project)
    if remembered is not None:
        return remembered.parent
    return Path(fallback_dir)


def _resolve_remembered_area(project, remembered_area: str | None) -> Path | None:
    """Resolve the last-opened game area against the selected project."""
    if not remembered_area:
        return None

    remembered_path = Path(remembered_area)
    if remembered_path.exists() and _area_belongs_to_project(project, remembered_path.resolve()):
        return remembered_path.resolve()

    resolved = _resolve_area_path(project, remembered_path)
    if resolved.exists() and _area_belongs_to_project(project, resolved):
        return resolved
    return None


def _area_belongs_to_project(project, area_path: Path) -> bool:
    """Return True when an area path is inside one of the project's area roots."""
    resolved = area_path.resolve()
    for area_dir in project.area_paths:
        try:
            resolved.relative_to(area_dir.resolve())
            return True
        except ValueError:
            continue
    try:
        resolved.relative_to(project.project_root.resolve())
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
