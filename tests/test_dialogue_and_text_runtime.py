from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from dungeon_engine.commands.builtin import register_builtin_commands
from dungeon_engine.commands.context_services import CommandUiServices, build_command_services
from dungeon_engine.commands.registry import CommandRegistry
from dungeon_engine.commands.runner import (
    CommandContext,
    CommandExecutionError,
    execute_command_spec,
    execute_registered_command,
)
from dungeon_engine.engine.dialogue_runtime import DialogueRuntime
from dungeon_engine.engine.screen import ScreenElementManager
from dungeon_engine.project_context import load_project
from dungeon_engine.world.area import Area
from dungeon_engine.world.entity import Entity
from dungeon_engine.world.world import World


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _dialogue_shared_variables() -> dict[str, object]:
    return {
        "dialogue_ui": {
            "default_preset": "standard",
            "presets": {
                "standard": {
                    "panel": {
                        "path": "assets/project/ui/dialogue_panel.png",
                        "x": 0,
                        "y": 148,
                    },
                    "portrait_slot": {
                        "x": 3,
                        "y": 151,
                        "width": 38,
                        "height": 38,
                    },
                    "text": {
                        "plain": {
                            "x": 8,
                            "y": 154,
                            "width": 240,
                            "max_lines": 3,
                        },
                        "with_portrait": {
                            "x": 56,
                            "y": 154,
                            "width": 192,
                            "max_lines": 3,
                        },
                    },
                    "choices": {
                        "mode": "inline",
                        "visible_rows": 3,
                        "base_y": 154,
                        "row_height": 10,
                        "overflow": "marquee",
                        "plain": {
                            "x": 8,
                            "width": 240,
                        },
                        "with_portrait": {
                            "x": 56,
                            "width": 188,
                        },
                    },
                    "font_id": "pixelbet",
                    "text_color": [245, 232, 190],
                    "choice_text_color": [238, 242, 248],
                    "ui_layer": 100,
                    "text_layer": 101,
                },
                "separate_choices": {
                    "panel": {
                        "path": "assets/project/ui/dialogue_panel.png",
                        "x": 0,
                        "y": 148,
                    },
                    "portrait_slot": {
                        "x": 3,
                        "y": 151,
                        "width": 38,
                        "height": 38,
                    },
                    "text": {
                        "plain": {
                            "x": 8,
                            "y": 154,
                            "width": 240,
                            "max_lines": 3,
                        },
                        "with_portrait": {
                            "x": 56,
                            "y": 154,
                            "width": 192,
                            "max_lines": 3,
                        },
                    },
                    "choices": {
                        "mode": "separate_panel",
                        "visible_rows": 3,
                        "x": 24,
                        "y": 96,
                        "width": 120,
                        "row_height": 10,
                        "overflow": "marquee",
                        "panel": {
                            "path": "assets/project/ui/dialogue_panel.png",
                            "x": 16,
                            "y": 88,
                        },
                    },
                    "font_id": "pixelbet",
                    "text_color": [245, 232, 190],
                    "choice_text_color": [238, 242, 248],
                    "ui_layer": 100,
                    "text_layer": 101,
                },
            },
        }
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


class _StubTextRenderer:
    def measure_text(self, text: str, *, font_id: str = "") -> tuple[int, int]:
        _ = font_id
        lines = str(text).split("\n")
        longest = max((len(line) for line in lines), default=0)
        return (longest * 6, max(1, len(lines)) * 8)

    def wrap_lines(self, text: str, max_width: int, *, font_id: str = "") -> list[str]:
        _ = max_width
        _ = font_id
        return [part for part in str(text).split(" ") if part]

    def paginate_text(
        self,
        text: str,
        max_width: int,
        max_lines: int,
        *,
        font_id: str = "",
    ) -> list[str]:
        lines = self.wrap_lines(text, max_width, font_id=font_id)
        if not lines:
            return [""]
        chunk_size = max(1, int(max_lines))
        pages: list[str] = []
        for index in range(0, len(lines), chunk_size):
            pages.append("\n".join(lines[index:index + chunk_size]))
        return pages or [""]


class DialogueAndTextRuntimeTests(unittest.TestCase):
    def _make_project(
        self,
        *,
        dialogues: dict[str, dict[str, object]] | None = None,
        shared_variables: dict[str, object] | None = None,
    ) -> tuple[Path, object]:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        project_root = Path(temp_dir.name)

        _write_json(
            project_root / "project.json",
            {
                "area_paths": ["areas/"],
                "entity_template_paths": ["entity_templates/"],
                "command_paths": ["commands/"],
                "item_paths": ["items/"],
                "shared_variables_path": "shared_variables.json",
            },
        )
        _write_json(project_root / "shared_variables.json", shared_variables or {})
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
        context.services.ui = CommandUiServices()
        return registry, context

    def _install_dialogue_runtime(
        self,
        *,
        registry: CommandRegistry,
        context: CommandContext,
        project: object,
    ) -> DialogueRuntime:
        dialogue_runtime = DialogueRuntime(
            project=project,
            screen_manager=ScreenElementManager(),
            text_renderer=_StubTextRenderer(),
            registry=registry,
            command_context=context,
        )
        assert context.services.ui is not None
        context.services.ui.screen_manager = dialogue_runtime.screen_manager
        context.services.ui.text_renderer = dialogue_runtime.text_renderer
        context.services.ui.dialogue_runtime = dialogue_runtime
        return dialogue_runtime

    def test_removed_dialogue_runtime_commands_raise_clear_errors(self) -> None:
        registry, context = self._make_command_context()
        for command_name in (
            "start_dialogue_session",
            "dialogue_advance",
            "dialogue_move_selection",
            "dialogue_confirm_choice",
            "dialogue_cancel",
            "close_dialogue",
        ):
            with self.assertRaises(CommandExecutionError) as raised:
                execute_registered_command(registry, context, command_name, {})
            self.assertIsNotNone(raised.exception.__cause__)
            self.assertIn(
                f"Unknown command '{command_name}'",
                str(raised.exception.__cause__),
            )

    def test_open_dialogue_session_runs_hooks_and_renders_text(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_note.json": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "Engine owned dialogue runtime",
                        }
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        caller = _make_runtime_entity("terminal", kind="terminal")
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        handle = execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_note.json",
                "dialogue_on_start": [
                    {
                        "type": "set_entity_var",
                        "entity_id": "$self_id",
                        "name": "phase",
                        "value": "opened",
                    }
                ],
                "dialogue_on_end": [
                    {
                        "type": "set_entity_var",
                        "entity_id": "$self_id",
                        "name": "phase",
                        "value": "closed",
                    }
                ],
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )
        self.assertFalse(handle.complete)
        self.assertTrue(dialogue_runtime.is_active())
        self.assertEqual(caller.variables["phase"], "opened")

        text_element = context.services.ui.screen_manager.get_element(DialogueRuntime.TEXT_ELEMENT_ID)
        assert text_element is not None
        self.assertIn("Engine", text_element.text)

        close_handle = execute_registered_command(
            registry,
            context,
            "close_dialogue_session",
            {},
        )
        self.assertTrue(close_handle.complete)
        self.assertFalse(dialogue_runtime.is_active())
        self.assertEqual(caller.variables["phase"], "closed")
        handle.update(0.0)
        self.assertTrue(handle.complete)

    def test_open_dialogue_session_accepts_inline_dialogue_definition(self) -> None:
        _, project = self._make_project(shared_variables=_dialogue_shared_variables())
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        caller = _make_runtime_entity("sign", kind="sign")
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        handle = execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_definition": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Read the sign?",
                            "options": [
                                {
                                    "text": "Read",
                                    "option_id": "read",
                                    "commands": [
                                        {
                                            "type": "set_entity_var",
                                            "entity_id": "$self_id",
                                            "name": "read_sign",
                                            "value": True,
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                },
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "sign"},
            },
        )

        self.assertFalse(handle.complete)
        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.dialogue_path, "")
        self.assertEqual(session.current_segment["text"], "Read the sign?")

        dialogue_runtime.handle_action("interact")

        self.assertFalse(dialogue_runtime.is_active())
        self.assertTrue(caller.variables["read_sign"])
        handle.update(0.0)
        self.assertTrue(handle.complete)

    def test_dialogue_runtime_choice_window_scrolls_after_three_visible_rows(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_choices.json": {
                    "segments": [
                        {
                            "type": "choice",
                            "options": [
                                {"text": "One", "option_id": "one"},
                                {"text": "Two", "option_id": "two"},
                                {"text": "Three", "option_id": "three"},
                                {"text": "Four", "option_id": "four"},
                                {"text": "Five", "option_id": "five"},
                            ],
                        }
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(_make_runtime_entity("terminal", kind="terminal"))
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_choices.json",
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )
        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.choice_index, 0)
        self.assertEqual(session.choice_scroll_offset, 0)

        option_0 = context.services.ui.screen_manager.get_element("engine_dialogue_option_0")
        option_1 = context.services.ui.screen_manager.get_element("engine_dialogue_option_1")
        option_2 = context.services.ui.screen_manager.get_element("engine_dialogue_option_2")
        assert option_0 is not None
        assert option_1 is not None
        assert option_2 is not None
        self.assertEqual(option_0.text, ">One")
        self.assertEqual(option_1.text, "Two")
        self.assertEqual(option_2.text, "Three")

        dialogue_runtime.handle_action("move_down")
        dialogue_runtime.handle_action("move_down")
        dialogue_runtime.handle_action("move_down")

        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.choice_index, 3)
        self.assertEqual(session.choice_scroll_offset, 1)

        option_0 = context.services.ui.screen_manager.get_element("engine_dialogue_option_0")
        option_1 = context.services.ui.screen_manager.get_element("engine_dialogue_option_1")
        option_2 = context.services.ui.screen_manager.get_element("engine_dialogue_option_2")
        assert option_0 is not None
        assert option_1 is not None
        assert option_2 is not None
        self.assertEqual(option_0.text, "Two")
        self.assertEqual(option_1.text, "Three")
        self.assertEqual(option_2.text, ">Four")

    def test_dialogue_runtime_inline_choices_render_below_prompt_text(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_inline_layout.json": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Prompt words here",
                            "options": [
                                {"text": "Confirm", "option_id": "confirm"},
                            ],
                        }
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(_make_runtime_entity("terminal", kind="terminal"))
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_inline_layout.json",
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        text_element = context.services.ui.screen_manager.get_element(DialogueRuntime.TEXT_ELEMENT_ID)
        option_element = context.services.ui.screen_manager.get_element("engine_dialogue_option_0")
        assert text_element is not None
        assert option_element is not None

        _, text_height = dialogue_runtime.text_renderer.measure_text(
            text_element.text,
            font_id=text_element.font_id,
        )
        self.assertGreaterEqual(
            option_element.y,
            text_element.y + text_height + DialogueRuntime.INLINE_CHOICE_TEXT_GAP,
        )

    def test_dialogue_runtime_inline_choices_use_remaining_lines_when_prompt_exists(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_inline_budget.json": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Prompt words here",
                            "options": [
                                {"text": "One", "option_id": "one"},
                                {"text": "Two", "option_id": "two"},
                                {"text": "Three", "option_id": "three"},
                            ],
                        }
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(_make_runtime_entity("terminal", kind="terminal"))
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_inline_budget.json",
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        option_0 = context.services.ui.screen_manager.get_element("engine_dialogue_option_0")
        option_1 = context.services.ui.screen_manager.get_element("engine_dialogue_option_1")
        option_2 = context.services.ui.screen_manager.get_element("engine_dialogue_option_2")
        assert option_0 is not None
        assert option_1 is not None
        self.assertEqual(option_0.text, ">One")
        self.assertEqual(option_1.text, "Two")
        self.assertIsNone(option_2)

    def test_dialogue_runtime_inline_choices_use_all_lines_when_no_prompt_exists(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_inline_no_prompt.json": {
                    "segments": [
                        {
                            "type": "choice",
                            "options": [
                                {"text": "One", "option_id": "one"},
                                {"text": "Two", "option_id": "two"},
                                {"text": "Three", "option_id": "three"},
                                {"text": "Four", "option_id": "four"},
                            ],
                        }
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(_make_runtime_entity("terminal", kind="terminal"))
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_inline_no_prompt.json",
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        option_0 = context.services.ui.screen_manager.get_element("engine_dialogue_option_0")
        option_1 = context.services.ui.screen_manager.get_element("engine_dialogue_option_1")
        option_2 = context.services.ui.screen_manager.get_element("engine_dialogue_option_2")
        option_3 = context.services.ui.screen_manager.get_element("engine_dialogue_option_3")
        assert option_0 is not None
        assert option_1 is not None
        assert option_2 is not None
        self.assertEqual(option_0.text, ">One")
        self.assertEqual(option_1.text, "Two")
        self.assertEqual(option_2.text, "Three")
        self.assertIsNone(option_3)

    def test_dialogue_runtime_inline_prompt_marquees_independently_of_choices(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_inline_prompt_marquee.json": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "This prompt is definitely long enough to scroll across the line",
                            "options": [
                                {"text": "One", "option_id": "one"},
                                {"text": "Two", "option_id": "two"},
                                {"text": "Three", "option_id": "three"},
                            ],
                        }
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(_make_runtime_entity("terminal", kind="terminal"))
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_inline_prompt_marquee.json",
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        text_before = context.services.ui.screen_manager.get_element(DialogueRuntime.TEXT_ELEMENT_ID)
        assert text_before is not None
        before_text = text_before.text

        dialogue_runtime.update(0.2)

        text_after = context.services.ui.screen_manager.get_element(DialogueRuntime.TEXT_ELEMENT_ID)
        assert text_after is not None
        self.assertNotEqual(text_after.text, before_text)

    def test_dialogue_runtime_can_render_choices_in_a_separate_panel(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_separate_panel.json": {
                    "ui_preset": "separate_choices",
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Pick one",
                            "options": [
                                {"text": "One", "option_id": "one"},
                                {"text": "Two", "option_id": "two"},
                            ],
                        }
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(_make_runtime_entity("terminal", kind="terminal"))
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_separate_panel.json",
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        self.assertTrue(dialogue_runtime.is_active())
        choices_panel = context.services.ui.screen_manager.get_element(
            DialogueRuntime.CHOICES_PANEL_ELEMENT_ID
        )
        option_0 = context.services.ui.screen_manager.get_element("engine_dialogue_option_0")
        assert choices_panel is not None
        assert option_0 is not None
        self.assertEqual(choices_panel.kind, "image")
        self.assertEqual((choices_panel.x, choices_panel.y), (16.0, 88.0))
        self.assertEqual((option_0.x, option_0.y), (24.0, 96.0))
        self.assertEqual(option_0.text, ">One")

    def test_dialogue_runtime_marquees_the_selected_long_option(self) -> None:
        shared_variables = copy.deepcopy(_dialogue_shared_variables())
        choices = shared_variables["dialogue_ui"]["presets"]["standard"]["choices"]["plain"]
        choices["width"] = 36
        _, project = self._make_project(
            shared_variables=shared_variables,
            dialogues={
                "system/runtime_marquee.json": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Pick one",
                            "options": [
                                {"text": "Long option text", "option_id": "long"},
                            ],
                        }
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(_make_runtime_entity("terminal", kind="terminal"))
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_marquee.json",
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        option_before = context.services.ui.screen_manager.get_element("engine_dialogue_option_0")
        assert option_before is not None
        before_text = option_before.text
        self.assertTrue(before_text.startswith(">"))

        dialogue_runtime.update(0.7)

        option_after = context.services.ui.screen_manager.get_element("engine_dialogue_option_0")
        assert option_after is not None
        self.assertTrue(option_after.text.startswith(">"))
        self.assertNotEqual(option_after.text, before_text)

    def test_dialogue_runtime_segment_hooks_override_inline_option_commands(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_override.json": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Resolve the choice",
                            "options": [
                                {
                                    "text": "Apply behavior",
                                    "option_id": "apply",
                                    "commands": [
                                        {
                                            "type": "set_entity_var",
                                            "entity_id": "$self_id",
                                            "name": "mode",
                                            "value": "inline",
                                        }
                                    ],
                                }
                            ],
                        }
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        caller = _make_runtime_entity("terminal", kind="terminal")
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_override.json",
                "segment_hooks": [
                    {
                        "option_commands_by_id": {
                            "apply": [
                                {
                                    "type": "set_entity_var",
                                    "entity_id": "$self_id",
                                    "name": "mode",
                                    "value": "hook",
                                }
                            ]
                        }
                    }
                ],
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        self.assertTrue(dialogue_runtime.is_active())
        dialogue_runtime.handle_action("interact")
        self.assertFalse(dialogue_runtime.is_active())
        self.assertEqual(caller.variables["mode"], "hook")

    def test_dialogue_runtime_timer_segments_advance_without_input(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_timer.json": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "Soon",
                            "advance": {
                                "mode": "timer",
                                "seconds": 0.25,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Later",
                        },
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(_make_runtime_entity("terminal", kind="terminal"))
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_timer.json",
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.segment_index, 0)

        dialogue_runtime.update(0.25)

        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.segment_index, 1)
        text_element = context.services.ui.screen_manager.get_element(DialogueRuntime.TEXT_ELEMENT_ID)
        assert text_element is not None
        self.assertIn("Later", text_element.text)

    def test_nested_dialogue_sessions_suspend_parent_flow_until_child_closes(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_parent.json": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Open the child dialogue",
                            "options": [
                                {
                                    "text": "Open child",
                                    "option_id": "open_child",
                                    "commands": [
                                        {
                                            "type": "open_dialogue_session",
                                            "dialogue_path": "dialogues/system/runtime_child.json",
                                            "allow_cancel": True,
                                        },
                                        {
                                            "type": "set_entity_var",
                                            "entity_id": "$self_id",
                                            "name": "result",
                                            "value": "resumed",
                                        },
                                    ],
                                }
                            ],
                        }
                    ]
                },
                "system/runtime_child.json": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "Nested child session",
                        }
                    ]
                },
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        caller = _make_runtime_entity("terminal", kind="terminal")
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        parent_handle = execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_path": "dialogues/system/runtime_parent.json",
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )
        self.assertFalse(parent_handle.complete)
        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.dialogue_path, "dialogues/system/runtime_parent.json")

        dialogue_runtime.handle_action("interact")

        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.dialogue_path, "dialogues/system/runtime_child.json")
        self.assertNotIn("result", caller.variables)

        dialogue_runtime.handle_action("menu")

        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.dialogue_path, "dialogues/system/runtime_parent.json")
        self.assertNotIn("result", caller.variables)

        dialogue_runtime.update(0.0)

        self.assertFalse(dialogue_runtime.is_active())
        self.assertEqual(caller.variables["result"], "resumed")
        parent_handle.update(0.0)
        self.assertTrue(parent_handle.complete)

    def test_inline_dialogue_can_open_file_backed_child_session(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_child.json": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "File backed child session",
                        }
                    ]
                },
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        caller = _make_runtime_entity("terminal", kind="terminal")
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        parent_handle = execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_definition": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Open child?",
                            "options": [
                                {
                                    "text": "Open",
                                    "option_id": "open",
                                    "commands": [
                                        {
                                            "type": "open_dialogue_session",
                                            "dialogue_path": "dialogues/system/runtime_child.json",
                                            "allow_cancel": True,
                                        },
                                        {
                                            "type": "set_entity_var",
                                            "entity_id": "$self_id",
                                            "name": "child_done",
                                            "value": True,
                                        },
                                    ],
                                }
                            ],
                        }
                    ]
                },
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        dialogue_runtime.handle_action("interact")
        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.dialogue_path, "dialogues/system/runtime_child.json")
        self.assertNotIn("child_done", caller.variables)

        dialogue_runtime.handle_action("menu")
        dialogue_runtime.update(0.0)

        self.assertFalse(dialogue_runtime.is_active())
        self.assertTrue(caller.variables["child_done"])
        parent_handle.update(0.0)
        self.assertTrue(parent_handle.complete)

    def test_choice_next_dialogue_definition_runs_commands_before_child_and_finishes_on_resume(self) -> None:
        _, project = self._make_project(shared_variables=_dialogue_shared_variables())
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        caller = _make_runtime_entity("terminal", kind="terminal")
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        parent_handle = execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_definition": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Open branch?",
                            "on_end": [
                                {
                                    "type": "set_entity_var",
                                    "entity_id": "$self_id",
                                    "name": "finished",
                                    "value": True,
                                }
                            ],
                            "options": [
                                {
                                    "text": "Open",
                                    "option_id": "open",
                                    "commands": [
                                        {
                                            "type": "set_entity_var",
                                            "entity_id": "$self_id",
                                            "name": "phase",
                                            "value": "before_child",
                                        }
                                    ],
                                    "next_dialogue_definition": {
                                        "segments": [
                                            {
                                                "type": "text",
                                                "text": "Child branch",
                                            }
                                        ]
                                    },
                                }
                            ],
                        }
                    ]
                },
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        dialogue_runtime.handle_action("interact")

        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.dialogue_path, "")
        self.assertEqual(session.current_segment["text"], "Child branch")
        self.assertEqual(caller.variables["phase"], "before_child")
        self.assertNotIn("finished", caller.variables)

        dialogue_runtime.handle_action("menu")
        resumed = dialogue_runtime.current_session
        assert resumed is not None
        self.assertEqual(resumed.current_segment["text"], "Open branch?")
        dialogue_runtime.update(0.0)

        self.assertFalse(dialogue_runtime.is_active())
        self.assertTrue(caller.variables["finished"])
        parent_handle.update(0.0)
        self.assertTrue(parent_handle.complete)

    def test_choice_next_dialogue_path_opens_file_backed_child_after_option_commands(self) -> None:
        _, project = self._make_project(
            shared_variables=_dialogue_shared_variables(),
            dialogues={
                "system/runtime_child.json": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "File child branch",
                        }
                    ]
                }
            },
        )
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        caller = _make_runtime_entity("terminal", kind="terminal")
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        parent_handle = execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_definition": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Open branch?",
                            "options": [
                                {
                                    "text": "Open",
                                    "option_id": "open",
                                    "commands": [
                                        {
                                            "type": "set_entity_var",
                                            "entity_id": "$self_id",
                                            "name": "phase",
                                            "value": "before_file_child",
                                        }
                                    ],
                                    "next_dialogue_path": "dialogues/system/runtime_child.json",
                                }
                            ],
                        }
                    ]
                },
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        dialogue_runtime.handle_action("interact")

        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.dialogue_path, "dialogues/system/runtime_child.json")
        self.assertEqual(caller.variables["phase"], "before_file_child")

        dialogue_runtime.handle_action("menu")
        dialogue_runtime.update(0.0)

        self.assertFalse(dialogue_runtime.is_active())
        parent_handle.update(0.0)
        self.assertTrue(parent_handle.complete)

    def test_choice_next_dialogue_rejects_command_based_dialogue_open_in_same_option(self) -> None:
        _, project = self._make_project(shared_variables=_dialogue_shared_variables())
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(_make_runtime_entity("terminal", kind="terminal"))
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_definition": {
                    "segments": [
                        {
                            "type": "choice",
                            "options": [
                                {
                                    "text": "Open",
                                    "option_id": "open",
                                    "commands": [
                                        {
                                            "type": "open_dialogue_session",
                                            "dialogue_definition": {
                                                "segments": [
                                                    {
                                                        "type": "text",
                                                        "text": "Command child",
                                                    }
                                                ]
                                            },
                                        }
                                    ],
                                    "next_dialogue_definition": {
                                        "segments": [
                                            {
                                                "type": "text",
                                                "text": "Field child",
                                            }
                                        ]
                                    },
                                }
                            ],
                        }
                    ]
                },
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        with self.assertRaisesRegex(ValueError, "must not combine next_dialogue_path"):
            dialogue_runtime.handle_action("interact")

    def test_text_segment_end_dialogue_closes_after_segment_finish(self) -> None:
        _, project = self._make_project(shared_variables=_dialogue_shared_variables())
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        caller = _make_runtime_entity("terminal", kind="terminal")
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        parent_handle = execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_definition": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "Last line",
                            "end_dialogue": True,
                            "on_end": [
                                {
                                    "type": "set_entity_var",
                                    "entity_id": "$self_id",
                                    "name": "finished",
                                    "value": True,
                                }
                            ],
                        },
                        {
                            "type": "text",
                            "text": "Unreachable",
                        },
                    ]
                },
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        dialogue_runtime.handle_action("interact")

        self.assertFalse(dialogue_runtime.is_active())
        self.assertTrue(caller.variables["finished"])
        parent_handle.update(0.0)
        self.assertTrue(parent_handle.complete)

    def test_choice_segment_end_dialogue_closes_after_child_branch_finishes(self) -> None:
        _, project = self._make_project(shared_variables=_dialogue_shared_variables())
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        caller = _make_runtime_entity("terminal", kind="terminal")
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        parent_handle = execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_definition": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Ask one thing?",
                            "end_dialogue": True,
                            "on_end": [
                                {
                                    "type": "set_entity_var",
                                    "entity_id": "$self_id",
                                    "name": "choice_finished",
                                    "value": True,
                                }
                            ],
                            "options": [
                                {
                                    "option_id": "yes",
                                    "text": "Yes",
                                    "next_dialogue_definition": {
                                        "segments": [
                                            {
                                                "type": "text",
                                                "text": "Child branch",
                                            }
                                        ]
                                    },
                                }
                            ],
                        },
                        {
                            "type": "text",
                            "text": "Unreachable sibling",
                        },
                    ]
                },
                "allow_cancel": True,
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        dialogue_runtime.handle_action("interact")

        session = dialogue_runtime.current_session
        assert session is not None
        self.assertEqual(session.current_segment["text"], "Child branch")

        dialogue_runtime.handle_action("menu")
        dialogue_runtime.update(0.0)
        dialogue_runtime.update(0.0)

        self.assertFalse(dialogue_runtime.is_active())
        self.assertTrue(caller.variables["choice_finished"])
        parent_handle.update(0.0)
        self.assertTrue(parent_handle.complete)

    def test_option_end_dialogue_closes_after_commands_without_opening_child_branch(self) -> None:
        _, project = self._make_project(shared_variables=_dialogue_shared_variables())
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        caller = _make_runtime_entity("terminal", kind="terminal")
        world.add_entity(caller)
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        parent_handle = execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_definition": {
                    "segments": [
                        {
                            "type": "choice",
                            "text": "Leave now?",
                            "on_end": [
                                {
                                    "type": "set_entity_var",
                                    "entity_id": "$self_id",
                                    "name": "segment_finished",
                                    "value": True,
                                }
                            ],
                            "options": [
                                {
                                    "option_id": "leave",
                                    "text": "Leave",
                                    "end_dialogue": True,
                                    "commands": [
                                        {
                                            "type": "set_entity_var",
                                            "entity_id": "$self_id",
                                            "name": "option_ran",
                                            "value": True,
                                        }
                                    ],
                                    "next_dialogue_definition": {
                                        "segments": [
                                            {
                                                "type": "text",
                                                "text": "Unreachable child",
                                            }
                                        ]
                                    },
                                }
                            ],
                        },
                        {
                            "type": "text",
                            "text": "Unreachable sibling",
                        },
                    ]
                },
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        dialogue_runtime.handle_action("interact")

        self.assertFalse(dialogue_runtime.is_active())
        self.assertTrue(caller.variables["option_ran"])
        self.assertTrue(caller.variables["segment_finished"])
        parent_handle.update(0.0)
        self.assertTrue(parent_handle.complete)

    def test_dialogue_runtime_rejects_non_boolean_end_dialogue_values(self) -> None:
        _, project = self._make_project(shared_variables=_dialogue_shared_variables())
        world = World()
        world.add_entity(_make_runtime_entity("player", kind="player"))
        world.add_entity(_make_runtime_entity("terminal", kind="terminal"))
        registry, context = self._make_command_context(project=project, world=world)
        dialogue_runtime = self._install_dialogue_runtime(
            registry=registry,
            context=context,
            project=project,
        )

        execute_registered_command(
            registry,
            context,
            "open_dialogue_session",
            {
                "dialogue_definition": {
                    "segments": [
                        {
                            "type": "text",
                            "text": "Oops",
                            "end_dialogue": "yes",
                        }
                    ]
                },
                "entity_refs": {"instigator": "player", "caller": "terminal"},
            },
        )

        with self.assertRaisesRegex(ValueError, "segment end_dialogue must be a boolean"):
            dialogue_runtime.handle_action("interact")

    def test_wrapped_lines_and_text_window_value_sources_store_visible_text(self) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("dialogue_controller", space="screen"))
        registry, context = self._make_command_context(world=world)
        context.services.ui.text_renderer = _StubTextRenderer()

        wrapped_handle = execute_command_spec(
            registry,
            context,
            {
                "entity_id": "dialogue_controller",
                "name": "wrapped_lines",
                "type": "set_entity_var",
                "value": {
                    "$wrapped_lines": {
                        "text": "one two three four",
                        "max_width": 64,
                    }
                },
            },
        )
        wrapped_handle.update(0.0)
        controller = world.get_entity("dialogue_controller")
        assert controller is not None

        window_handle = execute_command_spec(
            registry,
            context,
            {
                "entity_id": "dialogue_controller",
                "name": "text_window",
                "type": "set_entity_var",
                "value": {
                    "$text_window": {
                        "lines": controller.variables["wrapped_lines"],
                        "start": 1,
                        "max_lines": 2,
                    }
                },
            },
        )
        window_handle.update(0.0)

        self.assertEqual(
            controller.variables["wrapped_lines"],
            ["one", "two", "three", "four"],
        )
        self.assertEqual(controller.variables["text_window"]["visible_text"], "two\nthree")
        self.assertEqual(
            controller.variables["text_window"]["visible_lines"],
            ["two", "three"],
        )
        self.assertTrue(controller.variables["text_window"]["has_more"])
        self.assertEqual(controller.variables["text_window"]["total_lines"], 4)

    def test_slice_collection_wrap_index_and_join_text_value_sources_store_windowed_values(
        self,
    ) -> None:
        world = World()
        world.add_entity(_make_runtime_entity("dialogue_controller", space="screen"))
        registry, context = self._make_command_context(world=world)

        slice_handle = execute_command_spec(
            registry,
            context,
            {
                "entity_id": "dialogue_controller",
                "name": "visible_options",
                "type": "set_entity_var",
                "value": {
                    "$slice_collection": {
                        "value": ["zero", "one", "two", "three", "four"],
                        "start": 1,
                        "count": 3,
                    }
                },
            },
        )
        slice_handle.update(0.0)

        wrap_handle = execute_command_spec(
            registry,
            context,
            {
                "entity_id": "dialogue_controller",
                "name": "wrapped_index",
                "type": "set_entity_var",
                "value": {
                    "$wrap_index": {
                        "value": -1,
                        "count": 5,
                        "default": 0,
                    }
                },
            },
        )
        wrap_handle.update(0.0)

        join_handle = execute_command_spec(
            registry,
            context,
            {
                "entity_id": "dialogue_controller",
                "name": "joined_text",
                "type": "set_entity_var",
                "value": {"$join_text": [">", "one"]},
            },
        )
        join_handle.update(0.0)

        controller = world.get_entity("dialogue_controller")
        assert controller is not None
        self.assertEqual(controller.variables["visible_options"], ["one", "two", "three"])
        self.assertEqual(controller.variables["wrapped_index"], 4)
        self.assertEqual(controller.variables["joined_text"], ">one")
