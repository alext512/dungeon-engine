from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from area_editor.documents.area_document import load_area_document, save_area_document
from area_editor.json_io import DEFAULT_JSON5_FILE_HEADER, load_json_data
from area_editor.operations.areas import make_empty_area_document
from area_editor.project_io.project_manifest import discover_areas, load_manifest


class TestJson5AuthoringIo(unittest.TestCase):
    def test_manifest_discovery_accepts_json5_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            (project_root / "areas").mkdir()
            (project_root / "project.json5").write_text(
                f"{DEFAULT_JSON5_FILE_HEADER}"
                "{\n"
                "  area_paths: ['areas/',],\n"
                "  shared_variables_path: 'shared_variables.json5',\n"
                "  startup_area: 'areas/demo',\n"
                "}\n",
                encoding="utf-8",
            )
            (project_root / "shared_variables.json5").write_text(
                "{display: {internal_width: 384, internal_height: 216,},}\n",
                encoding="utf-8",
            )
            (project_root / "areas" / "demo.json5").write_text(
                "/* area notes */\n"
                "{\n"
                "  tile_size: 16,\n"
                "  tilesets: [],\n"
                "  tile_layers: [],\n"
                "  entities: [],\n"
                "}\n"
                "/* trailing area notes */\n",
                encoding="utf-8",
            )

            manifest = load_manifest(project_root)

            self.assertEqual(manifest.project_file.name, "project.json5")
            self.assertEqual(manifest.display_width, 384)
            self.assertEqual([entry.area_id for entry in discover_areas(manifest)], ["areas/demo"])

    def test_area_save_preserves_file_level_notes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            area_path = Path(tmp) / "demo.json5"
            area_path.write_text(
                "/* keep me */\n"
                "{\n"
                "  tile_size: 16,\n"
                "  tilesets: [],\n"
                "  tile_layers: [],\n"
                "  entities: [],\n"
                "}\n"
                "/* keep me too */\n",
                encoding="utf-8",
            )

            document = load_area_document(area_path)
            document.variables["visited"] = True
            save_area_document(area_path, document)

            saved = area_path.read_text(encoding="utf-8")
            self.assertTrue(saved.startswith("/* keep me */"))
            self.assertTrue(saved.rstrip().endswith("/* keep me too */"))
            self.assertTrue(load_json_data(area_path)["variables"]["visited"])

    def test_new_area_json_data_files_get_default_notes_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for suffix in (".json", ".json5"):
                area_path = Path(tmp) / f"new_area{suffix}"
                document = make_empty_area_document(
                    width=2,
                    height=2,
                    tile_size=16,
                    include_default_ground_layer=True,
                )

                save_area_document(area_path, document)

                saved = area_path.read_text(encoding="utf-8")
                self.assertTrue(saved.startswith(DEFAULT_JSON5_FILE_HEADER))
                self.assertEqual(load_json_data(area_path)["tile_size"], 16)


if __name__ == "__main__":
    unittest.main()
