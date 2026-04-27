from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from dungeon_engine.project_context import load_project


_EDITOR_PACKAGE_ROOT = (
    Path(__file__).resolve().parent.parent / "tools" / "area_editor"
).resolve()
if str(_EDITOR_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_EDITOR_PACKAGE_ROOT))

from area_editor.project_io.project_manifest import (  # type: ignore[import-not-found]
    discover_areas,
    discover_commands,
    discover_entity_templates,
    discover_global_entities,
    discover_items,
    load_manifest,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class ProjectLayoutParityTests(unittest.TestCase):
    def _make_project(
        self,
        *,
        project_payload: dict[str, object] | None = None,
        shared_variables: dict[str, object] | None = None,
        area_files: dict[str, dict[str, object]] | None = None,
        template_files: dict[str, dict[str, object]] | None = None,
        command_files: dict[str, dict[str, object]] | None = None,
        item_files: dict[str, dict[str, object]] | None = None,
    ) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        project_root = Path(temp_dir.name)

        _write_json(project_root / "project.json", project_payload or {})
        if shared_variables is not None:
            _write_json(project_root / "shared_variables.json", shared_variables)
        for relative_path, payload in (area_files or {}).items():
            _write_json(project_root / "areas" / relative_path, payload)
        for relative_path, payload in (template_files or {}).items():
            _write_json(project_root / "entity_templates" / relative_path, payload)
        for relative_path, payload in (command_files or {}).items():
            _write_json(project_root / "commands" / relative_path, payload)
        for relative_path, payload in (item_files or {}).items():
            _write_json(project_root / "items" / relative_path, payload)
        return project_root

    def test_runtime_and_editor_manifest_loaders_match_explicit_paths_and_dimensions(self) -> None:
        project_root = self._make_project(
            project_payload={
                "area_paths": ["content/areas/"],
                "entity_template_paths": ["content/templates/"],
                "asset_paths": ["content/assets/"],
                "command_paths": ["content/commands/"],
                "item_paths": ["content/items/"],
                "shared_variables_path": "config/shared_variables.json",
                "startup_area": "areas/intro/title_screen",
            },
        )
        (project_root / "content" / "areas").mkdir(parents=True, exist_ok=True)
        (project_root / "content" / "templates").mkdir(parents=True, exist_ok=True)
        (project_root / "content" / "assets").mkdir(parents=True, exist_ok=True)
        (project_root / "content" / "commands").mkdir(parents=True, exist_ok=True)
        (project_root / "content" / "items").mkdir(parents=True, exist_ok=True)
        _write_json(
            project_root / "config" / "shared_variables.json",
            {"display": {"internal_width": 400, "internal_height": 225}},
        )

        runtime = load_project(project_root)
        editor = load_manifest(project_root)

        self.assertEqual(runtime.project_root, editor.project_root)
        self.assertEqual(runtime.area_paths, editor.area_paths)
        self.assertEqual(runtime.entity_template_paths, editor.entity_template_paths)
        self.assertEqual(runtime.asset_paths, editor.asset_paths)
        self.assertEqual(runtime.command_paths, editor.command_paths)
        self.assertEqual(runtime.item_paths, editor.item_paths)
        self.assertEqual(runtime.shared_variables_path, editor.shared_variables_path)
        self.assertEqual(runtime.startup_area, editor.startup_area)
        self.assertEqual(runtime.internal_width, editor.display_width)
        self.assertEqual(runtime.internal_height, editor.display_height)

    def test_runtime_and_editor_manifest_loaders_share_default_directory_conventions(self) -> None:
        project_root = self._make_project(
            shared_variables={"display": {"internal_width": 256, "internal_height": 192}},
        )
        for relative_dir in (
            "areas",
            "entity_templates",
            "assets",
            "commands",
            "items",
        ):
            (project_root / relative_dir).mkdir(parents=True, exist_ok=True)

        runtime = load_project(project_root / "project.json")
        editor = load_manifest(project_root / "project.json")

        self.assertEqual(runtime.area_paths, editor.area_paths)
        self.assertEqual(runtime.entity_template_paths, editor.entity_template_paths)
        self.assertEqual(runtime.asset_paths, editor.asset_paths)
        self.assertEqual(runtime.command_paths, editor.command_paths)
        self.assertEqual(runtime.item_paths, editor.item_paths)
        self.assertEqual(runtime.shared_variables_path, editor.shared_variables_path)
        self.assertEqual(runtime.internal_width, editor.display_width)
        self.assertEqual(runtime.internal_height, editor.display_height)

    def test_runtime_and_editor_manifest_loaders_match_runtime_control_fields(self) -> None:
        project_root = self._make_project(
            project_payload={
                "startup_area": "  areas/intro/title_screen  ",
                "save_dir": "session_saves",
                "input_routes": {
                    "interact": {
                        "entity_id": "player_1",
                        "command_id": "interact",
                    },
                    "pause": {
                        "entity_id": "  pause_controller  ",
                        "command_id": "open_pause",
                    },
                    "menu": None,
                    "  ": {
                        "entity_id": "ignored",
                        "command_id": "ignored",
                    },
                },
                "debug_inspection_enabled": True,
                "global_entities": [
                    {
                        "id": "dialogue_controller",
                        "template": "entity_templates/controllers/dialogue_controller",
                    },
                    {
                        "id": "screen_fx",
                        "variables": {"active": True},
                    },
                ],
                "command_runtime": {
                    "max_settle_passes": "64",
                    "max_immediate_commands_per_settle": 4096.2,
                    "log_settle_usage_peaks": 1,
                    "settle_warning_ratio": 1.75,
                },
            },
        )

        runtime = load_project(project_root)
        editor = load_manifest(project_root)

        self.assertEqual(runtime.startup_area, editor.startup_area)
        self.assertEqual(runtime.save_dir, editor.save_dir)
        self.assertEqual(runtime.input_routes, editor.input_routes)
        self.assertEqual(runtime.debug_inspection_enabled, editor.debug_inspection_enabled)
        self.assertEqual(runtime.global_entities, editor.global_entities)
        self.assertEqual(
            {
                "max_settle_passes": runtime.command_runtime.max_settle_passes,
                "max_immediate_commands_per_settle": (
                    runtime.command_runtime.max_immediate_commands_per_settle
                ),
                "log_settle_usage_peaks": runtime.command_runtime.log_settle_usage_peaks,
                "settle_warning_ratio": runtime.command_runtime.settle_warning_ratio,
            },
            editor.command_runtime,
        )

    def test_runtime_and_editor_discover_same_area_template_command_and_item_ids(self) -> None:
        project_root = self._make_project(
            project_payload={
                "area_paths": ["content/areas/"],
                "entity_template_paths": ["content/templates/"],
                "command_paths": ["content/commands/"],
                "item_paths": ["content/items/"],
            },
            area_files={
                "intro/title_screen.json": {"tile_size": 16},
                "village/square.json": {"tile_size": 16},
            },
            template_files={
                "npc/shopkeeper.json": {"kind": "npc"},
                "props/sign.json": {"kind": "sign"},
            },
            command_files={
                "system/open_gate.json": {"commands": []},
                "ui/show_title.json": {"commands": []},
            },
            item_files={
                "consumables/apple.json": {"name": "Apple"},
                "keys/copper_key.json": {"name": "Copper Key"},
            },
        )

        # Move the authored files into the explicit roots declared in project.json.
        (project_root / "content").mkdir(exist_ok=True)
        (project_root / "content" / "areas").mkdir(parents=True, exist_ok=True)
        (project_root / "content" / "templates").mkdir(parents=True, exist_ok=True)
        (project_root / "content" / "commands").mkdir(parents=True, exist_ok=True)
        (project_root / "content" / "items").mkdir(parents=True, exist_ok=True)
        for source_root, target_root in (
            (project_root / "areas", project_root / "content" / "areas"),
            (project_root / "entity_templates", project_root / "content" / "templates"),
            (project_root / "commands", project_root / "content" / "commands"),
            (project_root / "items", project_root / "content" / "items"),
        ):
            for file_path in source_root.rglob("*.json"):
                relative = file_path.relative_to(source_root)
                destination = target_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")

        runtime = load_project(project_root)
        editor = load_manifest(project_root)

        self.assertEqual(
            runtime.list_area_ids(),
            [entry.area_id for entry in discover_areas(editor)],
        )
        self.assertEqual(
            runtime.list_entity_template_ids(),
            [entry.template_id for entry in discover_entity_templates(editor)],
        )
        self.assertEqual(
            [runtime.command_id(path) for path in runtime.list_command_files()],
            [entry.command_id for entry in discover_commands(editor)],
        )
        self.assertEqual(
            runtime.list_item_ids(),
            [entry.item_id for entry in discover_items(editor)],
        )

    def test_runtime_and_editor_preserve_global_entity_order_and_template_refs(self) -> None:
        project_root = self._make_project(
            project_payload={
                "global_entities": [
                    {
                        "id": "dialogue_controller",
                        "template": "entity_templates/controllers/dialogue_controller",
                    },
                    {
                        "id": "screen_fx",
                    },
                ]
            }
        )

        runtime = load_project(project_root)
        editor = load_manifest(project_root)

        self.assertEqual(
            [
                {
                    "entity_id": entry.entity_id,
                    "template_id": entry.template_id,
                    "index": entry.index,
                }
                for entry in discover_global_entities(editor)
            ],
            [
                {
                    "entity_id": str(raw_entry.get("id", "")).strip(),
                    "template_id": (
                        str(raw_entry.get("template")).strip()
                        if raw_entry.get("template") not in (None, "")
                        else None
                    ),
                    "index": index,
                }
                for index, raw_entry in enumerate(runtime.global_entities)
            ],
        )
