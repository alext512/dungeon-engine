"""Shared fixture builders and tree helpers for main-window editor tests."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QPixmap


def _save_test_pixmap(path: Path, width: int, height: int, color_name: str) -> None:
    # These helpers are called after the QApplication test harness is ready.
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(color_name))
    if not pixmap.save(str(path)):
        raise AssertionError(f"Failed to save test pixmap to '{path}'.")


def create_basic_project(root: Path) -> Path:
    project = root / "project"
    assets = project / "assets"
    areas = project / "areas"
    assets.mkdir(parents=True)
    areas.mkdir()

    _save_test_pixmap(assets / "base.png", 32, 16, "green")
    _save_test_pixmap(assets / "extra.png", 16, 16, "yellow")

    (project / "project.json").write_text(
        '{\n  "startup_area": "areas/demo"\n}\n',
        encoding="utf-8",
    )
    (areas / "demo.json").write_text(
        (
            '{\n'
            '  "tile_size": 16,\n'
            '  "tilesets": [\n'
            '    {\n'
            '      "firstgid": 1,\n'
            '      "path": "assets/base.png",\n'
            '      "tile_width": 16,\n'
            '      "tile_height": 16\n'
            '    }\n'
            '  ],\n'
            '  "tile_layers": [\n'
            '    {\n'
            '      "name": "ground",\n'
            '      "render_order": 0,\n'
            '      "y_sort": false,\n'
            '      "stack_order": 0,\n'
            '      "grid": [[1, 2]]\n'
            '    }\n'
            '  ],\n'
            '  "entities": [],\n'
            '  "variables": {}\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    return project / "project.json"


def create_layering_project(root: Path) -> Path:
    project = root / "project"
    assets = project / "assets"
    areas = project / "areas"
    assets.mkdir(parents=True)
    areas.mkdir()

    _save_test_pixmap(assets / "base.png", 32, 32, "cyan")

    (project / "project.json").write_text(
        '{\n  "startup_area": "areas/demo"\n}\n',
        encoding="utf-8",
    )
    (areas / "demo.json").write_text(
        (
            '{\n'
            '  "tile_size": 16,\n'
            '  "tilesets": [\n'
            '    {\n'
            '      "firstgid": 1,\n'
            '      "path": "assets/base.png",\n'
            '      "tile_width": 16,\n'
            '      "tile_height": 16\n'
            '    }\n'
            '  ],\n'
            '  "tile_layers": [\n'
            '    {\n'
            '      "name": "ground",\n'
            '      "render_order": 0,\n'
            '      "y_sort": false,\n'
            '      "stack_order": 0,\n'
            '      "grid": [[1]]\n'
            '    }\n'
            '  ],\n'
            '  "entities": [\n'
            '    {\n'
            '      "id": "actor",\n'
            '      "grid_x": 0,\n'
            '      "grid_y": 0,\n'
            '      "render_order": 10,\n'
            '      "y_sort": false,\n'
            '      "stack_order": 0\n'
            '    }\n'
            '  ],\n'
            '  "variables": {}\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    return project / "project.json"


def create_tile_selection_project(root: Path) -> Path:
    project = root / "project"
    assets = project / "assets"
    areas = project / "areas"
    assets.mkdir(parents=True)
    areas.mkdir()

    _save_test_pixmap(assets / "base.png", 32, 32, "cyan")

    (project / "project.json").write_text(
        '{\n  "startup_area": "areas/demo"\n}\n',
        encoding="utf-8",
    )
    (areas / "demo.json").write_text(
        (
            '{\n'
            '  "tile_size": 16,\n'
            '  "tilesets": [\n'
            '    {\n'
            '      "firstgid": 1,\n'
            '      "path": "assets/base.png",\n'
            '      "tile_width": 16,\n'
            '      "tile_height": 16\n'
            '    }\n'
            '  ],\n'
            '  "tile_layers": [\n'
            '    {\n'
            '      "name": "ground",\n'
            '      "render_order": 0,\n'
            '      "y_sort": false,\n'
            '      "stack_order": 0,\n'
            '      "grid": [[1, 2, 0], [3, 4, 0], [0, 0, 0]]\n'
            '    }\n'
            '  ],\n'
            '  "entities": [],\n'
            '  "variables": {}\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    return project / "project.json"


def create_entity_paint_project(root: Path) -> Path:
    project = root / "project"
    assets = project / "assets"
    areas = project / "areas"
    templates = project / "entity_templates"
    assets.mkdir(parents=True)
    areas.mkdir()
    templates.mkdir()

    _save_test_pixmap(assets / "base.png", 16, 16, "white")

    (project / "project.json").write_text(
        (
            '{\n'
            '  "startup_area": "areas/demo",\n'
            '  "entity_template_paths": ["entity_templates/"]\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    (areas / "demo.json").write_text(
        (
            '{\n'
            '  "tile_size": 16,\n'
            '  "tilesets": [\n'
            '    {\n'
            '      "firstgid": 1,\n'
            '      "path": "assets/base.png",\n'
            '      "tile_width": 16,\n'
            '      "tile_height": 16\n'
            '    }\n'
            '  ],\n'
            '  "tile_layers": [\n'
            '    {\n'
            '      "name": "ground",\n'
            '      "render_order": 0,\n'
            '      "y_sort": false,\n'
            '      "stack_order": 0,\n'
            '      "grid": [[1, 1], [1, 1]]\n'
            '    }\n'
            '  ],\n'
            '  "entities": [],\n'
            '  "variables": {}\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    (templates / "npc.json").write_text(
        (
            '{\n'
            '  "render_order": 10,\n'
            '  "y_sort": true,\n'
            '  "visuals": []\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    return project / "project.json"


def create_entity_select_project(root: Path) -> Path:
    project = root / "project"
    assets = project / "assets"
    areas = project / "areas"
    assets.mkdir(parents=True)
    areas.mkdir()

    _save_test_pixmap(assets / "base.png", 16, 16, "magenta")

    (project / "project.json").write_text(
        '{\n  "startup_area": "areas/demo"\n}\n',
        encoding="utf-8",
    )
    (areas / "demo.json").write_text(
        (
            '{\n'
            '  "tile_size": 16,\n'
            '  "tilesets": [\n'
            '    {\n'
            '      "firstgid": 1,\n'
            '      "path": "assets/base.png",\n'
            '      "tile_width": 16,\n'
            '      "tile_height": 16\n'
            '    }\n'
            '  ],\n'
            '  "tile_layers": [\n'
            '    {\n'
            '      "name": "ground",\n'
            '      "render_order": 0,\n'
            '      "y_sort": false,\n'
            '      "stack_order": 0,\n'
            '      "grid": [[1, 1], [1, 1]]\n'
            '    }\n'
            '  ],\n'
            '  "entities": [\n'
            '    {\n'
            '      "id": "npc_1",\n'
            '      "grid_x": 0,\n'
            '      "grid_y": 0,\n'
            '      "render_order": 10,\n'
            '      "y_sort": true,\n'
            '      "stack_order": 0\n'
            '    },\n'
            '    {\n'
            '      "id": "npc_2",\n'
            '      "grid_x": 0,\n'
            '      "grid_y": 0,\n'
            '      "render_order": 10,\n'
            '      "y_sort": true,\n'
            '      "stack_order": 2\n'
            '    }\n'
            '  ],\n'
            '  "variables": {}\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    return project / "project.json"


def create_entity_fields_project(root: Path) -> Path:
    project = root / "project"
    assets = project / "assets"
    areas = project / "areas"
    templates = project / "entity_templates"
    assets.mkdir(parents=True)
    areas.mkdir()
    templates.mkdir()

    _save_test_pixmap(assets / "base.png", 16, 16, "blue")

    (project / "project.json").write_text(
        (
            '{\n'
            '  "startup_area": "areas/demo",\n'
            '  "entity_template_paths": ["entity_templates/"],\n'
            '  "shared_variables_path": "shared_variables.json"\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    (project / "shared_variables.json").write_text(
        (
            '{\n'
            '  "display": {\n'
            '    "internal_width": 256,\n'
            '    "internal_height": 192\n'
            '  }\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    (areas / "demo.json").write_text(
        (
            '{\n'
            '  "tile_size": 16,\n'
            '  "tilesets": [\n'
            '    {\n'
            '      "firstgid": 1,\n'
            '      "path": "assets/base.png",\n'
            '      "tile_width": 16,\n'
            '      "tile_height": 16\n'
            '    }\n'
            '  ],\n'
            '  "tile_layers": [\n'
            '    {\n'
            '      "name": "ground",\n'
            '      "render_order": 0,\n'
            '      "y_sort": false,\n'
            '      "stack_order": 0,\n'
            '      "grid": [[1, 1], [1, 1]]\n'
            '    }\n'
            '  ],\n'
            '  "entities": [\n'
            '    {\n'
            '      "id": "house_door",\n'
            '      "grid_x": 0,\n'
            '      "grid_y": 0,\n'
            '      "template": "entity_templates/area_door",\n'
            '      "parameters": {\n'
            '        "target_area": "areas/village_house",\n'
            '        "target_entry": "from_square"\n'
            '      },\n'
            '      "render_order": 10,\n'
            '      "y_sort": true,\n'
            '      "stack_order": 0\n'
            '    },\n'
            '    {\n'
            '      "id": "title_backdrop",\n'
            '      "pixel_x": 12,\n'
            '      "pixel_y": 18,\n'
            '      "template": "entity_templates/display_sprite",\n'
            '      "parameters": {\n'
            '        "sprite_path": "assets/base.png"\n'
            '      },\n'
            '      "render_order": 0,\n'
            '      "y_sort": false,\n'
            '      "stack_order": 0\n'
            '    }\n'
            '  ],\n'
            '  "variables": {}\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    (templates / "area_door.json").write_text(
        (
            '{\n'
            '  "entity_commands": {\n'
            '    "interact": {\n'
            '      "enabled": true,\n'
            '      "commands": [\n'
            '        {\n'
            '          "type": "change_area",\n'
            '          "area_id": "$target_area",\n'
            '          "entry_id": "$target_entry"\n'
            '        }\n'
            '      ]\n'
            '    }\n'
            '  },\n'
            '  "render_order": 10\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    (templates / "display_sprite.json").write_text(
        (
            '{\n'
            '  "space": "screen",\n'
            '  "render_order": 0,\n'
            '  "y_sort": false,\n'
            '  "visuals": [\n'
            '    {\n'
            '      "path": "$sprite_path"\n'
            '    }\n'
            '  ]\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    return project / "project.json"


def create_dialogue_project(root: Path) -> Path:
    project = root / "project"
    assets = project / "assets"
    areas = project / "areas"
    dialogues = project / "dialogues"
    assets.mkdir(parents=True)
    areas.mkdir()
    dialogues.mkdir()

    _save_test_pixmap(assets / "base.png", 16, 16, "orange")

    (project / "project.json").write_text(
        (
            '{\n'
            '  "startup_area": "areas/demo",\n'
            '  "dialogue_paths": ["dialogues/"]\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    (areas / "demo.json").write_text(
        (
            '{\n'
            '  "tile_size": 16,\n'
            '  "tilesets": [\n'
            '    {\n'
            '      "firstgid": 1,\n'
            '      "path": "assets/base.png",\n'
            '      "tile_width": 16,\n'
            '      "tile_height": 16\n'
            '    }\n'
            '  ],\n'
            '  "tile_layers": [\n'
            '    {\n'
            '      "name": "ground",\n'
            '      "render_order": 0,\n'
            '      "y_sort": false,\n'
            '      "stack_order": 0,\n'
            '      "grid": [[1]]\n'
            '    }\n'
            '  ],\n'
            '  "entities": [],\n'
            '  "variables": {}\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    (dialogues / "intro.json").write_text(
        '{\n  "text": "Hello"\n}\n',
        encoding="utf-8",
    )
    return project / "project.json"


def create_project_content_project(root: Path) -> Path:
    project = root / "project"
    assets = project / "assets"
    areas = project / "areas"
    items = project / "items"
    nested_items = items / "keys"
    assets.mkdir(parents=True)
    areas.mkdir()
    nested_items.mkdir(parents=True)

    _save_test_pixmap(assets / "base.png", 16, 16, "red")
    (assets / "base.json").write_text('{"kind": "metadata"}\n', encoding="utf-8")

    (project / "project.json").write_text(
        (
            '{\n'
            '  "startup_area": "areas/demo",\n'
            '  "item_paths": ["items/"],\n'
            '  "shared_variables_path": "shared_variables.json",\n'
            '  "global_entities": [\n'
            '    {\n'
            '      "id": "pause_controller",\n'
            '      "template": "entity_templates/pause_controller"\n'
            '    }\n'
            '  ]\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    (project / "shared_variables.json").write_text(
        (
            '{\n'
            '  "display": {\n'
            '    "internal_width": 320,\n'
            '    "internal_height": 240\n'
            '  },\n'
            '  "inventory_ui": {\n'
            '    "preset": "standard"\n'
            '  }\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    (areas / "demo.json").write_text(
        (
            '{\n'
            '  "tile_size": 16,\n'
            '  "tilesets": [\n'
            '    {\n'
            '      "firstgid": 1,\n'
            '      "path": "assets/base.png",\n'
            '      "tile_width": 16,\n'
            '      "tile_height": 16\n'
            '    }\n'
            '  ],\n'
            '  "tile_layers": [\n'
            '    {\n'
            '      "name": "ground",\n'
            '      "render_order": 0,\n'
            '      "y_sort": false,\n'
            '      "stack_order": 0,\n'
            '      "grid": [[1]]\n'
            '    }\n'
            '  ],\n'
            '  "entities": [],\n'
            '  "variables": {}\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    (items / "apple.json").write_text(
        '{\n  "name": "Apple",\n  "max_stack": 9\n}\n',
        encoding="utf-8",
    )
    (nested_items / "silver_key.json").write_text(
        '{\n  "name": "Silver Key",\n  "max_stack": 1\n}\n',
        encoding="utf-8",
    )
    return project / "project.json"


def create_reference_rich_project(root: Path) -> Path:
    project = root / "project"
    assets = project / "assets"
    areas = project / "areas"
    items = project / "items"
    dialogues = project / "dialogues" / "system"
    commands = project / "commands" / "system"
    assets.mkdir(parents=True)
    areas.mkdir()
    items.mkdir()
    dialogues.mkdir(parents=True)
    commands.mkdir(parents=True)

    _save_test_pixmap(assets / "base.png", 16, 16, "blue")

    (project / "project.json").write_text(
        (
            '{\n'
            '  "startup_area": "areas/demo",\n'
            '  "item_paths": ["items/"],\n'
            '  "dialogue_paths": ["dialogues/"],\n'
            '  "command_paths": ["commands/"]\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    (areas / "demo.json").write_text(
        (
            '{\n'
            '  "tile_size": 16,\n'
            '  "tilesets": [],\n'
            '  "tile_layers": [],\n'
            '  "entities": [\n'
            '    {\n'
            '      "id": "terminal",\n'
            '      "grid_x": 0,\n'
            '      "grid_y": 0,\n'
            '      "item_id": "items/apple",\n'
            '      "required_item_id": "items/apple",\n'
            '      "dialogue_path": "dialogues/system/prompt",\n'
            '      "success_dialogue_path": "dialogues/system/prompt",\n'
            '      "command_id": "commands/system/do_thing"\n'
            '    }\n'
            '  ],\n'
            '  "variables": {}\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    (items / "apple.json").write_text(
        '{\n  "name": "Apple",\n  "max_stack": 9\n}\n',
        encoding="utf-8",
    )
    (dialogues / "prompt.json").write_text(
        '{\n  "segments": []\n}\n',
        encoding="utf-8",
    )
    (commands / "do_thing.json").write_text(
        '{\n  "commands": []\n}\n',
        encoding="utf-8",
    )
    return project / "project.json"


def create_entity_reference_project(root: Path) -> Path:
    project = root / "project"
    assets = project / "assets"
    areas = project / "areas"
    assets.mkdir(parents=True)
    areas.mkdir()

    _save_test_pixmap(assets / "base.png", 16, 16, "darkGreen")

    (project / "project.json").write_text(
        (
            '{\n'
            '  "startup_area": "areas/demo",\n'
            '  "global_entities": [\n'
            '    {\n'
            '      "id": "dialogue_controller"\n'
            '    }\n'
            '  ],\n'
            '  "input_routes": {\n'
            '    "confirm": {\n'
            '      "entity_id": "switch_a",\n'
            '      "command_id": "confirm"\n'
            '    }\n'
            '  }\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    (areas / "demo.json").write_text(
        (
            '{\n'
            '  "tile_size": 16,\n'
            '  "tilesets": [],\n'
            '  "tile_layers": [\n'
            '    {\n'
            '      "name": "ground",\n'
            '      "render_order": 0,\n'
            '      "y_sort": false,\n'
            '      "stack_order": 0,\n'
            '      "grid": [[0, 0]]\n'
            '    }\n'
            '  ],\n'
            '  "camera": {\n'
            '    "follow": {\n'
            '      "mode": "entity",\n'
            '      "entity_id": "switch_a"\n'
            '    }\n'
            '  },\n'
            '  "input_routes": {\n'
            '    "interact": {\n'
            '      "entity_id": "switch_a",\n'
            '      "command_id": "interact"\n'
            '    }\n'
            '  },\n'
            '  "entities": [\n'
            '    {\n'
            '      "id": "switch_a",\n'
            '      "grid_x": 0,\n'
            '      "grid_y": 0,\n'
            '      "kind": "switch"\n'
            '    },\n'
            '    {\n'
            '      "id": "relay",\n'
            '      "grid_x": 1,\n'
            '      "grid_y": 0,\n'
            '      "kind": "relay",\n'
            '      "target_id": "switch_a",\n'
            '      "source_entity_id": "switch_a",\n'
            '      "entity_ids": ["switch_a", "dialogue_controller"]\n'
            '    }\n'
            '  ],\n'
            '  "variables": {}\n'
            '}\n'
        ),
        encoding="utf-8",
    )
    return project / "project.json"


def panel_file_entries(panel) -> list[tuple[str, Path]]:
    entries: list[tuple[str, Path]] = []
    stack = [panel._tree.topLevelItem(i) for i in range(panel._tree.topLevelItemCount())]
    while stack:
        item = stack.pop()
        if item is None:
            continue
        data = item.data(0, 256)
        if data is not None:
            entries.append(data)
        for index in range(item.childCount()):
            stack.append(item.child(index))
    return sorted(entries, key=lambda pair: pair[0])


def panel_folder_entries(panel) -> list[tuple[str, Path]]:
    entries: list[tuple[str, Path]] = []
    stack = [panel._tree.topLevelItem(i) for i in range(panel._tree.topLevelItemCount())]
    while stack:
        item = stack.pop()
        if item is None:
            continue
        data = item.data(0, 257)
        if data is not None:
            relative_path, folder_path, _root_dir = data
            entries.append((str(relative_path), Path(folder_path)))
        for index in range(item.childCount()):
            stack.append(item.child(index))
    return sorted(entries, key=lambda pair: pair[0])


def find_tree_item_by_folder_path(panel, relative_path: str):
    stack = [panel._tree.topLevelItem(i) for i in range(panel._tree.topLevelItemCount())]
    while stack:
        item = stack.pop()
        if item is None:
            continue
        data = item.data(0, 257)
        if data is not None and str(data[0]) == relative_path:
            return item
        for index in range(item.childCount()):
            stack.append(item.child(index))
    return None
