# Contributing

Read `ARCHITECTURE.md` for how the systems work. Read `ROADMAP.md` for what to build and in what order.

## The short version

- Game behavior lives in **JSON command chains**, not in Python system code. If you're writing game logic (e.g., "lever opens door"), it should be a command, not code in a system.
- Components are **data only**. Systems process them.
- Code should be understandable by someone seeing it for the first time — use module docstrings, type hints, and comment non-obvious decisions. See `ARCHITECTURE.md` Section 14.
- The architecture docs are guides, not rigid contracts. If something doesn't work in practice, adapt it and document what changed.
