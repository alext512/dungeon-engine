"""Entry point for ``python -m area_editor``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Puzzle Dungeon Area Editor")
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="Path to project.json or its parent directory",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # Import Qt only after arg parsing so --help works without PySide6
    from area_editor.app.app import create_application
    from area_editor.app.main_window import MainWindow

    app = create_application(sys.argv)
    window = MainWindow()
    window.show()

    if args.project:
        window.open_project(args.project)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
