"""Project entrypoint for the Python puzzle engine prototype."""

from __future__ import annotations

import argparse
import os


def parse_args() -> argparse.Namespace:
    """Parse command line options for local development and smoke tests."""
    parser = argparse.ArgumentParser(description="Run the Python puzzle engine.")
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
    """Run the game until the window closes or the optional frame limit is hit."""
    args = parse_args()
    if args.headless:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    from puzzle_dungeon.logging_utils import install_exception_logging
    from puzzle_dungeon.engine.game import Game

    logger = install_exception_logging()

    try:
        game = Game()
        game.run(max_frames=args.max_frames)
        return 0
    except Exception:
        logger.exception("Fatal error while running the game")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
