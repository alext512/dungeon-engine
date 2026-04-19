from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dungeon_engine.commands.audit import audit_project_command_surfaces
from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.context_services import build_command_services
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import CommandContext, execute_command_spec
from dungeon_engine.project_context import load_project
from dungeon_engine.startup_validation import (
    CommandAuthoringValidationError,
    StaticReferenceValidationError,
    validate_project_startup,
)
from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity
from dungeon_engine.world.world import World


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _minimal_area() -> dict[str, object]:
    return {
        "tile_size": 16,
        "input_targets": {
            "move_up": "player",
            "move_down": "player",
            "move_left": "player",
            "move_right": "player",
            "interact": "player",
        },
        "variables": {},
        "tilesets": [
            {
                "firstgid": 1,
                "path": "assets/project/tiles/test.png",
                "tile_width": 16,
                "tile_height": 16,
            }
        ],
        "tile_layers": [
            {
                "name": "ground",
                "render_order": 0,
                "grid": [[1]],
            }
        ],
        "cell_flags": [[{"blocked": False}]],
        "entities": [],
    }


def _minimal_runtime_area() -> Area:
    return Area(
        area_id="areas/test_room",
        tile_size=16,
        tilesets=[],
        tile_layers=[],
        cell_flags=[],
    )


def _make_runtime_entity(
    entity_id: str,
    *,
    kind: str = "system",
    space: str = "world",
) -> Entity:
    return Entity(
        entity_id=entity_id,
        kind=kind,
        grid_x=0,
        grid_y=0,
        space=space,  # type: ignore[arg-type]
        scope="area",
        visuals=[],
    )


