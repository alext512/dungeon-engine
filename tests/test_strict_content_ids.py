from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import run_editor
import run_game
from dungeon_engine.commands.library import (
    NamedCommandValidationError,
    validate_project_named_commands,
)
from dungeon_engine.dialogue_library import (
    DialogueValidationError,
    validate_project_dialogues,
)
from dungeon_engine.project import load_project
from dungeon_engine.world.loader import AreaValidationError, validate_project_areas
from dungeon_engine.world.persistence import save_data_from_dict


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _minimal_area(*, name: str = "Test Room") -> dict[str, object]:
    return {
        "name": name,
        "tile_size": 16,
        "player_id": "player",
        "variables": {},
        "tilesets": [],
        "tile_layers": [],
        "cell_flags": [],
        "entities": [],
    }


class StrictContentIdTests(unittest.TestCase):
    def _make_project(
        self,
        *,
        startup_area: str | None = None,
        areas: dict[str, dict[str, object]] | None = None,
        commands: dict[str, dict[str, object]] | None = None,
        dialogues: dict[str, dict[str, object]] | None = None,
    ) -> tuple[Path, object]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        project_root = Path(temp_dir.name)

        project_payload: dict[str, object] = {
            "area_paths": ["areas/"],
            "command_paths": ["commands/"],
            "dialogue_paths": ["dialogues/"],
        }
        if startup_area is not None:
            project_payload["startup_area"] = startup_area

        _write_json(project_root / "project.json", project_payload)

        for relative_path, area_payload in (areas or {}).items():
            _write_json(project_root / "areas" / relative_path, area_payload)
        for relative_path, command_payload in (commands or {}).items():
            _write_json(project_root / "commands" / relative_path, command_payload)
        for relative_path, dialogue_payload in (dialogues or {}).items():
            _write_json(project_root / "dialogues" / relative_path, dialogue_payload)

        return project_root, load_project(project_root / "project.json")

    def test_area_validation_rejects_authored_area_id(self) -> None:
        _, project = self._make_project(
            startup_area="test_room",
            areas={
                "test_room.json": {
                    "area_id": "test_room",
                    **_minimal_area(),
                }
            },
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("must not declare 'area_id'" in issue for issue in raised.exception.issues)
        )

    def test_area_validation_rejects_missing_startup_area_id(self) -> None:
        _, project = self._make_project(
            startup_area="missing_room",
            areas={"test_room.json": _minimal_area()},
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("startup_area 'missing_room'" in issue for issue in raised.exception.issues)
        )

    def test_named_command_validation_rejects_authored_id(self) -> None:
        _, project = self._make_project(
            commands={
                "walk_one_tile.json": {
                    "id": "walk_one_tile",
                    "params": [],
                    "commands": [],
                }
            }
        )

        with self.assertRaises(NamedCommandValidationError) as raised:
            validate_project_named_commands(project)

        self.assertTrue(
            any("must not declare 'id'" in issue for issue in raised.exception.issues)
        )

    def test_dialogue_validation_rejects_authored_id(self) -> None:
        _, project = self._make_project(
            dialogues={
                "signs/gate_hint.json": {
                    "id": "signs/gate_hint",
                    "text": "Gate is closed.",
                }
            }
        )

        with self.assertRaises(DialogueValidationError) as raised:
            validate_project_dialogues(project)

        self.assertTrue(
            any("must not declare 'id'" in issue for issue in raised.exception.issues)
        )

    def test_launchers_resolve_startup_area_and_cli_ids(self) -> None:
        project_root, project = self._make_project(
            startup_area="intro/title_screen",
            areas={"intro/title_screen.json": _minimal_area(name="Title Screen")},
        )
        expected_path = (project_root / "areas" / "intro" / "title_screen.json").resolve()

        self.assertEqual(run_game._resolve_project_startup_area(project), expected_path)
        self.assertEqual(run_editor._resolve_project_startup_area(project), expected_path)
        self.assertEqual(run_game._resolve_area_argument(project, "intro/title_screen"), expected_path)
        self.assertEqual(run_editor._resolve_area_argument(project, "intro/title_screen"), expected_path)

    def test_save_data_ignores_removed_legacy_session_fields(self) -> None:
        save_data = save_data_from_dict(
            {
                "session": {
                    "current_area_path": "legacy/room",
                    "active_entity_id": "legacy_player",
                }
            }
        )

        self.assertEqual(save_data.current_area, "")
        self.assertEqual(save_data.active_entity, "")


if __name__ == "__main__":
    unittest.main()
