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

## Run The Runtime Tests

```bash
.venv/Scripts/python -m unittest discover -s tests -v
```

Useful smoke command:

```bash
.venv/Scripts/python run_game.py --project projects/new_project --headless --max-frames 2
```

## Run The Editor

From `tools/area_editor/`:

```bash
pip install -r requirements.txt
python -m area_editor
python -m area_editor --project ../../projects/new_project/project.json
```

Editor tests:

```bash
cd tools/area_editor
..\..\.venv\Scripts\python -m unittest discover -s tests -v
```

## Run The Docs Site Locally

Install the docs-only dependencies:

```bash
pip install -r requirements-docs.txt
```

Then preview the site:

```bash
mkdocs serve
```

Build static output:

```bash
mkdocs build
```

## Validation Habit

If you change command surfaces, authoring conventions, or repo-local example project content, do more than just unit tests:

- run the relevant automated tests
- validate each repo-local `project.json`
- prefer startup-style validation paths, not only low-level tests

The validation workflow is documented in the repo's [AGENTS.md](https://github.com/alext512/dungeon-engine/blob/main/AGENTS.md) and [README.md](https://github.com/alext512/dungeon-engine/blob/main/README.md).