class CommandAuthoringAndRuntimeCacheTests(unittest.TestCase):
    def _make_project(
        self,
        *,
        startup_area: str | None = None,
        entity_templates: dict[str, dict[str, object]] | None = None,
        areas: dict[str, dict[str, object]] | None = None,
        commands: dict[str, dict[str, object]] | None = None,
        dialogues: dict[str, dict[str, object]] | None = None,
        shared_variables: dict[str, object] | None = None,
    ) -> tuple[Path, object]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        project_root = Path(temp_dir.name)

        project_payload: dict[str, object] = {
            "area_paths": ["areas/"],
            "entity_template_paths": ["entity_templates/"],
            "command_paths": ["commands/"],
            "item_paths": ["items/"],
            "shared_variables_path": "shared_variables.json",
        }
        if startup_area is not None:
            project_payload["startup_area"] = startup_area

        _write_json(project_root / "project.json", project_payload)
        _write_json(project_root / "shared_variables.json", shared_variables or {})

        for relative_path, template_payload in (entity_templates or {}).items():
            _write_json(project_root / "entity_templates" / relative_path, template_payload)
        for relative_path, area_payload in (areas or {}).items():
            _write_json(project_root / "areas" / relative_path, area_payload)
        for relative_path, command_payload in (commands or {}).items():
            _write_json(project_root / "commands" / relative_path, command_payload)
        for relative_path, dialogue_payload in (dialogues or {}).items():
            _write_json(project_root / "dialogues" / relative_path, dialogue_payload)

        return project_root, load_project(project_root / "project.json")

    def _make_command_context(
        self,
        *,
        project: object | None = None,
        world: World | None = None,
    ) -> tuple[CommandRegistry, CommandContext]:
        registry = CommandRegistry()
        register_builtin_commands(registry)
        context = CommandContext(
            project=project,
            services=build_command_services(
                area=_minimal_runtime_area(),
                world=world or World(),
                collision_system=None,
                movement_system=None,
                interaction_system=None,
                animation_system=None,
            ),
        )
        return registry, context

    def test_registry_exposes_builtin_command_contract_snapshots(self) -> None:
        registry = CommandRegistry()
        register_builtin_commands(registry)

        contracts = {contract.name: contract for contract in registry.iter_command_contracts()}

        open_dialogue = contracts["open_dialogue_session"]
        self.assertEqual(open_dialogue.validation_mode, "strict")
        self.assertTrue(open_dialogue.accepts_runtime_kwargs)
        self.assertEqual(
            open_dialogue.deferred_param_shapes,
            {
                "dialogue_definition": "dialogue_definition",
                "dialogue_on_start": "command_payload",
                "dialogue_on_end": "command_payload",
                "segment_hooks": "dialogue_segment_hooks",
            },
        )
        self.assertIn("segment_hooks", open_dialogue.allowed_authored_params)
        self.assertIn("dialogue_definition", open_dialogue.allowed_authored_params)

        run_sequence = contracts["run_sequence"]
        self.assertEqual(run_sequence.validation_mode, "mixed")
        self.assertTrue(run_sequence.accepts_runtime_kwargs)
        self.assertEqual(
            run_sequence.deferred_param_shapes,
            {"commands": "command_payload"},
        )

    def test_command_audit_reports_unknown_strict_fields_in_project_commands(self) -> None:
        _, project = self._make_project(
            commands={
                "strict_typo.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "set_visible",
                            "entity_id": "gate",
                            "visible": False,
                            "persitent": True,
                        }
                    ],
                }
            }
        )

        issues = audit_project_command_surfaces(project)

        self.assertTrue(
            any(
                "command 'set_visible' contains unknown field(s): persitent."
                in issue
                for issue in issues
            )
        )

    def test_command_audit_allows_mixed_runtime_params_in_flow_commands(self) -> None:
        _, project = self._make_project(
            commands={
                "flow_with_runtime_params.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "run_sequence",
                            "reward_item": "items/key",
                            "commands": [
                                {
                                    "type": "set_current_area_var",
                                    "name": "reward_item",
                                    "value": "$reward_item",
                                }
                            ],
                        }
                    ],
                }
            }
        )

        issues = audit_project_command_surfaces(project)

        self.assertEqual(issues, [])

    def test_command_audit_allows_declared_set_camera_state_fields(self) -> None:
        _, project = self._make_project(
            commands={
                "camera_state.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "set_camera_state",
                            "follow": {
                                "mode": "none",
                            },
                            "bounds": None,
                            "deadzone": None,
                            "source_entity_id": "camera_anchor",
                        }
                    ],
                }
            }
        )

        issues = audit_project_command_surfaces(project)

        self.assertEqual(issues, [])

    def test_command_audit_scans_entity_command_shorthand(self) -> None:
        _, project = self._make_project(
            entity_templates={
                "lever.json": {
                    "kind": "lever",
                    "entity_commands": {
                        "interact": [
                            {
                                "type": "set_visible",
                                "entity_id": "gate",
                                "visible": False,
                                "persitent": True,
                            }
                        ]
                    },
                }
            }
        )

        issues = audit_project_command_surfaces(project)

        self.assertTrue(
            any(
                "entity_commands.interact" in issue
                and "command 'set_visible' contains unknown field(s): persitent."
                in issue
                for issue in issues
            )
        )

    def test_command_audit_allows_value_mode_on_raw_storage_commands(self) -> None:
        _, project = self._make_project(
            commands={
                "store_raw_hook.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "set_entity_var",
                            "entity_id": "$self_id",
                            "name": "dialogue_on_end",
                            "value_mode": "raw",
                            "value": "$dialogue_on_end",
                        }
                    ],
                }
            }
        )

        issues = audit_project_command_surfaces(project)

        self.assertEqual(issues, [])

    def test_command_audit_scans_nested_segment_hook_command_lists(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "open_dialogue_session",
                            "dialogue_path": "dialogues/system/test.json",
                            "segment_hooks": [
                                {
                                    "option_commands_by_id": {
                                        "continue": [
                                            {
                                                "type": "set_visible",
                                                "entity_id": "gate",
                                                "visible": False,
                                                "persitent": True,
                                            }
                                        ]
                                    }
                                }
                            ],
                        }
                    ],
                }
            },
            dialogues={
                "system/test.json": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "Continue?",
                            "options": [
                                {
                                    "option_id": "continue",
                                    "text": "Continue",
                                }
                            ],
                        }
                    ]
                }
            },
        )

        issues = audit_project_command_surfaces(project)

        self.assertTrue(
            any(
                "enter_commands[0].segment_hooks[0].option_commands_by_id.continue[0]" in issue
                and "persitent" in issue
                for issue in issues
            )
        )

    def test_command_audit_scans_inline_dialogue_definition_command_lists(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "open_dialogue_session",
                            "dialogue_definition": {
                                "segments": [
                                    {
                                        "type": "choice",
                                        "text": "Open?",
                                        "options": [
                                            {
                                                "option_id": "open",
                                                "text": "Open",
                                                "commands": [
                                                    {
                                                        "type": "set_visible",
                                                        "entity_id": "gate",
                                                        "visible": False,
                                                        "persitent": True,
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ]
                            },
                        }
                    ],
                }
            },
        )

        issues = audit_project_command_surfaces(project)

        self.assertTrue(
            any(
                "enter_commands[0].dialogue_definition.segments[0].options[0].commands[0]"
                in issue
                and "persitent" in issue
                for issue in issues
            )
        )

    def test_command_audit_scans_next_inline_dialogue_definition_command_lists(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "open_dialogue_session",
                            "dialogue_definition": {
                                "segments": [
                                    {
                                        "type": "choice",
                                        "options": [
                                            {
                                                "option_id": "open",
                                                "text": "Open",
                                                "next_dialogue_definition": {
                                                    "segments": [
                                                        {
                                                            "type": "choice",
                                                            "options": [
                                                                {
                                                                    "option_id": "continue",
                                                                    "text": "Continue",
                                                                    "commands": [
                                                                        {
                                                                            "type": "set_visible",
                                                                            "entity_id": "gate",
                                                                            "visible": False,
                                                                            "persitent": True,
                                                                        }
                                                                    ],
                                                                }
                                                            ],
                                                        }
                                                    ]
                                                },
                                            }
                                        ],
                                    }
                                ]
                            },
                        }
                    ],
                }
            },
        )

        issues = audit_project_command_surfaces(project)

        self.assertTrue(
            any(
                "enter_commands[0].dialogue_definition.segments[0].options[0]."
                "next_dialogue_definition.segments[0].options[0].commands[0]" in issue
                and "persitent" in issue
                for issue in issues
            )
        )

    def test_command_audit_rejects_option_with_both_next_dialogue_fields(self) -> None:
        _, project = self._make_project(
            dialogues={
                "system/test.json": {
                    "segments": [
                        {
                            "type": "choice",
                            "options": [
                                {
                                    "option_id": "open",
                                    "text": "Open",
                                    "next_dialogue_path": "dialogues/system/child.json",
                                    "next_dialogue_definition": {
                                        "segments": [
                                            {
                                                "type": "text",
                                                "text": "Child",
                                            }
                                        ]
                                    },
                                }
                            ],
                        }
                    ]
                }
            },
        )

        issues = audit_project_command_surfaces(project)

        self.assertTrue(
            any(
                "dialogue choice option must not define both 'next_dialogue_path' and "
                "'next_dialogue_definition'" in issue
                for issue in issues
            )
        )

    def test_command_audit_rejects_option_next_dialogue_mixed_with_open_dialogue_command(self) -> None:
        _, project = self._make_project(
            dialogues={
                "system/test.json": {
                    "segments": [
                        {
                            "type": "choice",
                            "options": [
                                {
                                    "option_id": "open",
                                    "text": "Open",
                                    "next_dialogue_definition": {
                                        "segments": [
                                            {
                                                "type": "text",
                                                "text": "Child",
                                            }
                                        ]
                                    },
                                    "commands": [
                                        {
                                            "type": "open_dialogue_session",
                                            "dialogue_path": "dialogues/system/other_child.json",
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            },
        )

        issues = audit_project_command_surfaces(project)

        self.assertTrue(
            any(
                "must not combine 'next_dialogue_path' or 'next_dialogue_definition' with "
                "'open_dialogue_session' in its commands" in issue
                for issue in issues
            )
        )

    def test_command_audit_rejects_non_boolean_segment_end_dialogue(self) -> None:
        _, project = self._make_project(
            dialogues={
                "system/test.json": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "Bad",
                            "end_dialogue": "yes",
                        }
                    ]
                }
            },
        )

        issues = audit_project_command_surfaces(project)

        self.assertTrue(
            any(
                "dialogue segment 'end_dialogue' must be a boolean" in issue
                for issue in issues
            )
        )

    def test_command_audit_rejects_non_boolean_option_end_dialogue(self) -> None:
        _, project = self._make_project(
            dialogues={
                "system/test.json": {
                    "segments": [
                        {
                            "type": "choice",
                            "options": [
                                {
                                    "option_id": "leave",
                                    "text": "Leave",
                                    "end_dialogue": 1,
                                }
                            ],
                        }
                    ]
                }
            },
        )

        issues = audit_project_command_surfaces(project)

        self.assertTrue(
            any(
                "dialogue choice option 'end_dialogue' must be a boolean" in issue
                for issue in issues
            )
        )

    def test_command_audit_scans_project_command_deferred_command_payloads(self) -> None:
        _, project = self._make_project(
            commands={
                "call_hook.json": {
                    "params": ["hook"],
                    "deferred_param_shapes": {
                        "hook": "command_payload",
                    },
                    "commands": [
                        {
                            "type": "run_sequence",
                            "commands": "$hook",
                        }
                    ],
                },
                "entry.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "run_project_command",
                            "command_id": "commands/call_hook",
                            "hook": [
                                {
                                    "type": "set_visible",
                                    "entity_id": "gate",
                                    "visible": False,
                                    "persitent": True,
                                }
                            ],
                        }
                    ],
                },
            }
        )

        issues = audit_project_command_surfaces(project)

        self.assertTrue(
            any(
                "commands[0].hook[0]" in issue
                and "command 'set_visible' contains unknown field(s): persitent."
                in issue
                for issue in issues
            )
        )

    def test_startup_validation_rejects_unknown_strict_command_fields(self) -> None:
        project_root, _ = self._make_project(
            startup_area="areas/test_room",
            areas={"test_room.json": _minimal_area()},
            commands={
                "strict_typo.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "set_visible",
                            "entity_id": "gate",
                            "visible": False,
                            "persitent": True,
                        }
                    ],
                }
            },
        )
        asset_path = project_root / "assets" / "project" / "tiles" / "test.png"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(b"fake")
        project = load_project(project_root / "project.json")

        error = validate_project_startup(
            project,
            ui_title="Test",
            show_dialog=False,
        )

        self.assertIsInstance(error, CommandAuthoringValidationError)
        assert isinstance(error, CommandAuthoringValidationError)
        self.assertTrue(any("persitent" in issue for issue in error.issues))

    def test_startup_validation_rejects_missing_literal_dialogue_reference(self) -> None:
        project_root, _ = self._make_project(
            startup_area="areas/test_room",
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "open_dialogue_session",
                            "dialogue_path": "dialogues/system/missing_title.json",
                        }
                    ],
                }
            },
        )
        asset_path = project_root / "assets" / "project" / "tiles" / "test.png"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(b"fake")
        project = load_project(project_root / "project.json")

        error = validate_project_startup(
            project,
            ui_title="Test",
            show_dialog=False,
        )

        self.assertIsInstance(error, StaticReferenceValidationError)
        assert isinstance(error, StaticReferenceValidationError)
        self.assertTrue(
            any(
                "missing dialogue 'dialogues/system/missing_title.json'" in issue
                for issue in error.issues
            )
        )

    def test_startup_validation_rejects_missing_literal_next_dialogue_reference(self) -> None:
        project_root, _ = self._make_project(
            startup_area="areas/test_room",
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "open_dialogue_session",
                            "dialogue_definition": {
                                "segments": [
                                    {
                                        "type": "choice",
                                        "options": [
                                            {
                                                "option_id": "open",
                                                "text": "Open",
                                                "next_dialogue_path": "dialogues/system/missing_branch.json",
                                            }
                                        ],
                                    }
                                ]
                            },
                        }
                    ],
                }
            },
        )
        asset_path = project_root / "assets" / "project" / "tiles" / "test.png"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(b"fake")
        project = load_project(project_root / "project.json")

        error = validate_project_startup(
            project,
            ui_title="Test",
            show_dialog=False,
        )

        self.assertIsInstance(error, StaticReferenceValidationError)
        assert isinstance(error, StaticReferenceValidationError)
        self.assertTrue(
            any(
                "missing dialogue 'dialogues/system/missing_branch.json'" in issue
                for issue in error.issues
            )
        )

    def test_startup_validation_rejects_missing_literal_asset_reference(self) -> None:
        project_root, _ = self._make_project(
            startup_area="areas/test_room",
            areas={"test_room.json": _minimal_area()},
            shared_variables={
                "dialogue_ui": {
                    "panel_path": "assets/project/ui/missing_panel.png",
                }
            },
        )
        tileset_path = project_root / "assets" / "project" / "tiles" / "test.png"
        tileset_path.parent.mkdir(parents=True, exist_ok=True)
        tileset_path.write_bytes(b"fake")
        (project_root / "assets" / "project" / "ui").mkdir(parents=True, exist_ok=True)
        project = load_project(project_root / "project.json")

        error = validate_project_startup(
            project,
            ui_title="Test",
            show_dialog=False,
        )

        self.assertIsInstance(error, StaticReferenceValidationError)
        assert isinstance(error, StaticReferenceValidationError)
        self.assertTrue(
            any("missing asset 'assets/project/ui/missing_panel.png'" in issue for issue in error.issues)
        )

    def test_startup_validation_allows_runtime_dynamic_references(self) -> None:
        project_root, _ = self._make_project(
            startup_area="areas/test_room",
            entity_templates={
                "display_sprite.json": {
                    "space": "screen",
                    "kind": "display",
                    "visuals": [
                        {
                            "id": "main",
                            "path": "$sprite_path",
                        }
                    ],
                }
            },
            areas={"test_room.json": _minimal_area()},
        )
        asset_path = project_root / "assets" / "project" / "tiles" / "test.png"
        asset_path.parent.mkdir(parents=True, exist_ok=True)
        asset_path.write_bytes(b"fake")
        project = load_project(project_root / "project.json")

        error = validate_project_startup(
            project,
            ui_title="Test",
            show_dialog=False,
        )

        self.assertIsNone(error)

    def test_startup_validation_rejects_statically_resolved_template_asset_reference(self) -> None:
        project_root, _ = self._make_project(
            startup_area="areas/test_room",
            entity_templates={
                "display_sprite.json": {
                    "space": "screen",
                    "kind": "display",
                    "visuals": [
                        {
                            "id": "main",
                            "path": "$sprite_path",
                        }
                    ],
                }
            },
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "screen_sprite",
                            "template": "entity_templates/display_sprite",
                            "parameters": {
                                "sprite_path": "assets/project/ui/missing_panel.png",
                            },
                            "pixel_x": 0,
                            "pixel_y": 0,
                        }
                    ],
                }
            },
        )
        tileset_path = project_root / "assets" / "project" / "tiles" / "test.png"
        tileset_path.parent.mkdir(parents=True, exist_ok=True)
        tileset_path.write_bytes(b"fake")
        (project_root / "assets" / "project" / "ui").mkdir(parents=True, exist_ok=True)
        project = load_project(project_root / "project.json")

        error = validate_project_startup(
            project,
            ui_title="Test",
            show_dialog=False,
        )

        self.assertIsInstance(error, StaticReferenceValidationError)
        assert isinstance(error, StaticReferenceValidationError)
        self.assertTrue(
            any("missing asset 'assets/project/ui/missing_panel.png'" in issue for issue in error.issues)
        )

    def test_json_file_value_source_loads_project_relative_dialogue_data(self) -> None:
        _, project = self._make_project(
            dialogues={
                "menus/test.json": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "Gate is closed.",
                        }
                    ],
                    "font_id": "pixelbet",
                }
            }
        )
        world = World()
        world.add_entity(
            _make_runtime_entity(
                "dialogue_controller",
                kind="system",
                space="screen",
            )
        )
        registry, context = self._make_command_context(project=project, world=world)

        handle = execute_command_spec(
            registry,
            context,
            {
                "entity_id": "dialogue_controller",
                "name": "dialogue_definition",
                "type": "set_entity_var",
                "value": {"$json_file": "dialogues/menus/test.json"},
            },
        )
        handle.update(0.0)

        controller = world.get_entity("dialogue_controller")
        assert controller is not None
        self.assertEqual(
            controller.variables["dialogue_definition"]["segments"][0]["text"],
            "Gate is closed.",
        )
        self.assertEqual(controller.variables["dialogue_definition"]["font_id"], "pixelbet")

    def test_json_file_value_source_cache_is_scoped_to_command_context(self) -> None:
        project_root, project = self._make_project(
            dialogues={
                "menus/test.json": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "Gate is closed.",
                        }
                    ],
                    "font_id": "pixelbet",
                }
            }
        )
        dialogue_path = project_root / "dialogues" / "menus" / "test.json"
        command_spec = {
            "entity_id": "dialogue_controller",
            "name": "dialogue_definition",
            "type": "set_entity_var",
            "value": {"$json_file": "dialogues/menus/test.json"},
        }

        world_a = World()
        world_a.add_entity(
            _make_runtime_entity(
                "dialogue_controller",
                kind="system",
                space="screen",
            )
        )
        registry_a, context_a = self._make_command_context(project=project, world=world_a)

        execute_command_spec(registry_a, context_a, command_spec).update(0.0)

        _write_json(
            dialogue_path,
            {
                "segments": [
                    {
                        "type": "text",
                        "text": "Gate is open.",
                    }
                ],
                "font_id": "pixelbet",
            },
        )

        execute_command_spec(registry_a, context_a, command_spec).update(0.0)
        controller_a = world_a.get_entity("dialogue_controller")
        assert controller_a is not None
        self.assertEqual(
            controller_a.variables["dialogue_definition"]["segments"][0]["text"],
            "Gate is closed.",
        )

        world_b = World()
        world_b.add_entity(
            _make_runtime_entity(
                "dialogue_controller",
                kind="system",
                space="screen",
            )
        )
        registry_b, context_b = self._make_command_context(project=project, world=world_b)

        execute_command_spec(registry_b, context_b, command_spec).update(0.0)
        controller_b = world_b.get_entity("dialogue_controller")
        assert controller_b is not None
        self.assertEqual(
            controller_b.variables["dialogue_definition"]["segments"][0]["text"],
            "Gate is open.",
        )


if __name__ == "__main__":
    unittest.main()
