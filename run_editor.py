"""Standalone editor entry point - pick a project and area file, then edit."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the puzzle dungeon level editor.")
    parser.add_argument(
        "area",
        nargs="?",
        default=None,
        help="Path to an area JSON file. If omitted, uses the project's startup area or opens a picker.",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="Path to a project folder or project.json. "
             "If omitted, opens a picker starting from the last project location.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    from dungeon_engine import config
    from dungeon_engine.display_setup import configure_process_dpi_awareness
    from dungeon_engine.launcher_state import load_launcher_state, update_launcher_state
    from dungeon_engine.logging_utils import install_exception_logging
    from dungeon_engine.project import load_project
    from dungeon_engine.startup_validation import validate_project_startup
    from dungeon_engine.world.loader import set_active_project

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
        show_dialog=True,
    )
    if validation_error is not None:
        return 1
    update_launcher_state(last_project=str(project_path))
    set_active_project(project)

    area_path = _choose_area_path(args.area, project, launcher_state.last_editor_area)
    if area_path is None:
        print("No area file selected.")
        return 0

    update_launcher_state(
        last_project=str(project_path),
        last_editor_area=str(area_path.resolve()),
    )

    try:
        from dungeon_engine.editor.editor_app import EditorApp

        app = EditorApp(area_path, project)
        app.run()
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


def _choose_area_path(cli_area, project, remembered_area) -> Path | None:
    """Choose an area path from CLI, project startup area, or a picker rooted at the last area location."""
    if cli_area:
        return _resolve_area_path(project, Path(cli_area))

    startup_area = _resolve_project_startup_area(project)
    if startup_area is not None:
        return startup_area

    return _pick_area_file(_default_area_path(project, remembered_area))


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


def _pick_area_file(default_path: Path) -> Path | None:
    """Open a file dialog to pick an area JSON file."""
    import tkinter as tk
    from tkinter import filedialog

    root = tk.Tk()
    root.withdraw()

    file_path = filedialog.askopenfilename(
        title="Select area file",
        initialdir=str(default_path.parent if default_path.is_file() else default_path),
        initialfile=default_path.name if default_path.is_file() else "",
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


def _default_project_path(launcher_state, fallback_dir) -> Path:
    """Pick a sensible initial project path for the project picker."""
    remembered = _existing_path(launcher_state.last_project)
    if remembered is not None:
        return remembered
    return Path(fallback_dir) / "test_project" / "project.json"


def _resolve_remembered_area(project, remembered_area: str | None) -> Path | None:
    """Resolve the last-opened editor area against the selected project."""
    if not remembered_area:
        return None

    remembered_path = Path(remembered_area)
    if remembered_path.exists() and _area_belongs_to_project(project, remembered_path.resolve()):
        return remembered_path.resolve()

    resolved = _resolve_area_path(project, remembered_path)
    if resolved.exists() and _area_belongs_to_project(project, resolved):
        return resolved
    return None


def _default_area_path(project, remembered_area: str | None) -> Path:
    """Pick a sensible initial area path for the area picker."""
    remembered = _resolve_remembered_area(project, remembered_area)
    if remembered is not None:
        return remembered

    startup_area = _resolve_project_startup_area(project)
    if startup_area is not None:
        return startup_area

    area_files = project.list_area_files()
    if area_files:
        return area_files[0]
    return project.project_root


def _resolve_project_startup_area(project) -> Path | None:
    """Resolve the project's authored startup area, if any."""
    startup_area = getattr(project, "startup_area", None)
    if not startup_area:
        return None

    resolved = _resolve_area_path(project, Path(startup_area))
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

