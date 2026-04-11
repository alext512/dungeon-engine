from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dungeon_engine.commands.library import validate_project_commands
from dungeon_engine.json_io import (
    DEFAULT_JSON5_FILE_HEADER,
    JsonDataDecodeError,
    compose_json_file_text,
    load_json_data,
    loads_json_data,
)
from dungeon_engine.project_context import load_project
from dungeon_engine.world.loader import load_area


class Json5AuthoringIoTests(unittest.TestCase):
    def test_runtime_loads_json5_project_content_with_file_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "areas").mkdir()
            (project_root / "commands").mkdir()
            (project_root / "entity_templates").mkdir()
            (project_root / "items").mkdir()

            (project_root / "project.json5").write_text(
                f"{DEFAULT_JSON5_FILE_HEADER}"
                "{\n"
                "  area_paths: ['areas/',],\n"
                "  command_paths: ['commands/',],\n"
                "  entity_template_paths: ['entity_templates/',],\n"
                "  item_paths: ['items/',],\n"
                "  shared_variables_path: 'shared_variables.json5',\n"
                "  startup_area: 'areas/demo',\n"
                "}\n"
                "/* end notes */\n",
                encoding="utf-8",
            )
            (project_root / "shared_variables.json5").write_text(
                "/* shared notes */\n"
                "{\n"
                "  display: {internal_width: 400, internal_height: 225,},\n"
                "}\n",
                encoding="utf-8",
            )
            (project_root / "areas" / "demo.json5").write_text(
                "/* area notes */\n"
                "{\n"
                "  tile_size: 16,\n"
                "  tilesets: [],\n"
                "  tile_layers: [\n"
                "    {name: 'ground', render_order: 0, grid: [[0]],},\n"
                "  ],\n"
                "  entities: [],\n"
                "  variables: {},\n"
                "}\n",
                encoding="utf-8",
            )
            (project_root / "commands" / "noop.json5").write_text(
                "{\n  params: [],\n  commands: [],\n}\n",
                encoding="utf-8",
            )

            project = load_project(project_root)

            self.assertEqual(project.internal_width, 400)
            self.assertEqual(project.internal_height, 225)
            self.assertEqual(project.list_area_ids(), ["areas/demo"])
            self.assertEqual(project.list_command_files()[0].suffix, ".json5")

            area_path = project.find_area_by_id("areas/demo")
            self.assertIsNotNone(area_path)
            assert area_path is not None
            area, world = load_area(area_path, project=project)
            self.assertEqual(area.area_id, "areas/demo")
            self.assertEqual(list(world.iter_entities()), [])

            validate_project_commands(project)

    def test_rejects_comments_inside_root_value(self) -> None:
        with self.assertRaises(JsonDataDecodeError) as raised:
            loads_json_data('{\n  "x": 1, // field note\n}\n')

        self.assertIn("comments are only supported before or after", str(raised.exception))

    def test_compose_preserves_file_level_notes(self) -> None:
        original = "/* leading */\n{x: 1,}\n/* trailing */\n"

        saved = compose_json_file_text('{\n  "x": 2\n}', original_text=original)

        self.assertTrue(saved.startswith("/* leading */"))
        self.assertIn('"x": 2', saved)
        self.assertTrue(saved.rstrip().endswith("/* trailing */"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.json5"
            path.write_text(saved, encoding="utf-8")
            self.assertEqual(load_json_data(path)["x"], 2)


if __name__ == "__main__":
    unittest.main()
