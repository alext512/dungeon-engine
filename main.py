"""Legacy entrypoint that forwards to the standalone game launcher."""

from __future__ import annotations
def main() -> int:
    """Run the standalone game launcher."""
    from run_game import main as run_game_main

    return run_game_main()


if __name__ == "__main__":
    raise SystemExit(main())
