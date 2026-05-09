from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import run_game
from dungeon_engine.commands.library import (
    ProjectCommandValidationError,
    instantiate_project_command_commands,
    load_project_command_definition,
    validate_project_commands,
)
from dungeon_engine.project_context import load_project
from dungeon_engine.world.entity import Entity
from dungeon_engine.world.loader import (
    AreaValidationError,
    load_area_from_data,
    validate_project_areas,
)
from dungeon_engine.world.loader_entities import (
    EntityTemplateValidationError,
    validate_project_entity_templates,
)
from dungeon_engine.world.serializer import serialize_area


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _minimal_area() -> dict[str, object]:
    return {
        "tile_size": 16,
        "input_routes": {
            "move_up": {"entity_id": "player", "command_id": "move_up"},
            "move_down": {"entity_id": "player", "command_id": "move_down"},
            "move_left": {"entity_id": "player", "command_id": "move_left"},
            "move_right": {"entity_id": "player", "command_id": "move_right"},
            "interact": {"entity_id": "player", "command_id": "interact"},
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


def _make_runtime_entity(
    entity_id: str,
    *,
    kind: str = "system",
    space: str = "world",
    scope: str = "area",
) -> Entity:
    return Entity(
        entity_id=entity_id,
        kind=kind,
        grid_x=0,
        grid_y=0,
        space=space,  # type: ignore[arg-type]
        scope=scope,  # type: ignore[arg-type]
        visuals=[],
    )


class ProjectContentContractTests(unittest.TestCase):
    def _make_project(
        self,
        *,
        startup_area: str | None = None,
        input_routes: dict[str, dict[str, str]] | None = None,
        command_runtime: dict[str, object] | None = None,
        global_entities: list[dict[str, object]] | None = None,
        entity_templates: dict[str, dict[str, object]] | None = None,
        areas: dict[str, dict[str, object]] | None = None,
        commands: dict[str, dict[str, object]] | None = None,
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
        if input_routes is not None:
            project_payload["input_routes"] = input_routes
        if command_runtime is not None:
            project_payload["command_runtime"] = command_runtime
        if global_entities is not None:
            project_payload["global_entities"] = global_entities

        _write_json(project_root / "project.json", project_payload)
        _write_json(project_root / "shared_variables.json", shared_variables or {})

        for relative_path, template_payload in (entity_templates or {}).items():
            _write_json(project_root / "entity_templates" / relative_path, template_payload)
        for relative_path, area_payload in (areas or {}).items():
            _write_json(project_root / "areas" / relative_path, area_payload)
        for relative_path, command_payload in (commands or {}).items():
            _write_json(project_root / "commands" / relative_path, command_payload)

        return project_root, load_project(project_root / "project.json")

    def test_project_manifest_loads_command_runtime_config(self) -> None:
        _, project = self._make_project(
            command_runtime={
                "max_settle_passes": 32,
                "max_immediate_commands_per_settle": 1024,
                "log_settle_usage_peaks": True,
                "settle_warning_ratio": 0.5,
            }
        )

        self.assertEqual(project.command_runtime.max_settle_passes, 32)
        self.assertEqual(project.command_runtime.max_immediate_commands_per_settle, 1024)
        self.assertTrue(project.command_runtime.log_settle_usage_peaks)
        self.assertEqual(project.command_runtime.settle_warning_ratio, 0.5)

    def test_area_validation_rejects_authored_area_id(self) -> None:
        _, project = self._make_project(
            startup_area="areas/test_room",
            areas={
                "test_room.json": {
                    "area_id": "areas/test_room",
                    **_minimal_area(),
                }
            },
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("must not declare 'area_id'" in issue for issue in raised.exception.issues)
        )

    def test_area_validation_rejects_authored_name_field(self) -> None:
        _, project = self._make_project(
            startup_area="areas/test_room",
            areas={
                "test_room.json": {
                    "name": "Legacy Room",
                    **_minimal_area(),
                }
            },
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("must not declare 'name'" in issue for issue in raised.exception.issues)
        )

    def test_area_validation_rejects_missing_startup_area_id(self) -> None:
        _, project = self._make_project(
            startup_area="areas/missing_room",
            areas={"test_room.json": _minimal_area()},
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any("startup_area 'areas/missing_room'" in issue for issue in raised.exception.issues)
        )

    def test_area_loader_preserves_enter_commands(self) -> None:
        _, project = self._make_project()
        raw_area = _minimal_area()
        raw_area["enter_commands"] = [
            {
                "type": "run_entity_command",
                "entity_id": "dialogue_controller",
                "command_id": "open_dialogue",
                "dialogue_path": "dialogues/system/title_menu.json",
                "segment_hooks": [
                    {
                        "option_commands_by_id": {
                            "new_game": [],
                        }
                    }
                ],
            }
        ]

        area, _ = load_area_from_data(raw_area, source_name="<memory>", project=project)

        self.assertEqual(len(area.enter_commands), 1)
        self.assertEqual(area.enter_commands[0]["type"], "run_entity_command")
        self.assertEqual(area.enter_commands[0]["entity_id"], "dialogue_controller")
        self.assertEqual(area.enter_commands[0]["dialogue_path"], "dialogues/system/title_menu.json")

    def test_area_loader_and_serializer_round_trip_entry_points(self) -> None:
        _, project = self._make_project()
        raw_area = _minimal_area()
        raw_area["entry_points"] = {
            "front_door": {
                "grid_x": 3,
                "grid_y": 4,
                "facing": "up",
                "pixel_x": 52,
                "pixel_y": 68,
            }
        }
        raw_area["camera"] = {
            "follow": {
                "mode": "entity",
                "entity_id": "player",
                "offset_x": 10,
                "offset_y": 0,
            },
            "bounds": {
                "x": 16,
                "y": 32,
                "width": 128,
                "height": 96,
            },
        }

        area, world = load_area_from_data(raw_area, source_name="<memory>", project=project)
        entry_point = area.entry_points["front_door"]
        self.assertEqual(entry_point.grid_x, 3)
        self.assertEqual(entry_point.grid_y, 4)
        self.assertEqual(entry_point.facing, "up")
        self.assertEqual(entry_point.pixel_x, 52.0)
        self.assertEqual(entry_point.pixel_y, 68.0)
        self.assertEqual(area.camera_defaults["follow"]["entity_id"], "player")
        self.assertEqual(area.camera_defaults["follow"]["offset_x"], 10)

        serialized = serialize_area(area, world, project=project)
        self.assertEqual(
            serialized["entry_points"],
            {
                "front_door": {
                    "grid_x": 3,
                    "grid_y": 4,
                    "facing": "up",
                    "pixel_x": 52,
                    "pixel_y": 68,
                }
            },
        )
        self.assertEqual(serialized["camera"], raw_area["camera"])

    def test_serialize_area_writes_unified_layering_fields(self) -> None:
        _, project = self._make_project()
        raw_area = _minimal_area()
        raw_area["tile_layers"] = [
            {
                "name": "front_wall",
                "render_order": 10,
                "y_sort": True,
                "sort_y_offset": -2,
                "stack_order": 4,
                "grid": [[1]],
            }
        ]
        raw_area["entities"] = [
            {
                "id": "player",
                "kind": "player",
                "grid_x": 0,
                "grid_y": 0,
                "render_order": 12,
                "y_sort": False,
                "sort_y_offset": 5,
                "stack_order": 9,
            }
        ]

        area, world = load_area_from_data(raw_area, source_name="<memory>", project=project)
        serialized = serialize_area(area, world, project=project)

        tile_layer = serialized["tile_layers"][0]
        self.assertEqual(tile_layer["render_order"], 10)
        self.assertTrue(tile_layer["y_sort"])
        self.assertEqual(tile_layer["sort_y_offset"], -2)
        self.assertEqual(tile_layer["stack_order"], 4)
        self.assertNotIn("draw_above_entities", tile_layer)

        entity_data = serialized["entities"][0]
        self.assertEqual(entity_data["render_order"], 12)
        self.assertFalse(entity_data["y_sort"])
        self.assertEqual(entity_data["sort_y_offset"], 5)
        self.assertEqual(entity_data["stack_order"], 9)
        self.assertNotIn("layer", entity_data)

    def test_serialize_area_omits_default_entity_render_fields(self) -> None:
        _, project = self._make_project(
            entity_templates={
                "marker.json": {
                    "kind": "marker",
                    "visible": False,
                    "interactable": False,
                }
            }
        )
        raw_area = _minimal_area()
        raw_area["entities"] = [
            {
                "id": "inline_world",
                "kind": "actor",
                "grid_x": 0,
                "grid_y": 0,
                "render_order": 10,
                "y_sort": True,
                "sort_y_offset": 0,
                "stack_order": 0,
            },
            {
                "id": "screen_overlay",
                "kind": "ui",
                "space": "screen",
                "pixel_x": 32,
                "pixel_y": 48,
                "render_order": 0,
                "y_sort": False,
                "sort_y_offset": 0,
                "stack_order": 0,
            },
            {
                "id": "template_marker",
                "grid_x": 1,
                "grid_y": 0,
                "template": "entity_templates/marker",
                "render_order": 10,
                "y_sort": True,
                "sort_y_offset": 0,
                "stack_order": 0,
            },
            {
                "id": "custom_render",
                "kind": "actor",
                "grid_x": 2,
                "grid_y": 0,
                "render_order": 12,
                "y_sort": False,
                "sort_y_offset": 5,
                "stack_order": 9,
            },
        ]

        area, world = load_area_from_data(raw_area, source_name="<memory>", project=project)
        serialized = serialize_area(area, world, project=project)
        entities_by_id = {entity["id"]: entity for entity in serialized["entities"]}

        inline_world = entities_by_id["inline_world"]
        self.assertNotIn("render_order", inline_world)
        self.assertNotIn("y_sort", inline_world)
        self.assertNotIn("sort_y_offset", inline_world)
        self.assertNotIn("stack_order", inline_world)

        screen_overlay = entities_by_id["screen_overlay"]
        self.assertNotIn("render_order", screen_overlay)
        self.assertNotIn("y_sort", screen_overlay)
        self.assertNotIn("sort_y_offset", screen_overlay)
        self.assertNotIn("stack_order", screen_overlay)

        template_marker = entities_by_id["template_marker"]
        self.assertEqual(template_marker["template"], "entity_templates/marker")
        self.assertNotIn("render_order", template_marker)
        self.assertNotIn("y_sort", template_marker)
        self.assertNotIn("sort_y_offset", template_marker)
        self.assertNotIn("stack_order", template_marker)

        custom_render = entities_by_id["custom_render"]
        self.assertEqual(custom_render["render_order"], 12)
        self.assertFalse(custom_render["y_sort"])
        self.assertEqual(custom_render["sort_y_offset"], 5)
        self.assertEqual(custom_render["stack_order"], 9)

    def test_area_loader_normalizes_blocked_cell_flags(self) -> None:
        _, project = self._make_project()
        raw_area = _minimal_area()
        raw_area["cell_flags"] = [
            [{"tags": ["wall"]}, {"blocked": True}],
        ]
        raw_area["tile_layers"] = [
            {
                "name": "ground",
                "render_order": 0,
                "grid": [[1, 1]],
            }
        ]

        area, world = load_area_from_data(raw_area, source_name="<memory>", project=project)

        self.assertTrue(area.is_blocked(1, 0))
        self.assertEqual(area.cell_flags_at(0, 0), {"tags": ["wall"], "blocked": False})
        self.assertEqual(
            area.cell_flags_at(1, 0),
            {"blocked": True},
        )

        serialized = serialize_area(area, world, project=project)
        self.assertEqual(
            serialized["cell_flags"],
            [[{"tags": ["wall"], "blocked": False}, {"blocked": True}]],
        )

    def test_loader_supports_new_top_level_physics_and_interaction_fields(self) -> None:
        _, project = self._make_project()
        raw_area = _minimal_area()
        raw_area["entities"] = [
            {
                "id": "crate",
                "kind": "block",
                "grid_x": 0,
                "grid_y": 0,
                "facing": "left",
                "solid": True,
                "pushable": True,
                "weight": 3,
                "push_strength": 2,
                "collision_push_strength": 4,
                "interactable": True,
                "interaction_priority": 7,
                "entity_commands": {
                    "interact": {
                        "enabled": True,
                        "commands": [],
                    }
                },
            }
        ]

        area, world = load_area_from_data(raw_area, source_name="<memory>", project=project)
        crate = world.get_entity("crate")
        self.assertIsNotNone(crate)
        assert crate is not None
        self.assertEqual(crate.get_effective_facing(), "left")
        self.assertTrue(crate.is_effectively_solid())
        self.assertTrue(crate.is_effectively_pushable())
        self.assertEqual(crate.weight, 3)
        self.assertEqual(crate.push_strength, 2)
        self.assertEqual(crate.collision_push_strength, 4)
        self.assertTrue(crate.is_effectively_interactable())
        self.assertEqual(crate.interaction_priority, 7)

        serialized = serialize_area(area, world, project=project)
        serialized_entity = serialized["entities"][0]
        self.assertEqual(serialized_entity["facing"], "left")
        self.assertTrue(serialized_entity["solid"])
        self.assertTrue(serialized_entity["pushable"])
        self.assertEqual(serialized_entity["weight"], 3)
        self.assertEqual(serialized_entity["push_strength"], 2)
        self.assertEqual(serialized_entity["collision_push_strength"], 4)
        self.assertTrue(serialized_entity["interactable"])
        self.assertEqual(serialized_entity["interaction_priority"], 7)

    def test_engine_physics_fields_ignore_same_named_variables_and_interact_commands(self) -> None:
        _, project = self._make_project()
        raw_area = _minimal_area()
        raw_area["entities"] = [
            {
                "id": "explicit_block",
                "kind": "block",
                "grid_x": 0,
                "grid_y": 0,
                "facing": "left",
                "solid": False,
                "pushable": False,
                "interactable": False,
                "variables": {
                    "direction": "right",
                    "blocks_movement": True,
                    "pushable": True,
                },
                "entity_commands": {
                    "interact": {
                        "enabled": True,
                        "commands": [],
                    }
                },
            }
        ]

        _, world = load_area_from_data(raw_area, source_name="<memory>", project=project)
        explicit_block = world.get_entity("explicit_block")
        self.assertIsNotNone(explicit_block)
        assert explicit_block is not None
        self.assertEqual(explicit_block.get_effective_facing(), "left")
        self.assertFalse(explicit_block.is_effectively_solid())
        self.assertFalse(explicit_block.is_effectively_pushable())
        self.assertFalse(explicit_block.is_effectively_interactable())

        explicit_block.variables["direction"] = "up"
        explicit_block.variables["blocks_movement"] = False
        explicit_block.variables["pushable"] = False

        self.assertEqual(explicit_block.get_effective_facing(), "left")
        self.assertFalse(explicit_block.is_effectively_solid())
        self.assertFalse(explicit_block.is_effectively_pushable())
        self.assertFalse(explicit_block.is_effectively_interactable())

    def test_entity_command_shorthand_loads_and_serializes_with_default_enabled(self) -> None:
        _, project = self._make_project()
        raw_area = _minimal_area()
        raw_area["entities"] = [
            {
                "id": "switch",
                "kind": "lever",
                "grid_x": 0,
                "grid_y": 0,
                "entity_commands": {
                    "interact": [
                        {
                            "type": "set_current_area_var",
                            "name": "opened",
                            "value": True,
                        }
                    ]
                },
            }
        ]

        area, world = load_area_from_data(raw_area, source_name="<memory>", project=project)
        switch = world.get_entity("switch")
        self.assertIsNotNone(switch)
        assert switch is not None
        self.assertTrue(switch.entity_commands["interact"].enabled)
        self.assertEqual(
            switch.entity_commands["interact"].commands,
            [{"type": "set_current_area_var", "name": "opened", "value": True}],
        )

        serialized = serialize_area(area, world, project=project)
        self.assertEqual(
            serialized["entities"][0]["entity_commands"],
            {
                "interact": [
                    {
                        "type": "set_current_area_var",
                        "name": "opened",
                        "value": True,
                    }
                ]
            },
        )

    def test_entity_command_long_form_preserves_disabled_state(self) -> None:
        _, project = self._make_project()
        raw_area = _minimal_area()
        raw_area["entities"] = [
            {
                "id": "sign_1",
                "kind": "sign",
                "grid_x": 0,
                "grid_y": 0,
                "entity_commands": {
                    "interact": {
                        "enabled": False,
                        "commands": [
                            {
                                "type": "set_current_area_var",
                                "name": "opened",
                                "value": True,
                            }
                        ],
                    }
                },
            }
        ]

        area, world = load_area_from_data(raw_area, source_name="<memory>", project=project)
        sign = world.get_entity("sign_1")
        self.assertIsNotNone(sign)
        assert sign is not None
        self.assertFalse(sign.entity_commands["interact"].enabled)

        serialized = serialize_area(area, world, project=project)
        self.assertEqual(
            serialized["entities"][0]["entity_commands"],
            {
                "interact": {
                    "enabled": False,
                    "commands": [
                        {
                            "type": "set_current_area_var",
                            "name": "opened",
                            "value": True,
                        }
                    ],
                }
            },
        )

    def test_entity_command_object_without_enabled_is_rejected(self) -> None:
        _, project = self._make_project(
            entity_templates={
                "sign.json": {
                    "kind": "sign",
                    "entity_commands": {
                        "interact": {
                            "commands": [
                                {
                                    "type": "set_current_area_var",
                                    "name": "opened",
                                    "value": True,
                                }
                            ]
                        }
                    },
                }
            }
        )

        with self.assertRaises(EntityTemplateValidationError) as raised:
            validate_project_entity_templates(project)

        self.assertTrue(
            any(
                "object form must define both 'enabled' and 'commands'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_load_project_requires_manifest(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)

        with self.assertRaises(FileNotFoundError):
            load_project(Path(temp_dir.name) / "project.json")

    def test_area_loader_leaves_unassigned_project_input_routes_unrouted(self) -> None:
        _, project = self._make_project(
            input_routes={
                "menu": {"entity_id": "pause_controller", "command_id": "open_pause"}
            },
        )
        raw_area = _minimal_area()
        raw_area.pop("input_routes", None)
        raw_area["entities"] = [
            {
                "id": "hero",
                "kind": "player",
                "grid_x": 0,
                "grid_y": 0,
            }
        ]

        _, world = load_area_from_data(raw_area, source_name="<memory>", project=project)
        world.add_entity(
            _make_runtime_entity(
                "pause_controller",
                kind="system",
                space="screen",
                scope="global",
            )
        )

        self.assertIsNone(world.get_input_target_id("move_up"))
        self.assertIsNone(world.get_input_target_id("interact"))
        self.assertEqual(world.get_input_target_id("menu"), "pause_controller")

    def test_entity_template_validation_rejects_removed_sprite_field(self) -> None:
        _, project = self._make_project(
            entity_templates={
                "removed_sprite_sign.json": {
                    "kind": "sign",
                    "sprite": {
                        "path": "assets/project/sprites/sign.png",
                    },
                }
            }
        )

        with self.assertRaises(EntityTemplateValidationError) as raised:
            validate_project_entity_templates(project)

        self.assertTrue(
            any("must not use 'sprite'" in issue for issue in raised.exception.issues)
        )

    def test_template_parameter_specs_validate_and_do_not_leak_to_instances(self) -> None:
        raw_area = _minimal_area()
        raw_area["entities"] = [
            {
                "id": "target",
                "kind": "marker",
                "grid_x": 0,
                "grid_y": 0,
                "entity_commands": {
                    "activate": []
                },
            },
            {
                "id": "relay",
                "grid_x": 0,
                "grid_y": 0,
                "template": "entity_templates/relay",
                "parameters": {
                    "target_entity_id": "target",
                    "target_command_id": "activate",
                    "count": 2,
                },
            },
        ]
        _, project = self._make_project(
            entity_templates={
                "relay.json": {
                    "kind": "relay",
                    "parameters": {
                        "target_entity_id": "",
                        "target_command_id": "",
                        "count": 1,
                    },
                    "parameter_specs": {
                        "target_entity_id": {
                            "type": "entity_id",
                            "required": True,
                            "scope": "area",
                            "space": "world",
                        },
                        "target_command_id": {
                            "type": "entity_command_id",
                            "required": True,
                            "of": "target_entity_id",
                        },
                        "count": {
                            "type": "int",
                            "min": 1,
                        },
                    },
                    "variables": {
                        "count": "$count",
                    },
                    "entity_commands": {
                        "interact": [
                            {
                                "type": "run_entity_command",
                                "entity_id": "$target_entity_id",
                                "command_id": "$target_command_id",
                            }
                        ]
                    },
                }
            },
            areas={"room.json": raw_area},
        )

        area, world = load_area_from_data(raw_area, source_name="<memory>", project=project)

        relay = world.get_entity("relay")
        self.assertIsNotNone(relay)
        assert relay is not None
        self.assertEqual(relay.variables["count"], 2)
        serialized = serialize_area(area, world, project=project)
        relay_data = next(entity for entity in serialized["entities"] if entity["id"] == "relay")
        self.assertNotIn("parameter_specs", relay_data)

    def test_area_loader_rejects_unknown_parameter_when_specs_declared(self) -> None:
        raw_area = _minimal_area()
        raw_area["entities"] = [
            {
                "id": "counter_1",
                "grid_x": 0,
                "grid_y": 0,
                "template": "entity_templates/counter",
                "parameters": {
                    "count": 2,
                    "extra": True,
                },
            }
        ]
        _, project = self._make_project(
            entity_templates={
                "counter.json": {
                    "kind": "counter",
                    "parameters": {
                        "count": 1,
                    },
                    "parameter_specs": {
                        "count": {
                            "type": "int",
                            "min": 0,
                        }
                    },
                    "variables": {
                        "count": "$count",
                    },
                }
            },
            areas={"room.json": raw_area},
        )

        with self.assertRaisesRegex(ValueError, "unknown template parameter"):
            load_area_from_data(raw_area, source_name="<memory>", project=project)

    def test_area_loader_rejects_parameter_spec_type_mismatch(self) -> None:
        raw_area = _minimal_area()
        raw_area["entities"] = [
            {
                "id": "counter_1",
                "grid_x": 0,
                "grid_y": 0,
                "template": "entity_templates/counter",
                "parameters": {
                    "count": "many",
                },
            }
        ]
        _, project = self._make_project(
            entity_templates={
                "counter.json": {
                    "kind": "counter",
                    "parameters": {
                        "count": 1,
                    },
                    "parameter_specs": {
                        "count": {
                            "type": "int",
                            "min": 0,
                        }
                    },
                    "variables": {
                        "count": "$count",
                    },
                }
            },
            areas={"room.json": raw_area},
        )

        with self.assertRaisesRegex(ValueError, "must be an integer"):
            load_area_from_data(raw_area, source_name="<memory>", project=project)

    def test_area_loader_rejects_entity_parameter_with_wrong_space(self) -> None:
        raw_area = _minimal_area()
        raw_area["entities"] = [
            {
                "id": "screen_target",
                "kind": "ui",
                "space": "screen",
                "pixel_x": 0,
                "pixel_y": 0,
            },
            {
                "id": "relay",
                "grid_x": 0,
                "grid_y": 0,
                "template": "entity_templates/relay",
                "parameters": {
                    "target_entity_id": "screen_target",
                },
            },
        ]
        _, project = self._make_project(
            entity_templates={
                "relay.json": {
                    "kind": "relay",
                    "parameters": {
                        "target_entity_id": "",
                    },
                    "parameter_specs": {
                        "target_entity_id": {
                            "type": "entity_id",
                            "scope": "area",
                            "space": "world",
                        }
                    },
                    "variables": {
                        "target": "$target_entity_id",
                    },
                }
            },
            areas={"room.json": raw_area},
        )

        with self.assertRaisesRegex(ValueError, "world-space entity"):
            load_area_from_data(raw_area, source_name="<memory>", project=project)

    def test_area_loader_rejects_entity_parameter_in_wrong_area(self) -> None:
        raw_area = _minimal_area()
        raw_area["entities"] = [
            {
                "id": "local_marker",
                "kind": "marker",
                "grid_x": 0,
                "grid_y": 0,
            },
            {
                "id": "transition",
                "grid_x": 0,
                "grid_y": 0,
                "template": "entity_templates/transition",
                "parameters": {
                    "target_area": "areas/destination",
                    "destination_entity_id": "local_marker",
                },
            },
        ]
        destination_area = _minimal_area()
        destination_area["entities"] = [
            {
                "id": "destination_marker",
                "kind": "marker",
                "grid_x": 0,
                "grid_y": 0,
            }
        ]
        _, project = self._make_project(
            entity_templates={
                "transition.json": {
                    "kind": "area_transition",
                    "parameters": {
                        "target_area": "areas/destination",
                        "destination_entity_id": "destination_marker",
                    },
                    "parameter_specs": {
                        "target_area": {
                            "type": "area_id",
                        },
                        "destination_entity_id": {
                            "type": "entity_id",
                            "of": "target_area",
                            "scope": "area",
                            "space": "world",
                        },
                    },
                    "entity_commands": {
                        "on_occupant_enter": [
                            {
                                "type": "change_area",
                                "area_id": "$target_area",
                                "destination_entity_id": "$destination_entity_id",
                            }
                        ]
                    },
                }
            },
            areas={
                "room.json": raw_area,
                "destination.json": destination_area,
            },
        )

        with self.assertRaisesRegex(ValueError, "entity in area 'areas/destination'"):
            load_area_from_data(raw_area, source_name="<memory>", project=project)

    def test_entity_template_validation_rejects_invalid_parameter_specs(self) -> None:
        _, project = self._make_project(
            entity_templates={
                "bad_spec.json": {
                    "kind": "counter",
                    "parameters": {
                        "count": 1,
                    },
                    "parameter_specs": {
                        "count": {
                            "type": "integer",
                        }
                    },
                    "variables": {
                        "count": "$count",
                    },
                }
            }
        )

        with self.assertRaises(EntityTemplateValidationError) as raised:
            validate_project_entity_templates(project)

        self.assertTrue(
            any("parameter_specs.count.type" in issue for issue in raised.exception.issues)
        )

    def test_entity_template_parameters_remain_untyped_without_specs(self) -> None:
        _, project = self._make_project(
            entity_templates={
                "legacy_counter.json": {
                    "kind": "counter",
                    "parameters": {
                        "count": 1,
                    },
                    "variables": {
                        "count": "$count",
                    },
                }
            }
        )

        validate_project_entity_templates(project)

    def test_project_command_validation_rejects_authored_id(self) -> None:
        _, project = self._make_project(
            commands={
                "walk_one_tile.json": {
                    "id": "walk_one_tile",
                    "params": [],
                    "commands": [],
                }
            }
        )

        with self.assertRaises(ProjectCommandValidationError) as raised:
            validate_project_commands(project)

        self.assertTrue(
            any("must not declare 'id'" in issue for issue in raised.exception.issues)
        )

    def test_project_command_validation_rejects_unknown_top_level_fields(self) -> None:
        _, project = self._make_project(
            commands={
                "call_hook.json": {
                    "params": ["hook"],
                    "deferred_params": ["hook"],
                    "commands": [],
                }
            }
        )

        with self.assertRaises(ProjectCommandValidationError) as raised:
            validate_project_commands(project)

        self.assertTrue(
            any(
                "contains unknown top-level field(s): deferred_params" in issue
                for issue in raised.exception.issues
            )
        )

    def test_project_command_validation_accepts_deferred_param_shapes(self) -> None:
        _, project = self._make_project(
            commands={
                "call_hook.json": {
                    "params": ["hook", "raw_blob", "dialogue"],
                    "deferred_param_shapes": {
                        "hook": "command_payload",
                        "raw_blob": "raw_data",
                        "dialogue": "dialogue_definition",
                    },
                    "commands": [],
                }
            }
        )

        validate_project_commands(project)

    def test_project_command_validation_accepts_typed_inputs_and_defaults(self) -> None:
        _, project = self._make_project(
            commands={
                "play_npc_animation.json": {
                    "inputs": {
                        "target_entity": {
                            "type": "entity_id",
                        },
                        "visual": {
                            "type": "visual_id",
                            "of": "target_entity",
                            "default": "body",
                        },
                        "animation": {
                            "type": "animation_id",
                            "of": "visual",
                            "default": "idle",
                        },
                    },
                    "commands": [
                        {
                            "type": "play_animation",
                            "entity_id": "$target_entity",
                            "visual_id": "$visual",
                            "animation": "$animation",
                        }
                    ],
                }
            }
        )

        validate_project_commands(project)
        definition = load_project_command_definition(
            project,
            "commands/play_npc_animation",
        )
        self.assertEqual(definition.params, ["target_entity", "visual", "animation"])

        commands = instantiate_project_command_commands(
            definition,
            {"target_entity": "npc_1"},
        )

        self.assertEqual(
            commands,
            [
                {
                    "type": "play_animation",
                    "entity_id": "npc_1",
                    "visual_id": "body",
                    "animation": "idle",
                }
            ],
        )

    def test_project_command_validation_rejects_forward_of_references(self) -> None:
        _, project = self._make_project(
            commands={
                "bad_animation.json": {
                    "inputs": {
                        "animation": {
                            "type": "animation_id",
                            "of": "visual",
                        },
                        "visual": {
                            "type": "visual_id",
                            "of": "target_entity",
                        },
                        "target_entity": {
                            "type": "entity_id",
                        },
                    },
                    "commands": [],
                }
            }
        )

        with self.assertRaises(ProjectCommandValidationError) as raised:
            validate_project_commands(project)

        self.assertTrue(
            any("unknown or later input 'visual'" in issue for issue in raised.exception.issues)
        )

    def test_template_parameter_specs_accept_dialogue_definition(self) -> None:
        _, project = self._make_project(
            entity_templates={
                "sign.json": {
                    "kind": "sign",
                    "parameters": {
                        "dialogue_definition": {
                            "segments": [
                                {
                                    "type": "text",
                                    "text": "A small sign.",
                                }
                            ]
                        }
                    },
                    "parameter_specs": {
                        "dialogue_definition": {
                            "type": "dialogue_definition",
                            "required": True,
                        }
                    },
                    "entity_commands": {
                        "interact": [
                            {
                                "type": "open_dialogue_session",
                                "dialogue_definition": "$dialogue_definition",
                            }
                        ]
                    },
                }
            }
        )

        validate_project_entity_templates(project)

    def test_template_parameter_specs_accept_visual_and_animation_ids(self) -> None:
        _, project = self._make_project(
            entity_templates={
                "animated_marker.json": {
                    "kind": "marker",
                    "parameters": {
                        "visual": "body",
                        "animation": "idle",
                    },
                    "parameter_specs": {
                        "visual": {
                            "type": "visual_id",
                        },
                        "animation": {
                            "type": "animation_id",
                            "of": "visual",
                        },
                    },
                    "visuals": [
                        {
                            "id": "body",
                            "path": "assets/project/sprites/test.png",
                            "frame_width": 16,
                            "frame_height": 16,
                            "frames": [0],
                            "animations": {
                                "idle": {"frames": [0]},
                            },
                        }
                    ],
                }
            }
        )

        validate_project_entity_templates(project)

    def test_entity_template_validation_rejects_forward_parameter_of_references(self) -> None:
        _, project = self._make_project(
            entity_templates={
                "bad_animation.json": {
                    "kind": "marker",
                    "parameters": {
                        "visual": "body",
                        "animation": "idle",
                    },
                    "parameter_specs": {
                        "animation": {
                            "type": "animation_id",
                            "of": "visual",
                        },
                        "visual": {
                            "type": "visual_id",
                        },
                    },
                }
            }
        )

        with self.assertRaises(EntityTemplateValidationError) as raised:
            validate_project_entity_templates(project)

        self.assertTrue(
            any("unknown or later parameter 'visual'" in issue for issue in raised.exception.issues)
        )

    def test_template_parameter_specs_accept_entity_dialogue_map_definitions(self) -> None:
        raw_area = _minimal_area()
        raw_area["entities"] = [
            {
                "id": "speaker",
                "grid_x": 0,
                "grid_y": 0,
                "template": "entity_templates/speaker",
                "parameters": {
                    "intro_dialogue": {
                        "segments": [
                            {
                                "type": "text",
                                "text": "Hello there.",
                            }
                        ]
                    }
                },
            }
        ]
        _, project = self._make_project(
            entity_templates={
                "speaker.json": {
                    "kind": "npc",
                    "parameters": {
                        "intro_dialogue": {
                            "segments": [
                                {
                                    "type": "text",
                                    "text": "Fallback.",
                                }
                            ]
                        }
                    },
                    "parameter_specs": {
                        "intro_dialogue": {
                            "type": "dialogue_definition",
                            "required": True,
                        }
                    },
                    "dialogues": {
                        "intro": {
                            "dialogue_definition": "$intro_dialogue",
                        }
                    },
                    "variables": {
                        "active_dialogue": "intro",
                    },
                }
            },
            areas={"room.json": raw_area},
        )

        area, world = load_area_from_data(raw_area, source_name="<memory>", project=project)
        speaker = world.get_entity("speaker")
        self.assertIsNotNone(speaker)
        assert speaker is not None
        self.assertEqual(
            speaker.dialogues["intro"]["dialogue_definition"]["segments"][0]["text"],
            "Hello there.",
        )

        serialized = serialize_area(area, world, project=project)
        speaker_data = next(entity for entity in serialized["entities"] if entity["id"] == "speaker")
        self.assertNotIn("dialogues", speaker_data)
        self.assertEqual(speaker_data["parameters"]["intro_dialogue"]["segments"][0]["text"], "Hello there.")

    def test_entity_template_validation_rejects_dialogue_entry_with_both_sources(self) -> None:
        _, project = self._make_project(
            entity_templates={
                "speaker.json": {
                    "kind": "npc",
                    "dialogues": {
                        "intro": {
                            "dialogue_path": "dialogues/npcs/intro.json",
                            "dialogue_definition": {
                                "segments": [
                                    {
                                        "type": "text",
                                        "text": "Hello.",
                                    }
                                ]
                            },
                        }
                    },
                }
            }
        )

        with self.assertRaises(EntityTemplateValidationError) as raised:
            validate_project_entity_templates(project)

        self.assertTrue(
            any(
                "must define exactly one of 'dialogue_path' or 'dialogue_definition'" in issue
                for issue in raised.exception.issues
            )
        )

    def test_project_command_validation_rejects_symbolic_entity_refs_for_strict_primitives(self) -> None:
        _, project = self._make_project(
            commands={
                "bad_primitive.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "set_entity_field",
                            "entity_id": "self",
                            "field_name": "visible",
                            "value": False,
                        }
                    ],
                }
            }
        )

        with self.assertRaises(ProjectCommandValidationError) as raised:
            validate_project_commands(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'self' with strict primitive 'set_entity_field'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_project_command_validation_rejects_symbolic_entity_refs_for_strict_visual_primitives(self) -> None:
        _, project = self._make_project(
            commands={
                "bad_visual_primitive.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "play_animation",
                            "entity_id": "self",
                            "animation": "open",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(ProjectCommandValidationError) as raised:
            validate_project_commands(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'self' with strict primitive 'play_animation'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_project_command_validation_rejects_symbolic_entity_refs_for_strict_movement_primitives(self) -> None:
        _, project = self._make_project(
            commands={
                "bad_move_primitive.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "move_entity_position",
                            "entity_id": "self",
                            "space": "world_pixel",
                            "x": 16,
                            "y": 0,
                            "mode": "relative",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(ProjectCommandValidationError) as raised:
            validate_project_commands(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'self' with strict primitive 'move_entity_position'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_project_command_validation_rejects_symbolic_entity_refs_for_camera_policy_follow(self) -> None:
        _, project = self._make_project(
            commands={
                "bad_camera_policy.json": {
                    "params": [],
                    "commands": [
                        {
                            "type": "set_camera_policy",
                            "follow": {
                                "mode": "entity",
                                "entity_id": "self",
                            },
                        }
                    ],
                }
            }
        )

        with self.assertRaises(ProjectCommandValidationError) as raised:
            validate_project_commands(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'self' inside 'set_camera_policy.follow.entity_id'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_area_validation_rejects_removed_interact_commands_field(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "sign_1",
                            "kind": "sign",
                            "grid_x": 1,
                            "grid_y": 1,
                            "interact_commands": [{"type": "run_dialogue", "text": "Old schema"}],
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "interact_commands" in issue and "entity_commands.interact" in issue
                for issue in raised.exception.issues
            )
        )

    def test_area_validation_rejects_symbolic_entity_refs_for_strict_primitives(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "set_input_route",
                            "action": "interact",
                            "entity_id": "self",
                            "command_id": "interact",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'self' with strict primitive 'set_input_route'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_area_validation_rejects_symbolic_entity_refs_for_strict_animation_primitives(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "play_animation",
                            "entity_id": "self",
                            "animation": "idle",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'self' with strict primitive 'play_animation'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_area_validation_rejects_symbolic_entity_refs_for_strict_movement_primitives(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "enter_commands": [
                        {
                            "type": "wait_for_move",
                            "entity_id": "self",
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "must not use symbolic entity id 'self' with strict primitive 'wait_for_move'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_area_validation_rejects_reserved_entity_id_self(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "self",
                            "kind": "sign",
                            "grid_x": 1,
                            "grid_y": 1,
                        }
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "reserved runtime entity reference 'self'" in issue
                for issue in raised.exception.issues
            )
        )

    def test_area_validation_allows_entity_id_actor(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "actor",
                            "kind": "sign",
                            "grid_x": 1,
                            "grid_y": 1,
                        }
                    ],
                }
            }
        )

        validate_project_areas(project)

    def test_area_validation_rejects_duplicate_project_global_entity_ids(self) -> None:
        _, project = self._make_project(
            global_entities=[
                {
                    "id": "dialogue_controller",
                    "kind": "system",
                    "space": "screen",
                },
                {
                    "id": "dialogue_controller",
                    "kind": "system",
                    "space": "screen",
                },
            ],
            areas={"test_room.json": _minimal_area()},
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "global_entities[1] uses duplicate entity id 'dialogue_controller'" in issue
                for issue in raised.exception.issues
            )
        )

    def test_area_validation_rejects_duplicate_area_entity_ids_within_one_area(self) -> None:
        _, project = self._make_project(
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "gate_1",
                            "kind": "gate",
                            "grid_x": 1,
                            "grid_y": 1,
                        },
                        {
                            "id": "gate_1",
                            "kind": "gate",
                            "grid_x": 2,
                            "grid_y": 1,
                        },
                    ],
                }
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "Entity id 'gate_1' already exists as a area-scope entity and cannot be added again."
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_area_validation_rejects_duplicate_area_entity_ids_across_areas(self) -> None:
        _, project = self._make_project(
            areas={
                "room_a.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "gate_1",
                            "kind": "gate",
                            "grid_x": 1,
                            "grid_y": 1,
                        }
                    ],
                },
                "room_b.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "gate_1",
                            "kind": "gate",
                            "grid_x": 2,
                            "grid_y": 1,
                        }
                    ],
                },
            }
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "Duplicate area entity id 'gate_1' found in:" in issue
                for issue in raised.exception.issues
            )
        )

    def test_area_validation_rejects_area_entity_id_collision_with_project_global(self) -> None:
        _, project = self._make_project(
            global_entities=[
                {
                    "id": "dialogue_controller",
                    "kind": "system",
                    "space": "screen",
                }
            ],
            areas={
                "test_room.json": {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "dialogue_controller",
                            "kind": "sign",
                            "grid_x": 1,
                            "grid_y": 1,
                        }
                    ],
                }
            },
        )

        with self.assertRaises(AreaValidationError) as raised:
            validate_project_areas(project)

        self.assertTrue(
            any(
                "conflicts with project.json global entity id 'dialogue_controller'"
                in issue
                for issue in raised.exception.issues
            )
        )

    def test_load_area_from_data_rejects_duplicate_entity_ids_in_one_area(self) -> None:
        _, project = self._make_project()

        with self.assertRaises(ValueError):
            load_area_from_data(
                {
                    **_minimal_area(),
                    "entities": [
                        {
                            "id": "gate_1",
                            "kind": "gate",
                            "grid_x": 1,
                            "grid_y": 1,
                        },
                        {
                            "id": "gate_1",
                            "kind": "sign",
                            "grid_x": 2,
                            "grid_y": 1,
                        },
                    ],
                },
                source_name="<memory>",
                project=project,
            )

    def test_game_launcher_resolves_startup_area_and_cli_ids(self) -> None:
        _, project = self._make_project(
            startup_area="areas/intro/title_screen",
            areas={"intro/title_screen.json": _minimal_area()},
        )

        self.assertEqual(run_game._resolve_project_startup_area(project), "areas/intro/title_screen")
        self.assertEqual(
            run_game._resolve_area_argument(project, "areas/intro/title_screen"),
            "areas/intro/title_screen",
        )

    def test_game_launcher_rejects_area_paths_as_cli_arguments(self) -> None:
        _, project = self._make_project(
            startup_area="areas/intro/title_screen",
            areas={"intro/title_screen.json": _minimal_area()},
        )

        with self.assertRaises(FileNotFoundError):
            run_game._resolve_area_argument(project, "areas/intro/title_screen.json")

    def test_game_launcher_default_project_path_prefers_existing_manifest_over_named_fixture(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        projects_dir = Path(temp_dir.name)
        launcher_state = SimpleNamespace(last_project=None)

        self.assertEqual(run_game._default_project_path(launcher_state, projects_dir), projects_dir.resolve())

        alpha_project = projects_dir / "alpha_project"
        beta_project = projects_dir / "beta_project"
        _write_json(alpha_project / "project.json", {"area_paths": ["areas/"]})
        _write_json(beta_project / "project.json", {"area_paths": ["areas/"]})

        self.assertEqual(
            run_game._default_project_path(launcher_state, projects_dir),
            (alpha_project / "project.json").resolve(),
        )
