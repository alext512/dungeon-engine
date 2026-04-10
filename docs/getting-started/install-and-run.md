# Install and Run

## Requirements

- Python 3.11+
- `pygame-ce`
- Windows is the main development environment right now

## Install Runtime Dependencies

From the repo root:

```bash
pip install -e .
```

If you only want the core runtime dependency directly:

```bash
pip install pygame-ce
```

## Run The Game

Typical commands:

```bash
python run_game.py --project projects/new_project
python run_game.py --project projects/new_project areas/start
python run_game.py --project projects/new_project/project.json
```

On Windows you can also use:

```text
Run_Game.cmd
```

## Optional Quick Startup Smoke

If you only want to confirm that a project loads and reaches the main loop cleanly, this is a fast check:

```bash
.venv/Scripts/python run_game.py --project projects/new_project --headless --max-frames 2
```

Headless mode requires `--project`.

## Run The Editor

From `tools/area_editor/`:

```bash
pip install -r requirements.txt
python -m area_editor
python -m area_editor --project ../../projects/new_project/project.json
```

## Next Steps

- Use [Project Layout](project-layout.md) to understand where authored JSON lives.
- Use [Authoring Workflow](../guides/authoring-workflow.md) for the practical build path.
- Use [Startup Checks](../guides/validation-and-startup-checks.md) if you want to know what the engine catches before play begins.
- If you are changing engine code, editor internals, or docs infrastructure, use [Verification and Validation](../development/verification-and-validation.md).
