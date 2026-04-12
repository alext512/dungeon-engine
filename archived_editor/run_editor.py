"""Standalone editor entry point - pick a project and area id, then edit."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the puzzle dungeon level editor.")
    parser.add_argument(
        "area",
        nargs="?",
        default=None,
        help="Authored area id. If omitted, uses the project's startup area or opens a picker.",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Path to a project folder or project.json. "
             "If omitted, opens a picker starting from the last project location.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Use SDL's dummy video driver for automated editor smoke tests.",
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
        if args.project is None:
            print("Headless mode requires --project. Pass an area id too, or define startup_area in project.json.")
            return 1

    from dungeon_engine import config
    from dungeon_engine.display_setup import configure_process_dpi_awareness
    from dungeon_engine.launcher_state import load_launcher_state, update_launcher_state
    from dungeon_engine.logging_utils import install_exception_logging
    from dungeon_engine.project_context import load_project
    from dungeon_engine.startup_validation import validate_project_startup

    if not args.headless:
        configure_process_dpi_awareness()

    logger = install_exception_logging()
    launcher_state = load_launcher_state()

    project_path = _choose_project_path(args.project, launcher_state, config.PROJECTS_DIR)
    if project_path is None:
        print("No project selected.")
        return 0

    project = load_project(project_path)
    validation_error = validate_project_startup(
        project,
        ui_title="Cannot open project",
        show_dialog=not args.headless,
    )
    if validation_error is not None:
        return 1
    update_launcher_state(last_project=str(project_path))

    area_id = _choose_area_id(
        args.area,
        project,
        launcher_state.last_editor_area,
        allow_picker=not args.headless,
    )
    if area_id is None:
        print("No area selected.")
        return 0
    area_path = _resolve_area_id(project, area_id)

    update_launcher_state(
        last_project=str(project_path),
        last_editor_area=area_id,
    )

    try:
        from dungeon_engine.editor.editor_app import EditorApp

        app = EditorApp(area_path, project)
        app.run(max_frames=args.max_frames)
        return 0
    except Exception:
        logger.exception("Fatal error while running the editor")
        raise


def _choose_project_path(cli_project, launcher_state, fallback_dir) -> Path | None:
    """Choose a project path from CLI or a picker rooted at the last project location."""
    if cli_project:
        return _normalize_project_path(Path(cli_project))

    picked = _pick_project_file(_default_project_path(launcher_state, fallback_dir))
    if picked is None:
        return None
    return _normalize_project_path(picked)


def _choose_area_id(cli_area, project, remembered_area, allow_picker: bool = True) -> str | None:
    """Choose an area id from CLI, project startup area, or a file picker."""
    if cli_area:
        return _resolve_area_argument(project, cli_area)

    startup_area_id = _resolve_project_startup_area(project)
    if startup_area_id is not None:
        return startup_area_id

    if not allow_picker:
        return None

    return _pick_area_id(project, _default_area_id(project, remembered_area))


def _pick_project_file(default_path: Path) -> Path | None:
    """Open a file dialog to pick a project.json file."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()

    file_path = filedialog.askopenfilename(
        title="Select project.json",
        initialdir=str(default_path.parent if default_path.is_file() else default_path),
        initialfile=default_path.name if default_path.is_file() else "",
        filetypes=[("Project file", "project.json"), ("JSON files", "*.json"), ("All files", "*.*")],
    )
    root.destroy()

    if not file_path:
        return None
    return Path(file_path)


def _pick_area_id(project, default_area_id: str | None) -> str | None:
    """Open a file dialog to pick an area file, then return its canonical area id."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()
    default_path = _default_area_path(project, default_area_id)

    file_path = filedialog.askopenfilename(
        title="Select area file",
        initialdir=str(default_path.parent if default_path.is_file() else default_path),
        initialfile=default_path.name if default_path.is_file() else "",
        filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
    )
    root.destroy()

    if not file_path:
        return None
    return _area_id_from_path(project, Path(file_path))


def _resolve_area_argument(project, area_argument: str) -> str:
    """Resolve and canonicalize one authored area id from the CLI."""
    area_reference = str(area_argument).strip()
    if not area_reference:
        raise FileNotFoundError("Area id must not be empty.")

    resolved_reference = project.resolve_area_reference(area_reference)
    if resolved_reference is None:
        raise FileNotFoundError(
            f"Cannot resolve authored area id '{area_reference}' in project '{project.project_root}'."
        )
    return project.area_path_to_reference(resolved_reference)


def _resolve_area_id(project, area_id: str) -> Path:
    """Resolve one canonical authored area id to its JSON file path."""
    resolved = project.resolve_area_reference(area_id)
    if resolved is None:
        raise FileNotFoundError(
            f"Cannot resolve authored area id '{area_id}' in project '{project.project_root}'."
        )
    return resolved


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


def _default_project_path(launcher_state, fallback_dir) -> Path:
    """Pick a sensible initial project path for the project picker."""
    remembered = _existing_path(launcher_state.last_project)
    if remembered is not None:
        return remembered
    return Path(fallback_dir) / "test_project" / "project.json"


def _default_area_id(project, remembered_area: str | None) -> str | None:
    """Pick a sensible initial area id for the area picker."""
    if remembered_area:
        resolved = project.resolve_area_reference(remembered_area)
        if resolved is not None:
            return project.area_path_to_reference(resolved)

    startup_area = _resolve_project_startup_area(project)
    if startup_area is not None:
        return startup_area

    area_ids = project.list_area_ids()
    if area_ids:
        return area_ids[0]
    return None


def _default_area_path(project, default_area_id: str | None) -> Path:
    """Resolve the picker default from an area id when possible."""
    if default_area_id:
        resolved = project.resolve_area_reference(default_area_id)
        if resolved is not None:
            return resolved
    for area_dir in project.area_paths:
        if area_dir.is_dir():
            return area_dir
    return project.project_root


def _resolve_project_startup_area(project) -> str | None:
    """Resolve the project's authored startup area id, if any."""
    startup_area = getattr(project, "startup_area", None)
    if not startup_area:
        return None

    resolved = project.resolve_area_reference(startup_area)
    if resolved is None:
        return None
    return project.area_path_to_reference(resolved)


def _area_id_from_path(project, area_path: Path) -> str:
    """Convert a picked area file into its canonical project area id."""
    resolved = area_path.resolve()
    try:
        return project.area_path_to_reference(resolved)
    except ValueError as exc:
        raise FileNotFoundError(
            f"Selected area '{resolved}' is outside the configured area roots for project '{project.project_root}'."
        ) from exc


if __name__ == "__main__":
    raise SystemExit(main())

