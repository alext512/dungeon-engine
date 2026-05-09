from __future__ import annotations

import unittest

from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.context_services import build_command_services
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import (
    CommandContext,
    _resolve_runtime_values,
    execute_command_spec,
)
from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity, EntityVisual
from dungeon_engine.world.world import World


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


class _FixedRandom:
    def __init__(self, randint_result: int, choice_result: object) -> None:
        self.randint_result = randint_result
        self.choice_result = choice_result
        self.randint_calls: list[tuple[int, int]] = []
        self.choice_calls: list[list[object]] = []

    def randint(self, minimum: int, maximum: int) -> int:
        self.randint_calls.append((minimum, maximum))
        return self.randint_result

    def choice(self, values: list[object]) -> object:
        self.choice_calls.append(list(values))
        return self.choice_result


class RuntimeValueSourceTests(unittest.TestCase):
    def _make_command_context(
        self,
        *,
        area: Area | None = None,
        world: World | None = None,
    ) -> tuple[CommandRegistry, CommandContext]:
        registry = CommandRegistry()
        register_builtin_commands(registry)
        context = CommandContext(
            services=build_command_services(
                area=area or _minimal_runtime_area(),
                world=world or World(),
                collision_system=None,
                movement_system=None,
                interaction_system=None,
                animation_system=None,
            ),
        )
        return registry, context

    def test_boolean_and_random_value_sources_store_resolved_values(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("dialogue_controller", space="screen"))
        registry, context = self._make_command_context(world=world)
        fixed_random = _FixedRandom(randint_result=4, choice_result="blue")
        context.random_generator = fixed_random

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "all_true",
                "value": {"$and": [True, 1, "yes"]},
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "any_true",
                "value": {"$or": [0, "", "picked"]},
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "negated",
                "value": {"$not": []},
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "strict_not_true",
                "value": {"$boolean_not": True},
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "strict_not_null",
                "value": {"$boolean_not": None},
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "list_length",
                "value": {"$length": [1, 2, 3]},
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "null_length",
                "value": {"$length": None},
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "random_roll",
                "value": {"$random_int": {"min": 2, "max": 6}},
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "picked_color",
                "value": {
                    "$random_choice": {
                        "value": ["red", "blue", "green"],
                        "default": "none",
                    }
                },
            },
        ).update(0.0)
        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "empty_pick",
                "value": {
                    "$random_choice": {
                        "value": [],
                        "default": "fallback",
                    }
                },
            },
        ).update(0.0)

        controller = world.get_entity("dialogue_controller")
        assert controller is not None
        self.assertTrue(controller.variables["all_true"])
        self.assertTrue(controller.variables["any_true"])
        self.assertTrue(controller.variables["negated"])
        self.assertFalse(controller.variables["strict_not_true"])
        self.assertTrue(controller.variables["strict_not_null"])
        self.assertEqual(controller.variables["list_length"], 3)
        self.assertEqual(controller.variables["null_length"], 0)
        self.assertEqual(controller.variables["random_roll"], 4)
        self.assertEqual(controller.variables["picked_color"], "blue")
        self.assertEqual(controller.variables["empty_pick"], "fallback")
        self.assertEqual(fixed_random.randint_calls, [(2, 6)])
        self.assertEqual(fixed_random.choice_calls, [["red", "blue", "green"]])

        with self.assertRaisesRegex(
            TypeError,
            r"\$boolean_not value source expects a boolean or null value",
        ):
            _resolve_runtime_values({"$boolean_not": "yes"}, context, {})
        with self.assertRaisesRegex(
            TypeError,
            r"\$length value source requires a sized value or null",
        ):
            _resolve_runtime_values({"$length": 5}, context, {})

    def test_arithmetic_value_sources_store_resolved_values(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("calculator", space="screen"))
        registry, context = self._make_command_context(world=world)

        arithmetic_specs = [
            ("added", {"$add": [2, 3, 4]}, 9),
            ("subtracted", {"$subtract": [10, 3, 2]}, 5),
            ("multiplied", {"$multiply": [3, 4, 2]}, 24),
            ("divided_evenly", {"$divide": [12, 2]}, 6),
            ("divided_fraction", {"$divide": [5, 2]}, 2.5),
        ]
        for name, value, expected in arithmetic_specs:
            with self.subTest(name=name):
                execute_command_spec(
                    registry,
                    context,
                    {
                        "type": "set_entity_var",
                        "entity_id": "calculator",
                        "name": name,
                        "value": value,
                    },
                ).update(0.0)
                calculator = world.get_entity("calculator")
                assert calculator is not None
                self.assertEqual(calculator.variables[name], expected)

        with self.assertRaisesRegex(KeyError, r"Unknown value source '\$sum'"):
            _resolve_runtime_values({"$sum": [1, 2]}, context, {})
        with self.assertRaisesRegex(KeyError, r"Unknown value source '\$product'"):
            _resolve_runtime_values({"$product": [2, 3]}, context, {})
        with self.assertRaisesRegex(ZeroDivisionError, r"\$divide value source cannot divide by zero"):
            _resolve_runtime_values({"$divide": [1, 0]}, context, {})

    def test_explicit_movement_query_value_sources_resolve_cell_flags_and_blockers(self) -> None:
        area = Area(
            area_id="areas/test_room",
            tile_size=16,
            tilesets=[],
            tile_layers=[],
            cell_flags=[
                [{"blocked": False}, {"blocked": False}, {"blocked": False}],
                [{"blocked": False}, {"blocked": False}, {"blocked": True}],
                [{"blocked": False}, {"blocked": False}, {"blocked": False}],
            ],
        )
        world = World()
        actor = _make_runtime_entity("player", kind="player")
        actor.grid_x = 1
        actor.grid_y = 1
        blocking_entity = _make_runtime_entity("crate", kind="crate")
        blocking_entity.grid_x = 2
        blocking_entity.grid_y = 1
        blocking_entity.solid = True
        blocking_entity.pushable = True
        world.add_entity(actor)
        world.add_entity(blocking_entity)
        registry, context = self._make_command_context(area=area, world=world)

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "player",
                "name": "target_cell",
                "value": {
                    "$cell_flags_at": {
                        "x": 2,
                        "y": 1,
                    }
                },
            },
        ).update(0.0)

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "player",
                "name": "target_entities",
                "value": {
                    "$entities_at": {
                        "x": 2,
                        "y": 1,
                        "select": {
                            "fields": ["entity_id", "solid", "pushable"],
                        },
                    }
                },
            },
        ).update(0.0)

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "player",
                "name": "blocking_entity",
                "value": {
                    "$find_in_collection": {
                        "value": "$self.target_entities",
                        "field": "solid",
                        "op": "eq",
                        "match": True,
                        "default": None,
                    }
                },
            },
            base_params={"source_entity_id": "player"},
        ).update(0.0)

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "player",
                "name": "has_pushable_blocker",
                "value": {
                    "$any_in_collection": {
                        "value": "$self.target_entities",
                        "field": "pushable",
                        "op": "eq",
                        "match": True,
                    }
                },
            },
            base_params={"source_entity_id": "player"},
        ).update(0.0)

        player = world.get_entity("player")
        assert player is not None
        self.assertEqual(player.variables["target_cell"]["blocked"], True)
        self.assertEqual(player.variables["blocking_entity"]["entity_id"], "crate")
        self.assertTrue(player.variables["has_pushable_blocker"])

    def test_entities_at_and_entity_at_value_sources_return_stable_plain_refs(self) -> None:
        world = World()
        low = _make_runtime_entity("low", kind="sign")
        low.grid_x = 2
        low.grid_y = 3
        low.render_order = 1
        low.stack_order = 0
        high = _make_runtime_entity("high", kind="lever")
        high.grid_x = 2
        high.grid_y = 3
        high.render_order = 2
        high.stack_order = 5
        high.solid = True
        high.pushable = True
        high.variables["custom_marker"] = "blocking"
        high.visuals.append(
            EntityVisual(
                visual_id="main",
                visible=False,
                flip_x=True,
                current_frame=3,
            )
        )
        world.add_entity(low)
        world.add_entity(high)
        world.add_entity(_make_runtime_entity("dialogue_controller", space="screen"))
        registry, context = self._make_command_context(world=world)

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "targets_here",
                "value": {
                    "$entities_at": {
                        "x": 2,
                        "y": 3,
                        "select": {
                            "fields": ["entity_id", "kind"],
                        },
                    }
                },
            },
        ).update(0.0)

        controller = world.get_entity("dialogue_controller")
        assert controller is not None
        targets_here = controller.variables["targets_here"]
        self.assertEqual([item["entity_id"] for item in targets_here], ["low", "high"])
        self.assertEqual(targets_here[0]["kind"], "sign")
        self.assertEqual(targets_here[1]["kind"], "lever")

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "first_target",
                "value": {
                    "$entity_at": {
                        "x": 2,
                        "y": 3,
                        "index": 0,
                        "select": {
                            "fields": ["entity_id"],
                        },
                        "default": None,
                    }
                },
            },
        ).update(0.0)
        self.assertEqual(controller.variables["first_target"]["entity_id"], "low")

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "last_target",
                "value": {
                    "$entity_at": {
                        "x": 2,
                        "y": 3,
                        "index": -1,
                        "select": {
                            "fields": ["entity_id"],
                        },
                        "default": None,
                    }
                },
            },
        ).update(0.0)
        self.assertEqual(controller.variables["last_target"]["entity_id"], "high")

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "self_ref",
                "value": {
                    "$entity_ref": {
                        "entity_id": "high",
                        "select": {
                            "fields": ["entity_id", "grid_x", "solid", "pushable"],
                            "variables": ["custom_marker"],
                        },
                    }
                },
            },
        ).update(0.0)
        self.assertEqual(controller.variables["self_ref"]["entity_id"], "high")
        self.assertEqual(controller.variables["self_ref"]["grid_x"], 2)
        self.assertTrue(controller.variables["self_ref"]["solid"])
        self.assertTrue(controller.variables["self_ref"]["pushable"])
        self.assertEqual(
            controller.variables["self_ref"]["variables"],
            {"custom_marker": "blocking"},
        )

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "selected_ref",
                "value": {
                    "$entity_ref": {
                        "entity_id": "high",
                        "select": {
                            "fields": ["grid_x", "pixel_y", "present", "pushable"],
                            "variables": ["custom_marker"],
                            "visuals": [
                                {
                                    "id": "main",
                                    "fields": ["visible", "flip_x", "current_frame"],
                                }
                            ],
                        },
                    }
                },
            },
        ).update(0.0)
        self.assertEqual(
            controller.variables["selected_ref"],
            {
                "grid_x": 2,
                "pixel_y": 0.0,
                "present": True,
                "pushable": True,
                "variables": {"custom_marker": "blocking"},
                "visuals": {
                    "main": {
                        "visible": False,
                        "flip_x": True,
                        "current_frame": 3,
                    }
                },
            },
        )

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "selected_target",
                "value": {
                    "$entity_at": {
                        "x": 2,
                        "y": 3,
                        "index": -1,
                        "select": {
                            "fields": ["entity_id", "pushable"],
                            "variables": ["custom_marker"],
                        },
                        "default": None,
                    }
                },
            },
        ).update(0.0)
        self.assertEqual(
            controller.variables["selected_target"],
            {
                "entity_id": "high",
                "pushable": True,
                "variables": {"custom_marker": "blocking"},
            },
        )

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "selected_targets",
                "value": {
                    "$entities_at": {
                        "x": 2,
                        "y": 3,
                        "select": {
                            "fields": ["entity_id", "solid", "pushable"],
                            "variables": ["custom_marker"],
                        },
                    }
                },
            },
        ).update(0.0)
        self.assertEqual(
            controller.variables["selected_targets"],
            [
                {
                    "entity_id": "low",
                    "solid": False,
                    "pushable": False,
                    "variables": {},
                },
                {
                    "entity_id": "high",
                    "solid": True,
                    "pushable": True,
                    "variables": {"custom_marker": "blocking"},
                },
            ],
        )

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "missing_selected_ref",
                "value": {
                    "$entity_ref": {
                        "entity_id": "missing",
                        "select": {
                            "fields": ["grid_x", "grid_y"],
                        },
                        "default": None,
                    }
                },
            },
        ).update(0.0)
        self.assertIsNone(controller.variables["missing_selected_ref"])

        with self.assertRaisesRegex(ValueError, r"\$entity_ref select\.fields does not support"):
            execute_command_spec(
                registry,
                context,
                {
                    "type": "set_entity_var",
                    "entity_id": "dialogue_controller",
                    "name": "invalid_select",
                    "value": {
                        "$entity_ref": {
                            "entity_id": "high",
                            "select": {
                                "fields": ["grid_x", "variables"],
                            },
                        }
                    },
                },
            )

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "target_x",
                "value": {
                    "$add": [
                        "$self.self_ref.grid_x",
                        -1,
                    ]
                },
            },
            base_params={"source_entity_id": "dialogue_controller"},
        ).update(0.0)
        self.assertEqual(controller.variables["target_x"], 1)

    def test_entity_query_value_sources_support_where_filters(self) -> None:
        world = World()
        sign = _make_runtime_entity("alpha_sign", kind="sign")
        sign.grid_x = 2
        sign.grid_y = 3
        sign.render_order = 1
        sign.stack_order = 0
        sign.tags = ["readable"]

        lever_visible = _make_runtime_entity("beta_lever", kind="lever")
        lever_visible.grid_x = 2
        lever_visible.grid_y = 3
        lever_visible.render_order = 2
        lever_visible.stack_order = 0
        lever_visible.tags = ["switch", "red"]
        lever_visible.variables["toggled"] = False

        lever_hidden = _make_runtime_entity("aardvark_hidden", kind="lever")
        lever_hidden.grid_x = 2
        lever_hidden.grid_y = 3
        lever_hidden.render_order = 2
        lever_hidden.stack_order = 0
        lever_hidden.visible = False
        lever_hidden.tags = ["switch", "red"]
        lever_hidden.variables["toggled"] = True

        lever_absent = _make_runtime_entity("absent_lever", kind="lever")
        lever_absent.grid_x = 5
        lever_absent.grid_y = 6
        lever_absent.render_order = 0
        lever_absent.stack_order = 0
        lever_absent.present = False
        lever_absent.tags = ["switch", "blue"]
        lever_absent.variables["toggled"] = True

        save_point = _make_runtime_entity(
            "global_save",
            kind="save_point",
            scope="global",
        )
        save_point.grid_x = 9
        save_point.grid_y = 9
        save_point.render_order = 0
        save_point.stack_order = 2
        save_point.tags = ["save_point"]

        world.add_entity(sign)
        world.add_entity(lever_visible)
        world.add_entity(lever_hidden)
        world.add_entity(lever_absent)
        world.add_entity(save_point)
        controller = _make_runtime_entity("dialogue_controller", kind="system", space="screen")
        world.add_entity(controller)
        registry, context = self._make_command_context(world=world)

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "all_switches",
                "value": {
                    "$entities_query": {
                        "where": {
                            "tags_any": ["switch"],
                        },
                        "select": {
                            "fields": ["entity_id", "visible"],
                            "variables": ["toggled"],
                        },
                    }
                },
            },
        ).update(0.0)

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "hidden_switches",
                "value": {
                    "$entities_query": {
                        "where": {
                            "tags_all": ["switch", "red"],
                            "visible": False,
                        },
                        "select": {
                            "fields": ["entity_id", "visible"],
                            "variables": ["toggled"],
                        },
                    }
                },
            },
        ).update(0.0)

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "absent_switches",
                "value": {
                    "$entities_query": {
                        "where": {
                            "kind": "lever",
                            "present": False,
                        },
                        "select": {
                            "fields": ["entity_id", "present"],
                            "variables": ["toggled"],
                        },
                    }
                },
            },
        ).update(0.0)

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "first_query_result",
                "value": {
                    "$entity_query": {
                        "where": {
                            "kinds": ["sign", "lever"],
                        },
                        "index": 0,
                        "default": None,
                        "select": {
                            "fields": ["entity_id", "kind"],
                        }
                    }
                },
            },
        ).update(0.0)

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "last_query_result",
                "value": {
                    "$entity_query": {
                        "where": {
                            "kinds": ["sign", "lever"],
                        },
                        "index": -1,
                        "default": None,
                        "select": {
                            "fields": ["entity_id", "kind"],
                        },
                    }
                },
            },
        ).update(0.0)

        execute_command_spec(
            registry,
            context,
            {
                "type": "set_entity_var",
                "entity_id": "dialogue_controller",
                "name": "hidden_tile_target",
                "value": {
                    "$entity_at": {
                        "x": 2,
                        "y": 3,
                        "index": 0,
                        "where": {
                            "kind": "lever",
                            "visible": False,
                        },
                        "select": {
                            "fields": ["entity_id", "visible"],
                        },
                        "default": None,
                    }
                },
            },
        ).update(0.0)

        controller_entity = world.get_entity("dialogue_controller")
        assert controller_entity is not None
        self.assertEqual(
            controller_entity.variables["all_switches"],
            [
                {
                    "entity_id": "beta_lever",
                    "visible": True,
                    "variables": {"toggled": False},
                }
            ],
        )
        self.assertEqual(
            controller_entity.variables["hidden_switches"],
            [
                {
                    "entity_id": "aardvark_hidden",
                    "visible": False,
                    "variables": {"toggled": True},
                }
            ],
        )
        self.assertEqual(
            controller_entity.variables["absent_switches"],
            [
                {
                    "entity_id": "absent_lever",
                    "present": False,
                    "variables": {"toggled": True},
                }
            ],
        )
        self.assertEqual(
            controller_entity.variables["first_query_result"],
            {"entity_id": "alpha_sign", "kind": "sign"},
        )
        self.assertEqual(
            controller_entity.variables["last_query_result"],
            {"entity_id": "beta_lever", "kind": "lever"},
        )
        self.assertEqual(
            controller_entity.variables["hidden_tile_target"],
            {"entity_id": "aardvark_hidden", "visible": False},
        )

        with self.assertRaisesRegex(
            ValueError,
            r"\$entities_query where does not allow both 'kind' and 'kinds'",
        ):
            execute_command_spec(
                registry,
                context,
                {
                    "type": "set_entity_var",
                    "entity_id": "dialogue_controller",
                    "name": "invalid_where",
                    "value": {
                        "$entities_query": {
                            "where": {
                                "kind": "lever",
                                "kinds": ["lever", "sign"],
                            },
                            "select": {
                                "fields": ["entity_id"],
                            },
                        }
                    },
                },
            )

        with self.assertRaisesRegex(
            ValueError,
            r"\$entities_query where\.tags_any requires a non-empty list",
        ):
            execute_command_spec(
                registry,
                context,
                {
                    "type": "set_entity_var",
                    "entity_id": "dialogue_controller",
                    "name": "invalid_where_tags",
                    "value": {
                        "$entities_query": {
                            "where": {
                                "tags_any": [],
                            },
                            "select": {
                                "fields": ["entity_id"],
                            },
                        }
                    },
                },
            )

    def test_runtime_token_lookup_rejects_removed_source_alias(self) -> None:
        context = CommandContext(
            services=build_command_services(
                area=_minimal_runtime_area(),
                world=World(),
                collision_system=None,
                movement_system=None,
                interaction_system=None,
                animation_system=None,
            ),
        )

        with self.assertRaises(KeyError):
            _resolve_runtime_values(
                "$source.some_flag",
                context,
                {"source_entity_id": "player"},
            )
